#!/usr/bin/env python3
"""Verify the complete MAIN-AUTH-010 passive/support capture authority."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv"
REVIEW_PATH = ROOT / "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.md"
STATUS_PATH = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
CAPTURE_SPEC_PATH = ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md"

FIELDS = [
    "RefDes", "Category", "Manufacturer", "MPN", "Package", "Value",
    "Population", "Temperature_C", "Logical_Net", "Pin_Map",
    "Electrical_Path", "Disposition", "Authority", "Notes",
]

EXPECTED_REFDES = (
    {f"C{i}" for i in range(1, 81)}
    | {f"R{i}" for i in range(1, 104)}
    | {"L1", "L2", "FB1", "FL1", "U5", "U6", "Q4", "X1"}
    | {f"U{i}" for i in range(19, 28)}
    | {f"D{i}" for i in range(1, 12)}
)

EXPECTED_DNP = {
    "C16", "C17", "C54", "C55", "C56", "C57", "C58", "C59",
    "C69", "C70", "C79", "C80", "R4", "R6", "R98",
}

EXPECTED_CATEGORY_COUNTS = {
    "Capacitor": 80,
    "Resistor": 103,
    "Inductor": 2,
    "Ferrite_Bead": 1,
    "SAW_Filter": 1,
    "Operational_Amplifier": 1,
    "Open_Drain_Buffer": 1,
    "Dual_MOSFET": 1,
    "ESD_Array": 7,
    "USB_ESD_Array": 2,
    "ESD_Diode": 6,
    "Supply_TVS": 2,
    "RF_ESD": 3,
    "TCXO": 1,
}

EXPECTED_CRITICAL = {
    "L1": ("LQH32PN2R2NN0L", "1=SMPS_SW;2=VCORE_1V1"),
    "L2": ("LQW15AN27NJ00D", "1=GNSS_ANT_SHORT_N;2=GNSS_RF_ANT_BIASED"),
    "FB1": ("BLM31KN601SN1L", "1=3V8_MODEM;2=3V8_MODEM_BB"),
    "FL1": (
        "ABSES5AF-L100KM",
        "C=GNSS_RF_DC_BLOCK;A=GNSS_RF_FILTERED;B=GND;D=GND;E=GND",
    ),
    "U5": (
        "LT6000IDCB#TRMPBF",
        "1=GNSS_ANT_DIV;2=GNSS_ANT_SHORT_N;3=GNSS_ANT_BIAS_RAW;"
        "4=GNSS_ANT_BIAS_RAW;5=GND;6=GNSS_ANT_DETECT;EP=GND",
    ),
    "U6": (
        "SN74LVC1G07DBVR",
        "1=NC;2=BLE_EN;3=GND;4=NRF_RESET_N;5=3V3_DIGITAL",
    ),
    "Q4": (
        "Si1016X-T1-GE3",
        "1=GND;2=GNSS_ANT_OFF_N;3=GNSS_ANT_SWITCHED;4=GNSS_ANT_BIAS_RAW;"
        "5=GNSS_ANT_GATE;6=GNSS_ANT_GATE",
    ),
    "U25": ("TPD2EUSB30DRTR", "1=USB_DP_CONN;2=USB_DM_CONN;3=GND"),
    "U26": (
        "TPD2EUSB30DRTR",
        "1=CELL_USB_DP_TP;2=CELL_USB_DM_TP;3=GND_MODEM",
    ),
    "D1": ("PESD5V0S1UL", "1=3V8_MODEM_BB;2=GND_MODEM"),
    "D2": ("PESD5V0S1UL", "1=3V8_MODEM_RF;2=GND_MODEM"),
    "D3": ("PESD5V0C1BSF", "1=CELL_RF_ANT;2=GND_MODEM"),
    "D4": ("TPD1E05U06DYAR", "1=GNSS_RF_ANT_BIASED;2=GND"),
    "D5": ("PESD5V0C1BSF", "1=LORA_RF_ANT;2=GND"),
    "X1": (
        "SiT1552AI-JE-DCC-32.768D",
        "1=GND;2=LSE_IN;3=3V3_DIGITAL;4=GND",
    ),
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def read_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == FIELDS, "passive/support authority header mismatch")
        return list(reader)


def parse_pin_map(refdes: str, value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for assignment in value.split(";"):
        require(assignment.count("=") == 1, f"{refdes}: malformed physical pin assignment")
        pin, net = assignment.split("=", 1)
        require(pin and net, f"{refdes}: blank physical pin or net")
        require(pin not in result, f"{refdes}: duplicate physical pin {pin}")
        result[pin] = net
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/pcb_main_passive_support_authority_rev_a.json",
    )
    args = parser.parse_args()

    rows = read_rows()
    require(len(rows) == 211, "authority must contain exactly 211 physical components")
    require(all(all(row[field].strip() for field in FIELDS) for row in rows), "blank authority field")

    by_ref = {row["RefDes"]: row for row in rows}
    require(len(by_ref) == len(rows), "duplicate RefDes in authority")
    require(set(by_ref) == EXPECTED_REFDES, "complete RefDes set mismatch")
    require(Counter(row["Category"] for row in rows) == EXPECTED_CATEGORY_COUNTS,
            "component category count mismatch")
    require({row["RefDes"] for row in rows if row["Population"] == "DNP"} == EXPECTED_DNP,
            "DNP population set mismatch")
    require(Counter(row["Population"] for row in rows) == {"FITTED": 196, "DNP": 15},
            "population count mismatch")

    for row in rows:
        parse_pin_map(row["RefDes"], row["Pin_Map"])
        if row["Population"] == "FITTED":
            require(row["Disposition"].startswith("LOCKED_FITTED"),
                    f"{row['RefDes']}: fitted disposition mismatch")
        else:
            require(row["Disposition"] == "LOCKED_DNP", f"{row['RefDes']}: DNP disposition mismatch")

    for refdes, (mpn, pin_map) in EXPECTED_CRITICAL.items():
        require(by_ref[refdes]["MPN"] == mpn, f"{refdes}: exact MPN mismatch")
        require(by_ref[refdes]["Pin_Map"] == pin_map, f"{refdes}: physical pin map mismatch")

    for refdes in ("U19", "U20", "U21", "U22", "U23", "U24", "U27"):
        require(by_ref[refdes]["MPN"] == "TPD4E05U06DQAR", f"{refdes}: ESD array MPN mismatch")
        require(set(parse_pin_map(refdes, by_ref[refdes]["Pin_Map"])) ==
                {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10"},
                f"{refdes}: incomplete ten-pin ESD map")

    require(by_ref["C13"]["Value"] == "10 uF 10 V X5R", "VDDSMPS capacitor mismatch")
    require("ESR below 10 mOhm at 3 MHz" in by_ref["C13"]["Notes"],
            "VDDSMPS ESR verification missing")
    require(by_ref["R3"]["Population"] == "FITTED" and by_ref["R5"]["Population"] == "FITTED",
            "Rev.A 00 strap pull-downs must be fitted")
    require(by_ref["R4"]["Population"] == "DNP" and by_ref["R6"]["Population"] == "DNP",
            "Rev.A alternate strap pull-ups must be DNP")
    require(by_ref["R103"]["Pin_Map"] == "1=FAULT;2=PWR_FAULT", "fault net bridge mismatch")
    require("800 Ohm from 700 to 960 MHz" in by_ref["FB1"]["Notes"],
            "cellular ferrite Review A requirement missing")
    require("RF node carries DC antenna bias" in by_ref["D4"]["Notes"],
            "GNSS biased-RF protection rationale missing")
    require("No external bypass capacitor" in by_ref["X1"]["Notes"],
            "SiT1552 no-external-bypass decision missing")

    digest = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
    review = REVIEW_PATH.read_text(encoding="utf-8")
    require(f"Authority CSV SHA-256: `{digest}`" in review, "authority SHA marker mismatch")
    for marker in (
        "211 unique physical components", "196 fitted and 15 DNP", "Figure 38",
        "LT6000IDCB#TRMPBF", "Si1016X-T1-GE3", "ABSES5AF-L100KM",
        "MAIN-AUTH-011", "NOT RUN", "production BOM remain blocked",
    ):
        require(marker in review, f"authority review marker missing: {marker}")

    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    closed = {item["id"] for item in status["capture_readiness"]["closed_authorities"]}
    opened = {item["id"] for item in status["capture_readiness"]["open_authorities"]}
    require(closed == {f"MAIN-AUTH-{i:03d}" for i in range(1, 12)},
            "closed authority set mismatch")
    require(opened == set() and status["capture_readiness"]["complete"] is True,
            "capture authority completion mismatch")
    inputs = set(status["source_control"]["authoritative_inputs"])
    require("hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv" in inputs,
            "machine authority missing from status inputs")
    require("hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.md" in inputs,
            "review authority missing from status inputs")
    require(status["native_schematic"]["status"] == "PRESENT_REVIEW_PENDING",
            "native schematic state mismatch")
    require(status["review_a"]["status"] ==
            "NATIVE_SOURCE_AND_KICAD_ERC_PASS_HUMAN_REVIEW_PENDING",
            "Review A state mismatch")

    capture_spec = CAPTURE_SPEC_PATH.read_text(encoding="utf-8")
    for marker in (
        "PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv", "MAIN-AUTH-010",
        "211", "MAIN-AUTH-011", "NOT FOR MANUFACTURE",
    ):
        require(marker in capture_spec, f"capture spec marker missing: {marker}")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "audit": "passive/support second independent control",
        "status": "PASS_PASSIVE_SUPPORT_AUTHORITY_ONLY",
        "components_verified": len(rows),
        "fitted_components": sum(row["Population"] == "FITTED" for row in rows),
        "dnp_components": sum(row["Population"] == "DNP" for row in rows),
        "category_counts": dict(sorted(Counter(row["Category"] for row in rows).items())),
        "authority_sha256": digest,
        "open_authorities": sorted(opened),
        "native_schematic": "PRESENT_REVIEW_PENDING",
        "physical_tests": "NOT_RUN",
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(
        "PCB-MAIN MAIN-AUTH-010 passive/support verification: PASS "
        "(211 unique components; 196 fitted; 15 DNP; physical pins complete; "
        "Reviews A/B remain blocking)"
    )
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()
