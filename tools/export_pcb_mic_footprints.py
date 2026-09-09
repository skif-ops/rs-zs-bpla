#!/usr/bin/env python3
"""Export the exact board-resident PCB-MIC footprints into a project-local KiCad library.

Runs with system Python because pcbnew is supplied by KiCad. MK1 is the manufacturer-
derived production candidate already present on the board; the EasyEDA T5838 reference
footprint is never exported as production CAD.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pcbnew


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    args = ap.parse_args()

    project_dir = args.board.parent
    pretty = project_dir / "libs" / "Dioneya.pretty"
    pretty.mkdir(parents=True, exist_ok=True)

    board = pcbnew.LoadBoard(str(args.board))
    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    missing_refs = {"MK1", "J1"} - set(by_ref)
    if missing_refs:
        raise RuntimeError(f"required footprints missing: {sorted(missing_refs)}")

    mk1 = by_ref["MK1"]
    j1 = by_ref["J1"]
    mk1.SetFPIDAsString("Dioneya:T5838_RevA")
    j1.SetFPIDAsString("Dioneya:Molex_5040500691")

    pcbnew.FootprintSave(str(pretty), mk1)
    pcbnew.FootprintSave(str(pretty), j1)
    pcbnew.SaveBoard(str(args.board), board)

    expected = [
        pretty / "T5838_RevA.kicad_mod",
        pretty / "Molex_5040500691.kicad_mod",
    ]
    missing = [str(p) for p in expected if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"controlled footprint export incomplete: {missing}")

    reread = pcbnew.LoadBoard(str(args.board))
    links = {fp.GetReference(): fp.GetFPIDAsString() for fp in reread.GetFootprints() if fp.GetReference() in ("MK1", "J1")}
    wanted = {"MK1": "Dioneya:T5838_RevA", "J1": "Dioneya:Molex_5040500691"}
    if links != wanted:
        raise RuntimeError(f"board FPID verification failed: {links}")

    print("PCB-MIC controlled footprint export PASS")
    print("board links", links)
    for p in expected:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
