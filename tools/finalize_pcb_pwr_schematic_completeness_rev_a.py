#!/usr/bin/env python3
"""Complete PCB-PWR Rev.A native schematic before full schematic Review A.

This stage materializes controlled elements already required by the power/net baseline
but intentionally does not freeze their production MPN/footprint where that remains an
open release item. It also replaces the generic bidirectional TVS symbol with a
unidirectional zener/TVS representation for the SMBJ18A candidate and adds explicit DFT
access points required by the EVT-PRE-20 power test plan.

No reviewed U1-U5/Q1/RSH1/J1/J2 pin/net mapping is changed.
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


def load_symbol(path: Path, entry: str, nickname: str):
    lib = SymbolLib.from_file(str(path), encoding="utf-8")
    matches = [s for s in lib.symbols if str(s.entryName) == entry]
    if len(matches) != 1:
        raise RuntimeError(f"{path}: expected one symbol {entry}, found {len(matches)}")
    symbol = copy.deepcopy(matches[0])
    symbol.libraryNickname = nickname
    return symbol


def rename_symbol_tree(symbol, old_entry: str, new_entry: str) -> None:
    """Keep KiCad unit/style child names consistent with a renamed symbol."""
    for child in symbol.units:
        child_name = str(child.entryName)
        if child_name == old_entry or child_name.startswith(f"{old_entry}_"):
            child.entryName = f"{new_entry}{child_name[len(old_entry):]}"
        rename_symbol_tree(child, old_entry, new_entry)


def ref_of(inst) -> str:
    return next((p.value for p in inst.properties if p.key == "Reference"), "")


def prop(key: str, value: str, ident: int, x: float, y: float, *, hide=False):
    return Property(key=key, value=value, id=ident,
                    position=Position(X=x, Y=y, angle=0), effects=Effects(hide=hide))


def make_instance(sch, symbol, *, reference: str, value: str, footprint: str,
                  datasheet: str, x: float, y: float, in_bom=True, on_board=True):
    inst = SchematicSymbol()
    inst.libId = symbol.libId
    inst.position = Position(X=x, Y=y, angle=0)
    inst.unit = 1
    inst.inBom = in_bom
    inst.onBoard = on_board
    inst.dnp = False
    inst.uuid = uid()
    inst.properties = [
        prop("Reference", reference, 0, x, y - 7.0),
        prop("Value", value, 1, x, y + 7.0),
        prop("Footprint", footprint, 2, x, y + 9.0, hide=True),
        prop("Datasheet", datasheet, 3, x, y + 11.0, hide=True),
    ]
    for number in sorted(selected_pins(symbol), key=lambda s: (len(s), s)):
        inst.pins[number] = uid()
    inst.instances = [SymbolProjectInstance(name="PCB-PWR", paths=[SymbolProjectPath(
        sheetInstancePath=f"/{sch.uuid}", reference=reference, unit=1)])]
    return inst


def endpoint(inst, symbol, pin_no: str):
    pin = selected_pins(symbol)[str(pin_no)]
    return Position(X=round(inst.position.X + pin.position.X, 4),
                    Y=round(inst.position.Y - pin.position.Y, 4), angle=0)


def add_label(sch, net: str, pos: Position):
    sch.labels.append(LocalLabel(text=net, position=pos, effects=Effects(), uuid=uid()))


def label_pins(sch, inst, symbol, mapping):
    for pin, net in mapping.items():
        add_label(sch, net, endpoint(inst, symbol, pin))


def remove_labels_at(sch, points: set[tuple[float, float]]):
    sch.labels = [lab for lab in sch.labels if (round(lab.position.X, 4), round(lab.position.Y, 4)) not in points]


def one_embedded(sch, nickname: str, entry: str):
    matches = [s for s in sch.libSymbols if s.libraryNickname == nickname and str(s.entryName) == entry]
    if len(matches) != 1:
        raise RuntimeError(f"embedded {nickname}:{entry} expected once, found {len(matches)}")
    return matches[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schematic", type=Path, required=True)
    ap.add_argument("--device-symbols", type=Path, default=Path("/usr/share/kicad/symbols/Device.kicad_sym"))
    ap.add_argument("--connector-symbols", type=Path, default=Path("/usr/share/kicad/symbols/Connector_Generic.kicad_sym"))
    args = ap.parse_args()

    sch = Schematic.from_file(str(args.schematic), encoding="utf-8")
    refs = {ref_of(s): s for s in sch.schematicSymbols}

    reserved = {"C9","C10","C11","C12","C13", *(f"TP{i}" for i in range(1,11))}
    clash = sorted(reserved & set(refs))
    if clash:
        raise RuntimeError(f"completeness references already exist before finalization: {clash}")

    capacitor = one_embedded(sch, "Device", "C")

    # Replace the generic bidirectional D_TVS graphic with a unidirectional TVS/Zener
    # symbol. The candidate MPN SMBJ18A is unidirectional; K is on VBAT_FUSED, A to GND.
    if "D1" not in refs:
        raise RuntimeError("D1 missing")
    old_d1 = refs["D1"]
    lib_by_id = {s.libId: s for s in sch.libSymbols}
    if old_d1.libId not in lib_by_id:
        raise RuntimeError("D1 embedded symbol missing")
    old_sym = lib_by_id[old_d1.libId]
    old_points = {(round(endpoint(old_d1, old_sym, n).X,4), round(endpoint(old_d1, old_sym, n).Y,4)) for n in selected_pins(old_sym)}
    remove_labels_at(sch, old_points)
    sch.schematicSymbols = [s for s in sch.schematicSymbols if ref_of(s) != "D1"]

    zener = load_symbol(args.device_symbols, "D_Zener", "Device")
    zpins = selected_pins(zener)
    if len(zpins) != 2:
        raise RuntimeError(f"Device:D_Zener must be 2-pin, got {sorted(zpins)}")
    by_name = {str(pin.name).strip().upper(): num for num, pin in zpins.items()}
    if "K" not in by_name or "A" not in by_name:
        raise RuntimeError(f"Device:D_Zener pin names must include K/A, got {by_name}")
    for p in zpins.values():
        p.electricalType = "passive"
    if not any(s.libraryNickname == "Device" and str(s.entryName) == "D_Zener" for s in sch.libSymbols):
        sch.libSymbols.append(zener)
    D1 = make_instance(sch, zener, reference="D1", value="SMBJ18A CANDIDATE UNIDIRECTIONAL TVS",
                       footprint="Diode_SMD:D_SMB", datasheet="Littelfuse SMBJ series", x=60.96, y=50.80)
    sch.schematicSymbols.append(D1)
    label_pins(sch, D1, zener, {by_name["K"]:"VBAT_FUSED", by_name["A"]:"GND_PWR"})

    # Passives already named in PCB_PWR_CAPTURE_NETS_REV_A.csv but absent from the
    # first native capture. Exact candidate identity and footprint are applied later
    # from PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv.
    caps = [
        ("C9",  "CIN_REV VALUE_TBD TRANSIENT_REVIEW",       "VBAT_FUSED",     73.66, 58.42),
        ("C10", "C_PROT_MIN VALUE_TBD TRANSIENT_REVIEW",    "VBAT_PROTECTED", 116.84, 58.42),
        ("C11", "CIN_3V8 >=4.7uF EFFECTIVE MPN_TBD",       "VBAT_SYS",       40.64, 88.90),
        ("C12", "CIN_3V3 >=4.7uF EFFECTIVE MPN_TBD",       "VBAT_SYS",       106.68, 88.90),
        ("C13", "VBAT_SYS_BULK VALUE_TBD",                  "VBAT_SYS",       157.48, 48.26),
    ]
    for ref, value, net, x, y in caps:
        inst = make_instance(sch, capacitor, reference=ref, value=value, footprint="",
                             datasheet="PCB-PWR Review-A passive freeze pending", x=x, y=y)
        sch.schematicSymbols.append(inst)
        label_pins(sch, inst, capacitor, {"1":net, "2":"GND_PWR"})

    # Explicit DFT access required by the PWR/I2C/Kelvin EVT plan. The controlled
    # no-paste footprint is applied later from the passive/DFT authority table.
    tp = load_symbol(args.connector_symbols, "Conn_01x01", "DioneyaPWR")
    rename_symbol_tree(tp, "Conn_01x01", "TESTPOINT")
    tp.entryName = "TESTPOINT"
    tppins = selected_pins(tp)
    if set(tppins) != {"1"}:
        raise RuntimeError("TESTPOINT source symbol is not one-pin")
    tppins["1"].name = "TEST"
    tppins["1"].electricalType = "passive"
    sch.libSymbols.append(tp)

    testpoints = [
        ("TP1",  "TP_VBAT_PROTECTED", "VBAT_PROTECTED"),
        ("TP2",  "TP_SHUNT_SRC",      "SHUNT_SOURCE_SENSE"),
        ("TP3",  "TP_SHUNT_LOAD",     "SHUNT_LOAD_SENSE"),
        ("TP4",  "TP_3V8",            "3V8_MODEM"),
        ("TP5",  "TP_PG_3V8",         "PG_3V8"),
        ("TP6",  "TP_PWR_GOOD",       "PWR_GOOD"),
        ("TP7",  "TP_1V8",            "1V8_MIC"),
        ("TP8",  "TP_FAULT",          "FAULT"),
        ("TP9",  "TP_SCL",            "I2C2_SCL"),
        ("TP10", "TP_SDA",            "I2C2_SDA"),
    ]
    for idx, (ref, value, net) in enumerate(testpoints):
        x = 218.44
        y = 30.48 + idx * 12.70
        inst = make_instance(sch, tp, reference=ref, value=value, footprint="",
                             datasheet="EVT-PRE-20 DFT pad geometry pending", x=x, y=y,
                             in_bom=False, on_board=True)
        sch.schematicSymbols.append(inst)
        label_pins(sch, inst, tp, {"1":net})

    sch.to_file(str(args.schematic), encoding="utf-8")

    # Independent round-trip verification of the additions and polarity.
    reread = Schematic.from_file(str(args.schematic), encoding="utf-8")
    refs2 = {ref_of(s): s for s in reread.schematicSymbols}
    required_refs = {"D1","C9","C10","C11","C12","C13", *(f"TP{i}" for i in range(1,11))}
    missing = sorted(required_refs - set(refs2))
    if missing:
        raise RuntimeError(f"completeness refs lost on round-trip: {missing}")

    lib_by_id2 = {s.libId: s for s in reread.libSymbols}
    labels = {}
    for lab in reread.labels:
        labels.setdefault((round(lab.position.X,4), round(lab.position.Y,4)), set()).add(str(lab.text))

    d1 = refs2["D1"]; d1sym = lib_by_id2[d1.libId]
    d1pins = selected_pins(d1sym)
    names = {str(p.name).strip().upper(): n for n,p in d1pins.items()}
    if "VBAT_FUSED" not in labels.get((round(endpoint(d1,d1sym,names["K"]).X,4), round(endpoint(d1,d1sym,names["K"]).Y,4)), set()):
        raise RuntimeError("D1 cathode is not on VBAT_FUSED")
    if "GND_PWR" not in labels.get((round(endpoint(d1,d1sym,names["A"]).X,4), round(endpoint(d1,d1sym,names["A"]).Y,4)), set()):
        raise RuntimeError("D1 anode is not on GND_PWR")

    print("PCB-PWR schematic completeness finalization PASS")
    print("added 5 missing input/protected-bus capacitors, unidirectional SMBJ18A symbol, 10 DFT testpoints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
