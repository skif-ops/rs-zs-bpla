#!/usr/bin/env python3
"""KiCad 9 stage of the autoroute pipeline (runs inside the pinned KiCad image).

export <board.kicad_pcb> <out.dsn> <plane_json>
    Lock every existing track and via (accepted copper stays byte-for-byte),
    add the requested inner-layer planes, write the Specctra DSN for Freerouting.
import <board.kicad_pcb> <in.ses> <out.kicad_pcb>
    Import the Freerouting session, refill zones and save the candidate.

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
    keepouts = 0
    if isinstance(config, dict) and config.get("hole_keepouts"):
        keepouts = add_hole_keepouts(board, config["hole_keepouts"]["refs"], config["hole_keepouts"]["radius_mm"])
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(board_path)
    assert pcbnew.ExportSpecctraDSN(board, dsn_path), "DSN export failed"
    print(json.dumps({"locked_track_items": locked, "zones": len(list(board.Zones())), "hole_keepouts": keepouts}))


def import_session(board_path: str, ses_path: str, out_path: str) -> None:
    board = pcbnew.LoadBoard(board_path)
    before = len(list(board.GetTracks()))
    assert pcbnew.ImportSpecctraSES(board, ses_path), "SES import failed"
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(out_path)
    print(json.dumps({"track_items_before": before, "track_items_after": len(list(board.GetTracks()))}))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "export":
        export(sys.argv[2], sys.argv[3], sys.argv[4])
    elif mode == "import":
        import_session(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        raise SystemExit(f"unknown mode {mode}")
