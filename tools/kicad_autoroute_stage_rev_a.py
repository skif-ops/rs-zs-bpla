#!/usr/bin/env python3
"""KiCad 9 stage of the autoroute pipeline (runs inside the pinned KiCad image).

export <board.kicad_pcb> <out.dsn> <plane_json>
    Lock every existing track and via (accepted copper stays byte-for-byte),
    add the requested inner-layer planes, write the Specctra DSN for Freerouting.
import <board.kicad_pcb> <in.ses> <out.kicad_pcb> [tracks.json]
    Import the Freerouting session, refill zones, save the candidate and dump
    the routed segments.
pours <board.kicad_pcb> <spec.json>
    Add thickening zones along power routes (polygons computed by the host),
    ground pours on the outer layers and stitching vias into the plane.

The project file next to the board carries the net classes, so the DSN
exports the per-class widths and clearances.
"""

from __future__ import annotations

import json
import sys

import pcbnew


def mm(value: float) -> int:
    return pcbnew.FromMM(float(value))


def add_plane(board, net_name: str, layer_name: str, inset_mm: float) -> None:
    net = board.FindNet(net_name)
    assert net is not None, f"net {net_name} missing"
    layer = board.GetLayerID(layer_name)
    box = board.GetBoardEdgesBoundingBox()
    x0, y0 = box.GetX() + mm(inset_mm), box.GetY() + mm(inset_mm)
    x1, y1 = box.GetRight() - mm(inset_mm), box.GetBottom() - mm(inset_mm)
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNetCode(net.GetNetCode())
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetLocalClearance(mm(0.3))
    zone.SetMinThickness(mm(0.25))
    zone.SetAssignedPriority(0)
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        outline.Append(x, y)
    board.Add(zone)


def add_hole_keepouts(board, references: list[str], radius_mm: float) -> int:
    """No tracks or vias within radius_mm of the mounting-hole centres on any
    copper layer (Freerouting does not honour NPTH hole clearance itself)."""
    import math

    added = 0
    for footprint in board.GetFootprints():
        if footprint.GetReference() not in references:
            continue
        centre = footprint.GetPosition()
        zone = pcbnew.ZONE(board)
        zone.SetIsRuleArea(True)
        zone.SetDoNotAllowTracks(True)
        zone.SetDoNotAllowVias(True)
        zone.SetDoNotAllowPads(False)
        zone.SetDoNotAllowCopperPour(False)
        zone.SetDoNotAllowFootprints(False)
        zone.SetLayerSet(pcbnew.LSET.AllCuMask())
        outline = zone.Outline()
        outline.NewOutline()
        for step in range(32):
            angle = 2 * math.pi * step / 32
            outline.Append(centre.x + int(mm(radius_mm) * math.cos(angle)),
                           centre.y + int(mm(radius_mm) * math.sin(angle)))
        board.Add(zone)
        added += 1
    return added


def _via(board, net_name: str, x_mm: float, y_mm: float, size_mm: float = 0.6, drill_mm: float = 0.3):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(mm(x_mm), mm(y_mm)))
    try:
        via.SetWidth(mm(size_mm))
    except TypeError:  # KiCad 9 padstack API
        via.SetWidth(pcbnew.F_Cu, mm(size_mm))
    via.SetDrill(mm(drill_mm))
    via.SetNetCode(board.FindNet(net_name).GetNetCode())
    board.Add(via)
    return via


def add_preroute(board, items) -> int:
    """Deterministic, locked escape stubs for pins the autorouter cannot enter
    (fine-pitch pins next to same-footprint land rules, net-tie exits)."""
    count = 0
    for kind, layer, net, width, points in items:
        if kind == "via":
            _via(board, net, points[0][0], points[0][1], width).SetLocked(True)
            count += 1
            continue
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0)))
            track.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1)))
            track.SetWidth(mm(width))
            track.SetLayer(board.GetLayerID(layer))
            track.SetNetCode(board.FindNet(net).GetNetCode())
            track.SetLocked(True)
            board.Add(track)
            count += 1
    return count


