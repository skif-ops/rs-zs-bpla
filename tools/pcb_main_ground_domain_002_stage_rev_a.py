#!/usr/bin/env python3
"""KiCad 9 stage of PCB-MAIN-GROUND-DOMAIN-ROUTING-002 (runs inside the pinned KiCad image).

fill <in.kicad_pcb> <out.kicad_pcb>   refill every zone and save
dump <board.kicad_pcb> <out.json>     filled copper of every zone (net, layer, outline + holes)
"""

from __future__ import annotations

import json
import sys

import pcbnew


def fill(src: str, dst: str) -> None:
    board = pcbnew.LoadBoard(src)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(dst)
    print(json.dumps({"filled_zones": len(list(board.Zones()))}))


def dump(src: str, dst: str) -> None:
    board = pcbnew.LoadBoard(src)
    fills = []
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        for layer in zone.GetLayerSet().Seq():
            poly = zone.GetFilledPolysList(layer)
            for index in range(poly.OutlineCount()):
                outline = poly.Outline(index)
                fills.append({
                    "net": zone.GetNetname(), "layer": board.GetLayerName(layer), "zone": zone.GetZoneName(),
                    "points": [[pcbnew.ToMM(outline.CPoint(i).x), pcbnew.ToMM(outline.CPoint(i).y)]
                               for i in range(outline.PointCount())],
                    "holes": [[[pcbnew.ToMM(poly.Hole(index, h).CPoint(i).x), pcbnew.ToMM(poly.Hole(index, h).CPoint(i).y)]
                               for i in range(poly.Hole(index, h).PointCount())]
                              for h in range(poly.HoleCount(index))]})
    with open(dst, "w", encoding="utf-8") as handle:
        json.dump({"fills": fills}, handle)
    print(json.dumps({"fills": len(fills)}))


if __name__ == "__main__":
    {"fill": fill, "dump": dump}[sys.argv[1]](sys.argv[2], sys.argv[3])
