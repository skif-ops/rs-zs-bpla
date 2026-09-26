#!/usr/bin/env python3
"""KiCad 9 stage of PCB routing 004 (runs inside the pinned KiCad image).

dsn  <board.kicad_pcb> <out.dsn>        Specctra DSN export of the board (input of the autorouter)
fill <in.kicad_pcb> <out.kicad_pcb>     refill every zone and save
"""

from __future__ import annotations

import json
import sys

import pcbnew


def dsn(src: str, dst: str) -> None:
    board = pcbnew.LoadBoard(src)
    ok = pcbnew.ExportSpecctraDSN(board, dst)
    print(json.dumps({"dsn": dst, "ok": bool(ok)}))
    if not ok:
        raise SystemExit(1)


def fill(src: str, dst: str) -> None:
    board = pcbnew.LoadBoard(src)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(dst)
    print(json.dumps({"filled_zones": len(list(board.Zones()))}))


if __name__ == "__main__":
    {"dsn": dsn, "fill": fill}[sys.argv[1]](*sys.argv[2:])
