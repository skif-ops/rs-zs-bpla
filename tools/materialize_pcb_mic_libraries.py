#!/usr/bin/env python3
"""Materialize project-local KiCad libraries for PCB-MIC Rev.A.

This is part of the second-control contour. The generated schematic must resolve every
symbol/footprint through a project-local library table instead of relying on a runner's
implicit global table. Production MK1 is exported from the manufacturer-derived board
footprint, never from the EasyEDA T5838 reference footprint.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pcbnew


def write_tables(project_dir: Path) -> None:
    sym = '''(sym_lib_table
  (version 7)
  (lib (name "Device")(type "KiCad")(uri "${KICAD9_SYMBOL_DIR}/Device.kicad_sym")(options "")(descr "KiCad Device symbols"))
  (lib (name "DioneyaT5838")(type "KiCad")(uri "${KIPRJMOD}/libs/DioneyaT5838.kicad_sym")(options "")(descr "Dioneya T5838 production symbol"))
  (lib (name "DioneyaMolex")(type "KiCad")(uri "${KIPRJMOD}/libs/DioneyaMolex.kicad_sym")(options "")(descr "Dioneya Molex 5040500691 symbol"))
)
'''
    fp = '''(fp_lib_table
  (version 7)
  (lib (name "Resistor_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Resistor_SMD.pretty")(options "")(descr "KiCad resistor SMD footprints"))
  (lib (name "Capacitor_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Capacitor_SMD.pretty")(options "")(descr "KiCad capacitor SMD footprints"))
  (lib (name "DioneyaT5838")(type "KiCad")(uri "${KIPRJMOD}/libs/DioneyaT5838.pretty")(options "")(descr "Dioneya manufacturer-derived T5838 footprint"))
  (lib (name "DioneyaMolex")(type "KiCad")(uri "${KIPRJMOD}/libs/DioneyaMolex.pretty")(options "")(descr "Dioneya Molex 5040500691 footprint"))
)
'''
    (project_dir / "sym-lib-table").write_text(sym, encoding="utf-8")
    (project_dir / "fp-lib-table").write_text(fp, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    ap.add_argument("--t5838-symbol", type=Path, required=True)
    ap.add_argument("--molex-symbol", type=Path, required=True)
    args = ap.parse_args()

    project_dir = args.board.parent
    libs = project_dir / "libs"
    t5838_pretty = libs / "DioneyaT5838.pretty"
    molex_pretty = libs / "DioneyaMolex.pretty"
    t5838_pretty.mkdir(parents=True, exist_ok=True)
    molex_pretty.mkdir(parents=True, exist_ok=True)

    shutil.copy2(args.t5838_symbol, libs / "DioneyaT5838.kicad_sym")
    shutil.copy2(args.molex_symbol, libs / "DioneyaMolex.kicad_sym")

    board = pcbnew.LoadBoard(str(args.board))
    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    if set(("MK1", "J1")) - set(by_ref):
        raise RuntimeError(f"required footprints missing: {sorted(set(('MK1','J1')) - set(by_ref))}")

    mk1 = by_ref["MK1"]
    j1 = by_ref["J1"]
    mk1.SetFPIDAsString("DioneyaT5838:T5838_RevA")
    j1.SetFPIDAsString("DioneyaMolex:Molex_5040500691")

    if not pcbnew.FootprintSave(str(t5838_pretty), mk1):
        raise RuntimeError("failed to save production T5838 footprint")
    if not pcbnew.FootprintSave(str(molex_pretty), j1):
        raise RuntimeError("failed to save production Molex footprint")

    pcbnew.SaveBoard(str(args.board), board)
    write_tables(project_dir)

    required = [
        libs / "DioneyaT5838.kicad_sym",
        libs / "DioneyaMolex.kicad_sym",
        t5838_pretty / "T5838_RevA.kicad_mod",
        molex_pretty / "Molex_5040500691.kicad_mod",
        project_dir / "sym-lib-table",
        project_dir / "fp-lib-table",
    ]
    missing = [str(p) for p in required if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"local KiCad library materialization incomplete: {missing}")

    print("PCB-MIC project-local library materialization PASS")
    for p in required:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
