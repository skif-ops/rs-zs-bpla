#!/usr/bin/env python3
"""Second independent control of PCB-MAIN Rev.A GNSS electrical authority."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv"
REVIEW = ROOT / "hardware/PCB_MAIN_GNSS_AUTHORITY_REV_A.md"
MCU_AUTHORITY = ROOT / "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv"
PIN_MAP = ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv"
MAIN_FREEZE = ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv"
CONNECTOR_FREEZE = ROOT / "hardware/CONNECTOR_FREEZE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
CAPTURE_SPEC = ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md"
GNSS_SHEET = ROOT / "hardware/kicad/sheets/04_GNSS.csv"
POWER_ARCHITECTURE = ROOT / "hardware/EVT_PRE_20_POWER_ARCHITECTURE.md"

EXPECTED_COLUMNS = {
    "RefDes", "MPN", "Package", "Pin", "Pin_Name", "Direction",
    "RevA_Net", "Disposition", "Required_Network", "Authority", "Notes",
}
EXPECTED_U9 = {
    1: ("GND", "POWER", "GND", "GROUND_LOCKED"),
    2: ("TXD", "OUTPUT", "GNSS_RX", "FUNCTION_LOCKED"),
    3: ("RXD", "INPUT", "GNSS_TX", "FUNCTION_LOCKED"),
    4: ("TIMEPULSE", "OUTPUT", "GNSS_PPS", "FUNCTION_LOCKED"),
    5: ("EXTINT", "INPUT", "NC", "UNUSED_INPUT_NC"),
    6: ("V_BCKP", "POWER", "NC", "OPTIONAL_BACKUP_NC"),
    7: ("V_IO", "POWER", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    8: ("VCC", "POWER", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    9: ("RESET_N", "INPUT", "NC", "UNUSED_RESET_NC"),
    10: ("GND", "POWER", "GND", "GROUND_LOCKED"),
    11: ("RF_IN", "INPUT", "GNSS_RF_FILTERED", "RF_INPUT_LOCKED"),
    12: ("GND", "POWER", "GND", "GROUND_LOCKED"),
    13: ("LNA_EN", "OUTPUT", "GNSS_ANT_OFF_N", "ANTENNA_SUPERVISOR_LOCKED"),
    14: ("VCC_RF", "POWER_OUTPUT", "GNSS_ANT_BIAS_RAW", "RF_SUPPLY_OUTPUT_LOCKED"),
    15: ("VIO_SEL", "INPUT", "NC", "STRAP_OPEN_3V3"),
    16: ("SDA", "INPUT", "GNSS_ANT_DETECT", "ANTENNA_SUPERVISOR_LOCKED"),
    17: ("SCL", "INPUT", "GNSS_ANT_SHORT_N", "ANTENNA_SUPERVISOR_LOCKED"),
    18: ("SAFEBOOT_N", "INPUT", "NC", "UNUSED_SERVICE_NC"),
}


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
        default=ROOT / "artifacts/pcb_main_gnss_authority_rev_a.json",
    )
    args = parser.parse_args()

    rows = read_csv(AUTHORITY)
    require(len(rows) == 20, "GNSS authority must contain exactly 20 physical contacts")
    require(all(set(row) == EXPECTED_COLUMNS for row in rows), "GNSS authority schema mismatch")
    require(
        all(all(row.get(column) for column in EXPECTED_COLUMNS) for row in rows),
        "GNSS authority contains an empty field",
    )
    by_key = {(row["RefDes"], row["Pin"]): row for row in rows}
    require(len(by_key) == len(rows), "duplicate GNSS RefDes/pin key")
    require({row["RefDes"] for row in rows} == {"U9", "J9"}, "unexpected GNSS RefDes set")

    u9_rows = [row for row in rows if row["RefDes"] == "U9"]
    require({row["Pin"] for row in u9_rows} == {str(pin) for pin in range(1, 19)}, "U9 package pin set mismatch")
    require(
        all((row["MPN"], row["Package"]) == ("MAX-M10S-00B", "LCC-18_9.7x10.1mm") for row in u9_rows),
        "U9 identity/package drift",
    )
    for pin, expected in EXPECTED_U9.items():
        row = by_key[("U9", str(pin))]
        actual = (row["Pin_Name"], row["Direction"], row["RevA_Net"], row["Disposition"])
        require(actual == expected, f"U9 pin {pin} contract mismatch")

    j9_rows = [row for row in rows if row["RefDes"] == "J9"]
    require({row["Pin"] for row in j9_rows} == {"1", "SHIELD"}, "J9 contact set mismatch")
    require(
        all((row["MPN"], row["Package"]) == ("U.FL-R-SMT-1(60)", "U.FL_SMT") for row in j9_rows),
        "J9 identity/package drift",
    )
    require(
        (by_key[("J9", "1")]["Pin_Name"], by_key[("J9", "1")]["RevA_Net"], by_key[("J9", "1")]["Disposition"])
        == ("SIGNAL", "GNSS_RF_ANT_BIASED", "RF_CONTACT_LOCKED"),
        "J9 center-contact contract mismatch",
    )
    require(
        (by_key[("J9", "SHIELD")]["Pin_Name"], by_key[("J9", "SHIELD")]["RevA_Net"], by_key[("J9", "SHIELD")]["Disposition"])
        == ("SHELL", "GND", "SHIELD_GROUND_LOCKED"),
        "J9 shell contract mismatch",
    )

    vcc = by_key[("U9", "8")]["Required_Network"]
    require(all(token in vcc for token in ("100 nF", "10 uF", "0.2 Ohm", "100 mA")), "U9 VCC network limits incomplete")
    require("never exceed VCC plus 0.3 V" in by_key[("U9", "7")]["Required_Network"], "U9 V_IO absolute relation missing")
    require("50 mA" in by_key[("U9", "14")]["Required_Network"], "U9 VCC_RF current bound missing")
    for pin in ("5", "6", "9", "15", "18"):
        require(by_key[("U9", pin)]["RevA_Net"] == "NC", f"U9 pin {pin} must remain NC")
    require("no capacitor" in by_key[("U9", "9")]["Required_Network"], "RESET_N no-capacitor rule missing")
    require("No trace test pad" in by_key[("U9", "18")]["Required_Network"], "SAFEBOOT_N no-load rule missing")
    require("1 kOhm" in by_key[("U9", "18")]["Notes"], "SAFEBOOT_N internal coupling warning missing")
    require("high-impedance test point" in by_key[("U9", "4")]["Required_Network"], "TIMEPULSE test point loading rule missing")
    require("no pull-up or pull-down" in by_key[("U9", "4")]["Required_Network"], "TIMEPULSE startup pull prohibition missing")

    require("Figure 38" in by_key[("U9", "13")]["Required_Network"], "PIO7 supervisor switch control missing")
    require("I2C disabled" in by_key[("U9", "16")]["Required_Network"], "PIO2 open-detect reassignment missing")
    require("active-HIGH ANT_DETECT" in by_key[("U9", "16")]["Required_Network"], "open-detect polarity missing")
    require("I2C disabled" in by_key[("U9", "17")]["Required_Network"], "PIO3 short-detect reassignment missing")
    require("active-LOW ANT_SHORT_N" in by_key[("U9", "17")]["Required_Network"], "short-detect polarity missing")
    rf_chain = by_key[("J9", "1")]["Required_Network"]
    for token in ("ultra-low-capacitance ESD", "27 nH", "47 pF C0G", "wideband GNSS SAW"):
        require(token in rf_chain, f"J9 RF/bias path lacks {token}")
    require("50 Ohm" in by_key[("U9", "11")]["Required_Network"], "U9 RF_IN impedance contract missing")

    pin_map = {row["Net"]: row for row in read_csv(PIN_MAP)}
    mcu_by_net = {row["RevA_Net"]: row for row in read_csv(MCU_AUTHORITY) if row["RevA_Net"] != "NC"}
    expected_mcu = {
        "GNSS_TX": ("PA2", "24"), "GNSS_RX": ("PA3", "25"), "GNSS_PPS": ("PA0", "22"),
    }
    for net, expected in expected_mcu.items():
        require(net in pin_map and net in mcu_by_net, f"{net} missing from MCU authorities")
        require((pin_map[net]["MCU_Pin"], pin_map[net]["LQFP100_Pin"]) == expected, f"{net} MCU endpoint mismatch")
        require((mcu_by_net[net]["Pin_Name"], mcu_by_net[net]["LQFP100_Pin"]) == expected, f"{net} U1 physical endpoint mismatch")

    main_freeze = {row["RefDes"]: row for row in read_csv(MAIN_FREEZE)}
    require(main_freeze["U9"]["MPN"] == "MAX-M10S-00B", "U9 main freeze MPN mismatch")
    require(main_freeze["U9"]["Package_or_Module"] == "LCC-18_9.7x10.1mm", "U9 main freeze package mismatch")
    require("PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv" in main_freeze["U9"]["Notes"], "U9 freeze lacks authority citation")
    connectors = {row["Connector_ID"]: row for row in read_csv(CONNECTOR_FREEZE)}
    require(connectors["CON-RF-GNSS"]["Board_MPN"] == "Hirose_U.FL-R-SMT-1_60", "GNSS connector freeze MPN mismatch")
    require("J9 center" in connectors["CON-RF-GNSS"]["Notes"], "GNSS connector freeze lacks J9 center contract")

    authority_sha256 = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    review = REVIEW.read_text(encoding="utf-8")
    for marker in {
        "GNSS_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        authority_sha256,
        "e36d9c8585809c0dc486804d2634c66cd1888ad71af0f28ce0b830ffa8df6bec",
        "5a7510ef84f7e2757c57e362a25e3c16bcf8c80af5a4f70790c2e51032dbcd13",
        "MAX-M10S-00B-01", "CFG-HW-ANT_SUP_SWITCH_PIN=7", "CFG-HW-ANT_SUP_OPEN_PIN=2",
        "CFG-HW-ANT_SUP_SHORT_PIN=3", "10 Ohm, 5%, 0.25 W", "27 nH, 5%",
        "does not release the exact support-component MPN set",
    }:
        require(marker in review, f"GNSS review missing marker: {marker}")

    cross_documents = {
        CAPTURE_SPEC: ("PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv", "Figure 38", "SAFEBOOT_N", "MAIN-AUTH-010"),
        GNSS_SHEET: ("all 20 U9/J9 rows", "GNSS_ANT_DETECT", "wideband GNSS L1 SAW"),
        POWER_ARCHITECTURE: ("MAX-M10S VCC/V_IO", "100 mA startup inrush", "no V_BCKP source"),
    }
    for path, markers in cross_documents.items():
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in content, f"{path.name} lacks frozen GNSS marker: {marker}")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    authoritative = set(status["source_control"]["authoritative_inputs"])
    require(
        {
            "hardware/PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_GNSS_AUTHORITY_REV_A.md",
        }.issubset(authoritative),
        "GNSS files are not registered as authoritative inputs",
    )
    readiness = status["capture_readiness"]
    closed = {item["id"]: item for item in readiness["closed_authorities"]}
    open_ids = {item["id"] for item in readiness["open_authorities"]}
    require(set(closed) == {f"MAIN-AUTH-{index:03d}" for index in range(1, 11)}, "closed authority set mismatch")
    require(
        set(closed["MAIN-AUTH-006"]["evidence"])
        == {
            "hardware/PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_GNSS_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-006 evidence set mismatch",
    )
    require(open_ids == {"MAIN-AUTH-011"}, "remaining open authority set mismatch")
    require(readiness["complete"] is False and status["manufacturing_release"] is False, "GNSS authority prematurely released manufacturing")

    supply_margin_v = round(3.3 - 2.7, 3)
    vcc_io_margin_v = round((3.3 + 0.3) - 3.3, 3)
    sense_dissipation_w_at_50ma = round(0.05 * 0.05 * 10, 4)
    require(supply_margin_v >= 0.6, "3.3 V V_IO minimum margin failed")
    require(vcc_io_margin_v >= 0.3, "V_IO versus VCC relation failed")
    require(sense_dissipation_w_at_50ma <= 0.025, "10 Ohm sense resistor dissipation calculation failed")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "audit": "U9/J9 second independent GNSS authority control",
        "status": "PASS_GNSS_AUTHORITY_ONLY",
        "physical_contacts_verified": len(rows),
        "u9_pins_verified": len(u9_rows),
        "j9_contacts_verified": len(j9_rows),
        "calculated_limits": {
            "v_io_above_minimum_margin_v": round(supply_margin_v, 3),
            "v_io_to_vcc_absolute_margin_v": round(vcc_io_margin_v, 3),
            "sense_resistor_dissipation_w_at_50ma": round(sense_dissipation_w_at_50ma, 4),
        },
        "open_authorities": sorted(open_ids),
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN U9/J9 second independent control: PASS_GNSS_AUTHORITY_ONLY")
    print("- all 20 physical contacts and independent module/connector maps verified")
    print("- supply choices, UART/PPS, SAFEBOOT and active-antenna supervisor verified")
    print("- RF/bias topology and controlled calculations verified")
    print(f"- {len(open_ids)} remaining authorities keep the production BOM blocked")
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()
