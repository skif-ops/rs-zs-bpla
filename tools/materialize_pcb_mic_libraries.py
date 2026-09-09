#!/usr/bin/env python3
"""Materialize project-local KiCad libraries for PCB-MIC Rev.A.

This is part of the second-control contour. The generated schematic must resolve every
symbol/footprint through a project-local library table instead of relying on a runner's
implicit global table. Production MK1 is exported from the manufacturer-derived board
footprint, never from the EasyEDA T5838 reference footprint.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pcbnew
from kiutils.schematic import Schematic
from kiutils.symbol import SymbolLib


def write_tables(project_dir: Path) -> None:
    sym = '''(sym_lib_table
  (version 7)
  (lib (name "Device")(type "KiCad")(uri "${KICAD9_SYMBOL_DIR}/Device.kicad_sym")(options "")(descr "KiCad Device symbols"))
  (lib (name "Dioneya")(type "KiCad")(uri "${KIPRJMOD}/libs/Dioneya.kicad_sym")(options "")(descr "Dioneya PCB-MIC controlled symbols"))
)
'''
    fp = '''(fp_lib_table
  (version 7)
  (lib (name "Resistor_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Resistor_SMD.pretty")(options "")(descr "KiCad resistor SMD footprints"))
  (lib (name "Capacitor_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Capacitor_SMD.pretty")(options "")(descr "KiCad capacitor SMD footprints"))
  (lib (name "Dioneya")(type "KiCad")(uri "${KIPRJMOD}/libs/Dioneya.pretty")(options "")(descr "Dioneya PCB-MIC controlled footprints"))
)
'''
    (project_dir / "sym-lib-table").write_text(sym, encoding="utf-8")
    (project_dir / "fp-lib-table").write_text(fp, encoding="utf-8")


def merge_custom_symbols(t5838_path: Path, molex_path: Path, output: Path) -> None:
    """Merge the two inspected reference symbol files into one project library.

    The symbol graphics/pin numbering remain the independently inspected inputs. This
    merge only gives both already-embedded schematic symbols a real project-library
    resolution target named Dioneya.
    """
    combined = SymbolLib.from_file(str(t5838_path), encoding="utf-8")
    molex = SymbolLib.from_file(str(molex_path), encoding="utf-8")
    names = {s.entryName for s in combined.symbols}
    for symbol in molex.symbols:
        if symbol.entryName not in names:
            combined.symbols.append(symbol)
            names.add(symbol.entryName)
    combined.to_file(str(output), encoding="utf-8")


def link_schematic_footprints(schematic_path: Path) -> None:
    """Replace bare custom footprint names with controlled project-library links."""
    sch = Schematic.from_file(str(schematic_path), encoding="utf-8")
    changed = set()
    for symbol in sch.schematicSymbols:
        ref = next((p.value for p in symbol.properties if p.key == "Reference"), "")
        footprint = next((p for p in symbol.properties if p.key == "Footprint"), None)
        if footprint is None:
            continue
        if ref == "MK1":
            footprint.value = "Dioneya:T5838_RevA"
            changed.add(ref)
        elif ref == "J1":
            footprint.value = "Dioneya:Molex_5040500691"
            changed.add(ref)
    if changed != {"MK1", "J1"}:
        raise RuntimeError(f"custom schematic footprint links incomplete: {sorted(changed)}")
    sch.to_file(str(schematic_path), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    ap.add_argument("--schematic", type=Path, required=True)
    ap.add_argument("--t5838-symbol", type=Path, required=True)
    ap.add_argument("--molex-symbol", type=Path, required=True)
    args = ap.parse_args()

    project_dir = args.board.parent
    libs = project_dir / "libs"
    pretty = libs / "Dioneya.pretty"
    libs.mkdir(parents=True, exist_ok=True)
    pretty.mkdir(parents=True, exist_ok=True)

    merge_custom_symbols(args.t5838_symbol, args.molex_symbol, libs / "Dioneya.kicad_sym")

    board = pcbnew.LoadBoard(str(args.board))
    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    missing_refs = set(("MK1", "J1")) - set(by_ref)
    if missing_refs:
        raise RuntimeError(f"required footprints missing: {sorted(missing_refs)}")

    mk1 = by_ref["MK1"]
    j1 = by_ref["J1"]
    mk1.SetFPIDAsString("Dioneya:T5838_RevA")
    j1.SetFPIDAsString("Dioneya:Molex_5040500691")

    pcbnew.FootprintSave(str(pretty), mk1)
    pcbnew.FootprintSave(str(pretty), j1)
    pcbnew.SaveBoard(str(args.board), board)

    link_schematic_footprints(args.schematic)
    write_tables(project_dir)

    required = [
        libs / "Dioneya.kicad_sym",
        pretty / "T5838_RevA.kicad_mod",
        pretty / "Molex_5040500691.kicad_mod",
        project_dir / "sym-lib-table",
        project_dir / "fp-lib-table",
        args.board,
        args.schematic,
    ]
    missing = [str(p) for p in required if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"local KiCad library materialization incomplete: {missing}")

    # First-control resolution check. KiCad ERC is the independent second control.
    reread = Schematic.from_file(str(args.schematic), encoding="utf-8")
    custom_links = {}
    for symbol in reread.schematicSymbols:
        ref = next((p.value for p in symbol.properties if p.key == "Reference"), "")
        footprint = next((p.value for p in symbol.properties if p.key == "Footprint"), "")
        if ref in ("MK1", "J1"):
            custom_links[ref] = footprint
    expected = {"MK1": "Dioneya:T5838_RevA", "J1": "Dioneya:Molex_5040500691"}
    if custom_links != expected:
        raise RuntimeError(f"schematic footprint link verification failed: {custom_links}")

    print("PCB-MIC project-local library materialization PASS")
    print("custom links", custom_links)
    for p in required:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
