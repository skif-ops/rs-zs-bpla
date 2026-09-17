#!/usr/bin/env python3
"""Bind PCB-PWR passives and DFT points to the controlled Rev.A authority."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from kiutils.schematic import Schematic

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv"


def rows() -> list[dict[str, str]]:
    with AUTHORITY.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def property_of(symbol, key: str):
    return next((item for item in symbol.properties if item.key == key), None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schematic", type=Path, required=True)
    args = parser.parse_args()

    authority = rows()
    if len(authority) != 47:
        raise RuntimeError(f"PCB-PWR passive authority must contain 47 physical rows, got {len(authority)}")
    by_ref = {row["RefDes"]: row for row in authority}
    if len(by_ref) != len(authority) or "" in by_ref:
        raise RuntimeError("PCB-PWR passive authority has duplicate or blank RefDes")

    schematic = Schematic.from_file(str(args.schematic), encoding="utf-8")
    symbols = {
        property_of(symbol, "Reference").value: symbol
        for symbol in schematic.schematicSymbols
        if property_of(symbol, "Reference") is not None
    }
    missing = sorted(set(by_ref) - set(symbols))
    if missing:
        raise RuntimeError(f"PCB-PWR passive authority references absent from schematic: {missing}")

    for ref, row in by_ref.items():
        symbol = symbols[ref]
        value = property_of(symbol, "Value")
        footprint = property_of(symbol, "Footprint")
        datasheet = property_of(symbol, "Datasheet")
        if value is None or footprint is None or datasheet is None:
            raise RuntimeError(f"{ref}: required schematic property missing")
        value.value = f"{row['Value']} {row['MPN']}"
        footprint.value = row["Footprint"]
        datasheet.value = row["Primary_Source"]
        expected_dnp = row["Population"] == "DNP"
        if bool(symbol.dnp) != expected_dnp:
            raise RuntimeError(
                f"{ref}: schematic DNP={bool(symbol.dnp)} differs from authority {row['Population']}"
            )

    schematic.to_file(str(args.schematic), encoding="utf-8")

    reread = Schematic.from_file(str(args.schematic), encoding="utf-8")
    reread_symbols = {
        property_of(symbol, "Reference").value: symbol
        for symbol in reread.schematicSymbols
        if property_of(symbol, "Reference") is not None
    }
    for ref, row in by_ref.items():
        symbol = reread_symbols[ref]
        if property_of(symbol, "Value").value != f"{row['Value']} {row['MPN']}":
            raise RuntimeError(f"{ref}: controlled value/MPN binding did not round-trip")
        if property_of(symbol, "Footprint").value != row["Footprint"]:
            raise RuntimeError(f"{ref}: controlled footprint binding did not round-trip")
        if property_of(symbol, "Datasheet").value != row["Primary_Source"]:
            raise RuntimeError(f"{ref}: controlled source binding did not round-trip")

    print("PCB-PWR passive/DFT authority binding PASS")
    print("47 physical references carry controlled value, MPN, footprint and source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
