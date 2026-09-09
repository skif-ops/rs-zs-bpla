#!/usr/bin/env python3
"""Materialize project-local symbol libraries and links for PCB-MIC Rev.A.

The external Dioneya symbol library is rebuilt from the already materialized schematic
library definitions, not from the raw reference CAD. This is required because the
schematic generator intentionally corrects electrical pin types for ERC. A second
structural comparison verifies that the exported library retains the same controlled
pin types before KiCad CLI is allowed to run.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

from kiutils.schematic import Schematic
from kiutils.symbol import SymbolLib


CUSTOM_ENTRIES = {"MMICT5838-00-012", "5040500691"}


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


def pin_signature(symbol) -> list[tuple[str, str, str, float, float]]:
    """Return a stable recursive pin signature without importing generator helpers."""
    result: list[tuple[str, str, str, float, float]] = []

    def visit(node) -> None:
        for pin in node.pins:
            result.append((
                str(pin.number),
                str(pin.name),
                str(pin.electricalType),
                float(pin.position.X),
                float(pin.position.Y),
            ))
        for child in node.units:
            visit(child)

    visit(symbol)
    return sorted(result)


def reference_entry_names(t5838_path: Path, molex_path: Path) -> set[str]:
    """Use the independent reference files only to prove expected source identities exist."""
    names: set[str] = set()
    for path in (t5838_path, molex_path):
        lib = SymbolLib.from_file(str(path), encoding="utf-8")
        names.update(str(s.entryName) for s in lib.symbols)
    return names


def materialize_custom_symbols_from_schematic(
    schematic_path: Path,
    t5838_path: Path,
    molex_path: Path,
    output: Path,
) -> None:
    source_names = reference_entry_names(t5838_path, molex_path)
    if not CUSTOM_ENTRIES.issubset(source_names):
        raise RuntimeError(
            f"reference CAD identities incomplete: expected {sorted(CUSTOM_ENTRIES)}, got {sorted(source_names)}"
        )

    sch = Schematic.from_file(str(schematic_path), encoding="utf-8")
    embedded = {
        str(s.entryName): s
        for s in sch.libSymbols
        if str(s.entryName) in CUSTOM_ENTRIES and s.libraryNickname == "Dioneya"
    }
    if set(embedded) != CUSTOM_ENTRIES:
        raise RuntimeError(f"controlled embedded symbols incomplete: {sorted(embedded)}")

    # Preserve a known-good symbol-library header/version from the T5838 reference,
    # but replace its symbol payload entirely with the controlled embedded definitions.
    combined = SymbolLib.from_file(str(t5838_path), encoding="utf-8")
    combined.symbols = []
    for name in sorted(CUSTOM_ENTRIES):
        exported = copy.deepcopy(embedded[name])
        # Library files contain entry names; the nickname is supplied by sym-lib-table.
        exported.libraryNickname = None
        combined.symbols.append(exported)
    combined.to_file(str(output), encoding="utf-8")

    # Independent round-trip comparison. The library must reproduce every controlled
    # pin number, name, electrical type and position from the schematic definition.
    reread = SymbolLib.from_file(str(output), encoding="utf-8")
    external = {str(s.entryName): s for s in reread.symbols if str(s.entryName) in CUSTOM_ENTRIES}
    if set(external) != CUSTOM_ENTRIES:
        raise RuntimeError(f"round-trip Dioneya library incomplete: {sorted(external)}")
    for name in sorted(CUSTOM_ENTRIES):
        embedded_sig = pin_signature(embedded[name])
        external_sig = pin_signature(external[name])
        if external_sig != embedded_sig:
            raise RuntimeError(
                f"Dioneya symbol mismatch before KiCad ERC for {name}: "
                f"embedded={embedded_sig} external={external_sig}"
            )


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

    link_schematic_footprints(args.schematic)
    materialize_custom_symbols_from_schematic(
        args.schematic,
        args.t5838_symbol,
        args.molex_symbol,
        libs / "Dioneya.kicad_sym",
    )
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
    print("controlled entries", sorted(CUSTOM_ENTRIES))
    for p in required:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
