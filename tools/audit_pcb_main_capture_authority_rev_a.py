#!/usr/bin/env python3
"""Independent pre-schematic authority audit for EVT-PRE-20 PCB-MAIN Rev.A.

This gate proves that the current capture inputs are internally consistent and that
known missing device-pad authorities remain explicit blockers. It does not claim
that Review A, Review B or the production BOM has passed.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
PIN_MAP_PATH = ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv"
ADDENDUM_PATH = ROOT / "hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv"
HARNESS_PATH = ROOT / "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv"
MAIN_FREEZE_PATH = ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv"
CONNECTOR_FREEZE_PATH = ROOT / "hardware/CONNECTOR_FREEZE_REV_A.csv"
CAPTURE_SPEC_PATH = ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md"
MCU_PIN_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv"
MCU_PIN_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.md"
STORAGE_SENSOR_PIN_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_STORAGE_SENSOR_PIN_AUTHORITY_REV_A.csv"
STORAGE_SENSOR_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_STORAGE_SENSOR_AUTHORITY_REV_A.md"

EXPECTED_AUTHORITATIVE_INPUTS = {
    "config/EVT_PRE_20_BASELINE.yaml",
    "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv",
    "hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv",
    "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_STORAGE_SENSOR_PIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_STORAGE_SENSOR_AUTHORITY_REV_A.md",
    "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv",
    "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv",
    "hardware/CONNECTOR_FREEZE_REV_A.csv",
    "hardware/CLOCKING_REV_A.md",
    "hardware/kicad/REV_A_CAPTURE_SPEC.md",
    "firmware/targets/evt_pre_20/dioneya_evt_pre_20_rev_a.ioc",
}
SUPERSEDED_INPUTS = {
    "hardware/kicad/components.csv",
    "hardware/kicad/nets.csv",
}
EXPECTED_MAIN_MPNS = {
    "U1": "STM32U585VIT6Q",
    "U2": "W25Q512JVFIQ",
    "U3": "LIS2DW12TR",
    "U4": "STTS22HTR",
    "U7": "SN74AXC8T245PWR",
    "U8": "BG95-M3",
    "U9": "MAX-M10S-00B",
    "U10": "E22-900M22S",
    "U11": "MDBT50Q-P1MV2",
    "U13": "TS3A27518EPWR",
    "U14": "ESDALC6V1-5P6",
    "U15": "ESDALC6V1-5P6",
    "U16": "SN74AXC8T245PWR",
    "U17": "SN74LVC32APWR",
    "U18": "SN74AXC1T45DRLR",
    "X1": "SiT1552AI-JE-DCC-32.768D",
}
EXPECTED_MAIN_POWER = {
    "1": "3V8_MODEM",
    "2": "GND_MODEM",
    "3": "3V3_DIGITAL",
    "4": "GND_DIGITAL",
    "5": "1V8_MIC",
    "6": "GND_MIC",
    "7": "PWR_GOOD",
    "8": "FAULT",
    "9": "EN_MODEM",
    "10": "EN_AUX",
    "11": "I2C2_SCL",
    "12": "I2C2_SDA",
}
EXPECTED_SWD = {
    "1": "VTREF",
    "2": "SWDIO",
    "3": "SWCLK",
    "4": "NRST",
    "5": "GND",
}
EXPECTED_OPEN_AUTHORITY_IDS = {f"MAIN-AUTH-{index:03d}" for index in range(3, 12)}
EXPECTED_CLOSED_AUTHORITY_IDS = {"MAIN-AUTH-001", "MAIN-AUTH-002"}
EXPECTED_DEVICE_METADATA = {
    "U2": ("W25Q512JVFIQ", "SOIC-16_300mil_F"),
    "U3": ("LIS2DW12TR", "LGA-12_2x2mm"),
    "U4": ("STTS22HTR", "UDFN-6L_2x2mm"),
}
EXPECTED_DEVICE_PIN_MAP = {
    "U2": {
        "1": ("/HOLD or /RESET (IO3)", "NOR_IO3", "FUNCTION_LOCKED"),
        "2": ("VCC", "3V3_DIGITAL", "SUPPLY_LOCKED"),
        "3": ("/RESET", "3V3_DIGITAL", "STRAP_DIRECT_HIGH"),
        "4": ("N/C", "NC", "DNU_NO_CONNECT"),
        "5": ("N/C", "NC", "DNU_NO_CONNECT"),
        "6": ("N/C", "NC", "DNU_NO_CONNECT"),
        "7": ("/CS", "NOR_NCS", "FUNCTION_LOCKED"),
        "8": ("DO (IO1)", "NOR_IO1", "FUNCTION_LOCKED"),
        "9": ("/WP (IO2)", "NOR_IO2", "FUNCTION_LOCKED"),
        "10": ("GND", "GND", "GROUND_LOCKED"),
        "11": ("N/C", "NC", "DNU_NO_CONNECT"),
        "12": ("N/C", "NC", "DNU_NO_CONNECT"),
        "13": ("N/C", "NC", "DNU_NO_CONNECT"),
        "14": ("N/C", "NC", "DNU_NO_CONNECT"),
        "15": ("DI (IO0)", "NOR_IO0", "FUNCTION_LOCKED"),
        "16": ("CLK", "NOR_CLK", "FUNCTION_LOCKED"),
    },
    "U3": {
        "1": ("SCL/SPC", "I2C2_SCL", "FUNCTION_LOCKED"),
        "2": ("CS", "3V3_DIGITAL", "STRAP_DIRECT_HIGH"),
        "3": ("SDO/SA0", "GND", "STRAP_DIRECT_LOW"),
        "4": ("SDA/SDI/SDO", "I2C2_SDA", "FUNCTION_LOCKED"),
        "5": ("NC", "NC", "NO_CONNECT"),
        "6": ("GND", "GND", "GROUND_LOCKED"),
        "7": ("RES", "GND", "RESERVED_DIRECT_LOW"),
        "8": ("GND", "GND", "GROUND_LOCKED"),
        "9": ("VDD", "3V3_DIGITAL", "SUPPLY_LOCKED"),
        "10": ("VDD_IO", "3V3_DIGITAL", "SUPPLY_LOCKED"),
        "11": ("INT2", "NC", "UNUSED_OUTPUT_NC"),
        "12": ("INT1", "ACCEL_INT", "FUNCTION_LOCKED"),
    },
    "U4": {
        "1": ("SCL", "I2C2_SCL", "FUNCTION_LOCKED"),
        "2": ("ALERT / INT", "NC", "UNUSED_OUTPUT_NC"),
        "3": ("VDD", "3V3_DIGITAL", "SUPPLY_LOCKED"),
        "4": ("Addr", "GND", "STRAP_DIRECT_LOW"),
        "5": ("GND", "GND", "GROUND_LOCKED"),
        "6": ("SDA", "I2C2_SDA", "FUNCTION_LOCKED"),
        "EP": ("Exposed pad", "NC", "MECHANICAL_PAD_NO_NET"),
    },
}
EXPECTED_PACKAGE_PIN_NAMES = {
    index: name
    for index, name in enumerate(
        """PE2
