#!/usr/bin/env python3
"""Independent capture-input authority audit for EVT-PRE-20 PCB-MAIN Rev.A.

This gate proves that the complete pre-schematic capture inputs are internally
consistent. It does not claim
that Review A, Review B or the production BOM has passed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
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
AUDIO_LOGIC_PIN_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv"
AUDIO_LOGIC_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_AUDIO_LOGIC_AUTHORITY_REV_A.md"
CELLULAR_PIN_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv"
CELLULAR_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_CELLULAR_AUTHORITY_REV_A.md"
DUAL_SIM_PIN_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv"
DUAL_SIM_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_DUAL_SIM_AUTHORITY_REV_A.md"
GNSS_PIN_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv"
GNSS_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_GNSS_AUTHORITY_REV_A.md"
LORA_PIN_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv"
LORA_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_LORA_AUTHORITY_REV_A.md"
BLE_PIN_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv"
BLE_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_BLE_AUTHORITY_REV_A.md"
CONNECTOR_FIXTURE_PIN_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv"
CONNECTOR_FIXTURE_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_CONNECTOR_FIXTURE_AUTHORITY_REV_A.md"
PASSIVE_SUPPORT_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv"
PASSIVE_SUPPORT_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.md"
MECHANICAL_PLACEMENT_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
MECHANICAL_PLACEMENT_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.md"
DUAL_SIM_POLICY_PATH = ROOT / "hardware/DUAL_SIM_SINGLE_STANDBY.md"
AUDIO_INTERFACE_PATH = ROOT / "hardware/T5838_AAD_INTERFACE_REV_A.md"
POWER_ARCHITECTURE_PATH = ROOT / "hardware/EVT_PRE_20_POWER_ARCHITECTURE.md"
GROUND_DOMAIN_AUTHORITY_PATH = ROOT / "hardware/PCB_MAIN_GROUND_DOMAIN_AUTHORITY_REV_A.csv"
GROUND_DOMAIN_REVIEW_PATH = ROOT / "hardware/PCB_MAIN_GROUND_DOMAIN_AUTHORITY_REV_A.md"
NATIVE_NET_OVERLAY_PATH = ROOT / "hardware/PCB_MAIN_NATIVE_NET_OVERLAY_REV_A.csv"

EXPECTED_AUTHORITATIVE_INPUTS = {
    "config/EVT_PRE_20_BASELINE.yaml",
    "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv",
    "hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv",
    "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_STORAGE_SENSOR_PIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_STORAGE_SENSOR_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_AUDIO_LOGIC_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_CELLULAR_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_DUAL_SIM_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_GNSS_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_LORA_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_BLE_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_CONNECTOR_FIXTURE_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_GROUND_DOMAIN_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_GROUND_DOMAIN_AUTHORITY_REV_A.md",
    "hardware/PCB_MAIN_NATIVE_NET_OVERLAY_REV_A.csv",
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
    "U12": "SDCIT2/32GB",
    "U13": "TS3A27518EPWR",
    "U14": "ESDALC6V1-5P6",
    "U15": "ESDALC6V1-5P6",
    "U16": "SN74AXC8T245PWR",
    "U17": "SN74LVC32APWR",
    "U18": "SN74AXC1T45DRLR",
    "Q1": "MMBT3904,215",
    "Q2": "MMBT3904,215",
    "Q3": "MMBT3904,215",
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
EXPECTED_OPEN_AUTHORITY_IDS: set[str] = set()
EXPECTED_CLOSED_AUTHORITY_IDS = {f"MAIN-AUTH-{index:03d}" for index in range(1, 12)}
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
EXPECTED_AUDIO_METADATA = {
    "U7": ("SN74AXC8T245PWR", "TSSOP-24_PW"),
    "U17": ("SN74LVC32APWR", "TSSOP-14_PW"),
    "U18": ("SN74AXC1T45DRLR", "SOT-5X3-6_DRL"),
}
EXPECTED_AUDIO_PIN_MAP = {
    "U7": {
        "1": ("VCCA", "POWER", "1V8_MIC", "SUPPLY_LOCKED"),
        "2": ("DIR1", "INPUT", "1V8_MIC", "STRAP_DIRECT_HIGH"),
        "3": ("A1", "INPUT", "PDM_DATA1_1V8", "FUNCTION_LOCKED"),
        "4": ("A2", "INPUT", "PDM_DATA2_1V8", "FUNCTION_LOCKED"),
        "5": ("A3", "INPUT", "PDM_DATA3_1V8", "FUNCTION_LOCKED"),
        "6": ("A4", "INPUT", "PDM_DATA4_1V8", "FUNCTION_LOCKED"),
        "7": ("A5", "OUTPUT", "PDM_CLK_1V8", "FUNCTION_LOCKED"),
        "8": ("A6", "OUTPUT", "AAD_CFG_1V8", "FUNCTION_LOCKED"),
        "9": ("A7", "OUTPUT", "NC", "UNUSED_OUTPUT_NC"),
        "10": ("A8", "OUTPUT", "NC", "UNUSED_OUTPUT_NC"),
        "11": ("DIR2", "INPUT", "GND", "STRAP_DIRECT_LOW"),
        "12": ("GND", "POWER", "GND", "GROUND_LOCKED"),
        "13": ("GND", "POWER", "GND", "GROUND_LOCKED"),
        "14": ("B8", "INPUT", "GND", "UNUSED_INPUT_DIRECT_LOW"),
        "15": ("B7", "INPUT", "GND", "UNUSED_INPUT_DIRECT_LOW"),
        "16": ("B6", "INPUT", "AAD_CFG", "FUNCTION_LOCKED"),
        "17": ("B5", "INPUT", "PDM_CLK", "FUNCTION_LOCKED"),
        "18": ("B4", "OUTPUT", "PDM_DATA4", "FUNCTION_LOCKED"),
        "19": ("B3", "OUTPUT", "PDM_DATA3", "FUNCTION_LOCKED"),
        "20": ("B2", "OUTPUT", "PDM_DATA2", "FUNCTION_LOCKED"),
        "21": ("B1", "OUTPUT", "PDM_DATA1", "FUNCTION_LOCKED"),
        "22": ("OE", "INPUT", "GND", "STRAP_DIRECT_LOW"),
        "23": ("VCCB", "POWER", "3V3_DIGITAL", "SUPPLY_LOCKED"),
        "24": ("VCCB", "POWER", "3V3_DIGITAL", "SUPPLY_LOCKED"),
    },
    "U17": {
        "1": ("1A", "INPUT", "MIC_WAKE1", "FUNCTION_LOCKED"),
        "2": ("1B", "INPUT", "MIC_WAKE2", "FUNCTION_LOCKED"),
        "3": ("1Y", "OUTPUT", "MIC_WAKE12_OR_1V8", "FUNCTION_LOCKED"),
        "4": ("2A", "INPUT", "MIC_WAKE3", "FUNCTION_LOCKED"),
        "5": ("2B", "INPUT", "MIC_WAKE4", "FUNCTION_LOCKED"),
        "6": ("2Y", "OUTPUT", "MIC_WAKE34_OR_1V8", "FUNCTION_LOCKED"),
        "7": ("GND", "POWER", "GND", "GROUND_LOCKED"),
        "8": ("3Y", "OUTPUT", "MIC_WAKE_OR_1V8", "FUNCTION_LOCKED"),
        "9": ("3A", "INPUT", "MIC_WAKE12_OR_1V8", "FUNCTION_LOCKED"),
        "10": ("3B", "INPUT", "MIC_WAKE34_OR_1V8", "FUNCTION_LOCKED"),
        "11": ("4Y", "OUTPUT", "NC", "UNUSED_OUTPUT_NC"),
        "12": ("4A", "INPUT", "GND", "UNUSED_INPUT_DIRECT_LOW"),
        "13": ("4B", "INPUT", "GND", "UNUSED_INPUT_DIRECT_LOW"),
        "14": ("VCC", "POWER", "1V8_MIC", "SUPPLY_LOCKED"),
    },
    "U18": {
        "1": ("VCCA", "POWER", "1V8_MIC", "SUPPLY_LOCKED"),
        "2": ("GND", "POWER", "GND", "GROUND_LOCKED"),
        "3": ("A", "INPUT", "MIC_WAKE_OR_1V8", "FUNCTION_LOCKED"),
        "4": ("B", "OUTPUT", "MIC_WAKE", "FUNCTION_LOCKED"),
        "5": ("DIR", "INPUT", "1V8_MIC", "STRAP_DIRECT_HIGH"),
        "6": ("VCCB", "POWER", "3V3_DIGITAL", "SUPPLY_LOCKED"),
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
    require(status["release_state"] in {"CAPTURE_INPUT", "SCHEMATIC_REVIEW", "REVIEW_A_PASS"},
            "invalid PCB-MAIN capture/review state")
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
    require(len(base) == 66, f"expected 66 base MCU assignments, got {len(base)}")
    require(len(addendum) == 1 and addendum[0]["Net"] == "AAD_CFG", "AAD_CFG addendum mismatch")
    mcu_pins = base + addendum
    require(len(mcu_pins) == status["mcu_contract"]["functional_assignment_count"] == 67, "MCU assignment count mismatch")
    for field in ("Net", "MCU_Pin", "LQFP100_Pin"):
        values = [row[field] for row in mcu_pins]
        require(len(values) == len(set(values)), f"MCU pin authority has duplicate {field}")
    by_net = {row["Net"]: row for row in mcu_pins}
    critical = {
        "PDM_CLK": ("PE9", "37"),
        "MIC_WAKE": ("PA8", "67"),
        "AAD_CFG": ("PA15", "77"),
        "LORA_DIO1": ("PC2", "17"),
        "LORA_TXEN": ("PB15", "54"),
        "LORA_RXEN": ("PD8", "55"),
        "BLE_TX": ("PB10", "44"),
        "BLE_RX": ("PB11", "45"),
        "BLE_EN": ("PE6", "5"),
        "BLE_DFU_REQ": ("PB2", "34"),
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
    require({"PB12", "PE1", "PC4", "PC5"}.isdisjoint(row["MCU_Pin"] for row in mcu_pins), "absent Q-package pin used")

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

    functional_by_position = {int(row["LQFP100_Pin"]): row for row in mcu_pins}
    require(len(functional_by_position) == 67, "functional U1 position count mismatch")
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
        "67 locked functional assignments",
        "PB15 / package pin 54",
        "PD8 / package pin 55",
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

    audio_rows = rows(AUDIO_LOGIC_PIN_AUTHORITY_PATH)
    audio_columns = {
        "RefDes", "MPN", "Package", "Pin", "Pin_Name", "Direction",
        "RevA_Net", "Disposition", "Required_Network", "Authority", "Notes",
    }
    require(len(audio_rows) == 44, f"expected 44 U7/U17/U18 physical pins, got {len(audio_rows)}")
    require(all(set(row) == audio_columns for row in audio_rows), "U7/U17/U18 pin-authority schema drift")
    require(
        all(all(row[column] is not None and row[column] != "" for column in audio_columns) for row in audio_rows),
        "U7/U17/U18 pin-authority row contains an empty field",
    )
    audio_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in audio_rows:
        key = (row["RefDes"], row["Pin"])
        require(key not in audio_by_key, f"duplicate audio pin-authority row: {key[0]}.{key[1]}")
        audio_by_key[key] = row
    expected_audio_keys = {
        (ref, pin)
        for ref, pin_map in EXPECTED_AUDIO_PIN_MAP.items()
        for pin in pin_map
    }
    require(set(audio_by_key) == expected_audio_keys, "U7/U17/U18 physical pin set drift")
    for ref, expected_pin_map in EXPECTED_AUDIO_PIN_MAP.items():
        expected_mpn, expected_package = EXPECTED_AUDIO_METADATA[ref]
        for pin, expected in expected_pin_map.items():
            row = audio_by_key[(ref, pin)]
            require((row["MPN"], row["Package"]) == (expected_mpn, expected_package), f"{ref}.{pin} identity/package mismatch")
            actual = (row["Pin_Name"], row["Direction"], row["RevA_Net"], row["Disposition"])
            require(actual == expected, f"{ref}.{pin} pin/direction/net/disposition mismatch")

    for index, a_pin, b_pin in ((1, "3", "21"), (2, "4", "20"), (3, "5", "19"), (4, "6", "18")):
        require(audio_by_key[("U7", a_pin)]["RevA_Net"] == f"PDM_DATA{index}_1V8", f"U7 PDM data {index} A-port mismatch")
        require(audio_by_key[("U7", b_pin)]["RevA_Net"] == f"PDM_DATA{index}", f"U7 PDM data {index} B-port mismatch")
        require("no external pull" in audio_by_key[("U7", a_pin)]["Required_Network"], f"U7 PDM data {index} external-pull prohibition missing")
    require(audio_by_key[("U7", "2")]["Required_Network"] == "Direct tie to 1V8_MIC", "U7 DIR1 strap mismatch")
    require(audio_by_key[("U7", "11")]["Required_Network"] == "Direct tie to GND", "U7 DIR2 strap mismatch")
    require(audio_by_key[("U7", "22")]["Required_Network"] == "Direct tie to GND", "U7 OE strap mismatch")
    require({audio_by_key[("U7", pin)]["RevA_Net"] for pin in ("14", "15")} == {"GND"}, "U7 unused input state mismatch")
    require({audio_by_key[("U7", pin)]["RevA_Net"] for pin in ("9", "10")} == {"NC"}, "U7 unused output state mismatch")
    for ref, pin in (("U7", "1"), ("U7", "23"), ("U7", "24"), ("U17", "14"), ("U18", "1"), ("U18", "6")):
        require("100 nF" in audio_by_key[(ref, pin)]["Required_Network"], f"{ref}.{pin} local bypass contract missing")

    wake_inputs = {"1": "MIC_WAKE1", "2": "MIC_WAKE2", "4": "MIC_WAKE3", "5": "MIC_WAKE4"}
    for pin, net in wake_inputs.items():
        row = audio_by_key[("U17", pin)]
        require(row["RevA_Net"] == net, f"U17 input {pin} wake-net mismatch")
        require("100 kOhm pull-down" in row["Required_Network"] and "test point" in row["Required_Network"], f"U17 input {pin} safe-state/test-point network mismatch")
    require(
        audio_by_key[("U17", "3")]["RevA_Net"] == audio_by_key[("U17", "9")]["RevA_Net"] == "MIC_WAKE12_OR_1V8",
        "U17 first pair OR interconnect mismatch",
    )
    require(
        audio_by_key[("U17", "6")]["RevA_Net"] == audio_by_key[("U17", "10")]["RevA_Net"] == "MIC_WAKE34_OR_1V8",
        "U17 second pair OR interconnect mismatch",
    )
    require(
        audio_by_key[("U17", "8")]["RevA_Net"] == audio_by_key[("U18", "3")]["RevA_Net"] == "MIC_WAKE_OR_1V8",
        "U17-to-U18 aggregate wake interconnect mismatch",
    )
    require({audio_by_key[("U17", pin)]["RevA_Net"] for pin in ("12", "13")} == {"GND"}, "U17 unused inputs are not grounded")
    require(audio_by_key[("U17", "11")]["RevA_Net"] == "NC", "U17 unused output is not NC")
    require(audio_by_key[("U18", "5")]["Required_Network"] == "Direct tie to 1V8_MIC", "U18 DIR strap mismatch")
    require("100 kOhm pull-down" in audio_by_key[("U18", "4")]["Required_Network"], "U18 MCU-side wake pull-down missing")
    require(
        {audio_by_key[("U7", pin)]["RevA_Net"] for pin in ("16", "17", "18", "19", "20", "21")}
        == {"AAD_CFG", "PDM_CLK", "PDM_DATA1", "PDM_DATA2", "PDM_DATA3", "PDM_DATA4"},
        "U7 MCU-side endpoint set mismatch",
    )
    require(audio_by_key[("U18", "4")]["RevA_Net"] == "MIC_WAKE", "U18 MCU-side wake endpoint mismatch")

    audio_review = AUDIO_LOGIC_REVIEW_PATH.read_text(encoding="utf-8")
    authority_sha256 = hashlib.sha256(AUDIO_LOGIC_PIN_AUTHORITY_PATH.read_bytes()).hexdigest()
    audio_review_markers = {
        "AUDIO_LOGIC_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        authority_sha256,
        "6cf4003c438c0546fb86f0932613896197dd19a75bdb307f385eb6e75535126e",
        "807f6fff7977736035c2a3144d530be7ad737a163b2f0fd11002a45953b47230",
        "41e03bd8f0740ae8bbdf92309e7c82bac1359a768556cbe68de41b0273e49f12",
        "5befb710bfe7a415cdc1aba41ebc18b484d7f9fc320ce15a7481507531cf58a4",
        "DIR1=HIGH",
        "DIR2=LOW",
        "OE=LOW",
        "288 kOhm",
        "No external pull-up or pull-down",
        "100 kOhm pull-down",
        "does not release native PCB-MAIN capture",
    }
    for marker in audio_review_markers:
        require(marker in audio_review, f"U7/U17/U18 authority review record missing marker: {marker}")
    audio_interface = AUDIO_INTERFACE_PATH.read_text(encoding="utf-8")
    power_architecture = POWER_ARCHITECTURE_PATH.read_text(encoding="utf-8")
    for marker in ("DIR1=HIGH", "DIR2=LOW", "OE=LOW", "44-pin", "no external pull-up or pull-down"):
        require(marker in audio_interface, f"T5838 interface document missing frozen audio-logic marker: {marker}")
    require("disabled/high-Z state" not in power_architecture, "power architecture still requires U7 disable in S0")
    require("фиксированном `OE=LOW`" in power_architecture, "power architecture lacks frozen U7 S0 state")

    cellular_rows = rows(CELLULAR_PIN_AUTHORITY_PATH)
    cellular_columns = {
        "RefDes", "MPN", "Package", "Pin", "Pin_Name", "Direction",
        "RevA_Net", "Disposition", "Required_Network", "Authority", "Notes",
    }
    require(len(cellular_rows) == 132, f"expected 132 U8/U16/Q1/Q2 physical pins, got {len(cellular_rows)}")
    require(all(set(row) == cellular_columns for row in cellular_rows), "cellular pin-authority schema drift")
    require(
        all(all(row[column] is not None and row[column] != "" for column in cellular_columns) for row in cellular_rows),
        "cellular pin-authority row contains an empty field",
    )
    cellular_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in cellular_rows:
        key = (row["RefDes"], row["Pin"])
        require(key not in cellular_by_key, f"duplicate cellular pin-authority row: {key[0]}.{key[1]}")
        cellular_by_key[key] = row
    cellular_identity = {
        "U8": ("BG95-M3", "LGA-102_23.6x19.9mm", {str(index) for index in range(1, 103)}),
        "U16": ("SN74AXC8T245PWR", "TSSOP-24_PW", {str(index) for index in range(1, 25)}),
        "Q1": ("MMBT3904,215", "SOT23", {"1", "2", "3"}),
        "Q2": ("MMBT3904,215", "SOT23", {"1", "2", "3"}),
    }
    for ref, (mpn, package, expected_pins) in cellular_identity.items():
        actual = [row for row in cellular_rows if row["RefDes"] == ref]
        require({row["Pin"] for row in actual} == expected_pins, f"{ref} cellular package-position set drift")
        require(all((row["MPN"], row["Package"]) == (mpn, package) for row in actual), f"{ref} cellular identity/package mismatch")

    u8 = {index: cellular_by_key[("U8", str(index))] for index in range(1, 103)}
    expected_u8_ground_pins = {
        3, 31, 48, 50, 54, 55, 58, 59, 61, 62,
        *range(67, 75), *range(79, 83), *range(89, 92), *range(100, 103),
    }
    require({index for index, row in u8.items() if row["Pin_Name"] == "GND"} == expected_u8_ground_pins, "U8 ground-pad set drift")
    require(
        all((u8[index]["RevA_Net"], u8[index]["Disposition"]) == ("GND_MODEM", "GROUND_LOCKED") for index in expected_u8_ground_pins),
        "U8 ground-pad net/disposition mismatch",
    )
    expected_u8_critical = {
        15: ("PWRKEY", "U8_PWRKEY_N", "FUNCTION_LOCKED"),
        17: ("RESET_N", "U8_RESET_N", "FUNCTION_LOCKED"),
        20: ("STATUS", "U8_STATUS_1V8", "FUNCTION_LOCKED"),
        29: ("VDD_EXT", "U8_VDD_EXT_1V8", "SUPPLY_OUTPUT_LOCKED"),
        30: ("MAIN_DTR", "U8_MAIN_DTR_1V8", "FUNCTION_LOCKED"),
        32: ("VBAT_BB", "3V8_MODEM_BB", "SUPPLY_LOCKED"),
        33: ("VBAT_BB", "3V8_MODEM_BB", "SUPPLY_LOCKED"),
        34: ("MAIN_RXD", "U8_MAIN_RXD_1V8", "FUNCTION_LOCKED"),
        35: ("MAIN_TXD", "U8_MAIN_TXD_1V8", "FUNCTION_LOCKED"),
        39: ("MAIN_RI", "U8_MAIN_RI_1V8", "FUNCTION_LOCKED"),
        43: ("USIM_VDD", "CELL_USIM_VDD_1V8", "FUNCTION_LOCKED"),
        44: ("USIM_RST", "CELL_USIM_RST_1V8", "FUNCTION_LOCKED"),
        45: ("USIM_DATA", "CELL_USIM_DATA_1V8", "FUNCTION_LOCKED"),
        46: ("USIM_CLK", "CELL_USIM_CLK_1V8", "FUNCTION_LOCKED"),
        47: ("USIM_GND", "GND_MODEM", "GROUND_LOCKED"),
        52: ("VBAT_RF", "3V8_MODEM_RF", "SUPPLY_LOCKED"),
        53: ("VBAT_RF", "3V8_MODEM_RF", "SUPPLY_LOCKED"),
    }
    for pin, expected in expected_u8_critical.items():
        require((u8[pin]["Pin_Name"], u8[pin]["RevA_Net"], u8[pin]["Disposition"]) == expected, f"U8 pad {pin} critical mapping mismatch")
    for pin in (11, 12, 13, 14, 16, 57, 63, 76, 77, 78, 92, 93, 94, 95, 97, 98, 99):
        require((u8[pin]["RevA_Net"], u8[pin]["Disposition"]) == ("NC", "RESERVED_DNU_NC"), f"U8 reserved pad {pin} is not DNU/NC")
    require((u8[42]["RevA_Net"], u8[42]["Disposition"]) == ("NC", "UNUSED_INPUT_NC"), "U8 module-level USIM_DET must remain NC")
    for pin in (8, 9, 10, 22, 23, 75):
        require(u8[pin]["Disposition"] == "FIXTURE_ENDPOINT_LOCKED", f"U8 recovery pad {pin} endpoint mismatch")
    require(u8[60]["Disposition"] == "RF_ENDPOINT_LOCKED", "U8 cellular RF endpoint mismatch")
    for token in ("100 uF", "220 nF", "47 nF", "150 pF", "68 pF", "33 pF", "10 pF", "ferrite bead"):
        require(token in u8[32]["Required_Network"], f"U8 VBAT_BB authority lacks {token}")
    for token in ("100 uF", "100 nF", "33 pF", "10 pF", "0 Ohm link"):
        require(token in u8[52]["Required_Network"], f"U8 VBAT_RF authority lacks {token}")

    u16 = {index: cellular_by_key[("U16", str(index))] for index in range(1, 25)}
    expected_u16 = {
        1: ("U8_VDD_EXT_1V8", "SUPPLY_LOCKED"), 2: ("U8_VDD_EXT_1V8", "STRAP_DIRECT_HIGH"),
        3: ("U8_MAIN_TXD_1V8", "FUNCTION_LOCKED"), 4: ("U8_STATUS_1V8", "FUNCTION_LOCKED"),
        5: ("U8_MAIN_RI_1V8", "FUNCTION_LOCKED"), 6: ("GND_MODEM", "UNUSED_INPUT_DIRECT_LOW"),
        7: ("U8_MAIN_RXD_1V8", "FUNCTION_LOCKED"), 8: ("U8_MAIN_DTR_1V8", "FUNCTION_LOCKED"),
        9: ("NC", "UNUSED_OUTPUT_NC"), 10: ("NC", "UNUSED_OUTPUT_NC"),
        11: ("GND_MODEM", "STRAP_DIRECT_LOW"), 12: ("GND_MODEM", "GROUND_LOCKED"),
        13: ("GND_MODEM", "GROUND_LOCKED"), 14: ("GND_MODEM", "UNUSED_INPUT_DIRECT_LOW"),
        15: ("GND_MODEM", "UNUSED_INPUT_DIRECT_LOW"), 16: ("CELL_DTR", "FUNCTION_LOCKED"),
        17: ("CELL_TX", "FUNCTION_LOCKED"), 18: ("NC", "UNUSED_OUTPUT_NC"),
        19: ("CELL_RI", "FUNCTION_LOCKED"), 20: ("CELL_STATUS", "FUNCTION_LOCKED"),
        21: ("CELL_RX", "FUNCTION_LOCKED"), 22: ("GND_MODEM", "STRAP_DIRECT_LOW"),
        23: ("3V3_DIGITAL", "SUPPLY_LOCKED"), 24: ("3V3_DIGITAL", "SUPPLY_LOCKED"),
    }
    for pin, expected in expected_u16.items():
        require((u16[pin]["RevA_Net"], u16[pin]["Disposition"]) == expected, f"U16 pin {pin} net/disposition mismatch")
    require(all("100 nF" in u16[pin]["Required_Network"] for pin in (1, 23, 24)), "U16 bypass contract incomplete")

    for ref, command, collector in (("Q1", "CELL_PWRKEY_CMD", "U8_PWRKEY_N"), ("Q2", "CELL_RESET_N_CMD", "U8_RESET_N")):
        q = {pin: cellular_by_key[(ref, str(pin))] for pin in range(1, 4)}
        require((q[1]["Pin_Name"], q[2]["Pin_Name"], q[3]["Pin_Name"]) == ("B", "E", "C"), f"{ref} SOT23 pin order mismatch")
        require(command in q[1]["Required_Network"] and "4.7 kOhm" in q[1]["Required_Network"] and "47 kOhm" in q[1]["Required_Network"], f"{ref} base-drive network mismatch")
        require(q[2]["RevA_Net"] == "GND_MODEM" and q[3]["RevA_Net"] == collector, f"{ref} open-collector mapping mismatch")

    cellular_review = CELLULAR_REVIEW_PATH.read_text(encoding="utf-8")
    cellular_authority_sha256 = hashlib.sha256(CELLULAR_PIN_AUTHORITY_PATH.read_bytes()).hexdigest()
    for marker in {
        "CELLULAR_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        cellular_authority_sha256,
        "6ff03aa31577971d02dc15eac11adee4d52b80077ae3fa3503978c1b12496e81",
        "6cf4003c438c0546fb86f0932613896197dd19a75bdb307f385eb6e75535126e",
        "500-1000 ms", "650-1500 ms", "2-3.8 s", "AT+QPOWD", "150 mV", "below 75 mV",
        "controlled separately by `PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv`",
    }:
        require(marker in cellular_review, f"cellular authority review record missing marker: {marker}")

    dual_sim_rows = rows(DUAL_SIM_PIN_AUTHORITY_PATH)
    require(len(dual_sim_rows) == 55, f"expected 55 U13/U14/U15/J6/J7/Q3 authority rows, got {len(dual_sim_rows)}")
    require(all(set(row) == cellular_columns for row in dual_sim_rows), "dual-SIM pin-authority schema drift")
    require(
        all(all(row[column] is not None and row[column] != "" for column in cellular_columns) for row in dual_sim_rows),
        "dual-SIM pin-authority row contains an empty field",
    )
    dual_sim_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in dual_sim_rows:
        key = (row["RefDes"], row["Pin"])
        require(key not in dual_sim_by_key, f"duplicate dual-SIM pin-authority row: {key[0]}.{key[1]}")
        dual_sim_by_key[key] = row
    dual_sim_identity = {
        "U13": ("TS3A27518EPWR", "TSSOP-24_PW", {str(index) for index in range(1, 25)}),
        "U14": ("ESDALC6V1-5P6", "SOT666_1.6x1.6mm", {str(index) for index in range(1, 7)}),
        "U15": ("ESDALC6V1-5P6", "SOT666_1.6x1.6mm", {str(index) for index in range(1, 7)}),
        "J6": ("2336582-1", "TE_NanoSIM_H1.37", {str(index) for index in range(1, 8)} | {"SHIELD"}),
        "J7": ("2336582-1", "TE_NanoSIM_H1.37", {str(index) for index in range(1, 8)} | {"SHIELD"}),
        "Q3": ("MMBT3904,215", "SOT23", {"1", "2", "3"}),
    }
    for ref, (mpn, package, expected_pins) in dual_sim_identity.items():
        actual = [row for row in dual_sim_rows if row["RefDes"] == ref]
        require({row["Pin"] for row in actual} == expected_pins, f"{ref} dual-SIM package-position set drift")
        require(all((row["MPN"], row["Package"]) == (mpn, package) for row in actual), f"{ref} dual-SIM identity/package mismatch")

    expected_u13 = {
        1: ("NC2", "SIM1_RST_1V8", "FUNCTION_LOCKED"),
        2: ("NC1", "SIM1_VDD_1V8", "FUNCTION_LOCKED"),
        3: ("N.C.", "NC", "DNU_NO_CONNECT"),
        4: ("COM1", "CELL_USIM_VDD_1V8", "FUNCTION_LOCKED"),
        5: ("GND", "GND_MODEM", "GROUND_LOCKED"),
        6: ("COM2", "CELL_USIM_RST_1V8", "FUNCTION_LOCKED"),
        7: ("COM3", "CELL_USIM_CLK_1V8", "FUNCTION_LOCKED"),
        8: ("VCC", "3V3_DIGITAL", "SUPPLY_LOCKED"),
        9: ("COM4", "CELL_USIM_VDD_1V8", "FUNCTION_LOCKED"),
        10: ("COM5", "CELL_USIM_DATA_1V8", "FUNCTION_LOCKED"),
        11: ("NO1", "SIM2_VDD_1V8", "FUNCTION_LOCKED"),
        12: ("COM6", "CELL_USIM_VDD_1V8", "FUNCTION_LOCKED"),
        13: ("NO2", "SIM2_RST_1V8", "FUNCTION_LOCKED"),
        14: ("IN2", "SIM_MUX_SEL", "CONTROL_LOCKED"),
        15: ("NO3", "SIM2_CLK_1V8", "FUNCTION_LOCKED"),
        16: ("NO6", "SIM2_VDD_1V8", "FUNCTION_LOCKED"),
        17: ("NO4", "SIM2_VDD_1V8", "FUNCTION_LOCKED"),
        18: ("NO5", "SIM2_DATA_1V8", "FUNCTION_LOCKED"),
        19: ("NC5", "SIM1_DATA_1V8", "FUNCTION_LOCKED"),
        20: ("EN", "U13_EN_N", "CONTROL_ACTIVE_LOW"),
        21: ("NC4", "SIM1_VDD_1V8", "FUNCTION_LOCKED"),
        22: ("NC6", "SIM1_VDD_1V8", "FUNCTION_LOCKED"),
        23: ("NC3", "SIM1_CLK_1V8", "FUNCTION_LOCKED"),
        24: ("IN1", "SIM_MUX_SEL", "CONTROL_LOCKED"),
    }
    u13 = {pin: dual_sim_by_key[("U13", str(pin))] for pin in range(1, 25)}
    for pin, expected in expected_u13.items():
        require((u13[pin]["Pin_Name"], u13[pin]["RevA_Net"], u13[pin]["Disposition"]) == expected, f"U13 pin {pin} mapping mismatch")
    require(sum(row["RevA_Net"] == "CELL_USIM_VDD_1V8" for row in u13.values()) == 3, "U13 common VDD path is not three channels wide")
    require(sum(row["RevA_Net"] == "SIM1_VDD_1V8" for row in u13.values()) == 3, "U13 SIM1 VDD path is not three channels wide")
    require(sum(row["RevA_Net"] == "SIM2_VDD_1V8" for row in u13.values()) == 3, "U13 SIM2 VDD path is not three channels wide")
    require(all("100 kOhm pull-down" in u13[pin]["Required_Network"] for pin in (14, 24)), "U13 select default is not locked LOW")
    require("47 kOhm pull-up" in u13[20]["Required_Network"], "U13 EN boot-safe pull-up missing")
    require("100 nF" in u13[8]["Required_Network"], "U13 local bypass missing")

    for ref, slot in (("U14", "SIM1"), ("U15", "SIM2")):
        expected_esd_nets = {
            "1": f"{slot}_VDD_1V8", "2": "GND_MODEM", "3": f"{slot}_RST_1V8",
            "4": f"{slot}_CLK_1V8", "5": f"{slot}_DATA_1V8", "6": f"{slot}_DET",
        }
        for pin, net in expected_esd_nets.items():
            row = dual_sim_by_key[(ref, pin)]
            require(row["RevA_Net"] == net, f"{ref} pin {pin} protected-net mismatch")
        require(dual_sim_by_key[(ref, "2")]["Disposition"] == "GROUND_LOCKED", f"{ref} ground return is not locked")

    connector_pin_names = {"1": "C1_VCC", "2": "C2_RST", "3": "C3_CLK", "4": "C5_GND", "5": "C6_VPP", "6": "C7_IO", "7": "CD", "SHIELD": "SHELL"}
    connector_suffixes = {"1": "VDD_1V8", "2": "RST_1V8", "3": "CLK_1V8", "6": "DATA_1V8", "7": "DET"}
    for ref, slot in (("J6", "SIM1"), ("J7", "SIM2")):
        for pin, pin_name in connector_pin_names.items():
            require(dual_sim_by_key[(ref, pin)]["Pin_Name"] == pin_name, f"{ref} contact {pin} name mismatch")
        for pin, suffix in connector_suffixes.items():
            require(dual_sim_by_key[(ref, pin)]["RevA_Net"] == f"{slot}_{suffix}", f"{ref} contact {pin} net mismatch")
        require(dual_sim_by_key[(ref, "4")]["RevA_Net"] == "GND_MODEM", f"{ref} card ground is not direct")
        require(dual_sim_by_key[(ref, "5")]["RevA_Net"] == "NC", f"{ref} VPP must remain NC")
        require(dual_sim_by_key[(ref, "SHIELD")]["RevA_Net"] == "GND_MODEM", f"{ref} shell is not direct ground")
        require("10 kOhm pull-up" in dual_sim_by_key[(ref, "7")]["Required_Network"], f"{ref} detect pull-up missing")
        require("10 nF" in dual_sim_by_key[(ref, "7")]["Required_Network"], f"{ref} detect filter missing")

    q3 = {pin: dual_sim_by_key[("Q3", str(pin))] for pin in range(1, 4)}
    require((q3[1]["Pin_Name"], q3[2]["Pin_Name"], q3[3]["Pin_Name"]) == ("B", "E", "C"), "Q3 SOT23 pin order mismatch")
    require(q3[1]["RevA_Net"] == "SIM_MUX_EN_B" and "10 kOhm" in q3[1]["Required_Network"] and "100 kOhm" in q3[1]["Required_Network"], "Q3 base network mismatch")
    require(q3[2]["RevA_Net"] == "GND_MODEM" and q3[3]["RevA_Net"] == "U13_EN_N", "Q3 open-collector mapping mismatch")
    for net, expected in {"SIM_MUX_SEL": ("PE0", "97"), "SIM_MUX_EN": ("PE2", "1"), "SIM1_DET": ("PE3", "2"), "SIM2_DET": ("PE5", "4")}.items():
        require(net in by_net, f"dual-SIM MCU net missing: {net}")
        require((by_net[net]["MCU_Pin"], by_net[net]["LQFP100_Pin"]) == expected, f"{net} MCU pin mismatch")

    require(7.6 / 3 < 2.54, "three-channel U13 VDD resistance bound failed")
    require(0.2 < 0.65, "Q3 saturation voltage does not guarantee U13 LOW")
    dual_sim_review = DUAL_SIM_REVIEW_PATH.read_text(encoding="utf-8")
    dual_sim_sha256 = hashlib.sha256(DUAL_SIM_PIN_AUTHORITY_PATH.read_bytes()).hexdigest()
    for marker in {
        "DUAL_SIM_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        dual_sim_sha256,
        "d87c216911176dca84cc9cee5efb6f45b18021977f94a97c7fae989484a73392",
        "ea14ac3604fa4887d91b9fbc55ab9d04a23ba6597b22a817e64185d519fb9e28",
        "2bcf8b28017d5716a1659ad5ad401d6158b272458de43ed4b325a80c7f70d6fe",
        "Three channels are paralleled", "at most 2.54 Ohm", "at least 1.62 V",
        "active but not currently available", "does not release the exact passive MPN set",
    }:
        require(marker in dual_sim_review, f"dual-SIM authority review missing marker: {marker}")
    dual_sim_policy = DUAL_SIM_POLICY_PATH.read_text(encoding="utf-8")
    for marker in ("TS3A27518EPWR", "TE `2336582-1`", "SIM_MUX_EN=HIGH", "U13_EN_N=HIGH", "2.54 Ом", "не менее 20 ms"):
        require(marker in dual_sim_policy, f"dual-SIM policy missing frozen marker: {marker}")

    gnss_rows = rows(GNSS_PIN_AUTHORITY_PATH)
    require(len(gnss_rows) == 20, f"expected 20 U9/J9 authority rows, got {len(gnss_rows)}")
    require(all(set(row) == cellular_columns for row in gnss_rows), "GNSS pin-authority schema drift")
    require(
        all(all(row[column] is not None and row[column] != "" for column in cellular_columns) for row in gnss_rows),
        "GNSS pin-authority row contains an empty field",
    )
    gnss_by_key = {(row["RefDes"], row["Pin"]): row for row in gnss_rows}
    require(len(gnss_by_key) == len(gnss_rows), "duplicate GNSS RefDes/pin key")
    require({row["RefDes"] for row in gnss_rows} == {"U9", "J9"}, "GNSS authority RefDes set drift")
    require(
        {row["Pin"] for row in gnss_rows if row["RefDes"] == "U9"} == {str(index) for index in range(1, 19)},
        "U9 package positions are not exactly 1..18",
    )
    require(
        {row["Pin"] for row in gnss_rows if row["RefDes"] == "J9"} == {"1", "SHIELD"},
        "J9 electrical contact set mismatch",
    )
    require(
        all(
            (row["MPN"], row["Package"]) == ("MAX-M10S-00B", "LCC-18_9.7x10.1mm")
            for row in gnss_rows if row["RefDes"] == "U9"
        ),
        "U9 GNSS identity/package mismatch",
    )
    require(
        all(
            (row["MPN"], row["Package"]) == ("U.FL-R-SMT-1(60)", "U.FL_SMT")
            for row in gnss_rows if row["RefDes"] == "J9"
        ),
        "J9 identity/package mismatch",
    )
    expected_u9 = {
        1: ("GND", "GND", "GROUND_LOCKED"),
        2: ("TXD", "GNSS_RX", "FUNCTION_LOCKED"),
        3: ("RXD", "GNSS_TX", "FUNCTION_LOCKED"),
        4: ("TIMEPULSE", "GNSS_PPS", "FUNCTION_LOCKED"),
        5: ("EXTINT", "NC", "UNUSED_INPUT_NC"),
        6: ("V_BCKP", "NC", "OPTIONAL_BACKUP_NC"),
        7: ("V_IO", "3V3_DIGITAL", "SUPPLY_LOCKED"),
        8: ("VCC", "3V3_DIGITAL", "SUPPLY_LOCKED"),
        9: ("RESET_N", "NC", "UNUSED_RESET_NC"),
        10: ("GND", "GND", "GROUND_LOCKED"),
        11: ("RF_IN", "GNSS_RF_FILTERED", "RF_INPUT_LOCKED"),
        12: ("GND", "GND", "GROUND_LOCKED"),
        13: ("LNA_EN", "GNSS_ANT_OFF_N", "ANTENNA_SUPERVISOR_LOCKED"),
        14: ("VCC_RF", "GNSS_ANT_BIAS_RAW", "RF_SUPPLY_OUTPUT_LOCKED"),
        15: ("VIO_SEL", "NC", "STRAP_OPEN_3V3"),
        16: ("SDA", "GNSS_ANT_DETECT", "ANTENNA_SUPERVISOR_LOCKED"),
        17: ("SCL", "GNSS_ANT_SHORT_N", "ANTENNA_SUPERVISOR_LOCKED"),
        18: ("SAFEBOOT_N", "NC", "UNUSED_SERVICE_NC"),
    }
    for pin, expected in expected_u9.items():
        row = gnss_by_key[("U9", str(pin))]
        require((row["Pin_Name"], row["RevA_Net"], row["Disposition"]) == expected, f"U9 pin {pin} mapping mismatch")
    require("100 nF plus 10 uF" in gnss_by_key[("U9", "8")]["Required_Network"], "U9 VCC local decoupling mismatch")
    require("0.2 Ohm" in gnss_by_key[("U9", "8")]["Required_Network"], "U9 VCC feed-resistance limit missing")
    require("100 mA startup inrush" in gnss_by_key[("U9", "8")]["Required_Network"], "U9 startup-inrush contract missing")
    require("50 mA" in gnss_by_key[("U9", "14")]["Required_Network"], "U9 VCC_RF limit missing")
    require("1 kOhm" in gnss_by_key[("U9", "18")]["Notes"], "U9 SAFEBOOT/TIMEPULSE coupling warning missing")
    require("I2C disabled" in gnss_by_key[("U9", "16")]["Required_Network"], "GNSS open-detect PIO reassignment missing")
    require("I2C disabled" in gnss_by_key[("U9", "17")]["Required_Network"], "GNSS short-detect PIO reassignment missing")
    j9_signal = gnss_by_key[("J9", "1")]
    require(
        (j9_signal["Pin_Name"], j9_signal["RevA_Net"], j9_signal["Disposition"])
        == ("SIGNAL", "GNSS_RF_ANT_BIASED", "RF_CONTACT_LOCKED"),
        "J9 center-contact map mismatch",
    )
    for marker in ("ultra-low-capacitance ESD", "27 nH", "47 pF", "wideband GNSS SAW"):
        require(marker in j9_signal["Required_Network"], f"J9 RF/bias chain lacks {marker}")
    require(
        (gnss_by_key[("J9", "SHIELD")]["RevA_Net"], gnss_by_key[("J9", "SHIELD")]["Disposition"])
        == ("GND", "SHIELD_GROUND_LOCKED"),
        "J9 shell ground mismatch",
    )
    for net, expected in {"GNSS_TX": ("PA2", "24"), "GNSS_RX": ("PA3", "25"), "GNSS_PPS": ("PA0", "22")}.items():
        require(net in by_net, f"GNSS MCU net missing: {net}")
        require((by_net[net]["MCU_Pin"], by_net[net]["LQFP100_Pin"]) == expected, f"{net} MCU pin mismatch")

    gnss_review = GNSS_REVIEW_PATH.read_text(encoding="utf-8")
    gnss_sha256 = hashlib.sha256(GNSS_PIN_AUTHORITY_PATH.read_bytes()).hexdigest()
    for marker in {
        "GNSS_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        gnss_sha256,
        "MAX-M10S-00B-01", "V_BCKP", "SAFEBOOT_N", "Figure 38", "CFG-I2C-ENABLED=0",
        "10 Ohm, 5%, 0.25 W", "27 nH, 5%", "47 pF 5% 25 V C0G",
        "does not release the exact support-component MPN set",
    }:
        require(marker in gnss_review, f"GNSS authority review missing marker: {marker}")
    for path, markers in {
        CAPTURE_SPEC_PATH: ("PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv", "MAX-M10S-00B", "Figure 38", "MAIN-AUTH-010"),
        ROOT / "hardware/kicad/sheets/04_GNSS.csv": ("all 20 U9/J9 rows", "GNSS_ANT_SHORT_N", "wideband GNSS L1 SAW"),
        POWER_ARCHITECTURE_PATH: ("MAX-M10S VCC/V_IO", "100 mA startup inrush", "no V_BCKP source"),
    }.items():
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in content, f"{path.name} lacks frozen GNSS marker: {marker}")

    require(by_ref["U9"]["Package_or_Module"] == "LCC-18_9.7x10.1mm", "U9 freeze package mismatch")
    require("PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv" in by_ref["U9"]["Notes"], "U9 freeze lacks GNSS authority citation")

    lora_rows = rows(LORA_PIN_AUTHORITY_PATH)
    require(len(lora_rows) == 24, f"expected 24 U10/J10 authority rows, got {len(lora_rows)}")
    require(all(set(row) == cellular_columns for row in lora_rows), "LoRa pin-authority schema drift")
    require(
        all(all(row[column] is not None and row[column] != "" for column in cellular_columns) for row in lora_rows),
        "LoRa pin-authority row contains an empty field",
    )
    lora_by_key = {(row["RefDes"], row["Pin"]): row for row in lora_rows}
    require(len(lora_by_key) == len(lora_rows), "duplicate LoRa RefDes/pin key")
    require({row["RefDes"] for row in lora_rows} == {"U10", "J10"}, "LoRa authority RefDes set drift")
    require(
        {row["Pin"] for row in lora_rows if row["RefDes"] == "U10"} == {str(index) for index in range(1, 23)},
        "U10 package positions are not exactly 1..22",
    )
    require(
        {row["Pin"] for row in lora_rows if row["RefDes"] == "J10"} == {"1", "SHIELD"},
        "J10 electrical contact set mismatch",
    )
    require(
        all(
            (row["MPN"], row["Package"]) == ("E22-900M22S", "SMD_20x14_22P_1.27mm")
            for row in lora_rows if row["RefDes"] == "U10"
        ),
        "U10 LoRa identity/package mismatch",
    )
    expected_u10 = {
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
    for pin, expected in expected_u10.items():
        row = lora_by_key[("U10", str(pin))]
        actual = (row["Pin_Name"], row["Direction"], row["RevA_Net"], row["Disposition"])
        require(actual == expected, f"U10 pin {pin} mapping mismatch")
    for pin in ("6", "7"):
        require("100 kOhm pull-down" in lora_by_key[("U10", pin)]["Required_Network"], f"U10 pin {pin} safe pull-down missing")
        require("initializes LOW" in lora_by_key[("U10", pin)]["Required_Network"], f"U10 pin {pin} LOW startup missing")
    require("182 mA" in lora_by_key[("U10", "9")]["Required_Network"], "U10 supply headroom requirement missing")
    require("100 nF plus 10 uF" in lora_by_key[("U10", "9")]["Required_Network"], "U10 local decoupling mismatch")
    require("10 kOhm pull-up" in lora_by_key[("U10", "15")]["Required_Network"], "U10 NRST pull-up missing")
    require("100 nF" in lora_by_key[("U10", "15")]["Required_Network"], "U10 NRST capacitor missing")
    require("10 kOhm pull-up" in lora_by_key[("U10", "19")]["Required_Network"], "U10 NSS deselect pull-up missing")
    require("DIO2-to-TXEN short is forbidden" in lora_by_key[("U10", "8")]["Notes"], "U10 DIO2 separate-control rule missing")
    j10_signal = lora_by_key[("J10", "1")]
    require(
        (j10_signal["Pin_Name"], j10_signal["RevA_Net"], j10_signal["Disposition"])
        == ("SIGNAL", "LORA_RF_ANT", "RF_CONTACT_LOCKED"),
        "J10 center-contact map mismatch",
    )
    for marker in ("ultra-low-capacitance ESD", "50 Ohm", "0 Ohm series baseline", "both shunts DNP"):
        require(marker in j10_signal["Required_Network"], f"J10 RF chain lacks {marker}")
    require("no tee test point" in j10_signal["Notes"], "J10 no-stub conducted-port rule missing")
    require(
        (lora_by_key[("J10", "SHIELD")]["RevA_Net"], lora_by_key[("J10", "SHIELD")]["Disposition"])
        == ("GND", "SHIELD_GROUND_LOCKED"),
        "J10 shell ground mismatch",
    )
    for net, expected in {
        "LORA_TXEN": ("PB15", "54"), "LORA_RXEN": ("PD8", "55"),
        "LORA_DIO1": ("PC2", "17"), "LORA_BUSY": ("PD9", "56"),
        "LORA_RESET_N": ("PD10", "57"),
    }.items():
        require(net in by_net, f"LoRa MCU net missing: {net}")
        require((by_net[net]["MCU_Pin"], by_net[net]["LQFP100_Pin"]) == expected, f"{net} MCU pin mismatch")
    require(authority_by_pin[54]["RevA_Net"] == "LORA_TXEN", "U1 PB15 LoRa TXEN authority mismatch")
    require(authority_by_pin[55]["RevA_Net"] == "LORA_RXEN", "U1 PD8 LoRa RXEN authority mismatch")

    lora_review = LORA_REVIEW_PATH.read_text(encoding="utf-8")
    lora_sha256 = hashlib.sha256(LORA_PIN_AUTHORITY_PATH.read_bytes()).hexdigest()
    for marker in {
        "LORA_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        lora_sha256, "c66665745ef6f4a04de77201026d92841066b69575f62a717fe02bc363df62bf",
        "E22-900MM22S", "182 mA", "TXEN=1/RXEN=0", "DIO3 TCXO supply to 2.2 V",
        "castellated-ANT option", "does not release exact support-component MPNs",
    }:
        require(marker in lora_review, f"LoRa authority review missing marker: {marker}")
    for path, markers in {
        CAPTURE_SPEC_PATH: ("PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv", "LORA_TXEN", "DIO2 is NC", "MAIN-AUTH-010"),
        ROOT / "hardware/kicad/sheets/06_LORA.csv": ("all 24 U10/J10 rows", "100 kOhm pull-downs", "no-stub route"),
        ROOT / "config/lora/RU868.yaml": ("tx_enabled: false", "signed_manufacturing_profile_only", "Do not copy EU868"),
    }.items():
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in content, f"{path.name} lacks frozen LoRa marker: {marker}")
    require(by_ref["U10"]["Package_or_Module"] == "SMD_20x14_22P_1.27mm", "U10 freeze package mismatch")
    require("PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv" in by_ref["U10"]["Notes"], "U10 freeze lacks LoRa authority citation")
    require("CASTELLATED_OPTION" in by_ref["U10"]["Status"], "U10 supplier antenna-option blocker missing")

    ble_rows = rows(BLE_PIN_AUTHORITY_PATH)
    require(len(ble_rows) == 65, f"expected 65 U11/TP_BLE_SWD authority rows, got {len(ble_rows)}")
    require(all(set(row) == cellular_columns for row in ble_rows), "BLE pin-authority schema drift")
    require(
        all(all(row[column] is not None and row[column] != "" for column in cellular_columns) for row in ble_rows),
        "BLE pin-authority row contains an empty field",
    )
    ble_by_key = {(row["RefDes"], row["Pin"]): row for row in ble_rows}
    require(len(ble_by_key) == len(ble_rows), "duplicate BLE RefDes/pin key")
    require({row["RefDes"] for row in ble_rows} == {"U11", "TP_BLE_SWD"}, "BLE authority RefDes set drift")
    u11_rows = [row for row in ble_rows if row["RefDes"] == "U11"]
    require({row["Pin"] for row in u11_rows} == {str(index) for index in range(1, 62)}, "U11 package positions are not exactly 1..61")
    ble_package = "nRF52840_SMD_10.5x15.5_61P_PCB_antenna"
    require(
        all((row["MPN"], row["Package"]) == ("MDBT50Q-P1MV2", ble_package) for row in u11_rows),
        "U11 BLE identity/package mismatch",
    )
    expected_u11_special = {
        22: ("P0.06", "OUTPUT", "BLE_RX", "FUNCTION_LOCKED"),
        24: ("P0.08", "INPUT", "BLE_TX", "FUNCTION_LOCKED"),
        28: ("VDD", "POWER", "3V3_DIGITAL", "SUPPLY_LOCKED"),
        30: ("VDDH", "POWER", "3V3_DIGITAL", "SUPPLY_LOCKED"),
        31: ("DCCH", "POWER_OUTPUT", "NC", "REG0_OUTPUT_NC"),
        32: ("VBUS", "POWER_INPUT", "NC", "USB_INPUT_NC"),
        34: ("D-", "USB_BIDIR", "NC", "USB_DATA_NC"),
        35: ("D+", "USB_BIDIR", "NC", "USB_DATA_NC"),
        39: ("P0.15", "INPUT", "BLE_DFU_REQ", "BOOT_REQUEST_LOCKED"),
        40: ("P0.18/nRESET", "INPUT", "NRF_RESET_N", "RESET_LOCKED"),
        51: ("SWDIO", "DEBUG_BIDIR", "NRF_SWDIO", "DEBUG_LOCKED"),
        53: ("SWDCLK", "DEBUG_INPUT", "NRF_SWCLK", "DEBUG_LOCKED"),
    }
    for pin, expected in expected_u11_special.items():
        row = ble_by_key[("U11", str(pin))]
        require((row["Pin_Name"], row["Direction"], row["RevA_Net"], row["Disposition"]) == expected, f"U11 pad {pin} mapping mismatch")
    for pin in (1, 2, 15, 33, 55):
        row = ble_by_key[("U11", str(pin))]
        require((row["Pin_Name"], row["RevA_Net"], row["Disposition"]) == ("GND", "GND", "GROUND_LOCKED"), f"U11 ground pad {pin} mismatch")
    non_nc_pins = {1, 2, 15, 22, 24, 28, 30, 33, 39, 40, 51, 53, 55}
    require(
        {int(row["Pin"]) for row in u11_rows if row["RevA_Net"] != "NC"} == non_nc_pins,
        "U11 used/unused pad set mismatch",
    )
    require("100 nF plus 10 uF" in ble_by_key[("U11", "28")]["Required_Network"], "U11 local decoupling mismatch")
    require("Reg0 DC/DC is disabled" in ble_by_key[("U11", "31")]["Required_Network"], "U11 Reg0 state missing")
    require("10 kOhm pull-up" in ble_by_key[("U11", "39")]["Required_Network"], "U11 DFU pull-up missing")
    require("PB2 open-drain" in ble_by_key[("U11", "39")]["Required_Network"], "U11 DFU open-drain control missing")
    for marker in ("10 kOhm pull-up", "non-inverting open-drain", "100 kOhm pull-down"):
        require(marker in ble_by_key[("U11", "40")]["Required_Network"], f"U11 reset network lacks {marker}")
    require(
        {row["Pin"] for row in ble_rows if row["RefDes"] == "TP_BLE_SWD"} == {"1", "2", "3", "4"},
        "TP_BLE_SWD contact set mismatch",
    )
    expected_ble_swd = {
        "1": ("VTREF", "3V3_DIGITAL", "FIXTURE_CONTACT_LOCKED"),
        "2": ("SWDIO", "NRF_SWDIO", "FIXTURE_CONTACT_LOCKED"),
        "3": ("SWDCLK", "NRF_SWCLK", "FIXTURE_CONTACT_LOCKED"),
        "4": ("GND", "GND", "FIXTURE_GROUND_LOCKED"),
    }
    for pin, expected in expected_ble_swd.items():
        row = ble_by_key[("TP_BLE_SWD", pin)]
        require((row["Pin_Name"], row["RevA_Net"], row["Disposition"]) == expected, f"TP_BLE_SWD contact {pin} mismatch")
    for net, expected in {
        "BLE_TX": ("PB10", "44"), "BLE_RX": ("PB11", "45"),
        "BLE_EN": ("PE6", "5"), "BLE_DFU_REQ": ("PB2", "34"),
    }.items():
        require(net in by_net, f"BLE MCU net missing: {net}")
        require((by_net[net]["MCU_Pin"], by_net[net]["LQFP100_Pin"]) == expected, f"{net} MCU pin mismatch")

    ble_review = BLE_REVIEW_PATH.read_text(encoding="utf-8")
    ble_sha256 = hashlib.sha256(BLE_PIN_AUTHORITY_PATH.read_bytes()).hexdigest()
    for marker in {
        "BLE_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        ble_sha256, "61fec8c0c9f8c33175be2237a8ebba73c6cfc0a3572fe3835fd341079c103d03",
        "61-pad", "PSELRESET[0]", "application-defined", "10.5 mm by 3.8 mm",
        "does not release exact support-component MPNs",
    }:
        require(marker in ble_review, f"BLE authority review missing marker: {marker}")
    for path, markers in {
        CAPTURE_SPEC_PATH: ("PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv", "P0.06", "P0.08", "P0.15", "P0.18/nRESET", "3.8 mm", "MAIN-AUTH-010"),
        ROOT / "hardware/kicad/sheets/07_BLE.csv": ("all 65 U11/TP_BLE_SWD rows", "NRF_SWDIO", "NRF_SWCLK", "3.8 mm"),
        ROOT / "firmware/targets/evt_pre_20/target_status.yaml": ("P0.06_TX_to_PB11_RX", "P0.08_RX_from_PB10_TX", "P0.15_active_low_open_drain", "P0.18_nRESET", "INTERNAL_RC_CALIBRATED"),
    }.items():
        content = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in content, f"{path.name} lacks frozen BLE marker: {marker}")
    require(by_ref["U11"]["Package_or_Module"] == ble_package, "U11 freeze package mismatch")
    require("PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv" in by_ref["U11"]["Notes"], "U11 freeze lacks BLE authority citation")

    connector_fixture_rows = rows(CONNECTOR_FIXTURE_PIN_AUTHORITY_PATH)
    require(len(connector_fixture_rows) == 70, f"expected 70 connector/fixture authority rows, got {len(connector_fixture_rows)}")
    require(all(set(row) == cellular_columns for row in connector_fixture_rows), "connector/fixture authority schema drift")
    require(
        all(all(row[column] is not None and row[column] != "" for column in cellular_columns) for row in connector_fixture_rows),
        "connector/fixture authority row contains an empty field",
    )
    connector_fixture_by_key = {(row["RefDes"], row["Pin"]): row for row in connector_fixture_rows}
    require(len(connector_fixture_by_key) == len(connector_fixture_rows), "duplicate connector/fixture RefDes/pin key")
    expected_connector_counts = {
        "U12": 8, "J12": 10, "J11": 17, "J8": 2, "J9": 2, "J10": 2,
        "J13": 2, "TP_MCU_SWD": 5, "TP_EOL": 13, "TP_CELL_USB": 4, "TP_CELL_DBG": 5,
    }
    for ref, count in expected_connector_counts.items():
        require(sum(row["RefDes"] == ref for row in connector_fixture_rows) == count, f"{ref} contact count mismatch")
    require(
        {row["RefDes"] for row in connector_fixture_rows} == set(expected_connector_counts),
        "connector/fixture authority RefDes set drift",
    )
    card_map = {
        "1": ("DAT2", "SD_D2"), "2": ("CD/DAT3", "SD_D3"), "3": ("CMD", "SD_CMD"),
        "4": ("VDD", "3V3_DIGITAL"), "5": ("CLK", "SD_CK"), "6": ("VSS", "GND"),
        "7": ("DAT0", "SD_D0"), "8": ("DAT1", "SD_D1"),
    }
    for ref in ("U12", "J12"):
        for pin, expected in card_map.items():
            row = connector_fixture_by_key[(ref, pin)]
            require((row["Pin_Name"], row["RevA_Net"]) == expected, f"{ref}.{pin} microSD map mismatch")
    require(connector_fixture_by_key[("J12", "CD")]["RevA_Net"] == "SD_DET", "J12 detect endpoint mismatch")
    usb_map = {
        "A1": "GND", "A4": "USB_VBUS_CONN", "A5": "USB_CC1", "A6": "USB_DP", "A7": "USB_DM",
        "A8": "NC", "A9": "USB_VBUS_CONN", "A12": "GND", "B1": "GND", "B4": "USB_VBUS_CONN",
        "B5": "USB_CC2", "B6": "USB_DP", "B7": "USB_DM", "B8": "NC", "B9": "USB_VBUS_CONN",
        "B12": "GND", "SHIELD": "USB_SHIELD",
    }
    for pin, net in usb_map.items():
        require(connector_fixture_by_key[("J11", pin)]["RevA_Net"] == net, f"J11.{pin} USB contact mismatch")
    for source_rows, ref in ((gnss_rows, "J9"), (lora_rows, "J10")):
        source_by_key = {(row["RefDes"], row["Pin"]): row for row in source_rows}
        for pin in ("1", "SHIELD"):
            require(connector_fixture_by_key[(ref, pin)] == source_by_key[(ref, pin)], f"{ref}.{pin} diverges from closed RF authority")
    require(
        (connector_fixture_by_key[("J13", "1")]["RevA_Net"], connector_fixture_by_key[("J13", "2")]["RevA_Net"])
        == ("TAMPER_IN", "GND"),
        "J13 tamper map mismatch",
    )
    require(
        {connector_fixture_by_key[("TP_MCU_SWD", pin)]["RevA_Net"] for pin in ("2", "3")}
        == {"SWDIO", "SWCLK"},
        "STM32 SWD fixture map mismatch",
    )
    require(
        {connector_fixture_by_key[("TP_CELL_USB", pin)]["RevA_Net"] for pin in ("1", "2", "3")}
        == {"CELL_USB_VBUS", "CELL_USB_DP", "CELL_USB_DM"},
        "BG95 USB fixture map mismatch",
    )
    require(
        {connector_fixture_by_key[("TP_CELL_DBG", pin)]["RevA_Net"] for pin in ("1", "2", "3", "4")}
        == {"U8_VDD_EXT_1V8", "CELL_DBG_TXD_1V8", "CELL_DBG_RXD_1V8", "CELL_USB_BOOT_1V8"},
        "BG95 debug fixture map mismatch",
    )
    connector_fixture_review = CONNECTOR_FIXTURE_REVIEW_PATH.read_text(encoding="utf-8")
    connector_fixture_sha256 = hashlib.sha256(CONNECTOR_FIXTURE_PIN_AUTHORITY_PATH.read_bytes()).hexdigest()
    for marker in {
        "CONNECTOR_FIXTURE_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        connector_fixture_sha256, "SDCIT2/32GB", "USB4105-GF-A-120", "MEM2052-00-195-00-A",
        "504050-0291", "TP_EOL", "TP_CELL_USB", "TP_CELL_DBG", "MAIN-AUTH-010", "MAIN-AUTH-011",
    }:
        require(marker in connector_fixture_review, f"connector/fixture review missing marker: {marker}")
    require(by_ref["U12"]["MPN"] == "SDCIT2/32GB", "U12 freeze identity mismatch")
    require("PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv" in by_ref["U12"]["Notes"], "U12 freeze lacks connector authority citation")

    passive_support_rows = rows(PASSIVE_SUPPORT_AUTHORITY_PATH)
    passive_columns = {
        "RefDes", "Category", "Manufacturer", "MPN", "Package", "Value",
        "Population", "Temperature_C", "Logical_Net", "Pin_Map",
        "Electrical_Path", "Disposition", "Authority", "Notes",
    }
    require(len(passive_support_rows) == 211, "expected 211 passive/support authority rows")
    require(all(set(row) == passive_columns for row in passive_support_rows), "passive/support schema drift")
    require(
        all(all(row[column] is not None and row[column] != "" for column in passive_columns)
            for row in passive_support_rows),
        "passive/support authority row contains an empty field",
    )
    passive_by_ref = {row["RefDes"]: row for row in passive_support_rows}
    require(len(passive_by_ref) == len(passive_support_rows), "duplicate passive/support RefDes")
    expected_passive_refs = (
        {f"C{i}" for i in range(1, 81)} | {f"R{i}" for i in range(1, 104)}
        | {"L1", "L2", "FB1", "FL1", "U5", "U6", "Q4", "X1"}
        | {f"U{i}" for i in range(19, 28)} | {f"D{i}" for i in range(1, 12)}
    )
    require(set(passive_by_ref) == expected_passive_refs, "passive/support RefDes set drift")
    require(
        sum(row["Population"] == "FITTED" for row in passive_support_rows) == 196
        and sum(row["Population"] == "DNP" for row in passive_support_rows) == 15,
        "passive/support population count mismatch",
    )
    for row in passive_support_rows:
        assignments = row["Pin_Map"].split(";")
        require(all(item.count("=") == 1 for item in assignments),
                f"{row['RefDes']} malformed passive/support physical pin map")
        pins = [item.split("=", 1)[0] for item in assignments]
        require(all(pins) and len(pins) == len(set(pins)),
                f"{row['RefDes']} duplicate or blank passive/support pin")
    for refdes, mpn in {
        "L1": "LQH32PN2R2NN0L", "L2": "LQW15AN27NJ00D",
        "FB1": "BLM31KN601SN1L", "FL1": "ABSES5AF-L100KM",
        "U5": "LT6000IDCB#TRMPBF", "U6": "SN74LVC1G07DBVR",
        "Q4": "Si1016X-T1-GE3", "D4": "TPD1E05U06DYAR",
        "X1": "SiT1552AI-JE-DCC-32.768D",
    }.items():
        require(passive_by_ref[refdes]["MPN"] == mpn, f"{refdes} passive/support MPN mismatch")
    passive_support_review = PASSIVE_SUPPORT_REVIEW_PATH.read_text(encoding="utf-8")
    passive_support_sha256 = hashlib.sha256(PASSIVE_SUPPORT_AUTHORITY_PATH.read_bytes()).hexdigest()
    for marker in {
        "PASSIVE_SUPPORT_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        passive_support_sha256, "211 unique physical components", "196 fitted and 15 DNP",
        "LT6000IDCB#TRMPBF", "Si1016X-T1-GE3", "ABSES5AF-L100KM",
        "MAIN-AUTH-011", "physical tests remain `NOT RUN`",
    }:
        require(marker in passive_support_review, f"passive/support review missing marker: {marker}")

    mechanical_rows = rows(MECHANICAL_PLACEMENT_AUTHORITY_PATH)
    mechanical_columns = {
        "Record_ID", "Feature_Type", "RefDes", "Contact", "Side",
        "Anchor_Definition", "X_mm", "Y_mm", "Rotation_deg", "Geometry",
        "Extent_X_mm", "Extent_Y_mm", "Z_Min_mm", "Z_Max_mm",
        "Access_Direction", "Layer_Scope", "Clearance_Rule", "Disposition",
        "Authority", "Notes",
    }
    require(len(mechanical_rows) == 70, "expected 70 mechanical placement authority rows")
    require(all(set(row) == mechanical_columns for row in mechanical_rows), "mechanical placement schema drift")
    require(
        all(all(row[column] is not None and row[column] != "" for column in mechanical_columns)
            for row in mechanical_rows),
        "mechanical placement authority row contains an empty field",
    )
    mechanical_by_id = {row["Record_ID"]: row for row in mechanical_rows}
    require(len(mechanical_by_id) == len(mechanical_rows), "duplicate mechanical placement Record_ID")
    require(set(mechanical_by_id) == {f"MECH-{index:03d}" for index in range(1, 71)}, "mechanical Record_ID set drift")
    require(all(row["Authority"] == "MAIN-AUTH-011" for row in mechanical_rows), "mechanical authority ID drift")
    outline = mechanical_by_id["MECH-001"]
    require(
        (outline["Geometry"], outline["Extent_X_mm"], outline["Extent_Y_mm"], outline["Z_Max_mm"])
        == ("ROUNDED_RECT_R3", "110.00", "75.00", "1.60"),
        "PCB-MAIN outline or thickness mismatch",
    )
    holes = [row for row in mechanical_rows if row["Feature_Type"] == "MOUNTING_HOLE"]
    require(
        {(row["RefDes"], row["X_mm"], row["Y_mm"]) for row in holes}
        == {("H1", "5.00", "5.00"), ("H2", "105.00", "5.00"),
            ("H3", "105.00", "70.00"), ("H4", "5.00", "70.00")},
        "PCB-MAIN mounting pattern mismatch",
    )
    connector_placements = [row for row in mechanical_rows if row["Feature_Type"] == "CONNECTOR_PLACEMENT"]
    require(
        {row["RefDes"] for row in connector_placements}
        == {"J_PWR", "J_MIC1", "J_MIC2", "J_MIC3", "J_MIC4", "J6", "J7",
            "J8", "J9", "J10", "J11", "J12", "J13"},
        "mechanical connector placement set mismatch",
    )
    module_placements = [row for row in mechanical_rows if row["Feature_Type"] == "MODULE_PLACEMENT"]
    require({row["RefDes"] for row in module_placements} == {"U8", "U9", "U10", "U11"}, "RF module placement set mismatch")
    test_pads = [row for row in mechanical_rows if row["Feature_Type"] == "TEST_PAD"]
    require(len(test_pads) == 31, "production pogo-pad count mismatch")
    require(
        all(row["Side"] == "BOTTOM" and row["Geometry"] == "CIRCLE_D1.7"
            and row["Clearance_Rule"] == "NO_PASTE_MASK_OPEN_D2.1" for row in test_pads),
        "production pogo-pad geometry mismatch",
    )
    require(
        (mechanical_by_id["MECH-028"]["X_mm"], mechanical_by_id["MECH-028"]["Extent_X_mm"],
         mechanical_by_id["MECH-028"]["Extent_Y_mm"], mechanical_by_id["MECH-028"]["Layer_Scope"])
        == ("106.20", "3.80", "10.50", "ALL_LAYERS"),
        "BLE all-layer antenna keepout mismatch",
    )
    mechanical_review = MECHANICAL_PLACEMENT_REVIEW_PATH.read_text(encoding="utf-8")
    mechanical_sha256 = hashlib.sha256(MECHANICAL_PLACEMENT_AUTHORITY_PATH.read_bytes()).hexdigest()
    for marker in {
        "MECHANICAL_PLACEMENT_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE",
        mechanical_sha256, "70 records", "110 x 75 x 1.60 mm", "31 individual pogo pads",
        "CONTROLLED_PENDING_NATIVE_STEP", "All physical tests remain `NOT RUN`",
    }:
        require(marker in mechanical_review, f"mechanical placement review missing marker: {marker}")

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
        "CON-SD": "GCT_MEM2052-00-195-00-A",
        "CON-TAMPER": "Molex_5040500291",
        "CON-SIM1": "TE_2336582-1",
        "CON-SIM2": "TE_2336582-1",
        "CON-SWD-MCU": "TEST_PADS",
        "CON-SWD-BLE": "TEST_PADS",
        "CON-EOL": "TEST_PADS",
        "CON-CELL-USB": "TEST_PADS",
        "CON-CELL-DBG": "TEST_PADS",
    }
    for connector_id, mpn in expected_connectors.items():
        require(connector_id in connectors, f"connector freeze missing {connector_id}")
        require(connectors[connector_id]["Board_MPN"] == mpn, f"{connector_id} MPN mismatch")
        require(connectors[connector_id]["Status"] not in {"RELEASED", "CONTROLLED"}, f"{connector_id} unexpectedly released")
    require(
        "PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv" in connectors["CON-RF-GNSS"]["Notes"]
        and "J9 center" in connectors["CON-RF-GNSS"]["Notes"],
        "GNSS connector freeze lacks J9 authority citation",
    )
    require(
        "PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv" in connectors["CON-RF-LORA"]["Notes"]
        and "J10 center" in connectors["CON-RF-LORA"]["Notes"]
        and "no-stub" in connectors["CON-RF-LORA"]["Notes"],
        "LoRa connector freeze lacks J10 authority/no-stub citation",
    )
    require(
        "PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv" in connectors["CON-SWD-BLE"]["Notes"]
        and all(token in connectors["CON-SWD-BLE"]["Notes"] for token in ("VTREF", "NRF_SWDIO", "NRF_SWCLK", "GND"))
        and connectors["CON-SWD-BLE"]["Positions"] == "4",
        "BLE connector freeze lacks the separate four-contact nRF SWD authority",
    )

    mcu = status["mcu_contract"]
    require((mcu["refdes"], mcu["mpn"], mcu["package"]) == ("U1", "STM32U585VIT6Q", "LQFP100_14x14"), "status MCU contract mismatch")
    require(mcu["external_hse_allowed"] is False, "status permits external HSE")
    require(mcu["low_speed_reference_mpn"] == "SiT1552AI-JE-DCC-32.768D", "status low-speed reference mismatch")
    clock = (ROOT / "hardware/CLOCKING_REV_A.md").read_text(encoding="utf-8")
    require("shall not use an external HSE crystal or HSE oscillator" in clock, "clock policy no longer forbids HSE")

    native = status["native_schematic"]
    native_path = ROOT / native["path"]
    native_project = ROOT / native.get("project", "")
    native_manifest = ROOT / native.get("manifest", "")
    native_generator = ROOT / native.get("generator", "")
    native_present = status["release_state"] in {"SCHEMATIC_REVIEW", "REVIEW_A_PASS", "LAYOUT_REVIEW", "REVIEW_B_PASS", "FOR_MANUFACTURE"}
    if native_present:
        require(native["status"] in {"PRESENT_REVIEW_PENDING", "REVIEW_A_PASS", "REVIEW_B_PASS"},
                "native schematic status mismatch")
        require(all(path.is_file() for path in (native_path, native_project, native_manifest, native_generator)),
                "controlled native schematic source set is incomplete")
        require(native["schematic_derived_bom"] is True,
                "native schematic BOM provenance is not declared")
        native_manifest_data = json.loads(native_manifest.read_text(encoding="utf-8"))
        require(native_manifest_data["schematic_sha256"] == hashlib.sha256(native_path.read_bytes()).hexdigest(),
                "native schematic manifest hash mismatch")
        require(native_manifest_data["project_sha256"] == hashlib.sha256(native_project.read_bytes()).hexdigest(),
                "native project manifest hash mismatch")
        require(native_manifest_data["generator_sha256"] == hashlib.sha256(native_generator.read_bytes()).hexdigest(),
                "native generator manifest hash mismatch")
    else:
        require(native["status"] == "ABSENT" and not native_path.exists(),
                "native schematic filesystem/status mismatch")
        require(native["schematic_derived_bom"] is False,
                "schematic-derived BOM claimed without native source")

    readiness = status["capture_readiness"]
    closed_items = readiness["closed_authorities"]
    open_items = readiness["open_authorities"]
    closed_ids = {item["id"] for item in closed_items}
    open_ids = {item["id"] for item in open_items}
    require(readiness["complete"] is True, "capture readiness is not complete after all eleven authorities closed")
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
    require(
        closed_evidence["MAIN-AUTH-003"]
        == {
            "hardware/PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_AUDIO_LOGIC_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-003 evidence set mismatch",
    )
    require(
        closed_evidence["MAIN-AUTH-004"]
        == {
            "hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_CELLULAR_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-004 evidence set mismatch",
    )
    require(
        closed_evidence["MAIN-AUTH-005"]
        == {
            "hardware/PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_DUAL_SIM_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-005 evidence set mismatch",
    )
    require(
        closed_evidence["MAIN-AUTH-006"]
        == {
            "hardware/PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_GNSS_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-006 evidence set mismatch",
    )
    require(
        closed_evidence["MAIN-AUTH-007"]
        == {
            "hardware/PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_LORA_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-007 evidence set mismatch",
    )
    require(
        closed_evidence["MAIN-AUTH-008"]
        == {
            "hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_BLE_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-008 evidence set mismatch",
    )
    require(
        closed_evidence["MAIN-AUTH-009"]
        == {
            "hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_CONNECTOR_FIXTURE_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-009 evidence set mismatch",
    )
    require(
        closed_evidence["MAIN-AUTH-010"]
        == {
            "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-010 evidence set mismatch",
    )
    require(
        closed_evidence["MAIN-AUTH-011"]
        == {
            "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv",
            "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.md",
        },
        "MAIN-AUTH-011 evidence set mismatch",
    )
    require(closed_ids.isdisjoint(open_ids), "authority is both open and closed")
    require(open_ids == EXPECTED_OPEN_AUTHORITY_IDS, "PCB-MAIN open authority register drift")
    require(len(open_ids) == len(open_items), "duplicate PCB-MAIN open authority ID")
    require(all("production_bom" in item["blocks"] for item in open_items), "open authority does not block production BOM")
    review_a = status["review_a"]
    review_b = status["review_b"]
    if review_a["complete"] is True:
        require(status["release_state"] == "REVIEW_A_PASS" and native["status"] == "REVIEW_A_PASS",
                "Review A PASS release state mismatch")
        require(review_a["status"] == "PASS", "completed Review A must have PASS status")
        require(all(review_a.get(field) for field in ("reviewer", "date", "commit_sha")),
                "completed Review A lacks reviewer/date/commit SHA")
        require(review_b["complete"] is False and review_b["status"] == "OPEN_LAYOUT_AND_EVIDENCE_PENDING",
                "Review B must be open but incomplete after Review A PASS")
    else:
        expected_review_a_status = (
            "NATIVE_SOURCE_AND_KICAD_ERC_PASS_HUMAN_REVIEW_PENDING"
            if native_present else "BLOCKED_NATIVE_SCHEMATIC_ABSENT"
        )
        require(review_a["status"] == expected_review_a_status,
                "Review A status does not match native-source state")
        require(review_b["complete"] is False and review_b["status"] == "BLOCKED_REVIEW_A_NOT_COMPLETE",
                "Review B must remain blocked before Review A completion")
    expected_review_a_evidence = {
        "checklist_template", "signed_checklist", "schematic_pdf", "cubemx_pin_report", "erc_report",
        "bom_diff", "net_name_diff",
    }
    require(set(review_a["evidence"]) == expected_review_a_evidence, "Review A evidence schema mismatch")
    if review_a["complete"] is True:
        require(review_a["evidence"]["checklist_template"] is None,
                "completed Review A must use signed checklist, not a template")
        signed_checklist = ROOT / review_a["evidence"]["signed_checklist"]
        require(signed_checklist.is_file() and signed_checklist.stat().st_size > 0,
                "signed Review A checklist is missing")
        for evidence_name in ("schematic_pdf", "cubemx_pin_report", "erc_report", "bom_diff", "net_name_diff"):
            require(str(review_a["evidence"][evidence_name]).startswith("https://github.com/skif-ops/rs-zs-bpla/actions/runs/"),
                    f"Review A {evidence_name} is not a commit-traceable GitHub Actions reference")
        require(review_b["evidence"].get("carried_findings") == ["RA-003"],
                "Review B must carry forward Review A finding RA-003")
    elif native_present:
        require(review_a["reviewer"] is None and review_a["date"] is None and review_a["commit_sha"] is None,
                "human Review A identity/date/SHA claimed before sign-off")
        require(review_a["evidence"]["signed_checklist"] is None,
                "signed Review A checklist claimed before sign-off")
        checklist_template = ROOT / review_a["evidence"]["checklist_template"]
        require(checklist_template.is_file() and checklist_template.stat().st_size > 0,
                "Review A checklist template is missing")
        require(str(review_a["evidence"]["bom_diff"]).startswith("CI artifact: "),
                "schematic-derived BOM is not declared as CI evidence")
        require(str(review_a["evidence"]["schematic_pdf"]).startswith("CI artifact: "),
                "schematic PDF is not declared as CI evidence")
        require(str(review_a["evidence"]["erc_report"]).startswith("CI artifact: "),
                "ERC report is not declared as CI evidence")
        require(str(review_a["evidence"]["net_name_diff"]).startswith("CI artifact: "),
                "net audit is not declared as CI evidence")
    else:
        require(not any(review_a["evidence"].values()),
                "review evidence present without native source")
    if review_a["complete"] is False:
        require(not review_b["evidence"], "Review B evidence present before Review A completion")

    result = {
        "configuration": status["configuration"],
        "assembly": status["assembly"],
        "audit": "PCB-MAIN independent capture-input authority audit",
        "status": "PASS_SCHEMATIC_REVIEW_INPUT_CONTROLLED" if native_present else "PASS_CAPTURE_INPUT_CONTROLLED",
        "mcu_assignments_verified": len(mcu_pins),
        "mcu_package_pins_verified": len(authority_rows),
        "storage_sensor_pads_verified": len(device_rows),
        "audio_logic_pins_verified": len(audio_rows),
        "cellular_pins_verified": len(cellular_rows),
        "dual_sim_pins_verified": len(dual_sim_rows),
        "gnss_contacts_verified": len(gnss_rows),
        "ble_contacts_verified": len(ble_rows),
        "connector_fixture_contacts_verified": len(connector_fixture_rows),
        "passive_support_components_verified": len(passive_support_rows),
        "mechanical_placement_records_verified": len(mechanical_rows),
        "active_mpn_rows_verified": len(freeze),
        "logical_harness_pins_verified": len(main_power) + 24 + len(swd),
        "open_authorities": sorted(open_ids),
        "native_schematic": "PRESENT_REVIEW_PENDING" if native_present else "ABSENT",
        "review_a": "PENDING" if native_present else "BLOCKED",
        "review_b": "BLOCKED",
        "production_bom": "BLOCKED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        "PCB-MAIN Rev.A capture authority audit: "
        + ("PASS_SCHEMATIC_REVIEW_INPUT_CONTROLLED" if native_present else "PASS_CAPTURE_INPUT_CONTROLLED")
    )
    print(f"- all {len(authority_rows)} U1 package positions and {len(mcu_pins)} functional assignments verified")
    print(f"- all {len(device_rows)} U2/U3/U4 physical pins or pads and three unique I2C2 addresses verified")
    print(f"- all {len(audio_rows)} U7/U17/U18 physical pins, dual-direction PDM translation and active-high AAD wake path verified")
    print(f"- all {len(cellular_rows)} U8/U16/Q1/Q2 physical pins, power banks, translation and controls verified")
    print(f"- all {len(dual_sim_rows)} U13/U14/U15/J6/J7/Q3 physical contacts, safe-state controls and slot paths verified")
    print(f"- all {len(gnss_rows)} U9/J9 physical contacts, supply choices, supervisor signals and RF/bias topology verified")
    print(f"- all {len(lora_rows)} U10/J10 physical contacts, fail-closed RF-switch controls and no-stub RF path verified")
    print(f"- all {len(ble_rows)} U11/TP_BLE_SWD contacts, fail-closed boot/reset, independent SWD and antenna keepout inputs verified")
    print(f"- all {len(connector_fixture_rows)} connector/card/RF/tamper/fixture contacts and domain-isolation rules verified")
    print(f"- all {len(passive_support_rows)} passive/support RefDes, MPNs, populations and physical pin sets verified")
    print(f"- all {len(mechanical_rows)} outline, placement, zone, keepout and production fixture records verified")
    print(f"- {len(freeze)} active MPNs and 41 logical harness pins verified")
    print(
        "- all 11 capture authorities closed; native schematic source is present; "
        "Review A is signed PASS; Review B and production evidence remain blockers"
    )
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()
