#!/usr/bin/env python3
"""Materialize project-local libraries for native PCB-PWR Rev.A schematic.

Electrical pin/net content is not changed. This layer makes KiCad ERC deterministic by
providing the local DioneyaPWR symbol library and standard library tables. Footprint
properties are cleared only for references whose exact production land pattern is still
an explicit Review-A/Review-B blocker; fake placeholder footprints are prohibited.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

from kiutils.schematic import Schematic
from kiutils.symbol import SymbolLib

UNRESOLVED_FOOTPRINT_REFS = {
    "J1",   # exact Micro-Fit 2-pin board land pattern/orientation pending mechanical review
    "Q1",   # CSD18540Q5B DNK manufacturer footprint to be controlled before layout
    "RSH1", # exact four-terminal shunt MPN/land pattern not frozen
    "U3", "U4", # LMR60440 RAK-9 manufacturer land pattern review pending
    "L1", "L2", # exact inductor MPN not frozen
    "C3", "C5", # effective COUT bank exact technology/MPNs not frozen
    "J2",   # 43045-1202 land pattern/orientation pending mechanical review
}

BASE_CONTROLLED_ENTRIES = {
    "Conn_01x02", "Conn_01x12", "Conn_01x06", "Conn_01x08",
    "Conn_01x10", "Conn_01x09", "Conn_01x05", "Conn_01x04",
}


def ref_of(symbol) -> str:
    return next((p.value for p in symbol.properties if p.key == "Reference"), "")


def footprint_prop(symbol):
    return next((p for p in symbol.properties if p.key == "Footprint"), None)


def write_tables(project_dir: Path) -> None:
    sym = '''(sym_lib_table
  (version 7)
  (lib (name "Device")(type "KiCad")(uri "${KICAD9_SYMBOL_DIR}/Device.kicad_sym")(options "")(descr "KiCad Device symbols"))
  (lib (name "DioneyaPWR")(type "KiCad")(uri "${KIPRJMOD}/libs/DioneyaPWR.kicad_sym")(options "")(descr "Dioneya PCB-PWR controlled Review-A symbols"))
)
'''
    fp = '''(fp_lib_table
  (version 7)
  (lib (name "Resistor_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Resistor_SMD.pretty")(options "")(descr "KiCad resistor SMD footprints"))
  (lib (name "Capacitor_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Capacitor_SMD.pretty")(options "")(descr "KiCad capacitor SMD footprints"))
  (lib (name "Diode_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Diode_SMD.pretty")(options "")(descr "KiCad diode SMD footprints"))
  (lib (name "Fuse")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Fuse.pretty")(options "")(descr "KiCad fuse footprints"))
  (lib (name "Package_TO_SOT_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Package_TO_SOT_SMD.pretty")(options "")(descr "KiCad SOT footprints"))
  (lib (name "Package_SO")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Package_SO.pretty")(options "")(descr "KiCad SO/VSSOP footprints"))
  (lib (name "NetTie")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/NetTie.pretty")(options "")(descr "KiCad net-tie footprints"))
)
'''
    (project_dir / "sym-lib-table").write_text(sym, encoding="utf-8")
    (project_dir / "fp-lib-table").write_text(fp, encoding="utf-8")


def export_custom_symbols(schematic: Schematic, connector_lib: Path, output: Path) -> None:
    custom = [s for s in schematic.libSymbols if s.libraryNickname == "DioneyaPWR"]
    entries = [str(s.entryName) for s in custom]
    if len(entries) != len(set(entries)):
        raise RuntimeError(f"duplicate DioneyaPWR symbol entries: {entries}")
    missing = BASE_CONTROLLED_ENTRIES - set(entries)
    if missing:
        raise RuntimeError(f"required controlled DioneyaPWR embedded symbols missing: {sorted(missing)}")

    combined = SymbolLib.from_file(str(connector_lib), encoding="utf-8")
    combined.symbols = []
    for symbol in custom:
        exported = copy.deepcopy(symbol)
        exported.libraryNickname = None
        combined.symbols.append(exported)
    combined.to_file(str(output), encoding="utf-8")

    reread = SymbolLib.from_file(str(output), encoding="utf-8")
    expected = sorted(entries)
    actual = sorted(str(s.entryName) for s in reread.symbols)
    if actual != expected:
        raise RuntimeError(f"DioneyaPWR local symbol library round-trip mismatch: {actual} != {expected}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schematic", type=Path, required=True)
    ap.add_argument("--connector-symbols", type=Path, default=Path("/usr/share/kicad/symbols/Connector_Generic.kicad_sym"))
    args = ap.parse_args()

    project_dir = args.schematic.parent
    libs = project_dir / "libs"
    libs.mkdir(parents=True, exist_ok=True)

    sch = Schematic.from_file(str(args.schematic), encoding="utf-8")
    refs = {ref_of(s): s for s in sch.schematicSymbols}
    missing = UNRESOLVED_FOOTPRINT_REFS - set(refs)
    if missing:
        raise RuntimeError(f"unresolved-footprint authority references missing from schematic: {sorted(missing)}")

    cleared = []
    for ref in sorted(UNRESOLVED_FOOTPRINT_REFS):
        fp = footprint_prop(refs[ref])
        if fp is None:
            raise RuntimeError(f"{ref}: Footprint property missing")
        fp.value = ""
        cleared.append(ref)

    sch.to_file(str(args.schematic), encoding="utf-8")
    reread = Schematic.from_file(str(args.schematic), encoding="utf-8")
    reread_refs = {ref_of(s): s for s in reread.schematicSymbols}
    for ref in UNRESOLVED_FOOTPRINT_REFS:
        fp = footprint_prop(reread_refs[ref])
        if fp is None or fp.value != "":
            raise RuntimeError(f"{ref}: unresolved footprint was not deterministically cleared")

    export_custom_symbols(reread, args.connector_symbols, libs / "DioneyaPWR.kicad_sym")
    write_tables(project_dir)

    required = [
        args.schematic,
        libs / "DioneyaPWR.kicad_sym",
        project_dir / "sym-lib-table",
        project_dir / "fp-lib-table",
    ]
    absent = [str(p) for p in required if not p.is_file() or p.stat().st_size == 0]
    if absent:
        raise RuntimeError(f"PCB-PWR local library materialization incomplete: {absent}")

    count = len([s for s in reread.libSymbols if s.libraryNickname == "DioneyaPWR"])
    print("PCB-PWR project-local library materialization PASS")
    print("unresolved production footprints intentionally blank:", sorted(cleared))
    print("controlled DioneyaPWR symbols:", count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
