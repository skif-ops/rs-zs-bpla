#!/usr/bin/env python3
"""Cross-check EVT-PRE-20 Rev.A component/connector freeze tables.

This gate validates internal consistency only. It does not turn pending parts into a
manufacturing release and preserves procurement/RF/SI/mechanical blockers.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rows(path: str) -> list[dict[str, str]]:
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def main() -> None:
    power = {r["Component_ID"]: r for r in rows("hardware/POWER_COMPONENT_FREEZE_REV_A.csv")}
    main_parts = {r["RefDes"]: r for r in rows("hardware/MAIN_COMPONENT_FREEZE_REV_A.csv")}
    connectors = {r["Connector_ID"]: r for r in rows("hardware/CONNECTOR_FREEZE_REV_A.csv")}
    pinmap = {r["Net"]: r for r in rows("hardware/EVT_PRE_20_PIN_MAP_REV_A.csv")}
    harness = rows("hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv")
    inputs = {r["Input_ID"]: r for r in rows("docs/OPEN_INPUTS_FOR_FREEZE.csv")}
    decisions = {r["Decision_ID"]: r for r in rows("docs/DECISION_LOG.csv")}
    baseline = (ROOT / "config/EVT_PRE_20_BASELINE.yaml").read_text(encoding="utf-8")

    require(inputs["IN-006"]["Status"] == "LOCKED", "operating temperature input IN-006 is not locked")
    require(decisions["DEC-019"]["Status"] == "LOCKED", "DEC-019 operating range decision is not locked")
    require("operating_ambient_c: [-40, 70]" in baseline, "baseline operating range is not -40..+70 C")
    require("electronic_component_minimum_rating_c: [-40, 85]" in baseline, "component temperature derating rule missing")
    require("lifepo4_charge_below_0c: PROHIBITED" in baseline, "low-temperature LiFePO4 charge prohibition missing")

    expected_power = {
        "PWR-REV-CTL": "LM74700QDBVRQ1",
        "PWR-REV-FET": "CSD18540Q5B",
        "U-PWR1": "LMR604403SRAKR",
        "U-PWR2": "LMR604403SRAKR",
        "U-PWR3": "TPS7A2018PDBVR",
    }
    for key, mpn in expected_power.items():
        require(key in power, f"missing power component {key}")
        require(power[key]["MPN"] == mpn, f"{key} MPN mismatch")
        require("OPEN" not in power[key]["Status"], f"{key} unexpectedly OPEN")

    expected_main = {
        "U1": "STM32U585VIT6Q",
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
    for ref, mpn in expected_main.items():
        require(ref in main_parts, f"missing main component {ref}")
        require(main_parts[ref]["MPN"] == mpn, f"{ref} MPN mismatch")

    require("nRF52840" in main_parts["U11"]["Package_or_Module"], "U11 is not identified as nRF52840")
    require("-40..85" in main_parts["U1"]["Temperature_C"], "exact STM32U585VIT6Q +85 C limit is not recorded")
    require("ENVIRONMENT" not in main_parts["U1"]["Status"], "resolved MCU environment blocker remains active")
    require("ENV" not in main_parts["U11"]["Status"], "resolved BLE environment blocker remains active")

    text = "\n".join((ROOT / p).read_text(encoding="utf-8") for p in (
        "hardware/POWER_COMPONENT_FREEZE_REV_A.csv",
        "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv",
        "hardware/CONNECTOR_FREEZE_REV_A.csv",
    ))
    require("ESP32-C3" not in text, "ESP32-C3 reappeared in active Rev.A freeze tables")
    require("JST_BM05B" not in text and "JST_GHR-05V" not in text, "-25 C JST GH reappeared after DEC-019")

    require(connectors["CON-MIC"]["Board_MPN"] == "Molex_5040500591", "MIC header is not 5-pin Molex Pico-Lock")
    require(connectors["CON-MIC"]["Mating_Housing_MPN"] == "Molex_5040510501", "MIC mating housing mismatch")
    require(connectors["CON-MIC"]["Terminal_MPN"] == "Molex_5040520098", "MIC crimp terminal mismatch")
    require(connectors["CON-MIC"]["Positions"] == "5", "MIC connector does not preserve AAD WAKE contact")
    require("-40..105" in connectors["CON-MIC"]["Temperature_C"], "MIC connector does not meet -40 C requirement")

    # Every physical MIC connector must have exactly 5 logical contacts and pin 5 is WAKE.
    for idx in range(1, 5):
        ref = f"J_MIC{idx}"
        physical = [r for r in harness if r["Connector_Ref"] == ref]
        require([r["Pin"] for r in physical] == ["1", "2", "3", "4", "5"], f"{ref} is not a complete 5-pin harness")
        require(physical[4]["Net"] == f"MIC_WAKE{idx}", f"{ref} pin 5 does not carry T5838 WAKE")
        require(physical[4]["Interface"] == f"AAD_WAKE{idx}", f"{ref} WAKE subinterface mismatch")

    require("MIC_WAKE" in pinmap, "aggregated microphone wake MCU net missing")
    require(pinmap["MIC_WAKE"]["MCU_Pin"] == "PA8", "MIC_WAKE must use PA8")
    require(pinmap["MIC_WAKE"]["LQFP100_Pin"] == "67", "MIC_WAKE PA8 physical pin must be 67")
    require(pinmap["MIC_WAKE"]["Direction_at_MCU"] == "IN", "MIC_WAKE must be an MCU input")

    require(connectors["CON-003"]["Board_MPN"] == "Molex_430450213", "battery input header mismatch")
    require(connectors["CON-003"]["Mating_Housing_MPN"] == "Molex_430250200", "battery input housing mismatch")
    require("-40..85" in connectors["CON-USB"]["Temperature_C"], "USB-C connector does not meet operating range")
    for key in ("CON-RF-CELL", "CON-RF-GNSS", "CON-RF-LORA"):
        require("U.FL" in connectors[key]["Board_MPN"], f"{key} is not U.FL")
        require("TEMP_VERIFY" in connectors[key]["Status"], f"{key} cable/connector temperature verification blocker was lost")
    for key in ("CON-SIM1", "CON-SIM2"):
        require(connectors[key]["Board_MPN"] == "TE_2336582-1", f"{key} is not the selected 4FF connector")
        require("Nano-SIM" in connectors[key]["Function"], f"{key} is not explicitly nano-SIM")
        require("PROCUREMENT_RISK" in connectors[key]["Status"], f"{key} procurement risk was lost")
        require("-40..85" in connectors[key]["Temperature_C"], f"{key} does not meet -40..+70 ambient requirement")
    require("3FF" not in text and "micro-SIM" not in text, "3FF/micro-SIM must not enter Rev.A connector freeze")

    print("EVT-PRE-20 Rev.A component/connector/environment/AAD-wake freeze consistency: PASS")


if __name__ == "__main__":
    main()
