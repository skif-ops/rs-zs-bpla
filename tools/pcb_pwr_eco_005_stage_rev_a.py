#!/usr/bin/env python3
"""KiCad 9 stage of PCB-PWR ECO-005 (runs inside the pinned KiCad image).

apply <in.kicad_pcb> <spec.json> <out.kicad_pcb>
    Apply a controlled geometry delta and save the refilled board:
      rotate        [{"ref", "angle_deg"}]                footprint orientation (about its origin)
      remove_tracks [{"net", "layer", "start", "end"}]    exact segment match (0.01 mm)
      remove_vias   [{"net", "pos"}]                      exact via match (0.01 mm)
      remove_zones  [{"net", "layer", "contains"}]        zone of that net/layer whose outline contains the point
      add_zones     [{"net", "layer", "polygon", "priority", "clearance_mm"}]   solid pad connection
      add_items     PREROUTE tuples (kind, layer, net, width, points)          locked copper
      silk_refs     true: re-place reference designators clear of pads, silkscreen and the
                    board edge (keep if already clear, else nearest free spot at 0/90 deg,
                    else hide on silkscreen - the F.Fab reference stays)
    Every requested removal must match exactly one item, otherwise the stage fails.
dump <board.kicad_pcb> <geometry.json>
    Same geometry dump as the autoroute stage, plus filled zone polygons per net/layer.
"""

from __future__ import annotations

import json
import sys

import pcbnew

sys.path.insert(0, sys.path[0])
from kicad_autoroute_stage_rev_a import _zone, add_preroute, dump_geometry, mm  # noqa: E402

TOL = mm(0.01)


def _near(a, x_mm: float, y_mm: float) -> bool:
    return abs(a.x - mm(x_mm)) <= TOL and abs(a.y - mm(y_mm)) <= TOL


