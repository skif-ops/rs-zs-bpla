#!/usr/bin/env python3
"""KiCad 9 stage of PCB-PWR ECO-006 (Review B R2.002: DFM-PWR-03). Runs inside the pinned KiCad image.

refs <in.kicad_pcb> <out.kicad_pcb> <report.json>
  Every visible reference designator on a silkscreen layer gets the JLCPCB legend minimum:
  text height 1.0 mm, stroke 0.15 mm (was 0.8 / 0.12). All of them are then re-placed:
  clear of every solder-mask OPENING by 0.15 mm (the opening is the pad inflated by the pad's own
  effective mask expansion - JLCPCB "pad to silkscreen 0.15 mm", measured as in
  tools/apply_pcb_pwr_dfm_register_rev_a.py), of all other silkscreen by 0.1 mm and of the board
  edge by 0.3 mm. A reference that fits nowhere is hidden; the footprint's F.Fab reference text
  stays on the assembly drawing. Nothing else on the board is touched.
"""

from __future__ import annotations

import json
import math
import sys

import pcbnew

TEXT_H, STROKE = 1.0, 0.15
OPENING_GAP, SILK_GAP, EDGE_GAP = 0.15, 0.10, 0.30


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def _box(item):
    return item.GetBoundingBox()


def _body(footprint):
    try:
        return footprint.GetBoundingBox(False, False)
    except TypeError:
        return footprint.GetBoundingBox(False)


def _mask_exp(pad, layer) -> int:
    try:
        return int(pad.GetSolderMaskExpansion(layer))
    except TypeError:
        return int(pad.GetSolderMaskExpansion())


def refs(src: str, dst: str, report_path: str) -> None:
    board = pcbnew.LoadBoard(src)
    silk_layers = (pcbnew.F_SilkS, pcbnew.B_SilkS)
    mask_of = {pcbnew.F_SilkS: pcbnew.F_Mask, pcbnew.B_SilkS: pcbnew.B_Mask}
    resized = []
    for footprint in board.GetFootprints():
        field = footprint.Reference()
        if field.GetLayer() in silk_layers and field.IsVisible():
            field.SetTextSize(pcbnew.VECTOR2I(mm(TEXT_H), mm(TEXT_H)))
            field.SetTextThickness(mm(STROKE))
            resized.append(footprint.GetReference())
    edge = board.GetBoardEdgesBoundingBox()
    edge.Inflate(-mm(EDGE_GAP))
    openings = {layer: [] for layer in silk_layers}
    silk = {layer: [] for layer in silk_layers}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            for layer in silk_layers:
                if pad.IsOnLayer(mask_of[layer]):
                    box = _box(pad)
                    box.Inflate(_mask_exp(pad, mask_of[layer]) + mm(OPENING_GAP))
                    openings[layer].append(box)
        for item in footprint.GraphicalItems():
            if item.GetLayer() in silk:
                box = _box(item)
                box.Inflate(mm(SILK_GAP))
                silk[item.GetLayer()].append(box)
    for item in board.GetDrawings():
        if item.GetLayer() in silk:
            box = _box(item)
            box.Inflate(mm(SILK_GAP))
            silk[item.GetLayer()].append(box)

    def clear(box, layer) -> bool:
        if not edge.Contains(box.GetOrigin()) or not edge.Contains(box.GetEnd()):
            return False
        return not any(box.Intersects(o) for o in openings[layer] + silk[layer] + placed[layer])

    placed = {layer: [] for layer in silk_layers}
    kept, moved, hidden = [], [], []
    todo = []
    footprints = sorted(board.GetFootprints(), key=lambda f: _body(f).GetArea())
    for footprint in footprints:  # pass 1: keep every resized reference that is already clear
        field = footprint.Reference()
        layer = field.GetLayer()
        if layer not in silk_layers or not field.IsVisible():
            continue
        box = _box(field)
        if clear(box, layer):
            kept.append(footprint.GetReference())
            placed[layer].append(box)
        else:
            todo.append(footprint)
    for footprint in todo:  # pass 2: nearest free spot around the body, 0 or 90 deg
        field = footprint.Reference()
        layer = field.GetLayer()
        start_pos, start_angle = field.GetPosition(), field.GetTextAngleDegrees()
        body = _body(footprint)
        cx, cy = body.GetCenter().x, body.GetCenter().y
        options = []
        for angle in (0.0, 90.0):
            field.SetTextAngleDegrees(angle)
            field.SetPosition(pcbnew.VECTOR2I(cx, cy))
            probe = _box(field)
            tw, th = probe.GetWidth(), probe.GetHeight()
            for gap in (mm(0.15), mm(0.4), mm(0.8), mm(1.3), mm(2.0)):
                ys = (body.GetY() - gap - th // 2, body.GetBottom() + gap + th // 2)
                xs = (body.GetX() - gap - tw // 2, body.GetRight() + gap + tw // 2)
                for y in ys:
                    for dx in range(-10, 11):
                        options.append((angle, cx + dx * mm(0.25), y))
                for x in xs:
                    for dy in range(-10, 11):
                        options.append((angle, x, cy + dy * mm(0.25)))
        options.sort(key=lambda o: (math.hypot(o[1] - start_pos.x, o[2] - start_pos.y), o[0]))
        done = False
        for angle, x, y in options:
            field.SetTextAngleDegrees(angle)
            field.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
            box = _box(field)
            field.SetPosition(pcbnew.VECTOR2I(int(x) - (box.GetCenter().x - int(x)),
                                              int(y) - (box.GetCenter().y - int(y))))
            box = _box(field)
            if clear(box, layer):
                placed[layer].append(box)
                moved.append(footprint.GetReference())
                done = True
                break
        if not done:
            field.SetTextAngleDegrees(start_angle)
            field.SetPosition(start_pos)
            field.SetVisible(False)
            hidden.append(footprint.GetReference())
    board.Save(dst)
    report = {"text_height_mm": TEXT_H, "stroke_mm": STROKE, "opening_gap_mm": OPENING_GAP,
              "silk_gap_mm": SILK_GAP, "edge_gap_mm": EDGE_GAP, "resized": sorted(resized),
              "kept": sorted(kept), "moved": sorted(moved), "hidden": sorted(hidden)}
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in report.items()}))


if __name__ == "__main__":
    {"refs": refs}[sys.argv[1]](*sys.argv[2:])
