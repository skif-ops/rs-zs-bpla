#!/usr/bin/env python3
"""Independent completeness audit for the final PCB-PWR Rev.A native schematic."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from kiutils.schematic import Schematic

ROOT = Path(__file__).resolve().parents[1]
PASSIVE_AUTHORITY = ROOT / "hardware/PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv"

CAP_NETS = {
    "C9":  ("VBAT_FUSED", "GND_PWR", "CIN_REV"),
    "C10": ("VBAT_PROTECTED", "GND_PWR", "C_PROT_MIN"),
    "C11": ("VBAT_SYS", "GND_PWR", "CIN_3V8"),
    "C12": ("VBAT_SYS", "GND_PWR", "CIN_3V3"),
    "C13": ("VBAT_SYS", "GND_PWR", "VBAT_SYS_BULK"),
}
TP_NETS = {
    "TP1": "VBAT_PROTECTED",
    "TP2": "SHUNT_SOURCE_SENSE",
    "TP3": "SHUNT_LOAD_SENSE",
    "TP4": "3V8_MODEM",
    "TP5": "PG_3V8",
    "TP6": "PWR_GOOD",
    "TP7": "1V8_MIC",
    "TP8": "FAULT",
    "TP9": "I2C2_SCL",
    "TP10": "I2C2_SDA",
}


def ref_of(inst):
    return next((p.value for p in inst.properties if p.key == "Reference"), "")


def value_of(inst):
    return next((p.value for p in inst.properties if p.key == "Value"), "")


def footprint_of(inst):
    return next((p.value for p in inst.properties if p.key == "Footprint"), None)


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


def endpoint(inst, symbol, pin_no: str):
    pin = selected_pins(symbol)[str(pin_no)]
    return (round(inst.position.X + pin.position.X, 4), round(inst.position.Y - pin.position.Y, 4))


def labels_by_point(sch):
    out = {}
    for lab in sch.labels:
        key = (round(lab.position.X,4), round(lab.position.Y,4))
        out.setdefault(key, set()).add(str(lab.text))
    return out


def pin_net(labels, inst, symbol, pin_no: str):
    nets = labels.get(endpoint(inst, symbol, pin_no), set())
    if len(nets) != 1:
        raise RuntimeError(f"{ref_of(inst)} pin {pin_no}: expected exactly one local net label, got {sorted(nets)}")
    return next(iter(nets))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schematic", type=Path, required=True)
    args = ap.parse_args()

    sch = Schematic.from_file(str(args.schematic), encoding="utf-8")
    refs = {ref_of(s): s for s in sch.schematicSymbols}
    libs = {s.libId: s for s in sch.libSymbols}
    labels = labels_by_point(sch)

    required = {"D1", *CAP_NETS, *TP_NETS, "#FLG01", "#FLG02", "#FLG03"}
    missing = sorted(required - set(refs))
    if missing:
        raise RuntimeError(f"PCB-PWR completeness refs missing: {missing}")

    # Candidate is SMBJ18A (unidirectional): cathode to positive protected input side,
    # anode to common ground. A bidirectional D_TVS symbol is forbidden for this MPN.
    d1 = refs["D1"]
    d1sym = libs[d1.libId]
    if str(d1sym.entryName) != "D_Zener":
        raise RuntimeError(f"D1 must use Device:D_Zener/unidirectional representation, got {d1sym.entryName}")
    if "SMBJ18A" not in value_of(d1) or "UNIDIRECTIONAL" not in value_of(d1):
        raise RuntimeError(f"D1 value does not identify unidirectional SMBJ18A candidate: {value_of(d1)}")
    dpins = selected_pins(d1sym)
    by_name = {str(p.name).strip().upper(): n for n,p in dpins.items()}
    if not {"K","A"}.issubset(by_name):
        raise RuntimeError(f"D1 zener pin naming invalid: {by_name}")
    if pin_net(labels, d1, d1sym, by_name["K"]) != "VBAT_FUSED":
        raise RuntimeError("D1 cathode must connect to VBAT_FUSED")
    if pin_net(labels, d1, d1sym, by_name["A"]) != "GND_PWR":
        raise RuntimeError("D1 anode must connect to GND_PWR")

    with PASSIVE_AUTHORITY.open(encoding="utf-8-sig", newline="") as source:
        passive_authority = {row["RefDes"]: row for row in csv.DictReader(source)}

    # Missing passives from the first capture must now be explicit and bound to the
    # separately controlled candidate authority. Release blockers stay open there.
    for ref, (net1, net2, semantic) in CAP_NETS.items():
        inst = refs[ref]
        sym = libs[inst.libId]
        authority = passive_authority[ref]
        if value_of(inst) != f"{authority['Value']} {authority['MPN']}":
            raise RuntimeError(f"{ref} does not identify {semantic}: {value_of(inst)}")
        if footprint_of(inst) != authority["Footprint"]:
            raise RuntimeError(f"{ref} footprint differs from passive authority")
        if pin_net(labels, inst, sym, "1") != net1 or pin_net(labels, inst, sym, "2") != net2:
            raise RuntimeError(f"{ref} net mapping mismatch; expected {net1}/GND_PWR")

    # DFT access uses one controlled no-paste probe target. Fixture access, wear and
    # final side assignment remain layout/Review-B controls.
    for ref, net in TP_NETS.items():
        inst = refs[ref]
        sym = libs[inst.libId]
        authority = passive_authority[ref]
        if str(sym.entryName) != "TESTPOINT":
            raise RuntimeError(f"{ref}: not using controlled TESTPOINT symbol")
        if footprint_of(inst) != "DioneyaPWR:TestPoint_DFT_1.7mm_NoPaste":
            raise RuntimeError(f"{ref}: testpoint footprint authority drift")
        if value_of(inst) != f"{authority['Value']} {authority['MPN']}":
            raise RuntimeError(f"{ref}: testpoint identity authority drift")
        if pin_net(labels, inst, sym, "1") != net:
            raise RuntimeError(f"{ref}: expected {net}, got {pin_net(labels, inst, sym, '1')}")

    # ERC source flags are schematic-only and must never enter BOM/board placement.
    for ref, net in {
        "#FLG01":"VBAT_SYS",
        "#FLG02":"GND_PWR",
        "#FLG03":"3V3_DIGITAL",
    }.items():
        inst = refs[ref]
        sym = libs[inst.libId]
        if str(sym.entryName) != "ERC_SOURCE_FLAG":
            raise RuntimeError(f"{ref}: wrong ERC source symbol")
        pins = selected_pins(sym)
        if str(pins["1"].electricalType) != "power_out":
            raise RuntimeError(f"{ref}: ERC source pin is not power_out")
        if pin_net(labels, inst, sym, "1") != net:
            raise RuntimeError(f"{ref}: expected on {net}")
        if inst.inBom or inst.onBoard:
            raise RuntimeError(f"{ref}: ERC source must be schematic-only")

    print("PCB-PWR Rev.A independent native completeness audit PASS")
    print("unidirectional TVS, 5 controlled passives, 10 controlled DFT points and ERC-source semantics verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
