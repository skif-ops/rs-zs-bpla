#!/usr/bin/env python3
"""Independently audit PCB-PWR passive/DFT authority and native bindings."""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from kiutils.schematic import Schematic

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv"
BOM_GENERATOR = ROOT / "tools/generate_evt_pre_20_bom_rev_a.py"

EXPECTED_REFS = {
    *(f"C{i}" for i in range(1, 20)),
    *(f"R{i}" for i in range(1, 16)),
    "NT1", "NT2", "NT3",
    *(f"TP{i}" for i in range(1, 11)),
}
EXPECTED_DNP = {"R5", "R9", "R13", "R14", "R15"}
EXPECTED_GROUPS = {
    "PWR-C-100N": ("CGA2B3X7R1E104K050BB", "Capacitor_SMD:C_0402_1005Metric", 4),
    "PWR-C-LDO": ("CGA3E1X7R1A225K080AC", "Capacitor_SMD:C_0603_1608Metric", 2),
    "PWR-C-CIN-HF": ("CGA3E2X7R1H104K080AA", "Capacitor_SMD:C_0603_1608Metric", 1),
    "PWR-C-INPUT": ("CGA6P3X7R1H475K250AB", "Capacitor_SMD:C_1210_3225Metric", 3),
    "PWR-C-BULK": ("EEH-ZK1V101XP", "Capacitor_SMD:CP_Elec_6.3x7.7", 1),
    "PWR-COUT-3V8": ("CGA6P3X7R1E226M250AB", "Capacitor_SMD:C_1210_3225Metric", 4),
    "PWR-COUT-3V3": ("CGA6P3X7R1E226M250AB", "Capacitor_SMD:C_1210_3225Metric", 4),
    "PWR-R-100K-01": ("ERA-2AEB104X", "Resistor_SMD:R_0402_1005Metric", 1),
    "PWR-R-35K7": ("ERA-2AEB3572X", "Resistor_SMD:R_0402_1005Metric", 1),
    "PWR-R-86K6": ("ERA-2AEB8662X", "Resistor_SMD:R_0402_1005Metric", 2),
    "PWR-R-0R": ("ERJ-2GE0R00X", "Resistor_SMD:R_0402_1005Metric", 2),
    "PWR-R-0R-DNP": ("ERJ-2GE0R00X", "Resistor_SMD:R_0402_1005Metric", 2),
    "PWR-R-100K": ("ERJ-2RKF1003X", "Resistor_SMD:R_0402_1005Metric", 2),
    "PWR-R-10K": ("ERJ-2RKF1002X", "Resistor_SMD:R_0402_1005Metric", 2),
    "PWR-R-4K7-DNP": ("ERJ-2RKF4701X", "Resistor_SMD:R_0402_1005Metric", 2),
    "PWR-R-10K-DNP": ("ERJ-2RKF1002X", "Resistor_SMD:R_0402_1005Metric", 1),
    "PWR-NET-TIE": ("NET_TIE_COPPER_REV_A", "NetTie:NetTie-2_SMD_Pad0.5mm", 3),
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def read_rows() -> list[dict[str, str]]:
    with AUTHORITY.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def property_value(symbol, key: str) -> str:
    return next((item.value for item in symbol.properties if item.key == key), "")


def selected_pins(symbol, unit: int = 1) -> dict[str, object]:
    found: dict[str, object] = {}

    def visit(node, active: bool) -> None:
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


def endpoint(instance, symbol, pin_number: str) -> tuple[float, float]:
    pin = selected_pins(symbol, instance.unit or 1)[pin_number]
    return (
        round(instance.position.X + pin.position.X, 4),
        round(instance.position.Y - pin.position.Y, 4),
    )


def parse_pin_map(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for assignment in value.split(";"):
        number, net = assignment.split("=", 1)
        result[number] = net
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schematic", type=Path, required=True)
    args = parser.parse_args()

    authority = read_rows()
    refs = {row["RefDes"] for row in authority}
    require(len(authority) == 47 and refs == EXPECTED_REFS,
            f"authority physical set drift: missing={sorted(EXPECTED_REFS-refs)} extra={sorted(refs-EXPECTED_REFS)}")
    require(len(refs) == len(authority), "duplicate passive/DFT RefDes")
    require({row["RefDes"] for row in authority if row["Population"] == "DNP"} == EXPECTED_DNP,
            "PCB-PWR DNP authority set drift")
    require(all(row["Authority_Status"] and row["Primary_Source"] and row["Release_Blockers"]
                for row in authority), "authority evidence/status/blocker field is blank")

    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in authority:
        if row["BOM_Item_ID"]:
            groups[row["BOM_Item_ID"]].append(row)
    require(set(groups) == set(EXPECTED_GROUPS), "PCB-PWR BOM passive group set drift")
    for item_id, (mpn, footprint, count) in EXPECTED_GROUPS.items():
        rows = groups[item_id]
        require(len(rows) == count, f"{item_id}: expected {count} physical references")
        require({row["MPN"] for row in rows} == {mpn}, f"{item_id}: exact MPN drift")
        require({row["Footprint"] for row in rows} == {footprint}, f"{item_id}: footprint drift")

    testpoints = [row for row in authority if row["Category"] == "DFT point"]
    require(len(testpoints) == 10, "exactly ten PCB-PWR DFT points are required")
    require({row["Footprint"] for row in testpoints} ==
            {"DioneyaPWR:TestPoint_DFT_1.7mm_NoPaste"}, "DFT footprint authority drift")
    require(all(not row["BOM_Item_ID"] and row["Population"] == "PCB_FEATURE"
                for row in testpoints), "DFT points must remain non-procured PCB features")

    schematic = Schematic.from_file(str(args.schematic), encoding="utf-8")
    instances = {property_value(item, "Reference"): item for item in schematic.schematicSymbols}
    libraries = {item.libId: item for item in schematic.libSymbols}
    labels: dict[tuple[float, float], set[str]] = defaultdict(set)
    for label in schematic.labels:
        labels[(round(label.position.X, 4), round(label.position.Y, 4))].add(str(label.text))

    for row in authority:
        ref = row["RefDes"]
        require(ref in instances, f"native schematic missing authority reference {ref}")
        instance = instances[ref]
        require(property_value(instance, "Value") == f"{row['Value']} {row['MPN']}",
                f"{ref}: value/MPN binding drift")
        require(property_value(instance, "Footprint") == row["Footprint"],
                f"{ref}: footprint binding drift")
        require(property_value(instance, "Datasheet") == row["Primary_Source"],
                f"{ref}: source binding drift")
        require(bool(instance.dnp) == (row["Population"] == "DNP"),
                f"{ref}: population binding drift")
        symbol = libraries[instance.libId]
        for pin_number, net in parse_pin_map(row["Pin_Map"]).items():
            actual = labels.get(endpoint(instance, symbol, pin_number), set())
            require(actual == {net}, f"{ref}.{pin_number}: expected {net}, found {sorted(actual)}")

    generator = BOM_GENERATOR.read_text(encoding="utf-8")
    require("PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv" in generator,
            "BOM generator does not consume passive authority")
    pwr_generator_block = generator.split("# PCB-PWR passives come only", 1)[1].split(
        "    full_text =", 1
    )[0]
    for forbidden in {value[0] for value in EXPECTED_GROUPS.values()}:
        require(forbidden not in pwr_generator_block,
                f"BOM generator still embeds hidden PCB-PWR passive MPN {forbidden}")

    print("PCB-PWR passive/DFT independent authority audit PASS")
    print("47 refs; exact identity/footprint/population/net binding; BOM hidden constants absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
