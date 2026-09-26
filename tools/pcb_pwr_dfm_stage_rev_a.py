#!/usr/bin/env python3
"""KiCad 9 stage of the PCB-PWR DFM register (Review B R2.002). Runs inside the pinned KiCad image.

dump <board.kicad_pcb> <out.json>
  refills the zones of a scratch copy, then writes the exact KiCad geometry used by
  tools/audit_pcb_pwr_dfm_register_rev_a.py:
    pads      copper polygon per outer copper layer, solder-mask opening per mask layer (pad shape
              inflated by the pad's effective mask expansion), paste aperture per paste layer (pad shape
              inflated by the effective paste margin), drill, net, reference, pad number, attributes
    copper    outer-layer tracks, vias and filled zones (polygon, net, kind)
    silk      every silkscreen item: polygon, stroke width, text height, visibility, owner
    holes     every drilled hole: centre, diameter, plated
Nothing is written back to the board.
"""

from __future__ import annotations

import json
import sys

import pcbnew

MAX_ERR = pcbnew.FromMM(0.002)
OUTER = {"F": (pcbnew.F_Cu, pcbnew.F_Mask, pcbnew.F_Paste, pcbnew.F_SilkS),
         "B": (pcbnew.B_Cu, pcbnew.B_Mask, pcbnew.B_Paste, pcbnew.B_SilkS)}


def mm(v: int) -> float:
    return round(pcbnew.ToMM(v), 5)


def polys(poly_set) -> list:
    out = []
    for i in range(poly_set.OutlineCount()):
        outline = poly_set.Outline(i)
        out.append({"points": [[mm(outline.CPoint(k).x), mm(outline.CPoint(k).y)] for k in range(outline.PointCount())],
                    "holes": [[[mm(poly_set.Hole(i, h).CPoint(k).x), mm(poly_set.Hole(i, h).CPoint(k).y)]
                               for k in range(poly_set.Hole(i, h).PointCount())] for h in range(poly_set.HoleCount(i))]})
    return out


def shape(item, layer: int, inflate: int = 0) -> list:
    buffer = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(buffer, layer, inflate, MAX_ERR, pcbnew.ERROR_INSIDE)
    return polys(buffer)


def mask_expansion(pad, layer: int) -> tuple[int, str]:
    try:
        return int(pad.GetSolderMaskExpansion(layer)), "PAD.GetSolderMaskExpansion(layer)"
    except TypeError:
        return int(pad.GetSolderMaskExpansion()), "PAD.GetSolderMaskExpansion()"


def paste_margin(pad, layer: int) -> tuple[int, str]:
    try:
        margin = pad.GetSolderPasteMargin(layer)
        method = "PAD.GetSolderPasteMargin(layer)"
    except TypeError:
        margin = pad.GetSolderPasteMargin()
        method = "PAD.GetSolderPasteMargin()"
    if hasattr(margin, "x"):
        assert margin.x == margin.y, f"anisotropic paste margin {margin.x} / {margin.y} not supported"
        margin = margin.x
    return int(margin), method


def dump(src: str, dst: str) -> None:
    board = pcbnew.LoadBoard(src)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    methods: set = set()
    pads, holes, silk = [], [], []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            row = {"ref": ref, "pad": pad.GetNumber(), "net": pad.GetNetname(), "attr": int(pad.GetAttribute()),
                   "smd": pad.GetAttribute() in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN),
                   "at": [mm(pad.GetPosition().x), mm(pad.GetPosition().y)], "copper": {}, "mask": {}, "paste": {},
                   "mask_expansion_mm": {}, "paste_margin_mm": {}}
            for side, (cu, mask, paste, _) in OUTER.items():
                if pad.IsOnLayer(cu):
                    row["copper"][side] = shape(pad, cu)
                if pad.IsOnLayer(mask):
                    exp, method = mask_expansion(pad, mask)
                    methods.add(method)
                    row["mask_expansion_mm"][side] = mm(exp)
                    row["mask"][side] = shape(pad, mask, exp)
                if pad.IsOnLayer(paste):
                    margin, method = paste_margin(pad, paste)
                    methods.add(method)
                    row["paste_margin_mm"][side] = mm(margin)
                    row["paste"][side] = shape(pad, paste, margin) if margin >= 0 else _deflate(pad, paste, -margin)
            drill = pad.GetDrillSize()
            if drill.x > 0:
                holes.append({"owner": f"{ref}.{pad.GetNumber()}", "at": row["at"], "d_mm": mm(min(drill.x, drill.y)),
                              "plated": pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH, "kind": "pad",
                              "net": pad.GetNetname()})
            pads.append(row)
        items = list(fp.GraphicalItems()) + [fp.Reference(), fp.Value()]
        for item in items:
            _silk(item, ref, silk)
    for item in board.GetDrawings():
        _silk(item, "board", silk)
    copper = []
    for track in board.GetTracks():
        is_via = track.Type() == pcbnew.PCB_VIA_T
        for side, (cu, *_rest) in OUTER.items():
            if track.IsOnLayer(cu):
                copper.append({"kind": "via" if is_via else "track", "side": side, "net": track.GetNetname(),
                               "width_mm": mm(track.GetWidth()), "polys": shape(track, cu)})
        if is_via:
            holes.append({"owner": f"via@{mm(track.GetPosition().x)},{mm(track.GetPosition().y)}",
                          "at": [mm(track.GetPosition().x), mm(track.GetPosition().y)],
                          "d_mm": mm(track.GetDrillValue()), "plated": True, "kind": "via",
                          "net": track.GetNetname()})
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        for side, (cu, *_rest) in OUTER.items():
            if zone.IsOnLayer(cu):
                copper.append({"kind": "zone", "side": side, "net": zone.GetNetname(), "name": zone.GetZoneName(),
                               "polys": polys(zone.GetFilledPolysList(cu))})
    with open(dst, "w", encoding="utf-8") as handle:
        json.dump({"kicad_version": pcbnew.GetBuildVersion(), "api_methods": sorted(methods),
                   "pads": pads, "copper": copper, "silk": silk, "holes": holes}, handle)
    print(json.dumps({"pads": len(pads), "copper": len(copper), "silk": len(silk), "holes": len(holes),
                      "methods": sorted(methods)}))


def _deflate(pad, layer: int, amount: int) -> list:
    buffer = pcbnew.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(buffer, layer, 0, MAX_ERR, pcbnew.ERROR_INSIDE)
    buffer.Deflate(amount, pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, MAX_ERR)
    return polys(buffer)


def _silk(item, owner: str, out: list) -> None:
    for side, (*_rest, silk_layer) in OUTER.items():
        if item.GetLayer() != silk_layer:
            continue
        visible = item.IsVisible() if hasattr(item, "IsVisible") else True
        row = {"owner": owner, "side": side, "class": item.GetClass(), "visible": bool(visible)}
        if hasattr(item, "GetTextHeight"):
            row.update({"text": item.GetText() if hasattr(item, "GetText") else "",
                        "text_height_mm": mm(item.GetTextHeight()), "stroke_mm": mm(item.GetTextThickness())})
        elif hasattr(item, "GetWidth"):
            row["stroke_mm"] = mm(item.GetWidth())
        row["polys"] = shape(item, silk_layer) if visible else []
        out.append(row)


if __name__ == "__main__":
    {"dump": dump}[sys.argv[1]](sys.argv[2], sys.argv[3])
