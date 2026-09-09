#!/usr/bin/env python3
"""Finalize PCB-PWR Rev.A ERC power-source semantics.

This is an ERC-modeling layer only. It does not alter any reviewed electrical net:
- physical connector power contacts are passive interconnect pins, not regulator outputs;
- VBAT_SYS and GND_PWR receive explicit KiCad PWR_FLAG symbols because their source is
  external and reaches those nets through passive/protection/current-sense elements.

Regulator and monitor power pins retain the meaningful types applied by
finalize_pcb_pwr_symbol_types_rev_a.py.
"""
from __future__ import annotations

import argparse
import copy
import uuid
from pathlib import Path

from kiutils.items.common import Effects, Position, Property
from kiutils.items.schitems import LocalLabel, SchematicSymbol, SymbolProjectInstance, SymbolProjectPath
from kiutils.schematic import Schematic
from kiutils.symbol import SymbolLib


def uid() -> str:
    return str(uuid.uuid4())


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


def controlled_by_entry(sch):
    return {str(s.entryName): s for s in sch.libSymbols if s.libraryNickname == "DioneyaPWR"}


def load_power_flag(path: Path):
    lib = SymbolLib.from_file(str(path), encoding="utf-8")
    matches = [s for s in lib.symbols if str(s.entryName) == "PWR_FLAG"]
    if len(matches) != 1:
        raise RuntimeError(f"expected one PWR_FLAG in {path}, found {len(matches)}")
    symbol = copy.deepcopy(matches[0])
    symbol.libraryNickname = "power"
    pins = selected_pins(symbol)
    if set(pins) != {"1"}:
        raise RuntimeError(f"KiCad PWR_FLAG must expose only pin 1, got {sorted(pins)}")
    # KiCad/kiutils versions do not serialize the library pin type consistently here.
    # Normalize the controlled copy explicitly; post-write round-trip verification below
    # guarantees the ERC source pin is actually power_out in our native schematic.
    pins["1"].electricalType = "power_out"
    return symbol


def prop(key: str, value: str, ident: int, x: float, y: float, *, hide=False):
    return Property(key=key, value=value, id=ident,
                    position=Position(X=x, Y=y, angle=0), effects=Effects(hide=hide))


def endpoint(inst, symbol, pin_no: str):
    pin = selected_pins(symbol)[pin_no]
    return Position(X=round(inst.position.X + pin.position.X, 4),
                    Y=round(inst.position.Y - pin.position.Y, 4), angle=0)


def make_flag(sch, symbol, reference: str, net: str, x: float, y: float):
    inst = SchematicSymbol()
    inst.libId = symbol.libId
    inst.position = Position(X=x, Y=y, angle=0)
    inst.unit = 1
    inst.inBom = False
    inst.onBoard = False
    inst.dnp = False
    inst.uuid = uid()
    inst.properties = [
        prop("Reference", reference, 0, x, y - 5.0, hide=True),
        prop("Value", "PWR_FLAG", 1, x, y + 5.0),
        prop("Footprint", "", 2, x, y + 7.0, hide=True),
        prop("Datasheet", "~", 3, x, y + 9.0, hide=True),
    ]
    inst.pins["1"] = uid()
    inst.instances = [SymbolProjectInstance(name="PCB-PWR", paths=[SymbolProjectPath(
        sheetInstancePath=f"/{sch.uuid}", reference=reference, unit=1)])]
    sch.schematicSymbols.append(inst)
    sch.labels.append(LocalLabel(text=net, position=endpoint(inst, symbol, "1"), effects=Effects(), uuid=uid()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schematic", type=Path, required=True)
    ap.add_argument("--power-symbols", type=Path, default=Path("/usr/share/kicad/symbols/power.kicad_sym"))
    args = ap.parse_args()

    sch = Schematic.from_file(str(args.schematic), encoding="utf-8")
    controlled = controlled_by_entry(sch)
    for needed in ("Conn_01x02", "Conn_01x12"):
        if needed not in controlled:
            raise RuntimeError(f"controlled symbol {needed} missing")

    # External harness connectors are interconnect, not internal power generators.
    j1pins = selected_pins(controlled["Conn_01x02"])
    for n in ("1", "2"):
        j1pins[n].electricalType = "passive"
    j2pins = selected_pins(controlled["Conn_01x12"])
    for n in ("1", "2", "3", "4", "5", "6"):
        j2pins[n].electricalType = "passive"

    refs = {next((p.value for p in s.properties if p.key == "Reference"), ""): s for s in sch.schematicSymbols}
    if "#FLG01" in refs or "#FLG02" in refs:
        raise RuntimeError("PCB-PWR ERC flags already exist before finalization")

    flag = load_power_flag(args.power_symbols)
    sch.libSymbols.append(flag)
    make_flag(sch, flag, "#FLG01", "VBAT_SYS", 22.86, 73.66)
    make_flag(sch, flag, "#FLG02", "GND_PWR", 35.56, 73.66)

    sch.to_file(str(args.schematic), encoding="utf-8")
    reread = Schematic.from_file(str(args.schematic), encoding="utf-8")
    ctl = controlled_by_entry(reread)
    if any(str(selected_pins(ctl["Conn_01x02"])[n].electricalType) != "passive" for n in ("1", "2")):
        raise RuntimeError("J1 external supply pins are not passive after round-trip")
    if any(str(selected_pins(ctl["Conn_01x12"])[n].electricalType) != "passive" for n in ("1","2","3","4","5","6")):
        raise RuntimeError("J2 power/return connector pins are not passive after round-trip")

    refs2 = {next((p.value for p in s.properties if p.key == "Reference"), ""): s for s in reread.schematicSymbols}
    if not {"#FLG01", "#FLG02"}.issubset(refs2):
        raise RuntimeError("PWR_FLAG instances lost on round-trip")
    flag_syms = [s for s in reread.libSymbols if s.libraryNickname == "power" and str(s.entryName) == "PWR_FLAG"]
    if len(flag_syms) != 1 or str(selected_pins(flag_syms[0])["1"].electricalType) != "power_out":
        raise RuntimeError("PWR_FLAG library symbol invalid after round-trip")

    print("PCB-PWR ERC power-source model finalization PASS")
    print("J1/J2 physical power contacts passive; PWR_FLAG on VBAT_SYS and GND_PWR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
