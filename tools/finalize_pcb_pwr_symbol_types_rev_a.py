#!/usr/bin/env python3
"""Apply Review-A electrical pin types to the controlled PCB-PWR schematic symbols.

The native generator uses generic connector bodies for deterministic pin numbering and
geometry. This stage converts their default passive pins into meaningful KiCad ERC types
without changing any pin number, pin name or net. It then round-trips the schematic and
verifies the exact type map before KiCad ERC is allowed to run.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from kiutils.schematic import Schematic


def selected_pins(symbol, unit: int = 1):
    found = {}
    def visit(node, active: bool):
        node_active = active
        if node is not symbol:
            node_active = (node.unitId in (None, 0, unit)) and (node.styleId in (None, 1))
        if node_active:
            for pin in node.pins:
                found[str(pin.number)] = pin
        for child in node.units:
            visit(child, node_active)
    visit(symbol, True)
    return found


EXPECTED = {
    "Conn_01x02": {
        "1": "power_in", "2": "power_in",
    },
    "Conn_01x12": {
        "1": "power_out", "2": "power_out", "3": "power_out", "4": "power_out",
        "5": "power_out", "6": "power_out", "7": "open_collector", "8": "open_collector",
        "9": "input", "10": "input", "11": "bidirectional", "12": "bidirectional",
    },
    "Conn_01x06": { # LM74700-Q1
        "1": "output", "2": "power_in", "3": "input", "4": "input", "5": "output", "6": "input",
    },
    "Conn_01x08": { # CSD18540Q5B
        "1": "passive", "2": "passive", "3": "passive", "4": "input",
        "5": "passive", "6": "passive", "7": "passive", "8": "passive",
    },
    "Conn_01x10": { # INA226
        "1": "input", "2": "input", "3": "open_collector", "4": "bidirectional", "5": "input",
        "6": "power_in", "7": "power_in", "8": "input", "9": "input", "10": "input",
    },
    "Conn_01x09": { # LMR60440, shared by U3/U4
        "1": "power_in", "2": "power_in", "3": "power_out", "4": "output", "5": "open_collector",
        "6": "input", "7": "input", "8": "input", "9": "input",
    },
    "Conn_01x05": { # TPS7A2018
        "1": "power_in", "2": "power_in", "3": "input", "4": "no_connect", "5": "power_out",
    },
    "Conn_01x04": { # 4-terminal Kelvin shunt
        "1": "passive", "2": "passive", "3": "passive", "4": "passive",
    },
}


def controlled(sch):
    result = {}
    for symbol in sch.libSymbols:
        if symbol.libraryNickname != "DioneyaPWR":
            continue
        name = str(symbol.entryName)
        if name in result:
            raise RuntimeError(f"duplicate controlled symbol entry {name}")
        result[name] = symbol
    return result


def verify(sch) -> None:
    symbols = controlled(sch)
    if set(symbols) != set(EXPECTED):
        raise RuntimeError(f"controlled symbol set mismatch: {sorted(symbols)} != {sorted(EXPECTED)}")
    for name, expected in EXPECTED.items():
        pins = selected_pins(symbols[name])
        if set(pins) != set(expected):
            raise RuntimeError(f"{name}: pin set mismatch")
        actual = {pin: str(pins[pin].electricalType) for pin in expected}
        if actual != expected:
            raise RuntimeError(f"{name}: electrical type mismatch {actual} != {expected}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schematic", type=Path, required=True)
    args = ap.parse_args()

    sch = Schematic.from_file(str(args.schematic), encoding="utf-8")
    symbols = controlled(sch)
    if set(symbols) != set(EXPECTED):
        raise RuntimeError(f"controlled symbol set mismatch: {sorted(symbols)} != {sorted(EXPECTED)}")

    for name, expected in EXPECTED.items():
        pins = selected_pins(symbols[name])
        for number, electrical_type in expected.items():
            if number not in pins:
                raise RuntimeError(f"{name}: missing pin {number}")
            pins[number].electricalType = electrical_type

    sch.to_file(str(args.schematic), encoding="utf-8")
    reread = Schematic.from_file(str(args.schematic), encoding="utf-8")
    verify(reread)

    counts = {}
    for symbol in controlled(reread).values():
        for pin in selected_pins(symbol).values():
            t = str(pin.electricalType)
            counts[t] = counts.get(t, 0) + 1
    print("PCB-PWR Review-A electrical symbol-type finalization PASS")
    print("electrical pin-type counts:", dict(sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
