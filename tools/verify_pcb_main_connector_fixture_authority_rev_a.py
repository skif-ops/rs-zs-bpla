#!/usr/bin/env python3
"""Second independent control of PCB-MAIN Rev.A connector and fixture authority."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv"
REVIEW = ROOT / "hardware/PCB_MAIN_CONNECTOR_FIXTURE_AUTHORITY_REV_A.md"
MCU_AUTHORITY = ROOT / "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv"
PIN_MAP = ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv"
CELLULAR_AUTHORITY = ROOT / "hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv"
GNSS_AUTHORITY = ROOT / "hardware/PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv"
LORA_AUTHORITY = ROOT / "hardware/PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv"
BLE_AUTHORITY = ROOT / "hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv"
MAIN_FREEZE = ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv"
CONNECTOR_FREEZE = ROOT / "hardware/CONNECTOR_FREEZE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
CAPTURE_SPEC = ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md"
STORAGE_SHEET = ROOT / "hardware/kicad/sheets/08_STORAGE_SENSORS.csv"
CONNECTOR_SHEET = ROOT / "hardware/kicad/sheets/09_CONNECTORS_TEST.csv"
TARGET_STATUS = ROOT / "firmware/targets/evt_pre_20/target_status.yaml"

EXPECTED_COLUMNS = {
    "RefDes", "MPN", "Package", "Pin", "Pin_Name", "Direction",
    "RevA_Net", "Disposition", "Required_Network", "Authority", "Notes",
}
EXPECTED_COUNTS = {
    "U12": 8,
    "J12": 10,
    "J11": 17,
    "J8": 2,
    "J9": 2,
    "J10": 2,
    "J13": 2,
    "TP_MCU_SWD": 5,
    "TP_EOL": 13,
    "TP_CELL_USB": 4,
    "TP_CELL_DBG": 5,
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
        default=ROOT / "artifacts/pcb_main_connector_fixture_authority_rev_a.json",
    )
    args = parser.parse_args()

    rows = read_csv(AUTHORITY)
    require(len(rows) == 70, "connector/fixture authority must contain exactly 70 physical contacts")
    require(all(set(row) == EXPECTED_COLUMNS for row in rows), "connector/fixture authority schema mismatch")
    require(
        all(all(row.get(column) for column in EXPECTED_COLUMNS) for row in rows),
        "connector/fixture authority contains an empty field",
    )
    by_key = {(row["RefDes"], row["Pin"]): row for row in rows}
    require(len(by_key) == len(rows), "duplicate connector/fixture RefDes/pin key")
    require(Counter(row["RefDes"] for row in rows) == Counter(EXPECTED_COUNTS), "contact-group count mismatch")

    card_map = {
        "1": ("DAT2", "SD_D2"), "2": ("CD/DAT3", "SD_D3"),
        "3": ("CMD", "SD_CMD"), "4": ("VDD", "3V3_DIGITAL"),
        "5": ("CLK", "SD_CK"), "6": ("VSS", "GND"),
        "7": ("DAT0", "SD_D0"), "8": ("DAT1", "SD_D1"),
    }
    for ref in ("U12", "J12"):
        for pin, expected in card_map.items():
            row = by_key[(ref, pin)]
            require((row["Pin_Name"], row["RevA_Net"]) == expected, f"{ref}.{pin} microSD map mismatch")
    require(by_key[("U12", "1")]["MPN"] == "SDCIT2/32GB", "U12 industrial card identity drift")
    require(by_key[("J12", "1")]["MPN"] == "MEM2052-00-195-00-A", "J12 socket identity drift")
    require(
        (by_key[("J12", "CD")]["RevA_Net"], by_key[("J12", "SHIELD")]["RevA_Net"])
        == ("SD_DET", "GND"),
        "J12 detect/shell mapping mismatch",
    )
    require("Normally-open" in by_key[("J12", "CD")]["Required_Network"], "J12 detect polarity missing")

    usb_expected = {
        "A1": ("GND", "GND"), "A4": ("VBUS", "USB_VBUS_CONN"),
        "A5": ("CC1", "USB_CC1"), "A6": ("D+", "USB_DP"),
        "A7": ("D-", "USB_DM"), "A8": ("SBU1", "NC"),
        "A9": ("VBUS", "USB_VBUS_CONN"), "A12": ("GND", "GND"),
        "B1": ("GND", "GND"), "B4": ("VBUS", "USB_VBUS_CONN"),
        "B5": ("CC2", "USB_CC2"), "B6": ("D+", "USB_DP"),
        "B7": ("D-", "USB_DM"), "B8": ("SBU2", "NC"),
        "B9": ("VBUS", "USB_VBUS_CONN"), "B12": ("GND", "GND"),
        "SHIELD": ("SHELL", "USB_SHIELD"),
    }
    for pin, expected in usb_expected.items():
        row = by_key[("J11", pin)]
        require(row["MPN"] == "USB4105-GF-A-120", f"J11.{pin} identity drift")
        require((row["Pin_Name"], row["RevA_Net"]) == expected, f"J11.{pin} contact mismatch")
    for pin in ("A5", "B5"):
        require("5.1 kOhm" in by_key[("J11", pin)]["Required_Network"], f"J11.{pin} device Rd missing")
    for pin in ("A6", "B6", "A7", "B7"):
        require("No routing to U11 BLE or U8 cellular modem" in by_key[("J11", pin)]["Notes"], f"J11.{pin} isolation rule missing")
    for pin in ("A4", "A9", "B4", "B9"):
        require("sense" in by_key[("J11", pin)]["Required_Network"], f"J11.{pin} VBUS sense-only rule missing")

    for ref, net, ground in (
        ("J8", "CELL_RF_ANT", "GND_MODEM"),
        ("J9", "GNSS_RF_ANT_BIASED", "GND"),
        ("J10", "LORA_RF_ANT", "GND"),
    ):
        require(by_key[(ref, "1")]["MPN"] == "U.FL-R-SMT-1(60)", f"{ref} U.FL identity drift")
        require(by_key[(ref, "1")]["RevA_Net"] == net, f"{ref} RF center net mismatch")
        require(by_key[(ref, "SHIELD")]["RevA_Net"] == ground, f"{ref} shell ground mismatch")
    for source_path, ref in ((GNSS_AUTHORITY, "J9"), (LORA_AUTHORITY, "J10")):
        source = {(row["RefDes"], row["Pin"]): row for row in read_csv(source_path)}
        for pin in ("1", "SHIELD"):
            require(by_key[(ref, pin)] == source[(ref, pin)], f"{ref}.{pin} diverges from its closed RF authority")

    tamper = {pin: by_key[("J13", pin)] for pin in ("1", "2")}
    require(all(row["MPN"] == "504050-0291" for row in tamper.values()), "J13 identity drift")
    require((tamper["1"]["RevA_Net"], tamper["2"]["RevA_Net"]) == ("TAMPER_IN", "GND"), "tamper pin map mismatch")
    require("Normally-closed" in tamper["1"]["Required_Network"] and "open circuit" in tamper["1"]["Required_Network"], "tamper fail-safe polarity missing")

    fixture_expected = {
        "TP_MCU_SWD": {
            "1": ("VTREF", "3V3_DIGITAL"), "2": ("SWDIO", "SWDIO"),
            "3": ("SWCLK", "SWCLK"), "4": ("NRST", "NRST"), "5": ("GND", "GND"),
        },
        "TP_EOL": {
            "1": ("GND", "GND"), "2": ("VTREF_3V3", "3V3_DIGITAL"),
            "3": ("VSENSE_3V8", "3V8_MODEM"), "4": ("VSENSE_1V8", "1V8_MIC"),
            "5": ("DUT_TX", "TEST_UART_TX"), "6": ("DUT_RX", "TEST_UART_RX"),
            "7": ("PWR_GOOD", "PWR_GOOD"), "8": ("FAULT", "FAULT"),
            "9": ("BOOT0", "BOOT0"), "10": ("REV0", "REV_STRAP0"),
            "11": ("REV1", "REV_STRAP1"), "12": ("I2C_SCL", "I2C2_SCL"),
            "13": ("I2C_SDA", "I2C2_SDA"),
        },
        "TP_CELL_USB": {
            "1": ("HOST_VBUS", "CELL_USB_VBUS"), "2": ("USB_DP", "CELL_USB_DP"),
            "3": ("USB_DM", "CELL_USB_DM"), "4": ("GND", "GND_MODEM"),
        },
        "TP_CELL_DBG": {
            "1": ("VREF_1V8", "U8_VDD_EXT_1V8"), "2": ("DUT_TX", "CELL_DBG_TXD_1V8"),
            "3": ("DUT_RX", "CELL_DBG_RXD_1V8"), "4": ("USB_BOOT", "CELL_USB_BOOT_1V8"),
            "5": ("GND", "GND_MODEM"),
        },
    }
    for ref, contacts in fixture_expected.items():
        for pin, expected in contacts.items():
            require((by_key[(ref, pin)]["Pin_Name"], by_key[(ref, pin)]["RevA_Net"]) == expected, f"{ref}.{pin} fixture mismatch")
    for key in (("TP_MCU_SWD", "1"), ("TP_EOL", "2"), ("TP_EOL", "3"), ("TP_EOL", "4"), ("TP_CELL_DBG", "1")):
        require("never source" in by_key[key]["Required_Network"], f"{key[0]}.{key[1]} sense-only rule missing")

    fixture_signal_sets = {
        ref: {row["RevA_Net"] for row in rows if row["RefDes"] == ref and row["RevA_Net"] not in {"GND", "GND_MODEM", "3V3_DIGITAL"}}
        for ref in ("TP_MCU_SWD", "TP_EOL", "TP_CELL_USB", "TP_CELL_DBG")
    }
    require(fixture_signal_sets["TP_CELL_USB"].isdisjoint({"USB_DP", "USB_DM", "USB_VBUS_CONN"}), "BG95 USB shares STM32 USB nets")
    ble_nets = {row["RevA_Net"] for row in read_csv(BLE_AUTHORITY) if row["RefDes"] == "TP_BLE_SWD"}
    require(fixture_signal_sets["TP_MCU_SWD"].isdisjoint(ble_nets - {"3V3_DIGITAL"}), "STM32 and BLE SWD signal nets overlap")

    pin_map = {row["Net"]: row for row in read_csv(PIN_MAP)}
    mcu_by_net = {row["RevA_Net"]: row for row in read_csv(MCU_AUTHORITY) if row["RevA_Net"] != "NC"}
    expected_mcu = {
        "SD_D0": ("PC8", "65"), "SD_D1": ("PC9", "66"), "SD_D2": ("PC10", "78"),
        "SD_D3": ("PC11", "79"), "SD_CK": ("PC12", "80"), "SD_CMD": ("PD2", "83"),
        "SD_DET": ("PC13", "7"), "TAMPER_IN": ("PC7", "64"),
        "TEST_UART_RX": ("PC0", "15"), "TEST_UART_TX": ("PC1", "16"),
        "USB_VBUS": ("PA9", "68"), "USB_DM": ("PA11", "70"), "USB_DP": ("PA12", "71"),
        "SWDIO": ("PA13", "72"), "SWCLK": ("PA14", "76"),
        "BOOT0": ("PH3", "94"), "REV_STRAP0": ("PB8", "95"), "REV_STRAP1": ("PB9", "96"),
        "I2C2_SCL": ("PB13", "52"), "I2C2_SDA": ("PB14", "53"),
    }
    for net, expected in expected_mcu.items():
        require(net in pin_map and net in mcu_by_net, f"{net} missing from MCU authorities")
        require((pin_map[net]["MCU_Pin"], pin_map[net]["LQFP100_Pin"]) == expected, f"{net} pin-map endpoint mismatch")
        require(mcu_by_net[net]["LQFP100_Pin"] == expected[1], f"{net} U1 physical endpoint mismatch")
    require(mcu_by_net["NRST"]["LQFP100_Pin"] == "14", "NRST physical endpoint mismatch")

    cellular = {(row["RefDes"], row["Pin"]): row for row in read_csv(CELLULAR_AUTHORITY)}
    cellular_expected = {
        "8": ("CELL_USB_VBUS", "TP_CELL_USB", "1"),
        "9": ("CELL_USB_DP", "TP_CELL_USB", "2"),
        "10": ("CELL_USB_DM", "TP_CELL_USB", "3"),
        "22": ("CELL_DBG_RXD_1V8", "TP_CELL_DBG", "3"),
        "23": ("CELL_DBG_TXD_1V8", "TP_CELL_DBG", "2"),
        "60": ("CELL_RF", "J8", "1"),
        "75": ("CELL_USB_BOOT_1V8", "TP_CELL_DBG", "4"),
    }
    for pin, (net, endpoint, contact) in cellular_expected.items():
        row = cellular[("U8", pin)]
        require(row["RevA_Net"] == net and row["Disposition"] in {"FIXTURE_ENDPOINT_LOCKED", "RF_ENDPOINT_LOCKED"}, f"U8.{pin} remains unresolved")
        require(endpoint in row["Required_Network"] and contact in row["Required_Network"], f"U8.{pin} fixture endpoint mismatch")

    main_freeze = {row["RefDes"]: row for row in read_csv(MAIN_FREEZE)}
    require(main_freeze["U12"]["MPN"] == "SDCIT2/32GB", "U12 main freeze MPN mismatch")
    require("PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv" in main_freeze["U12"]["Notes"], "U12 freeze lacks authority citation")
    connectors = {row["Connector_ID"]: row for row in read_csv(CONNECTOR_FREEZE)}
    expected_connectors = {
        "CON-USB": ("GCT_USB4105-GF-A-120", "16"),
        "CON-SD": ("GCT_MEM2052-00-195-00-A", "9"),
        "CON-TAMPER": ("Molex_5040500291", "2"),
        "CON-SWD-MCU": ("TEST_PADS", "5"), "CON-EOL": ("TEST_PADS", "13"),
        "CON-CELL-USB": ("TEST_PADS", "4"), "CON-CELL-DBG": ("TEST_PADS", "5"),
    }
    for cid, expected in expected_connectors.items():
        require((connectors[cid]["Board_MPN"], connectors[cid]["Positions"]) == expected, f"{cid} freeze mismatch")
        require("PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv" in connectors[cid]["Notes"], f"{cid} lacks authority citation")

    authority_sha256 = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    review = REVIEW.read_text(encoding="utf-8")
    for marker in (
        "CONNECTOR_FIXTURE_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        authority_sha256, "SDCIT2/32GB", "USB4105-GF-A-120", "MEM2052-00-195-00-A",
        "504050-0291", "U.FL-R-SMT-1(60)", "TP_EOL", "TP_CELL_USB", "TP_CELL_DBG",
        "MAIN-AUTH-010", "MAIN-AUTH-011", "production BOM",
    ):
        require(marker in review, f"connector/fixture review missing marker: {marker}")
    for path, markers in {
        CAPTURE_SPEC: ("PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv", "TP_CELL_USB", "MAIN-AUTH-010", "MAIN-AUTH-011"),
        STORAGE_SHEET: ("SDCIT2/32GB", "MEM2052-00-195-00-A", "504050-0291"),
        CONNECTOR_SHEET: ("all 70 rows", "TP_EOL", "TP_CELL_DBG"),
        TARGET_STATUS: ("Kingston_SDCIT2_32GB", "TP_EOL_13P", "TP_CELL_USB_4P"),
    }.items():
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in content, f"{path.name} lacks frozen connector/fixture marker: {marker}")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    authoritative = set(status["source_control"]["authoritative_inputs"])
    require(
        {
            "hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_CONNECTOR_FIXTURE_AUTHORITY_REV_A.md",
        }.issubset(authoritative),
        "connector/fixture files are not registered as authoritative inputs",
    )
    readiness = status["capture_readiness"]
    closed = {item["id"]: item for item in readiness["closed_authorities"]}
    open_ids = {item["id"] for item in readiness["open_authorities"]}
    require(set(closed) == {f"MAIN-AUTH-{index:03d}" for index in range(1, 12)}, "closed authority set mismatch")
    require(
        set(closed["MAIN-AUTH-009"]["evidence"])
        == {
            "hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_CONNECTOR_FIXTURE_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-009 evidence set mismatch",
    )
    require(open_ids == set(), "open authority set mismatch")
    require(readiness["complete"] is True and status["manufacturing_release"] is False, "capture/manufacturing state mismatch")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "audit": "connector/card/RF/tamper/production fixture second independent control",
        "status": "PASS_CONNECTOR_FIXTURE_AUTHORITY_ONLY",
        "physical_contacts_verified": len(rows),
        "contact_groups_verified": EXPECTED_COUNTS,
        "open_authorities": sorted(open_ids),
        "native_schematic": "ABSENT",
        "physical_tests": "NOT_RUN",
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN connector/fixture second independent control: PASS_CONNECTOR_FIXTURE_AUTHORITY_ONLY")
    print("- all 70 microSD/USB/RF/tamper/STM32/EOL/BG95 contacts verified")
    print("- STM32 USB, BG95 USB, nRF USB and both SWD domains remain isolated")
    print("- native capture and Reviews A/B keep the production BOM blocked")


if __name__ == "__main__":
    main()
