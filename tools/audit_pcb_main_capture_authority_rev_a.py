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

EXPECTED_AUTHORITATIVE_INPUTS = {
    "config/EVT_PRE_20_BASELINE.yaml",
    "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv",
    "hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv",
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
EXPECTED_OPEN_AUTHORITY_IDS = {f"MAIN-AUTH-{index:03d}" for index in range(1, 12)}


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
    open_items = readiness["open_authorities"]
    open_ids = {item["id"] for item in open_items}
    require(readiness["complete"] is False, "capture readiness released with open authorities")
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
    print(f"- 65 MCU assignments, {len(freeze)} active MPNs and 41 logical harness pins verified")
    print(f"- {len(open_items)} missing pad/mechanical authorities remain explicit production blockers")
    print(f"report: {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")


if __name__ == "__main__":
    main()