def add_tie_strips(board, references) -> int:
    """Thin no-track strips beside net-tie bridges: the bridge polygon is not
    exported to the DSN, so the autorouter would otherwise pass too close."""
    added = 0
    for footprint in board.GetFootprints():
        if footprint.GetReference() not in references:
            continue
        pads = sorted(footprint.Pads(), key=lambda pad: pad.GetPosition().x)
        x0, x1 = pads[0].GetPosition().x, pads[-1].GetPosition().x
        yc = pads[0].GetPosition().y
        for sign in (1,):  # below the bridge only: exits upward stay free
            zone = pcbnew.ZONE(board)
            zone.SetIsRuleArea(True)
            zone.SetDoNotAllowTracks(True)
            zone.SetDoNotAllowVias(True)
            zone.SetDoNotAllowPads(False)
            zone.SetDoNotAllowCopperPour(False)
            zone.SetDoNotAllowFootprints(False)
            zone.SetLayer(footprint.GetLayer())
            ya, yb = yc + sign * mm(0.30), yc + sign * mm(0.70)
            outline = zone.Outline()
            outline.NewOutline()
            for x, y in ((x0, ya), (x1, ya), (x1, yb), (x0, yb)):
                outline.Append(x, y)
            board.Add(zone)
            added += 1
    return added


def export(board_path: str, dsn_path: str, plane_json: str) -> None:
    config = json.loads(plane_json)
    planes = config["planes"] if isinstance(config, dict) else config
    board = pcbnew.LoadBoard(board_path)
    locked = 0
    for track in board.GetTracks():
        track.SetLocked(True)
        locked += 1
    plane_layers = {board.GetLayerID(plane["layer"]) for plane in planes}
    for zone in board.Zones():
        if not zone.GetIsRuleArea() and zone.GetLayer() in plane_layers:
            zone.SetAssignedPriority(max(1, zone.GetAssignedPriority()))
    for layer in plane_layers:
        board.SetLayerType(layer, pcbnew.LT_POWER)
    for plane in planes:
        add_plane(board, plane["net"], plane["layer"], plane.get("inset_mm", 0.5))
    prerouted = add_preroute(board, config.get("preroute", []) if isinstance(config, dict) else [])
    strips = add_tie_strips(board, config.get("tie_strips", []) if isinstance(config, dict) else [])
    keepouts = 0
    if isinstance(config, dict) and config.get("hole_keepouts"):
        keepouts = add_hole_keepouts(board, config["hole_keepouts"]["refs"], config["hole_keepouts"]["radius_mm"])
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(board_path)
    assert pcbnew.ExportSpecctraDSN(board, dsn_path), "DSN export failed"
    print(json.dumps({"locked_track_items": locked, "zones": len(list(board.Zones())), "hole_keepouts": keepouts,
                      "preroute_items": prerouted, "tie_strips": strips}))


def import_session(board_path: str, ses_path: str, out_path: str, tracks_json: str = "") -> None:
    board = pcbnew.LoadBoard(board_path)
    before = len(list(board.GetTracks()))
    assert pcbnew.ImportSpecctraSES(board, ses_path), "SES import failed"
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(out_path)
    if tracks_json:
        segments = []
        for track in board.GetTracks():
            if track.GetClass() != "PCB_TRACK":
                continue
            segments.append({
                "net": track.GetNetname(), "layer": board.GetLayerName(track.GetLayer()),
                "start": [pcbnew.ToMM(track.GetStart().x), pcbnew.ToMM(track.GetStart().y)],
                "end": [pcbnew.ToMM(track.GetEnd().x), pcbnew.ToMM(track.GetEnd().y)],
                "width": pcbnew.ToMM(track.GetWidth()),
            })
        with open(tracks_json, "w", encoding="utf-8") as handle:
            json.dump(segments, handle)
    print(json.dumps({"track_items_before": before, "track_items_after": len(list(board.GetTracks()))}))


