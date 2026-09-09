#!/usr/bin/env python3
"""Export the exact board-resident PCB-MIC footprints into a project-local KiCad library.

Runs with system Python because pcbnew is supplied by KiCad. MK1 is the manufacturer-
derived production candidate already present on the board; the EasyEDA T5838 reference
footprint is never exported as production CAD.

KiCad 9's global FootprintSave() tries to infer a plugin from the target path and does
not recognize a newly-created empty .pretty directory. This exporter therefore selects
the native KiCad S-expression IO plugin explicitly via PCB_IO_KICAD_SEXPR and uses its
FootprintSave() method. That is the controlled format-selection path, not an exception
or a text-level footprint rewrite.
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

    io = pcbnew.PCB_IO_KICAD_SEXPR()
    io.FootprintSave(str(pretty), mk1)
    io.FootprintSave(str(pretty), j1)
    pcbnew.SaveBoard(str(args.board), board)

    expected = [
        pretty / "T5838_RevA.kicad_mod",
        pretty / "Molex_5040500691.kicad_mod",
    ]
    missing = [str(p) for p in expected if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"controlled footprint export incomplete: {missing}")

    # Independent re-read of both the board and library footprints is the first
    # control contour. KiCad CLI DRC/ERC remains the separate second contour.
    reread = pcbnew.LoadBoard(str(args.board))
    links = {
        fp.GetReference(): fp.GetFPIDAsString()
        for fp in reread.GetFootprints()
        if fp.GetReference() in ("MK1", "J1")
    }
    wanted = {"MK1": "Dioneya:T5838_RevA", "J1": "Dioneya:Molex_5040500691"}
    if links != wanted:
        raise RuntimeError(f"board FPID verification failed: {links}")

    mk1_lib = pcbnew.FootprintLoad(str(pretty), "T5838_RevA")
    j1_lib = pcbnew.FootprintLoad(str(pretty), "Molex_5040500691")
    if mk1_lib is None or j1_lib is None:
        raise RuntimeError("controlled footprints could not be reloaded from Dioneya.pretty")
    if len(list(mk1_lib.Pads())) != len(list(mk1.Pads())):
        raise RuntimeError("T5838 library footprint pad-count mismatch after export")
    if len(list(j1_lib.Pads())) != len(list(j1.Pads())):
        raise RuntimeError("Molex library footprint pad-count mismatch after export")

    print("PCB-MIC controlled footprint export PASS")
    print("board links", links)
    print("reload pad counts", len(list(mk1_lib.Pads())), len(list(j1_lib.Pads())))
    for p in expected:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
