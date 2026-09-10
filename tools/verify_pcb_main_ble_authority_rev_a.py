#!/usr/bin/env python3
"""Second independent control of PCB-MAIN Rev.A BLE electrical authority."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv"
REVIEW = ROOT / "hardware/PCB_MAIN_BLE_AUTHORITY_REV_A.md"
MCU_AUTHORITY = ROOT / "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv"
PIN_MAP = ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv"
MAIN_FREEZE = ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv"
CONNECTOR_FREEZE = ROOT / "hardware/CONNECTOR_FREEZE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
CAPTURE_SPEC = ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md"
BLE_SHEET = ROOT / "hardware/kicad/sheets/07_BLE.csv"
TARGET_STATUS = ROOT / "firmware/targets/evt_pre_20/target_status.yaml"
IOC = ROOT / "firmware/targets/evt_pre_20/dioneya_evt_pre_20_rev_a.ioc"

EXPECTED_COLUMNS = {
    "RefDes", "MPN", "Package", "Pin", "Pin_Name", "Direction",
    "RevA_Net", "Disposition", "Required_Network", "Authority", "Notes",
}
PACKAGE = "nRF52840_SMD_10.5x15.5_61P_PCB_antenna"
EXPECTED_U11_PIN_NAMES = {
    index: name
    for index, name in enumerate(
        (
            "GND", "GND", "P1.10", "P1.11", "P1.12", "P1.13", "P1.14", "P1.15",
            "P0.03/AIN1", "P0.29/AIN5", "P0.02/AIN0", "P0.31/AIN7", "P0.28/AIN4",
            "P0.30/AIN6", "GND", "P0.27", "P0.00/XL1", "P0.01/XL2", "P0.26",
            "P0.04/AIN2", "P0.05/AIN3", "P0.06", "P0.07/TRACECLK", "P0.08", "P1.08",
            "P1.09/TRACEDATA3", "P0.11/TRACEDATA2", "VDD", "P0.12/TRACEDATA1", "VDDH",
            "DCCH", "VBUS", "GND", "D-", "D+", "P0.14", "P0.13", "P0.16", "P0.15",
            "P0.18/nRESET", "P0.17", "P0.19", "P0.21", "P0.20", "P0.23", "P0.22",
            "P1.00/TRACEDATA0", "P0.24", "P0.25", "P1.02", "SWDIO", "P0.09/NFC1",
            "SWDCLK", "P0.10/NFC2", "GND", "P1.04", "P1.06", "P1.07", "P1.05", "P1.03",
            "P1.01",
        ),
        start=1,
    )
}
EXPECTED_SPECIAL = {
    22: ("OUTPUT", "BLE_RX", "FUNCTION_LOCKED"),
    24: ("INPUT", "BLE_TX", "FUNCTION_LOCKED"),
    28: ("POWER", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    30: ("POWER", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    31: ("POWER_OUTPUT", "NC", "REG0_OUTPUT_NC"),
    32: ("POWER_INPUT", "NC", "USB_INPUT_NC"),
    34: ("USB_BIDIR", "NC", "USB_DATA_NC"),
    35: ("USB_BIDIR", "NC", "USB_DATA_NC"),
    39: ("INPUT", "BLE_DFU_REQ", "BOOT_REQUEST_LOCKED"),
    40: ("INPUT", "NRF_RESET_N", "RESET_LOCKED"),
    51: ("DEBUG_BIDIR", "NRF_SWDIO", "DEBUG_LOCKED"),
    53: ("DEBUG_INPUT", "NRF_SWCLK", "DEBUG_LOCKED"),
}
GROUND_PINS = {1, 2, 15, 33, 55}
LOW_FREQUENCY_NC_PINS = {*range(3, 15), 50, 56, 57, 58, 59, 60, 61}
NFC_NC_PINS = {52, 54}
LFRC_NC_PINS = {17, 18}


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
        default=ROOT / "artifacts/pcb_main_ble_authority_rev_a.json",
    )
    args = parser.parse_args()

    rows = read_csv(AUTHORITY)
    require(len(rows) == 65, "BLE authority must contain exactly 61 U11 pads and four SWD contacts")
    require(all(set(row) == EXPECTED_COLUMNS for row in rows), "BLE authority schema mismatch")
    require(
        all(all(row.get(column) for column in EXPECTED_COLUMNS) for row in rows),
        "BLE authority contains an empty field",
    )
    by_key = {(row["RefDes"], row["Pin"]): row for row in rows}
    require(len(by_key) == len(rows), "duplicate BLE RefDes/pin key")
    require({row["RefDes"] for row in rows} == {"U11", "TP_BLE_SWD"}, "unexpected BLE RefDes set")

    u11_rows = [row for row in rows if row["RefDes"] == "U11"]
    require({row["Pin"] for row in u11_rows} == {str(pin) for pin in range(1, 62)}, "U11 pad set mismatch")
    require(
        all((row["MPN"], row["Package"]) == ("MDBT50Q-P1MV2", PACKAGE) for row in u11_rows),
        "U11 identity/package drift",
    )
    for pin, expected_name in EXPECTED_U11_PIN_NAMES.items():
        row = by_key[("U11", str(pin))]
        require(row["Pin_Name"] == expected_name, f"U11 pad {pin} name mismatch")
        if pin in EXPECTED_SPECIAL:
            actual = (row["Direction"], row["RevA_Net"], row["Disposition"])
            require(actual == EXPECTED_SPECIAL[pin], f"U11 pad {pin} special contract mismatch")
        elif pin in GROUND_PINS:
            require(
                (row["Direction"], row["RevA_Net"], row["Disposition"])
                == ("POWER", "GND", "GROUND_LOCKED"),
                f"U11 pad {pin} ground contract mismatch",
            )
        else:
            require(row["RevA_Net"] == "NC", f"unused U11 pad {pin} is not NC")
            expected_disposition = (
                "UNUSED_LOW_FREQ_GPIO_NC" if pin in LOW_FREQUENCY_NC_PINS
                else "UNUSED_NFC_GPIO_NC" if pin in NFC_NC_PINS
                else "LFCLK_RC_GPIO_NC" if pin in LFRC_NC_PINS
                else "UNUSED_IO_NC"
            )
            require(row["Disposition"] == expected_disposition, f"U11 pad {pin} NC disposition mismatch")

    require("22 Ohm" in by_key[("U11", "22")]["Required_Network"], "U11 UART TX source damping missing")
    require("STM32 PB11" in by_key[("U11", "22")]["Required_Network"], "U11 UART TX endpoint mismatch")
    require("22 Ohm" in by_key[("U11", "24")]["Required_Network"], "STM32 UART TX source damping missing")
    require("STM32 PB10" in by_key[("U11", "24")]["Required_Network"], "U11 UART RX endpoint mismatch")
    for pin in ("28", "30"):
        require("3V3_DIGITAL" in by_key[("U11", pin)]["Required_Network"], f"U11 supply pad {pin} topology incomplete")
    require("100 nF plus 10 uF" in by_key[("U11", "28")]["Required_Network"], "U11 local decoupling mismatch")
    require("Reg0 DC/DC is disabled" in by_key[("U11", "31")]["Required_Network"], "U11 Reg0 state missing")
    for pin in ("17", "18"):
        require("external 32.768 kHz crystal" in by_key[("U11", pin)]["Required_Network"], f"U11 LFRC choice missing at pad {pin}")
    dfu = by_key[("U11", "39")]["Required_Network"]
    require(all(token in dfu for token in ("10 kOhm pull-up", "PB2 open-drain", "LOW")), "U11 DFU safe network incomplete")
    reset = by_key[("U11", "40")]["Required_Network"]
    require(all(token in reset for token in ("10 kOhm pull-up", "non-inverting open-drain", "100 kOhm pull-down")), "U11 reset network incomplete")

    swd_rows = [row for row in rows if row["RefDes"] == "TP_BLE_SWD"]
    require({row["Pin"] for row in swd_rows} == {"1", "2", "3", "4"}, "nRF SWD fixture contact set mismatch")
    require(all((row["MPN"], row["Package"]) == ("TEST_PADS", "POGO_FIXTURE_4P") for row in swd_rows), "nRF SWD fixture identity drift")
    expected_swd = {
        "1": ("VTREF", "3V3_DIGITAL", "FIXTURE_CONTACT_LOCKED"),
        "2": ("SWDIO", "NRF_SWDIO", "FIXTURE_CONTACT_LOCKED"),
        "3": ("SWDCLK", "NRF_SWCLK", "FIXTURE_CONTACT_LOCKED"),
        "4": ("GND", "GND", "FIXTURE_GROUND_LOCKED"),
    }
    for pin, expected in expected_swd.items():
        row = by_key[("TP_BLE_SWD", pin)]
        require((row["Pin_Name"], row["RevA_Net"], row["Disposition"]) == expected, f"nRF SWD contact {pin} mismatch")
    require("never source station power" in by_key[("TP_BLE_SWD", "1")]["Required_Network"], "nRF SWD VTREF direction rule missing")
    for pin in ("2", "3"):
        require("no shared contact or net with STM32" in by_key[("TP_BLE_SWD", pin)]["Required_Network"], f"nRF SWD separation missing at contact {pin}")

    pin_map = {row["Net"]: row for row in read_csv(PIN_MAP)}
    mcu_by_net = {row["RevA_Net"]: row for row in read_csv(MCU_AUTHORITY) if row["RevA_Net"] != "NC"}
    expected_mcu = {
        "BLE_TX": ("PB10", "44"),
        "BLE_RX": ("PB11", "45"),
        "BLE_EN": ("PE6", "5"),
        "BLE_DFU_REQ": ("PB2", "34"),
    }
    for net, expected in expected_mcu.items():
        require(net in pin_map and net in mcu_by_net, f"{net} missing from MCU authorities")
        require((pin_map[net]["MCU_Pin"], pin_map[net]["LQFP100_Pin"]) == expected, f"{net} MCU endpoint mismatch")
        require((mcu_by_net[net]["Pin_Name"], mcu_by_net[net]["LQFP100_Pin"]) == expected, f"{net} U1 physical endpoint mismatch")

    ioc = IOC.read_text(encoding="utf-8")
    for marker in (
        "PE6.GPIO_Label=BLE_EN", "PE6.PinState=GPIO_PIN_RESET",
        "PB2.GPIO_Label=BLE_DFU_REQ", "PB2.PinState=GPIO_PIN_SET",
        "PB2.GPIO_OType=GPIO_MODE_OUTPUT_OD",
        "PB10.GPIO_Label=BLE_TX", "PB10.Signal=USART3_TX",
        "PB11.GPIO_Label=BLE_RX", "PB11.Signal=USART3_RX",
    ):
        require(marker in ioc, f"CubeMX BLE safe-state marker missing: {marker}")

    main_freeze = {row["RefDes"]: row for row in read_csv(MAIN_FREEZE)}
    require(main_freeze["U11"]["MPN"] == "MDBT50Q-P1MV2", "U11 main freeze MPN mismatch")
    require(main_freeze["U11"]["Package_or_Module"] == PACKAGE, "U11 main freeze package mismatch")
    require("PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv" in main_freeze["U11"]["Notes"], "U11 main freeze lacks BLE authority citation")

    connectors = {row["Connector_ID"]: row for row in read_csv(CONNECTOR_FREEZE)}
    ble_swd = connectors["CON-SWD-BLE"]
    require((ble_swd["Board_MPN"], ble_swd["Positions"]) == ("TEST_PADS", "4"), "CON-SWD-BLE identity/contact count mismatch")
    require("PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv" in ble_swd["Notes"], "CON-SWD-BLE lacks authority citation")
    require(all(token in ble_swd["Notes"] for token in ("VTREF", "NRF_SWDIO", "NRF_SWCLK", "GND")), "CON-SWD-BLE contact map incomplete")

    review = REVIEW.read_text(encoding="utf-8")
    authority_sha256 = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    for marker in (
        "BLE_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        authority_sha256,
        "61fec8c0c9f8c33175be2237a8ebba73c6cfc0a3572fe3835fd341079c103d03",
        "7ff6f11d0185a9db73c7140a4fe7e70b31615539916e60d5c27af8178f9f9fc2",
        "61-pad", "PSELRESET[0]", "PSELRESET[1]", "application-defined",
        "10.5 mm by 3.8 mm", "no copper pours", "does not release exact support-component MPNs",
    ):
        require(marker in review, f"BLE authority review missing marker: {marker}")

    for path, markers in {
        CAPTURE_SPEC: ("PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv", "P0.06", "P0.08", "P0.15", "P0.18/nRESET", "3.8 mm", "MAIN-AUTH-010"),
        BLE_SHEET: ("all 65 U11/TP_BLE_SWD rows", "P0.06", "P0.08", "P0.15", "P0.18/nRESET", "3.8 mm"),
        TARGET_STATUS: ("P0.06_TX_to_PB11_RX", "P0.08_RX_from_PB10_TX", "P0.15_active_low_open_drain", "P0.18_nRESET", "INTERNAL_RC_CALIBRATED"),
    }.items():
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in content, f"{path.name} lacks frozen BLE marker: {marker}")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    authoritative = set(status["source_control"]["authoritative_inputs"])
    require(
        {
            "hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_BLE_AUTHORITY_REV_A.md",
        }.issubset(authoritative),
        "BLE files are not registered as authoritative inputs",
    )
    readiness = status["capture_readiness"]
    closed = {item["id"]: item for item in readiness["closed_authorities"]}
    open_ids = {item["id"] for item in readiness["open_authorities"]}
    require(set(closed) == {f"MAIN-AUTH-{index:03d}" for index in range(1, 9)}, "closed authority set mismatch")
    require(
        set(closed["MAIN-AUTH-008"]["evidence"])
        == {
            "hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_BLE_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-008 evidence set mismatch",
    )
    require(open_ids == {f"MAIN-AUTH-{index:03d}" for index in range(9, 12)}, "remaining open authority set mismatch")
    require(readiness["complete"] is False and status["manufacturing_release"] is False, "BLE authority prematurely released manufacturing")

    result = {
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "audit": "U11/TP_BLE_SWD second independent BLE authority control",
        "status": "PASS_BLE_AUTHORITY_ONLY",
        "physical_contacts_verified": len(rows),
        "u11_pads_verified": len(u11_rows),
        "swd_contacts_verified": len(swd_rows),
        "frozen_endpoints": {
            "uart_tx": "U11.22 P0.06 -> STM32 PB11",
            "uart_rx": "STM32 PB10 -> U11.24 P0.08",
            "dfu_request": "STM32 PB2 open-drain -> U11.39 P0.15",
            "reset": "STM32 PE6 -> fail-closed buffer -> U11.40 P0.18/nRESET",
        },
        "antenna_no_ground_minimum_mm": {"width": 10.5, "depth": 3.8, "layers": "ALL"},
        "open_authorities": sorted(open_ids),
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN U11/TP_BLE_SWD second independent control: PASS_BLE_AUTHORITY_ONLY")
    print("- all 61 U11 pads and four independent nRF SWD contacts verified")
    print("- UART, fail-closed reset, active-LOW DFU and normal-voltage supply contracts verified")
    print("- all-layer 10.5 mm by 3.8 mm minimum antenna no-ground rule verified")
    print(f"- {len(open_ids)} remaining authorities keep the production BOM blocked")
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()
