#!/usr/bin/env python3
"""Materialize project-local symbol libraries and links for PCB-MIC Rev.A.

This script intentionally uses only kiutils and runs in the same Python environment as
schematic generation. Footprint export is handled separately by the system-Python
pcbnew tool. Keeping those environments separate avoids hidden dependency on the CI
runner while preserving the two-control gate.
"""
from __future__ import annotations

import argparse
from pathlib import Path

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
    combined = SymbolLib.from_file(str(t5838_path), encoding="utf-8")
    molex = SymbolLib.from_file(str(molex_path), encoding="utf-8")
    names = {s.entryName for s in combined.symbols}
    for symbol in molex.symbols:
        if symbol.entryName not in names:
            combined.symbols.append(symbol)
            names.add(symbol.entryName)
    combined.to_file(str(output), encoding="utf-8")


def link_schematic_footprints(schematic_path: Path) -> None:
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
    ap.add_argument("--schematic", type=Path, required=True)
    ap.add_argument("--t5838-symbol", type=Path, required=True)
    ap.add_argument("--molex-symbol", type=Path, required=True)
    args = ap.parse_args()

    project_dir = args.schematic.parent
    libs = project_dir / "libs"
    libs.mkdir(parents=True, exist_ok=True)

    merge_custom_symbols(args.t5838_symbol, args.molex_symbol, libs / "Dioneya.kicad_sym")
    link_schematic_footprints(args.schematic)
    write_tables(project_dir)

    required = [
        libs / "Dioneya.kicad_sym",
        project_dir / "sym-lib-table",
        project_dir / "fp-lib-table",
        args.schematic,
    ]
    missing = [str(p) for p in required if not p.is_file() or p.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"local KiCad symbol materialization incomplete: {missing}")

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

    print("PCB-MIC project-local symbol library materialization PASS")
    print("custom links", custom_links)
    for p in required:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