def apply(in_path: str, spec_path: str, out_path: str) -> None:
    spec = json.load(open(spec_path, encoding="utf-8"))
    board = pcbnew.LoadBoard(in_path)
    report = {"rotated": [], "removed_tracks": 0, "removed_vias": 0, "removed_zones": 0,
              "added_zones": 0, "added_items": 0}

    for item in spec.get("rotate", []):
        footprint = board.FindFootprintByReference(item["ref"])
        assert footprint is not None, f"footprint {item['ref']} not found"
        footprint.SetOrientationDegrees(float(item["angle_deg"]))
        report["rotated"].append(item["ref"])

    def live_tracks():  # re-read after every removal: KiCad frees removed items
        return list(board.GetTracks())

    for item in spec.get("remove_tracks", []):
        (x0, y0), (x1, y1) = item["start"], item["end"]
        hits = [t for t in live_tracks() if t.GetClass() == "PCB_TRACK" and t.GetNetname() == item["net"]
                and board.GetLayerName(t.GetLayer()) == item["layer"]
                and ((_near(t.GetStart(), x0, y0) and _near(t.GetEnd(), x1, y1))
                     or (_near(t.GetStart(), x1, y1) and _near(t.GetEnd(), x0, y0)))]
        assert len(hits) == 1, f"track removal matched {len(hits)}: {item}"
        board.Remove(hits[0])
        report["removed_tracks"] += 1
    for item in spec.get("remove_vias", []):
        x, y = item["pos"]
        hits = [t for t in live_tracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == item["net"]
                and _near(t.GetPosition(), x, y)]
        assert len(hits) == 1, f"via removal matched {len(hits)}: {item}"
        board.Remove(hits[0])
        report["removed_vias"] += 1

    for item in spec.get("remove_zones", []):
        x, y = item["contains"]
        hits = [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == item["net"]
                and board.GetLayerName(z.GetLayer()) == item["layer"]
                and z.Outline().Contains(pcbnew.VECTOR2I(mm(x), mm(y)))]
        assert len(hits) == 1, f"zone removal matched {len(hits)}: {item}"
        board.Remove(hits[0])
        report["removed_zones"] += 1

    for item in spec.get("add_zones", []):
        _zone(board, item["net"], item["layer"], item["polygon"], item["priority"], item["clearance_mm"])
        report["added_zones"] += 1
    report["added_items"] = add_preroute(board, spec.get("add_items", []), lock=True)

    if spec.get("silk_refs"):
        report["silk_refs"] = place_references(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(out_path)
    print(json.dumps(report))


def _box(item):
    return item.GetBoundingBox()  # returned by value: a private copy


def _fp_body_box(footprint):
    try:
        return footprint.GetBoundingBox(False, False)
    except TypeError:
        return footprint.GetBoundingBox(False)


def place_references(board) -> dict:
    """Reference designators clear of pad copper (+0.15 mm), all other silkscreen (+0.1 mm)
    and the board edge (0.3 mm inside)."""
    import math

    pad_gap, silk_gap = mm(0.15), mm(0.1)
    edge = board.GetBoardEdgesBoundingBox()
    edge.Inflate(-mm(0.3))
    pads = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    silk = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            box = _box(pad)
            box.Inflate(pad_gap)
            if pad.IsOnLayer(pcbnew.F_Cu):
                pads[pcbnew.F_SilkS].append(box)
            if pad.IsOnLayer(pcbnew.B_Cu):
                pads[pcbnew.B_SilkS].append(box)
        for item in footprint.GraphicalItems():
            if item.GetLayer() in silk:
                box = _box(item)
                box.Inflate(silk_gap)
                silk[item.GetLayer()].append(box)
    for item in board.GetDrawings():
        if item.GetLayer() in silk:
            box = _box(item)
            box.Inflate(silk_gap)
            silk[item.GetLayer()].append(box)

    def clear(box, layer, own) -> bool:
        if not edge.Contains(box.GetOrigin()) or not edge.Contains(box.GetEnd()):
            return False
        return not any(box.Intersects(o) for o in pads[layer] + silk[layer] if o is not own)

    footprints = sorted(board.GetFootprints(), key=lambda f: _fp_body_box(f).GetArea())
    kept, moved, hidden = [], [], []
    placed = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
    todo = []
    for footprint in footprints:  # pass 1: keep every reference that is already clear
        field = footprint.Reference()
        layer = field.GetLayer()
        if layer not in silk or not field.IsVisible():
            continue
        box = _box(field)
        if clear(box, layer, None) and not any(box.Intersects(o) for o in placed[layer]):
            kept.append(footprint.GetReference())
            placed[layer].append(box)
        else:
            todo.append(footprint)
    for footprint in todo:  # pass 2: move the rest to the nearest free spot
        field = footprint.Reference()
        layer = field.GetLayer()
        ref = footprint.GetReference()
        start_pos, start_angle = field.GetPosition(), field.GetTextAngleDegrees()
        body = _fp_body_box(footprint)
        cx, cy = body.GetCenter().x, body.GetCenter().y
        options = []
        for angle in (0.0, 90.0):
            field.SetTextAngleDegrees(angle)
            field.SetPosition(pcbnew.VECTOR2I(cx, cy))
            probe = _box(field)
            tw, th = probe.GetWidth(), probe.GetHeight()
            for gap in (mm(0.15), mm(0.4), mm(0.8), mm(1.3)):
                ys = (body.GetY() - gap - th // 2, body.GetBottom() + gap + th // 2)
                xs = (body.GetX() - gap - tw // 2, body.GetRight() + gap + tw // 2)
                for y in ys:
                    for dx in range(-8, 9):
                        options.append((angle, cx + dx * mm(0.25), y))
                for x in xs:
                    for dy in range(-8, 9):
                        options.append((angle, x, cy + dy * mm(0.25)))
        options.sort(key=lambda o: (math.hypot(o[1] - start_pos.x, o[2] - start_pos.y), o[0]))
        done = False
        for angle, x, y in options:
            field.SetTextAngleDegrees(angle)
            field.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
            box = _box(field)
            # the text centre may be offset from its anchor: re-centre on the requested point
            field.SetPosition(pcbnew.VECTOR2I(int(x) - (box.GetCenter().x - int(x)),
                                              int(y) - (box.GetCenter().y - int(y))))
            box = _box(field)
            if clear(box, layer, None) and not any(box.Intersects(o) for o in placed[layer]):
                placed[layer].append(box)
                moved.append(ref)
                done = True
                break
        if not done:
            field.SetTextAngleDegrees(start_angle)
            field.SetPosition(start_pos)
            field.SetVisible(False)
            hidden.append(ref)
    return {"kept": sorted(kept), "moved": sorted(moved), "hidden": sorted(hidden)}


def dump(board_path: str, out_json: str) -> None:
    dump_geometry(board_path, out_json)
    board = pcbnew.LoadBoard(board_path)
    geometry = json.load(open(out_json, encoding="utf-8"))
    fills = []
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        for layer in zone.GetLayerSet().Seq():
            poly = zone.GetFilledPolysList(layer)
            for index in range(poly.OutlineCount()):
                outline = poly.Outline(index)
                fills.append({"net": zone.GetNetname(), "layer": board.GetLayerName(layer),
                              "points": [[pcbnew.ToMM(outline.CPoint(i).x), pcbnew.ToMM(outline.CPoint(i).y)]
                                         for i in range(outline.PointCount())],
                              "holes": [[[pcbnew.ToMM(poly.Hole(index, h).CPoint(i).x),
                                          pcbnew.ToMM(poly.Hole(index, h).CPoint(i).y)]
                                         for i in range(poly.Hole(index, h).PointCount())]
                                        for h in range(poly.HoleCount(index))]})
    geometry["fills"] = fills
    with open(out_json, "w", encoding="utf-8") as handle:
        json.dump(geometry, handle)
    print(json.dumps({"fills": len(fills)}))


if __name__ == "__main__":
    if sys.argv[1] == "apply":
        apply(sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "dump":
        dump(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(f"unknown mode {sys.argv[1]}")
