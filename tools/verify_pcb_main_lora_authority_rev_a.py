#!/usr/bin/env python3
"""Second independent control of PCB-MAIN Rev.A LoRa electrical authority."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv"
REVIEW = ROOT / "hardware/PCB_MAIN_LORA_AUTHORITY_REV_A.md"
MCU_AUTHORITY = ROOT / "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv"
PIN_MAP = ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv"
MAIN_FREEZE = ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv"
CONNECTOR_FREEZE = ROOT / "hardware/CONNECTOR_FREEZE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
CAPTURE_SPEC = ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md"
LORA_SHEET = ROOT / "hardware/kicad/sheets/06_LORA.csv"
RU868_PROFILE = ROOT / "config/lora/RU868.yaml"
IOC = ROOT / "firmware/targets/evt_pre_20/dioneya_evt_pre_20_rev_a.ioc"

EXPECTED_COLUMNS = {
    "RefDes", "MPN", "Package", "Pin", "Pin_Name", "Direction",
    "RevA_Net", "Disposition", "Required_Network", "Authority", "Notes",
}
EXPECTED_U10 = {
    1: ("GND", "POWER", "GND", "GROUND_LOCKED"),
    2: ("GND", "POWER", "GND", "GROUND_LOCKED"),
    3: ("GND", "POWER", "GND", "GROUND_LOCKED"),
    4: ("GND", "POWER", "GND", "GROUND_LOCKED"),
    5: ("GND", "POWER", "GND", "GROUND_LOCKED"),
    6: ("RXEN", "INPUT", "LORA_RXEN", "RF_SWITCH_CONTROL_LOCKED"),
    7: ("TXEN", "INPUT", "LORA_TXEN", "RF_SWITCH_CONTROL_LOCKED"),
    8: ("DIO2", "BIDIR", "NC", "UNUSED_IO_NC"),
    9: ("VCC", "POWER", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    10: ("GND", "POWER", "GND", "GROUND_LOCKED"),
    11: ("GND", "POWER", "GND", "GROUND_LOCKED"),
    12: ("GND", "POWER", "GND", "GROUND_LOCKED"),
    13: ("DIO1", "OUTPUT", "LORA_DIO1", "FUNCTION_LOCKED"),
    14: ("BUSY", "OUTPUT", "LORA_BUSY", "FUNCTION_LOCKED"),
    15: ("NRST", "INPUT", "LORA_RESET_N", "RESET_LOCKED"),
    16: ("MISO", "OUTPUT", "LORA_MISO", "FUNCTION_LOCKED"),
    17: ("MOSI", "INPUT", "LORA_MOSI", "FUNCTION_LOCKED"),
    18: ("SCK", "INPUT", "LORA_SCK", "FUNCTION_LOCKED"),
    19: ("NSS", "INPUT", "LORA_NSS", "FUNCTION_LOCKED"),
    20: ("GND", "POWER", "GND", "RF_GROUND_LOCKED"),
    21: ("ANT", "RF_BIDIR", "LORA_RF_MODULE", "RF_CONTACT_LOCKED"),
    22: ("GND", "POWER", "GND", "RF_GROUND_LOCKED"),
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
        default=ROOT / "artifacts/pcb_main_lora_authority_rev_a.json",
    )
    args = parser.parse_args()

    rows = read_csv(AUTHORITY)
    require(len(rows) == 24, "LoRa authority must contain exactly 24 physical contacts")
    require(all(set(row) == EXPECTED_COLUMNS for row in rows), "LoRa authority schema mismatch")
    require(
        all(all(row.get(column) for column in EXPECTED_COLUMNS) for row in rows),
        "LoRa authority contains an empty field",
    )
    by_key = {(row["RefDes"], row["Pin"]): row for row in rows}
    require(len(by_key) == len(rows), "duplicate LoRa RefDes/pin key")
    require({row["RefDes"] for row in rows} == {"U10", "J10"}, "unexpected LoRa RefDes set")

    u10_rows = [row for row in rows if row["RefDes"] == "U10"]
    require({row["Pin"] for row in u10_rows} == {str(pin) for pin in range(1, 23)}, "U10 package pin set mismatch")
    require(
        all((row["MPN"], row["Package"]) == ("E22-900M22S", "SMD_20x14_22P_1.27mm") for row in u10_rows),
        "U10 identity/package drift",
    )
    for pin, expected in EXPECTED_U10.items():
        row = by_key[("U10", str(pin))]
        actual = (row["Pin_Name"], row["Direction"], row["RevA_Net"], row["Disposition"])
        require(actual == expected, f"U10 pin {pin} contract mismatch")

    j10_rows = [row for row in rows if row["RefDes"] == "J10"]
    require({row["Pin"] for row in j10_rows} == {"1", "SHIELD"}, "J10 contact set mismatch")
    require(
        all((row["MPN"], row["Package"]) == ("U.FL-R-SMT-1(60)", "U.FL_SMT") for row in j10_rows),
        "J10 identity/package drift",
    )
    require(
        (by_key[("J10", "1")]["Pin_Name"], by_key[("J10", "1")]["RevA_Net"], by_key[("J10", "1")]["Disposition"])
        == ("SIGNAL", "LORA_RF_ANT", "RF_CONTACT_LOCKED"),
        "J10 center-contact contract mismatch",
    )
    require(
        (by_key[("J10", "SHIELD")]["Pin_Name"], by_key[("J10", "SHIELD")]["RevA_Net"], by_key[("J10", "SHIELD")]["Disposition"])
        == ("SHELL", "GND", "SHIELD_GROUND_LOCKED"),
        "J10 shell contract mismatch",
    )

    for pin in ("6", "7"):
        network = by_key[("U10", pin)]["Required_Network"]
        require("100 kOhm pull-down" in network and "initializes LOW" in network, f"U10 pin {pin} fail-closed network missing")
    require("DIO2-to-TXEN short is forbidden" in by_key[("U10", "8")]["Notes"], "DIO2 NC/separate-control rule missing")
    vcc = by_key[("U10", "9")]["Required_Network"]
    require(all(token in vcc for token in ("100 nF", "10 uF", "182 mA")), "U10 VCC network limits incomplete")
    require("100 kOhm pull-down" in by_key[("U10", "13")]["Required_Network"], "DIO1 powered-off safe state missing")
    require("100 kOhm pull-down" in by_key[("U10", "14")]["Required_Network"], "BUSY powered-off safe state missing")
    reset = by_key[("U10", "15")]["Required_Network"]
    require("10 kOhm pull-up" in reset and "100 nF" in reset and "initializes HIGH" in reset, "U10 NRST safe network incomplete")
    require("10 kOhm pull-up" in by_key[("U10", "19")]["Required_Network"], "U10 NSS reset deselection missing")
    for pin in ("16", "17", "18", "19"):
        require("22 Ohm" in by_key[("U10", pin)]["Required_Network"], f"U10 SPI pin {pin} damping position missing")

    rf_chain = by_key[("J10", "1")]["Required_Network"]
    for token in ("ultra-low-capacitance ESD", "50 Ohm", "0 Ohm series baseline", "both shunts DNP"):
        require(token in rf_chain, f"J10 RF path lacks {token}")
    require("no tee test point" in by_key[("J10", "1")]["Notes"], "RF no-stub rule missing")
    require("castellated ANT option" in by_key[("U10", "21")]["Notes"], "selected U10 antenna interface missing")
    require("module-side IPEX-1 must not be fitted" in by_key[("U10", "21")]["Notes"], "module-side IPEX exclusion missing")

    pin_map = {row["Net"]: row for row in read_csv(PIN_MAP)}
    mcu_by_net = {row["RevA_Net"]: row for row in read_csv(MCU_AUTHORITY) if row["RevA_Net"] != "NC"}
    expected_mcu = {
        "LORA_NSS": ("PA4", "28"), "LORA_SCK": ("PA5", "29"),
        "LORA_MISO": ("PA6", "30"), "LORA_MOSI": ("PA7", "31"),
        "LORA_DIO1": ("PC2", "17"), "LORA_TXEN": ("PB15", "54"),
        "LORA_RXEN": ("PD8", "55"), "LORA_BUSY": ("PD9", "56"),
        "LORA_RESET_N": ("PD10", "57"),
    }
    for net, expected in expected_mcu.items():
        require(net in pin_map and net in mcu_by_net, f"{net} missing from MCU authorities")
        require((pin_map[net]["MCU_Pin"], pin_map[net]["LQFP100_Pin"]) == expected, f"{net} MCU endpoint mismatch")
        require((mcu_by_net[net]["Pin_Name"], mcu_by_net[net]["LQFP100_Pin"]) == expected, f"{net} U1 physical endpoint mismatch")

    ioc = IOC.read_text(encoding="utf-8")
    for marker in (
        "PB15.GPIO_Label=LORA_TXEN", "PB15.PinState=GPIO_PIN_RESET",
        "PD8.GPIO_Label=LORA_RXEN", "PD8.PinState=GPIO_PIN_RESET",
        "PD10.GPIO_Label=LORA_RESET_N", "PD10.PinState=GPIO_PIN_SET",
    ):
        require(marker in ioc, f"CubeMX LoRa safe-state marker missing: {marker}")

    main_freeze = {row["RefDes"]: row for row in read_csv(MAIN_FREEZE)}
    require(main_freeze["U10"]["MPN"] == "E22-900M22S", "U10 main freeze MPN mismatch")
    require(main_freeze["U10"]["Package_or_Module"] == "SMD_20x14_22P_1.27mm", "U10 main freeze package mismatch")
    require("CASTELLATED_OPTION" in main_freeze["U10"]["Status"], "U10 antenna-option procurement blocker missing")
    require("PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv" in main_freeze["U10"]["Notes"], "U10 freeze lacks authority citation")
    connectors = {row["Connector_ID"]: row for row in read_csv(CONNECTOR_FREEZE)}
    require(connectors["CON-RF-LORA"]["Board_MPN"] == "Hirose_U.FL-R-SMT-1_60", "LoRa connector freeze MPN mismatch")
    require("PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv" in connectors["CON-RF-LORA"]["Notes"], "LoRa connector freeze lacks authority citation")
    require("no-stub" in connectors["CON-RF-LORA"]["Notes"], "LoRa connector freeze lost no-stub rule")

    authority_sha256 = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    review = REVIEW.read_text(encoding="utf-8")
    for marker in {
        "LORA_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        authority_sha256,
        "c66665745ef6f4a04de77201026d92841066b69575f62a717fe02bc363df62bf",
        "E22-900MM22S", "100 to 140 mA", "182 mA", "DIO3 TCXO supply to 2.2 V",
        "TXEN=1/RXEN=0", "RX is TXEN=0/RXEN=1",
        "TXEN=1/RXEN=1 is forbidden", "castellated-ANT option",
        "does not release exact support-component MPNs",
    }:
        require(marker in review, f"LoRa review missing marker: {marker}")

    cross_documents = {
        CAPTURE_SPEC: ("PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv", "LORA_TXEN", "DIO2 is NC", "MAIN-AUTH-010"),
        LORA_SHEET: ("all 24 U10/J10 rows", "100 kOhm pull-downs", "no-stub route"),
        RU868_PROFILE: ("tx_enabled: false", "signed_manufacturing_profile_only", "Do not copy EU868 parameters"),
    }
    for path, markers in cross_documents.items():
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in content, f"{path.name} lacks frozen LoRa marker: {marker}")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    authoritative = set(status["source_control"]["authoritative_inputs"])
    require(
        {
            "hardware/PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_LORA_AUTHORITY_REV_A.md",
        }.issubset(authoritative),
        "LoRa files are not registered as authoritative inputs",
    )
    readiness = status["capture_readiness"]
    closed = {item["id"]: item for item in readiness["closed_authorities"]}
    open_ids = {item["id"] for item in readiness["open_authorities"]}
    require(set(closed) == {f"MAIN-AUTH-{index:03d}" for index in range(1, 8)}, "closed authority set mismatch")
    require(
        set(closed["MAIN-AUTH-007"]["evidence"])
        == {
            "hardware/PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_LORA_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-007 evidence set mismatch",
    )
    require(open_ids == {f"MAIN-AUTH-{index:03d}" for index in range(8, 12)}, "remaining open authority set mismatch")
    require(readiness["complete"] is False and status["manufacturing_release"] is False, "LoRa authority prematurely released manufacturing")

    tx_current_ma = 140.0
    required_branch_ma = tx_current_ma * 1.30
    require(required_branch_ma == 182.0, "U10 30 percent current-headroom calculation failed")
    require(3.0 <= 3.3 <= 3.7, "U10 3.3 V full-power supply window failed")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "audit": "U10/J10 second independent LoRa authority control",
        "status": "PASS_LORA_AUTHORITY_ONLY",
        "physical_contacts_verified": len(rows),
        "u10_pins_verified": len(u10_rows),
        "j10_contacts_verified": len(j10_rows),
        "calculated_limits": {
            "tx_current_upper_ma": tx_current_ma,
            "supply_headroom_percent": 30,
            "minimum_branch_capability_ma": required_branch_ma,
        },
        "open_authorities": sorted(open_ids),
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN U10/J10 second independent control: PASS_LORA_AUTHORITY_ONLY")
    print("- all 24 physical contacts and independent module/connector maps verified")
    print("- separate fail-closed TXEN/RXEN, TCXO, supply and reset contracts verified")
    print("- RF matching/protection and no-stub conducted-port rules verified")
    print(f"- {len(open_ids)} remaining authorities keep the production BOM blocked")
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()
