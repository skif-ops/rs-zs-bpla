#!/usr/bin/env python3
"""Second independent electrical control of the EVT-PRE-20 U1 pin authority.

This verifier deliberately checks electrical invariants and project-source
agreement without importing the primary capture-authority auditor.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv"
PIN_MAP = ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv"
ADDENDUM = ROOT / "hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
HARNESS = ROOT / "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv"
IOC = ROOT / "firmware/targets/evt_pre_20/dioneya_evt_pre_20_rev_a.ioc"

SUPPLY_PINS = {
    6: ("VBAT", "3V3_DIGITAL"),
    10: ("VSS", "GND"),
    11: ("VDD", "3V3_DIGITAL"),
    19: ("VSSA", "GND"),
    20: ("VREF+", "3V3_DIGITAL"),
    21: ("VDDA", "3V3_DIGITAL"),
    26: ("VSS", "GND"),
    27: ("VDD", "3V3_DIGITAL"),
    46: ("VLXSMPS", "SMPS_SW"),
    47: ("VDDSMPS", "3V3_DIGITAL"),
    48: ("VSSSMPS", "GND"),
    49: ("VDD11", "VCORE_1V1"),
    50: ("VSS", "GND"),
    51: ("VDD", "3V3_DIGITAL"),
    73: ("VDDUSB", "3V3_DIGITAL"),
    74: ("VSS", "GND"),
    75: ("VDD", "3V3_DIGITAL"),
    98: ("VDD11", "VCORE_1V1"),
    99: ("VSS", "GND"),
    100: ("VDD", "3V3_DIGITAL"),
}
UNUSED_IO_PINS = {12, 13, 18, 23, 32, 36, 54, 55, 69, 84, 88, 89, 90, 91}
ALL_EXTERNAL_NC_PINS = UNUSED_IO_PINS | {9}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/pcb_main_mcu_pin_authority_rev_a.json",
    )
    args = parser.parse_args()

    authority_rows = read_csv(AUTHORITY)
    by_position = {int(row["LQFP100_Pin"]): row for row in authority_rows}
    require(len(authority_rows) == len(by_position) == 100, "U1 authority is not one unique row per package position")
    require(set(by_position) == set(range(1, 101)), "U1 authority does not cover package positions 1..100")

    source_rows = read_csv(PIN_MAP) + read_csv(ADDENDUM)
    source_by_position = {int(row["LQFP100_Pin"]): row for row in source_rows}
    require(len(source_rows) == len(source_by_position) == 65, "functional-source position set is not exactly 65 unique rows")
    for position, source in source_by_position.items():
        expected_net = "NC" if position == 9 else source["Net"]
        require(by_position[position]["RevA_Net"] == expected_net, f"functional-source mismatch at U1 pin {position}")

    actual_nc = {position for position, row in by_position.items() if row["RevA_Net"] == "NC"}
    require(actual_nc == ALL_EXTERNAL_NC_PINS, "external NC set drift")
    require(by_position[9]["Disposition"] == "FUNCTION_RESERVED_EXTERNAL_NC", "PC15 external-NC policy drift")
    require(
        by_position[12]["Disposition"] == by_position[13]["Disposition"] == "HSE_FORBIDDEN_NC",
        "HSE-capable pins are not explicitly forbidden and NC",
    )
    require(by_position[55]["Pin_Name"] == "PD8", "retired PD8 LoRa mapping is not explicitly controlled")

    for position, expected in SUPPLY_PINS.items():
        row = by_position[position]
        require((row["Pin_Name"], row["RevA_Net"]) == expected, f"supply invariant mismatch at U1 pin {position}")
    require(len(SUPPLY_PINS) == 20, "independent supply/reference position count drift")
    require({by_position[49]["RevA_Net"], by_position[98]["RevA_Net"]} == {"VCORE_1V1"}, "VDD11 rail mismatch")
    require(all(by_position[position]["RevA_Net"] == "GND" for position in (10, 19, 26, 48, 50, 74, 99)), "ground pin mismatch")

    require(
        (by_position[14]["Pin_Name"], by_position[14]["RevA_Net"], by_position[14]["Disposition"])
        == ("NRST", "NRST", "RESET_LOCKED"),
        "NRST authority mismatch",
    )
    require(by_position[72]["RevA_Net"] == "SWDIO" and by_position[76]["RevA_Net"] == "SWCLK", "SWD pin authority mismatch")
    swd_rows = [row for row in read_csv(HARNESS) if row["Interface"] == "SWD"]
    require(
        {row["Pin"]: row["Net"] for row in swd_rows}
        == {"1": "VTREF", "2": "SWDIO", "3": "SWCLK", "4": "NRST", "5": "GND"},
        "five-pin STM32 SWD fixture mismatch",
    )

    ioc = IOC.read_text(encoding="utf-8")
    require("PC14-OSC32_IN\\ (PC14).Mode=LSE-External-Clock-Source" in ioc, "CubeMX does not select the external LSE clock source")
    require("PC14-OSC32_IN\\ (PC14).Signal=RCC_OSC32_IN" in ioc, "CubeMX PC14 LSE input mismatch")
    require("PC15-OSC32_OUT\\ (PC15).Signal=RCC_OSC32_OUT" in ioc, "CubeMX PC15 RCC reservation mismatch")
    require("PH0-OSC_IN" not in ioc and "PH1-OSC_OUT" not in ioc, "CubeMX unexpectedly allocates HSE pins")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    closed = {item["id"] for item in status["capture_readiness"]["closed_authorities"]}
    open_ids = {item["id"] for item in status["capture_readiness"]["open_authorities"]}
    require(closed == {"MAIN-AUTH-001"}, "closed authority identity mismatch")
    require(open_ids == {f"MAIN-AUTH-{index:03d}" for index in range(2, 12)}, "remaining authority set mismatch")
    require(status["manufacturing_release"] is False, "manufacturing release asserted before remaining authorities close")

    covered = set(source_by_position) | UNUSED_IO_PINS | set(SUPPLY_PINS) | {14}
    require(covered == set(range(1, 101)), "independent package-category accounting mismatch")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "audit": "second independent U1 electrical pin-authority control",
        "status": "PASS_PIN_AUTHORITY_ONLY",
        "package_positions": len(by_position),
        "functional_source_positions": len(source_by_position),
        "external_nc_positions": len(actual_nc),
        "supply_reference_ground_positions": len(SUPPLY_PINS),
        "closed_authorities": sorted(closed),
        "open_authorities": sorted(open_ids),
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN U1 second independent electrical control: PASS_PIN_AUTHORITY_ONLY")
    print("- 100 package positions: 65 functional, 14 unused I/O, NRST and 20 supply/reference/ground")
    print("- HSE forbidden, PC15 external NC, SWD/NRST fixture and SMPS rails verified")
    print("- production BOM remains BLOCKED by 10 open PCB-MAIN authorities")
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()