PE3
PE4
PE5
PE6
VBAT
PC13
PC14-OSC32_IN (PC14)
PC15-OSC32_OUT (PC15)
VSS
VDD
PH0-OSC_IN (PH0)
PH1-OSC_OUT (PH1)
NRST
PC0
PC1
PC2
PC3
VSSA
VREF+
VDDA
PA0
PA1
PA2
PA3
VSS
VDD
PA4
PA5
PA6
PA7
PB0
PB1
PB2
PE7
PE8
PE9
PE10
PE11
PE12
PE13
PE14
PE15
PB10
PB11
VLXSMPS
VDDSMPS
VSSSMPS
VDD11
VSS
VDD
PB13
PB14
PB15
PD8
PD9
PD10
PD11
PD12
PD13
PD14
PD15
PC6
PC7
PC8
PC9
PA8
PA9
PA10
PA11
PA12
PA13 (JTMS/SWDIO)
VDDUSB
VSS
VDD
PA14 (JTCK/SWCLK)
PA15 (JTDI)
PC10
PC11
PC12
PD0
PD1
PD2
PD3
PD4
PD5
PD6
PD7
PB3 (JTDO/TRACESWO)
PB4 (NJTRST)
PB5
PB6
PB7
PH3-BOOT0
PB8
PB9
PE0
VDD11
VSS
VDD""".splitlines(),
        start=1,
    )
}
EXPECTED_POWER_PINS = {
    6: ("POWER_IN", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    10: ("GROUND", "GND", "GROUND_LOCKED"),
    11: ("POWER_IN", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    19: ("GROUND", "GND", "GROUND_LOCKED"),
    20: ("REFERENCE_IN", "3V3_DIGITAL", "REFERENCE_LOCKED"),
    21: ("POWER_IN", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    26: ("GROUND", "GND", "GROUND_LOCKED"),
    27: ("POWER_IN", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    46: ("POWER_SWITCH", "SMPS_SW", "SMPS_LOCKED"),
    47: ("POWER_IN", "3V3_DIGITAL", "SMPS_LOCKED"),
    48: ("GROUND", "GND", "GROUND_LOCKED"),
    49: ("POWER_OUT", "VCORE_1V1", "SMPS_LOCKED"),
    50: ("GROUND", "GND", "GROUND_LOCKED"),
    51: ("POWER_IN", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    73: ("POWER_IN", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    74: ("GROUND", "GND", "GROUND_LOCKED"),
    75: ("POWER_IN", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    98: ("POWER_OUT", "VCORE_1V1", "SMPS_LOCKED"),
    99: ("GROUND", "GND", "GROUND_LOCKED"),
    100: ("POWER_IN", "3V3_DIGITAL", "SUPPLY_LOCKED"),
}
EXPECTED_UNUSED_IO = {
    12: "HSE_FORBIDDEN_NC",
    13: "HSE_FORBIDDEN_NC",
    18: "UNUSED_GPIO_NC",
    23: "UNUSED_GPIO_NC",
    32: "UNUSED_GPIO_NC",
    36: "UNUSED_GPIO_NC",
    54: "UNUSED_GPIO_NC",
    55: "UNUSED_GPIO_NC",
    69: "UNUSED_GPIO_NC",
    84: "UNUSED_GPIO_NC",
    88: "UNUSED_GPIO_NC",
    89: "JTAG_TRACE_UNUSED_NC",
    90: "JTAG_UNUSED_NC",
    91: "UNUSED_GPIO_NC",
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def interface(rows_: list[dict[str, str]], name: str) -> list[dict[str, str]]:
    return [row for row in rows_ if row["Interface"] == name]


def pin_contract(rows_: list[dict[str, str]]) -> dict[str, str]:
    return {row["Pin"]: row["Net"] for row in rows_}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/pcb_main_capture_authority_rev_a.json",
    )
    args = parser.parse_args()

    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    require(status["schema_version"] == 1, "PCB-MAIN status schema mismatch")
    require(status["configuration"] == "EVT-PRE-20 Rev.A", "configuration mismatch")
    require(status["assembly"] == "PCB-MAIN", "assembly mismatch")
    require(status["release_state"] == "CAPTURE_INPUT", "premature PCB-MAIN release state")
    require(status["manufacturing_release"] is False, "PCB-MAIN must remain blocked")

    source_control = status["source_control"]
    authoritative = set(source_control["authoritative_inputs"])
    superseded = set(source_control["superseded_do_not_use"])
    require(authoritative == EXPECTED_AUTHORITATIVE_INPUTS, "PCB-MAIN authoritative input set drift")
    require(superseded == SUPERSEDED_INPUTS, "PCB-MAIN superseded input set drift")
    require(authoritative.isdisjoint(superseded), "superseded input marked authoritative")
    for relative in authoritative | superseded:
        require((ROOT / relative).is_file(), f"registered source file missing: {relative}")

    capture_spec = CAPTURE_SPEC_PATH.read_text(encoding="utf-8")
    for relative in sorted(SUPERSEDED_INPUTS):
        require(relative in capture_spec, f"capture spec does not identify superseded source: {relative}")
    require("must not be used" in capture_spec, "capture spec lacks explicit stale-source prohibition")
    workflow_text = (ROOT / ".github/workflows/pcb-native.yml").read_text(encoding="utf-8")
    pcb_main_generators = list((ROOT / "tools").glob("generate_pcb_main*.py"))
    live_capture_implementation = workflow_text + "\n".join(
        path.read_text(encoding="utf-8") for path in pcb_main_generators
    )
    for relative in sorted(SUPERSEDED_INPUTS):
        require(relative not in live_capture_implementation, f"live PCB-MAIN capture implementation references superseded source: {relative}")

    freeze = rows(MAIN_FREEZE_PATH)
    by_ref = {row["RefDes"]: row for row in freeze}
    require(len(by_ref) == len(freeze), "duplicate PCB-MAIN freeze RefDes")
    require(set(by_ref) == set(EXPECTED_MAIN_MPNS), "PCB-MAIN active RefDes set drift")
    for ref, mpn in EXPECTED_MAIN_MPNS.items():
        require(by_ref[ref]["Assembly"] == "PCB-MAIN", f"{ref} assembly mismatch")
        require(by_ref[ref]["MPN"] == mpn, f"{ref} MPN mismatch")
        require(by_ref[ref]["Package_or_Module"], f"{ref} package is empty")
        require(by_ref[ref]["Status"], f"{ref} selection status is empty")

    base = rows(PIN_MAP_PATH)
    addendum = rows(ADDENDUM_PATH)
    require(len(base) == 64, f"expected 64 base MCU assignments, got {len(base)}")
    require(len(addendum) == 1 and addendum[0]["Net"] == "AAD_CFG", "AAD_CFG addendum mismatch")
    pins = base + addendum
    require(len(pins) == status["mcu_contract"]["functional_assignment_count"] == 65, "MCU assignment count mismatch")
    for field in ("Net", "MCU_Pin", "LQFP100_Pin"):
        values = [row[field] for row in pins]
        require(len(values) == len(set(values)), f"MCU pin authority has duplicate {field}")
    by_net = {row["Net"]: row for row in pins}
    critical = {
        "PDM_CLK": ("PE9", "37"),
        "MIC_WAKE": ("PA8", "67"),
        "AAD_CFG": ("PA15", "77"),
        "LORA_DIO1": ("PC2", "17"),
        "I2C2_SCL": ("PB13", "52"),
        "I2C2_SDA": ("PB14", "53"),
        "USB_DM": ("PA11", "70"),
        "USB_DP": ("PA12", "71"),
        "LSE_IN": ("PC14", "8"),
        "LSE_OUT": ("PC15", "9"),
    }
    for net, expected in critical.items():
        require(net in by_net, f"critical MCU net missing: {net}")
        require((by_net[net]["MCU_Pin"], by_net[net]["LQFP100_Pin"]) == expected, f"{net} pin mismatch")
    require({by_net[f"PDM_DATA{i}"]["MCU_Pin"] for i in range(1, 5)} == {"PB1", "PD6", "PE7", "PE4"}, "four-channel PDM map mismatch")
    require({"PB12", "PE1", "PC4", "PC5"}.isdisjoint(row["MCU_Pin"] for row in pins), "absent Q-package pin used")

    # Independent full-package control. The expected package list is copied from
    # the pinned ST CubeMX STM32U585VITxQ LQFP100_SMPS definition rather than
    # derived from this CSV, so a shifted or omitted position is detectable.
    authority_rows = rows(MCU_PIN_AUTHORITY_PATH)
    expected_columns = {
        "LQFP100_Pin", "Pin_Name", "Pin_Type", "RevA_Net",
        "Disposition", "Authority", "Notes",
    }
    require(len(authority_rows) == 100, f"expected 100 U1 package positions, got {len(authority_rows)}")
    require(all(set(row) == expected_columns for row in authority_rows), "U1 pin-authority schema drift")
    authority_by_pin: dict[int, dict[str, str]] = {}
    for row in authority_rows:
        try:
            position = int(row["LQFP100_Pin"])
        except ValueError as exc:
            raise AssertionError(f"non-numeric U1 package position: {row['LQFP100_Pin']}") from exc
        require(position not in authority_by_pin, f"duplicate U1 package position: {position}")
        authority_by_pin[position] = row
    require(set(authority_by_pin) == set(range(1, 101)), "U1 package positions are not exactly 1..100")
    for position, expected_name in EXPECTED_PACKAGE_PIN_NAMES.items():
        row = authority_by_pin[position]
        require(row["Pin_Name"] == expected_name, f"U1 position {position} pin-name mismatch")
        expected_type = EXPECTED_POWER_PINS.get(position, ("RESET" if position == 14 else "IO", "", ""))[0]
        require(row["Pin_Type"] == expected_type, f"U1 position {position} pin-type mismatch")

    functional_by_position = {int(row["LQFP100_Pin"]): row for row in pins}
    require(len(functional_by_position) == 65, "functional U1 position count mismatch")
    for position, source_row in functional_by_position.items():
        authority_row = authority_by_pin[position]
        if position == 9:
            require(source_row["Net"] == "LSE_OUT", "source PC15 role drift")
            require(
                authority_row["RevA_Net"] == "NC"
                and authority_row["Disposition"] == "FUNCTION_RESERVED_EXTERNAL_NC",
                "PC15 must be reserved by RCC but externally NC",
            )
        else:
            require(authority_row["RevA_Net"] == source_row["Net"], f"U1 position {position} functional-net mismatch")
            require(authority_row["Disposition"] == "FUNCTION_LOCKED", f"U1 position {position} functional disposition mismatch")

    actual_unused = {
        position: row["Disposition"]
        for position, row in authority_by_pin.items()
        if row["RevA_Net"] == "NC" and position != 9
    }
    require(actual_unused == EXPECTED_UNUSED_IO, "U1 explicit unused-I/O disposition mismatch")
    for position, expected in EXPECTED_POWER_PINS.items():
        row = authority_by_pin[position]
        require(
            (row["Pin_Type"], row["RevA_Net"], row["Disposition"]) == expected,
            f"U1 position {position} power/reference disposition mismatch",
        )
    require(
        (authority_by_pin[14]["RevA_Net"], authority_by_pin[14]["Disposition"])
        == ("NRST", "RESET_LOCKED"),
        "U1 NRST disposition mismatch",
    )
    covered_positions = set(functional_by_position) | set(EXPECTED_UNUSED_IO) | {14} | set(EXPECTED_POWER_PINS)
    require(covered_positions == set(range(1, 101)), "U1 package-accounting categories do not cover exactly 100 positions")
    require(sum(row["Pin_Name"] == "VDD" for row in authority_rows) == 5, "U1 VDD pin count mismatch")
    require(sum(row["Pin_Name"] == "VSS" for row in authority_rows) == 5, "U1 VSS pin count mismatch")
    require(sum(row["Pin_Name"] == "VDD11" for row in authority_rows) == 2, "U1 VDD11 pin count mismatch")

    pin_review = MCU_PIN_REVIEW_PATH.read_text(encoding="utf-8")
    review_markers = {
        "PIN_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        "f4ec11f00e762e37ffc4020f6d4f20d225bc061d",
        "4349055dfd06e6eb2dce1a440c44a995ad7c924e28435ede119a7d4bb10f556d",
        "No HSE is fitted",
        "VREFBUF disabled",
        "2.2 uH",
        "2 x 2.2 uF",
        "10 uF",
        "does not release the native PCB-MAIN schematic",
    }
    for marker in review_markers:
        require(marker in pin_review, f"U1 pin-authority review record missing marker: {marker}")

    device_rows = rows(STORAGE_SENSOR_PIN_AUTHORITY_PATH)
    device_columns = {
        "RefDes", "MPN", "Package", "Pin", "Pin_Name", "Direction",
        "RevA_Net", "Disposition", "Required_Network", "Authority", "Notes",
    }
    require(len(device_rows) == 35, f"expected 35 U2/U3/U4 physical pin or pad rows, got {len(device_rows)}")
    require(all(set(row) == device_columns for row in device_rows), "U2/U3/U4 pin-authority schema drift")
    require(
        all(all(row[column] is not None and row[column] != "" for column in device_columns) for row in device_rows),
        "U2/U3/U4 pin-authority row contains an empty field",
    )
    device_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in device_rows:
        key = (row["RefDes"], row["Pin"])
        require(key not in device_by_key, f"duplicate device pin-authority row: {key[0]}.{key[1]}")
        device_by_key[key] = row
    expected_device_keys = {
        (ref, pin)
        for ref, pin_map in EXPECTED_DEVICE_PIN_MAP.items()
        for pin in pin_map
    }
    require(set(device_by_key) == expected_device_keys, "U2/U3/U4 physical pin set drift")
    for ref, expected_pin_map in EXPECTED_DEVICE_PIN_MAP.items():
        expected_mpn, expected_package = EXPECTED_DEVICE_METADATA[ref]
        for pin, expected in expected_pin_map.items():
            row = device_by_key[(ref, pin)]
            require((row["MPN"], row["Package"]) == (expected_mpn, expected_package), f"{ref}.{pin} identity/package mismatch")
            require((row["Pin_Name"], row["RevA_Net"], row["Disposition"]) == expected, f"{ref}.{pin} pin/net/disposition mismatch")

    required_nor_nets = {"NOR_CLK", "NOR_NCS", "NOR_IO0", "NOR_IO1", "NOR_IO2", "NOR_IO3"}
    require(required_nor_nets.issubset(by_net), "MCU functional map lacks the complete U2 OCTOSPI bus")
    require(
        {row["RevA_Net"] for row in device_rows if row["RefDes"] == "U2"} - {"NC", "3V3_DIGITAL", "GND"}
        == required_nor_nets,
        "U2 OCTOSPI endpoint set mismatch",
    )
    require(device_by_key[("U2", "2")]["Required_Network"] == "100 nF plus 1 uF local decoupling", "U2 decoupling contract mismatch")
    require("10 kOhm pull-up" in device_by_key[("U2", "7")]["Required_Network"], "U2 chip-select power-transition pull-up missing")
    require(device_by_key[("U2", "3")]["Required_Network"] == "Direct tie to 3V3_DIGITAL", "U2 dedicated reset strap mismatch")

    require({"I2C2_SCL", "I2C2_SDA", "ACCEL_INT"}.issubset(by_net), "MCU functional map lacks sensor endpoints")
    require("0x18" in device_by_key[("U3", "3")]["Notes"], "U3 address 0x18 evidence missing")
    require(device_by_key[("U3", "2")]["RevA_Net"] == "3V3_DIGITAL", "U3 is not hard-strapped to I2C mode")
    require(device_by_key[("U3", "7")]["RevA_Net"] == "GND", "U3 reserved pin is not grounded")
    require("100 nF plus 10 uF" in device_by_key[("U3", "9")]["Required_Network"], "U3 VDD decoupling mismatch")
    require("100 nF" in device_by_key[("U3", "10")]["Required_Network"], "U3 VDD_IO decoupling mismatch")
    require("0x3F" in device_by_key[("U4", "4")]["Notes"], "U4 address 0x3F evidence missing")
    require("100 nF" in device_by_key[("U4", "3")]["Required_Network"], "U4 VDD decoupling mismatch")
    require(device_by_key[("U4", "EP")]["RevA_Net"] == "NC", "U4 unnumbered exposed pad unexpectedly has an electrical net")
    i2c_addresses = {"LIS2DW12": 0x18, "STTS22H": 0x3F, "INA226": 0x40}
    require(len(i2c_addresses.values()) == len(set(i2c_addresses.values())), "Rev.A I2C2 address collision")

    device_review = STORAGE_SENSOR_REVIEW_PATH.read_text(encoding="utf-8")
    device_review_markers = {
        "DEVICE_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        "a898962af314ca90719eadba732e7f5fd42a1c48c4bfd283062c403d1c27bfd0",
        "5208623aa91c63a33be0e930518c20f5210c4eb76932350f35369687ae1d0dd5",
        "3f6937595517c4f738021037942e7d19d5b7c84cfe4e9b7e8635fcc06ff783fe",
        "factory default `QE=1`",
        "4-byte addressing mode",
        "0x18",
        "0x3F",
        "0x40",
        "2.2 kOhm, 1%",
        "0.746 us",
        "1.32 mA",
        "22 Ohm series-damping",
        "Initial bus speed is 100 kHz",
        "does not release the native PCB-MAIN schematic",
    }
    for marker in device_review_markers:
        require(marker in device_review, f"U2/U3/U4 authority review record missing marker: {marker}")

    harness = rows(HARNESS_PATH)
    main_power = interface(harness, "MAIN_PWR")
    require(pin_contract(main_power) == EXPECTED_MAIN_POWER, "12-pin MAIN/PWR harness contract mismatch")
    require(all(row["Connector_Ref"] == "J_PWR" and row["Release_status"] == "LOGICAL_FROZEN" for row in main_power), "MAIN/PWR harness is not frozen on J_PWR")
    for index in range(1, 5):
        name = f"MIC{index}"
        wake = f"AAD_WAKE{index}"
        aad = f"AAD_CFG{index}"
        mic_rows = interface(harness, name) + interface(harness, wake) + interface(harness, aad)
        expected = {
            "1": "1V8_MIC",
            "2": "GND",
            "3": "PDM_CLK",
            "4": f"PDM_DATA{index}",
            "5": f"MIC_WAKE{index}",
            "6": "AAD_CFG",
        }
        require(pin_contract(mic_rows) == expected, f"J_MIC{index} six-pin contract mismatch")
        require(all(row["Connector_Ref"] == f"J_MIC{index}" and row["Release_status"] == "LOGICAL_FROZEN" for row in mic_rows), f"J_MIC{index} harness is not frozen")
    swd = interface(harness, "SWD")
    require(pin_contract(swd) == EXPECTED_SWD, "STM32 SWD fixture contract mismatch")

    pin_nets = set(by_net)
    require({"PWR_GOOD", "PWR_FAULT", "EN_MODEM", "EN_AUX", "I2C2_SCL", "I2C2_SDA"}.issubset(pin_nets), "MAIN/PWR MCU-side nets missing")
    require({"PDM_CLK", "PDM_DATA1", "PDM_DATA2", "PDM_DATA3", "PDM_DATA4", "MIC_WAKE", "AAD_CFG"}.issubset(pin_nets), "microphone MCU-side nets missing")
    require({"SWDIO", "SWCLK", "BOOT0"}.issubset(pin_nets), "debug/recovery MCU-side nets missing")

    connector_rows = rows(CONNECTOR_FREEZE_PATH)
    connectors = {row["Connector_ID"]: row for row in connector_rows}
    expected_connectors = {
        "CON-004B": "Molex_430451202",
        "CON-MIC": "Molex_5040500691",
        "CON-RF-CELL": "Hirose_U.FL-R-SMT-1_60",
        "CON-RF-GNSS": "Hirose_U.FL-R-SMT-1_60",
        "CON-RF-LORA": "Hirose_U.FL-R-SMT-1_60",
        "CON-USB": "GCT_USB4105-GF-A-120",
        "CON-SIM1": "TE_2336582-1",
        "CON-SIM2": "TE_2336582-1",
        "CON-SWD-MCU": "TEST_PADS",
        "CON-SWD-BLE": "TEST_PADS",
    }
    for connector_id, mpn in expected_connectors.items():
        require(connector_id in connectors, f"connector freeze missing {connector_id}")
        require(connectors[connector_id]["Board_MPN"] == mpn, f"{connector_id} MPN mismatch")
        require(connectors[connector_id]["Status"] not in {"RELEASED", "CONTROLLED"}, f"{connector_id} unexpectedly released")

    mcu = status["mcu_contract"]
    require((mcu["refdes"], mcu["mpn"], mcu["package"]) == ("U1", "STM32U585VIT6Q", "LQFP100_14x14"), "status MCU contract mismatch")
    require(mcu["external_hse_allowed"] is False, "status permits external HSE")
    require(mcu["low_speed_reference_mpn"] == "SiT1552AI-JE-DCC-32.768D", "status low-speed reference mismatch")
    clock = (ROOT / "hardware/CLOCKING_REV_A.md").read_text(encoding="utf-8")
    require("shall not use an external HSE crystal or HSE oscillator" in clock, "clock policy no longer forbids HSE")

    native = status["native_schematic"]
    native_path = ROOT / native["path"]
    require(native["status"] == "ABSENT" and not native_path.exists(), "native schematic filesystem/status mismatch")
    require(native["schematic_derived_bom"] is False, "schematic-derived BOM claimed without native source")

    readiness = status["capture_readiness"]
    closed_items = readiness["closed_authorities"]
    open_items = readiness["open_authorities"]
    closed_ids = {item["id"] for item in closed_items}
    open_ids = {item["id"] for item in open_items}
    require(readiness["complete"] is False, "capture readiness released with open authorities")
    require(closed_ids == EXPECTED_CLOSED_AUTHORITY_IDS, "PCB-MAIN closed authority register drift")
    require(len(closed_ids) == len(closed_items), "duplicate PCB-MAIN closed authority ID")
    closed_evidence = {item["id"]: set(item["evidence"]) for item in closed_items}
    require(
        closed_evidence["MAIN-AUTH-001"]
        == {
            "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-001 evidence set mismatch",
    )
    require(
        closed_evidence["MAIN-AUTH-002"]
        == {
            "hardware/PCB_MAIN_STORAGE_SENSOR_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_STORAGE_SENSOR_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-002 evidence set mismatch",
    )
    require(closed_ids.isdisjoint(open_ids), "authority is both open and closed")
    require(open_ids == EXPECTED_OPEN_AUTHORITY_IDS, "PCB-MAIN open authority register drift")
    require(len(open_ids) == len(open_items), "duplicate PCB-MAIN open authority ID")
    require(all("production_bom" in item["blocks"] for item in open_items), "open authority does not block production BOM")
    review_a = status["review_a"]
    review_b = status["review_b"]
    require(review_a["complete"] is False and review_a["status"] == "BLOCKED_CAPTURE_AUTHORITY_INCOMPLETE", "Review A must remain blocked")
    require(review_b["complete"] is False and review_b["status"] == "BLOCKED_REVIEW_A_NOT_COMPLETE", "Review B must remain blocked")
    expected_review_a_evidence = {
        "signed_checklist", "schematic_pdf", "cubemx_pin_report", "erc_report",
        "bom_diff", "net_name_diff",
    }
    require(set(review_a["evidence"]) == expected_review_a_evidence, "Review A evidence schema mismatch")
    require(not any(review_a["evidence"].values()) and not review_b["evidence"], "review evidence present while review is incomplete")

    result = {
        "configuration": status["configuration"],
        "assembly": status["assembly"],
        "audit": "PCB-MAIN independent pre-schematic authority audit",
        "status": "PASS_CAPTURE_INPUT_CONTROLLED",
        "mcu_assignments_verified": len(pins),
        "mcu_package_pins_verified": len(authority_rows),
        "storage_sensor_pads_verified": len(device_rows),
        "active_mpn_rows_verified": len(freeze),
        "logical_harness_pins_verified": len(main_power) + 24 + len(swd),
        "open_authorities": sorted(open_ids),
        "native_schematic": "ABSENT",
        "review_a": "BLOCKED",
        "review_b": "BLOCKED",
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN Rev.A pre-schematic authority audit: PASS_CAPTURE_INPUT_CONTROLLED")
    print(f"- all {len(authority_rows)} U1 package positions and {len(pins)} functional assignments verified")
    print(f"- all {len(device_rows)} U2/U3/U4 physical pins or pads and three unique I2C2 addresses verified")
    print(f"- {len(freeze)} active MPNs and 41 logical harness pins verified")
    print(f"- {len(open_items)} missing pad/mechanical authorities remain explicit production blockers")
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()
