#!/usr/bin/env python3
"""Materialize project-local libraries for native PCB-PWR Rev.A schematic.

Electrical pin/net content is not changed. This layer makes KiCad ERC deterministic by
providing the local DioneyaPWR symbol library and standard library tables. Exact
manufacturer-controlled footprints are bound here; fake placeholder footprints are
prohibited.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

from kiutils.schematic import Schematic
from kiutils.symbol import SymbolLib

UNRESOLVED_FOOTPRINT_REFS: set[str] = set()

CONTROLLED_FOOTPRINTS = {
    # Molex SD-43045-005 Rev G1 defines the two contacts and both possible
    # polarization-peg holes for the gold-plated 43045-0213 vertical header.
    "J1": "DioneyaPWR:Molex_43045-0213_MicroFit-2_Vertical",
    # TI SNOSD17G package drawing DBV0006A 4214840/G defines exact lands,
    # solder-mask and equal stencil apertures for the six-pin SOT-23.
    "U1": "DioneyaPWR:TI_DBV0006A_SOT23-6",
    # TI SBOS547C package drawing DGS0010A 4221984/A defines exact lands,
    # solder-mask and equal stencil apertures for the ten-pin VSSOP.
    "U2": "DioneyaPWR:TI_DGS0010A_VSSOP10",
    # Vishay document 30108 defines the four independent WSK2512 lands.
    "RSH1": "DioneyaPWR:Vishay_WSK2512_4T_T1.19mm",
    # TI SLPS488B sections 7.2/7.3 provide the exact PCB and stencil patterns.
    "Q1": "DioneyaPWR:CSD18540Q5B_DNK",
    # TI SNAS877 RAK0009A drawing 4229353/J provides board and stencil patterns.
    "U3": "DioneyaPWR:LMR60440_RAK0009A",
    "U4": "DioneyaPWR:LMR60440_RAK0009A",
    # Coilcraft document 863-2 defines the -472 terminal width and land pattern.
    "L1": "DioneyaPWR:Coilcraft_XAL7030_472",
    "L2": "DioneyaPWR:Coilcraft_XAL7030_472",
    # TPS7A20 SBVS338H carries the same TI DBV0005A 4214839/K pattern that
    # is already controlled and parsed in the shared PCB-MAIN library.
    "U5": "DioneyaMain:TI_DBV0005A_SOT23-5",
    # The identical CON-004A/CON-004B board header uses the single audited
    # manufacturer pattern already controlled by PCB-MAIN.
    "J2": "DioneyaMain:Molex_43045-1202_MicroFit-12_RA",
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
  (lib (name "DioneyaPWR")(type "KiCad")(uri "${KIPRJMOD}/libs/DioneyaPWR.pretty")(options "")(descr "Dioneya PCB-PWR manufacturer-controlled footprints"))
  (lib (name "DioneyaMain")(type "KiCad")(uri "${KIPRJMOD}/../PCB-MAIN/libs/DioneyaMain.pretty")(options "")(descr "Shared manufacturer-controlled PCB-MAIN/PWR footprints"))
)
'''
    (project_dir / "sym-lib-table").write_text(sym, encoding="utf-8")
    (project_dir / "fp-lib-table").write_text(fp, encoding="utf-8")


def verify_unit_names(symbol) -> None:
    root = str(symbol.entryName)
    for child in symbol.units:
        child_name = str(child.entryName)
        if child_name != root and not child_name.startswith(f"{root}_"):
            raise RuntimeError(
                f"{root}: KiCad child symbol name {child_name!r} is inconsistent with renamed root"
            )
        verify_unit_names(child)


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
        verify_unit_names(exported)
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
    missing = (UNRESOLVED_FOOTPRINT_REFS | set(CONTROLLED_FOOTPRINTS)) - set(refs)
    if missing:
        raise RuntimeError(f"unresolved-footprint authority references missing from schematic: {sorted(missing)}")

    cleared = []
    for ref in sorted(UNRESOLVED_FOOTPRINT_REFS):
        fp = footprint_prop(refs[ref])
        if fp is None:
            raise RuntimeError(f"{ref}: Footprint property missing")
        fp.value = ""
        cleared.append(ref)
    for ref, value in CONTROLLED_FOOTPRINTS.items():
        fp = footprint_prop(refs[ref])
        if fp is None:
            raise RuntimeError(f"{ref}: Footprint property missing")
        fp.value = value

    sch.to_file(str(args.schematic), encoding="utf-8")
    reread = Schematic.from_file(str(args.schematic), encoding="utf-8")
    reread_refs = {ref_of(s): s for s in reread.schematicSymbols}
    for ref in UNRESOLVED_FOOTPRINT_REFS:
        fp = footprint_prop(reread_refs[ref])
        if fp is None or fp.value != "":
            raise RuntimeError(f"{ref}: unresolved footprint was not deterministically cleared")
    for ref, value in CONTROLLED_FOOTPRINTS.items():
        fp = footprint_prop(reread_refs[ref])
        if fp is None or fp.value != value:
            raise RuntimeError(f"{ref}: controlled footprint link was not materialized")

    export_custom_symbols(reread, args.connector_symbols, libs / "DioneyaPWR.kicad_sym")
    write_tables(project_dir)

    required = [
        args.schematic,
        libs / "DioneyaPWR.kicad_sym",
        project_dir / "sym-lib-table",
        project_dir / "fp-lib-table",
        libs / "DioneyaPWR.pretty" / "CSD18540Q5B_DNK.kicad_mod",
        libs / "DioneyaPWR.pretty" / "LMR60440_RAK0009A.kicad_mod",
        libs / "DioneyaPWR.pretty" / "TI_DBV0006A_SOT23-6.kicad_mod",
        libs / "DioneyaPWR.pretty" / "TI_DGS0010A_VSSOP10.kicad_mod",
        libs / "DioneyaPWR.pretty" / "Molex_43045-0213_MicroFit-2_Vertical.kicad_mod",
        libs / "DioneyaPWR.pretty" / "Vishay_WSK2512_4T_T1.19mm.kicad_mod",
        libs / "DioneyaPWR.pretty" / "Coilcraft_XAL7030_472.kicad_mod",
        libs / "DioneyaPWR.pretty" / "TestPoint_DFT_1.7mm_NoPaste.kicad_mod",
        project_dir.parent / "PCB-MAIN" / "libs" / "DioneyaMain.pretty" /
            "TI_DBV0005A_SOT23-5.kicad_mod",
        project_dir.parent / "PCB-MAIN" / "libs" / "DioneyaMain.pretty" /
            "Molex_43045-1202_MicroFit-12_RA.kicad_mod",
    ]
    absent = [str(p) for p in required if not p.is_file() or p.stat().st_size == 0]
    if absent:
        raise RuntimeError(f"PCB-PWR local library materialization incomplete: {absent}")

    count = len([s for s in reread.libSymbols if s.libraryNickname == "DioneyaPWR"])
    print("PCB-PWR project-local library materialization PASS")
    print("unresolved production footprints intentionally blank:", sorted(cleared))
    print("manufacturer-controlled footprints:", CONTROLLED_FOOTPRINTS)
    print("controlled DioneyaPWR symbols:", count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