def _zone(board, net_name: str, layer_name: str, points_mm, priority: int, clearance_mm: float,
          remove_islands: bool = False):
    zone = pcbnew.ZONE(board)
    zone.SetLayer(board.GetLayerID(layer_name))
    zone.SetNetCode(board.FindNet(net_name).GetNetCode())
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetLocalClearance(mm(clearance_mm))
    zone.SetMinThickness(mm(0.25))
    zone.SetAssignedPriority(priority)
    if remove_islands:  # ground pours: drop islands the fill cannot connect
        try:
            zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        except AttributeError:
            pass
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in points_mm:
        outline.Append(mm(x), mm(y))
    board.Add(zone)
    return zone


def _inside(polys, x: int, y: int) -> bool:
    return polys.Contains(pcbnew.VECTOR2I(int(x), int(y)))


def pours(board_path: str, spec_json: str) -> None:
    """Add thickening zones along power routes, GND pours on the outer layers and
    stitching vias into the plane; refill and save."""
    import math

    spec = json.load(open(spec_json, encoding="utf-8"))
    board = pcbnew.LoadBoard(board_path)
    for item in spec["thicken"]:
        for polygon in item["polygons"]:
            _zone(board, item["net"], item["layer"], polygon, item["priority"], item["clearance_mm"])
    box = board.GetBoardEdgesBoundingBox()
    inset = mm(spec["pour_inset_mm"])
    rect = [(pcbnew.ToMM(box.GetX() + inset), pcbnew.ToMM(box.GetY() + inset)),
            (pcbnew.ToMM(box.GetRight() - inset), pcbnew.ToMM(box.GetY() + inset)),
            (pcbnew.ToMM(box.GetRight() - inset), pcbnew.ToMM(box.GetBottom() - inset)),
            (pcbnew.ToMM(box.GetX() + inset), pcbnew.ToMM(box.GetBottom() - inset))]
    ground_zones = [_zone(board, spec["ground_net"], layer, rect, 0, spec["pour_clearance_mm"], True)
                    for layer in spec["ground_pour_layers"]]
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    ground = board.FindNet(spec["ground_net"])
    radius = mm(spec["stitch_keep_mm"])
    pitch = mm(spec["stitch_pitch_mm"])
    fills = [zone.GetFilledPolysList(zone.GetLayer()) for zone in ground_zones]
    blockers = [t for t in board.GetTracks() if t.GetNetCode() != ground.GetNetCode()]
    placed = 0
    y = box.GetY() + pitch
    while y < box.GetBottom():
        x = box.GetX() + pitch
        while x < box.GetRight():
            probes = [(x + int(radius * math.cos(a)), y + int(radius * math.sin(a)))
                      for a in [i * math.pi / 4 for i in range(8)]] + [(x, y)]
            if all(all(_inside(fill, px, py) for px, py in probes) for fill in fills):
                clear = True
                for track in blockers:
                    if track.HitTest(pcbnew.VECTOR2I(int(x), int(y)), radius):
                        clear = False
                        break
                if clear:
                    via = pcbnew.PCB_VIA(board)
                    via.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
                    try:
                        via.SetWidth(mm(0.6))
                    except TypeError:  # KiCad 9 padstack API
                        via.SetWidth(pcbnew.F_Cu, mm(0.6))
                    via.SetDrill(mm(0.3))
                    via.SetNetCode(ground.GetNetCode())
                    board.Add(via)
                    placed += 1
            x += pitch
        y += pitch
    filler.Fill(board.Zones())
    board.Save(board_path)
    print(json.dumps({"thicken_zones": sum(len(i["polygons"]) for i in spec["thicken"]), "stitching_vias": placed}))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "export":
        export(sys.argv[2], sys.argv[3], sys.argv[4])
    elif mode == "import":
        import_session(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else "")
    elif mode == "pours":
        pours(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(f"unknown mode {mode}")
