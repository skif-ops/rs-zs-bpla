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
    aad_cfg = {r["Net"]: r for r in rows("hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv")}
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
        "U-MON-01": "INA226AIDGSR",
    }
    for key, mpn in expected_power.items():
        require(key in power, f"missing power component {key}")
        require(power[key]["MPN"] == mpn, f"{key} MPN mismatch")
        require("OPEN" not in power[key]["Status"], f"{key} unexpectedly OPEN")

    monitor = power["U-MON-01"]
    require("Total battery" in monitor["Function"], "INA226 is not defined as the total battery monitor")
    require("0x40" in monitor["Electrical_Baseline"], "INA226 Rev.A address 0x40 missing")
    require("I2C" in monitor["Electrical_Baseline"], "INA226 I2C baseline missing")
    require("pins 11/12" in monitor["Notes"], "INA226 is not bound to MAIN-PWR pins 11/12")

    expected_main = {
        "U1": "STM32U585VIT6Q",
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
        "Q1": "MMBT3904,215",
        "Q2": "MMBT3904,215",
        "Q3": "MMBT3904,215",
        "X1": "SiT1552AI-JE-DCC-32.768D",
    }
    for ref, mpn in expected_main.items():
        require(ref in main_parts, f"missing main component {ref}")
        require(main_parts[ref]["MPN"] == mpn, f"{ref} MPN mismatch")

    require("nRF52840" in main_parts["U11"]["Package_or_Module"], "U11 is not identified as nRF52840")
    require(main_parts["U4"]["Package_or_Module"] == "UDFN-6L_2x2mm", "U4 package is not exact STTS22H UDFN-6L")
    require(main_parts["U4"]["Temperature_C"] == "-40..125", "U4 temperature range is not frozen")
    require("-40..85" in main_parts["U1"]["Temperature_C"], "exact STM32U585VIT6Q +85 C limit is not recorded")
    require("ENVIRONMENT" not in main_parts["U1"]["Status"], "resolved MCU environment blocker remains active")
    require("ENV" not in main_parts["U11"]["Status"], "resolved BLE environment blocker remains active")
    require(main_parts["U8"]["Package_or_Module"] == "LGA-102_23.6x19.9mm", "U8 exact LGA package is not frozen")
    require("PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv" in main_parts["U8"]["Notes"], "U8 freeze does not cite cellular authority")
    require("PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv" in main_parts["U16"]["Notes"], "U16 freeze does not cite cellular authority")
    require(main_parts["U9"]["Package_or_Module"] == "LCC-18_9.7x10.1mm", "U9 exact LCC-18 package is not frozen")
    require("GNSS_RF_TIMING" in main_parts["U9"]["Status"], "U9 GNSS RF/timing sample blocker was lost")
    require("PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv" in main_parts["U9"]["Notes"], "U9 freeze does not cite GNSS authority")
    require("V_BCKP NC" in main_parts["U9"]["Notes"], "U9 no-backup choice is not frozen")
    require(main_parts["U10"]["Package_or_Module"] == "SMD_20x14_22P_1.27mm", "U10 exact 22-pad package is not frozen")
    require("CASTELLATED_OPTION" in main_parts["U10"]["Status"], "U10 castellated antenna-option blocker was lost")
    require("PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv" in main_parts["U10"]["Notes"], "U10 freeze does not cite LoRa authority")
    for ref in ("Q1", "Q2", "Q3"):
        require(main_parts[ref]["Package_or_Module"] == "SOT23", f"{ref} package is not SOT23")
        require(main_parts[ref]["Temperature_C"] == "-65..150", f"{ref} temperature range drift")
    for ref in ("Q1", "Q2"):
        require("PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv" in main_parts[ref]["Notes"], f"{ref} freeze does not cite cellular authority")
    require("PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv" in main_parts["Q3"]["Notes"], "Q3 freeze does not cite dual-SIM authority")
    require(main_parts["U13"]["Package_or_Module"] == "TSSOP-24_PW", "U13 exact PW package is not frozen")
    require("PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv" in main_parts["U13"]["Notes"], "U13 freeze does not cite dual-SIM authority")
    for ref in ("U14", "U15"):
        require(main_parts[ref]["Package_or_Module"] == "SOT666_1.6x1.6mm", f"{ref} exact SOT666 package is not frozen")
        require(main_parts[ref]["Temperature_C"] == "-40..125", f"{ref} temperature range drift")
        require("PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv" in main_parts[ref]["Notes"], f"{ref} freeze does not cite dual-SIM authority")

    text = "\n".join((ROOT / p).read_text(encoding="utf-8") for p in (
        "hardware/POWER_COMPONENT_FREEZE_REV_A.csv",
        "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv",
        "hardware/CONNECTOR_FREEZE_REV_A.csv",
    ))
    require("ESP32-C3" not in text, "ESP32-C3 reappeared in active Rev.A freeze tables")
    require("JST_BM05B" not in text and "JST_GHR-05V" not in text, "-25 C JST GH reappeared after DEC-019")

    mic = connectors["CON-MIC"]
    require(mic["Board_MPN"] == "Molex_5040500691", "MIC header is not 6-pin Molex Pico-Lock")
    require(mic["Mating_Housing_MPN"] == "Molex_5040510601", "MIC 6-pin mating housing mismatch")
    require(mic["Terminal_MPN"] == "Molex_5040520098", "MIC crimp terminal mismatch")
    require(mic["Positions"] == "6", "MIC connector does not preserve WAKE+THSEL contacts")
    require("-40..105" in mic["Temperature_C"], "MIC connector does not meet -40 C requirement")
    require("AAD_CFG" in mic["Function"], "MIC connector contract does not expose T5838 THSEL/AAD_CFG")

    # Every physical MIC connector must have 6 contacts: WAKE on 5 and shared THSEL/AAD_CFG on 6.
    for idx in range(1, 5):
        ref = f"J_MIC{idx}"
        physical = [r for r in harness if r["Connector_Ref"] == ref]
        require([r["Pin"] for r in physical] == ["1", "2", "3", "4", "5", "6"], f"{ref} is not a complete 6-pin harness")
        require(physical[4]["Net"] == f"MIC_WAKE{idx}", f"{ref} pin 5 does not carry T5838 WAKE")
        require(physical[4]["Interface"] == f"AAD_WAKE{idx}", f"{ref} WAKE subinterface mismatch")
        require(physical[5]["Net"] == "AAD_CFG", f"{ref} pin 6 does not carry shared T5838 THSEL/AAD_CFG")
        require(physical[5]["Interface"] == f"AAD_CFG{idx}", f"{ref} AAD configuration subinterface mismatch")

    require("MIC_WAKE" in pinmap, "aggregated microphone wake MCU net missing")
    require(pinmap["MIC_WAKE"]["MCU_Pin"] == "PA8", "MIC_WAKE must use PA8")
    require(pinmap["MIC_WAKE"]["LQFP100_Pin"] == "67", "MIC_WAKE PA8 physical pin must be 67")
    require(pinmap["MIC_WAKE"]["Direction_at_MCU"] == "IN", "MIC_WAKE must be an MCU input")

    require("AAD_CFG" in aad_cfg, "T5838 THSEL/AAD_CFG MCU addendum missing")
    require(aad_cfg["AAD_CFG"]["MCU_Pin"] == "PA15", "AAD_CFG must use PA15")
    require(aad_cfg["AAD_CFG"]["LQFP100_Pin"] == "77", "AAD_CFG PA15 physical pin must be 77")
    require(aad_cfg["AAD_CFG"]["Direction_at_MCU"] == "OUT", "AAD_CFG must be an MCU output")
    used_base_pins = {r["MCU_Pin"] for r in rows("hardware/EVT_PRE_20_PIN_MAP_REV_A.csv")}
    require("PA15" not in used_base_pins, "PA15/AAD_CFG collides with an existing Rev.A pin assignment")

    require(connectors["CON-003"]["Board_MPN"] == "Molex_430450213", "battery input header mismatch")
    require(connectors["CON-003"]["Mating_Housing_MPN"] == "Molex_430250200", "battery input housing mismatch")

    for key in ("CON-004A", "CON-004B"):
        pwr = connectors[key]
        require(pwr["Board_MPN"] == "Molex_430451202", f"{key} board header is not frozen 12-pin Micro-Fit")
        require(pwr["Mating_Housing_MPN"] == "Molex_430251200", f"{key} housing is not frozen 12-pin Micro-Fit")
        require(pwr["Positions"] == "12", f"{key} is not 12 positions")
        require("I2C" in pwr["Function"], f"{key} does not expose INA226 I2C")

    main_pwr = [r for r in harness if r["Interface"] == "MAIN_PWR"]
    require([r["Pin"] for r in main_pwr] == [str(i) for i in range(1, 13)], "MAIN-PWR logical harness is not 12-pin")
    require(main_pwr[10]["Net"] == "I2C2_SCL", "MAIN-PWR pin 11 is not I2C2_SCL")
    require(main_pwr[11]["Net"] == "I2C2_SDA", "MAIN-PWR pin 12 is not I2C2_SDA")

    require("-40..85" in connectors["CON-USB"]["Temperature_C"], "USB-C connector does not meet operating range")
    for key in ("CON-RF-CELL", "CON-RF-GNSS", "CON-RF-LORA"):
        require("U.FL" in connectors[key]["Board_MPN"], f"{key} is not U.FL")
        require("RF_LAYOUT" in connectors[key]["Status"], f"{key} RF layout blocker was lost")
        require("-40..90 board receptacle" in connectors[key]["Temperature_C"], f"{key} board receptacle rating is not frozen")
        require("exact cable assembly temperature" in connectors[key]["Release_Blockers"], f"{key} cable temperature blocker was lost")
    require("PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv" in connectors["CON-RF-GNSS"]["Notes"], "GNSS connector freeze lacks authority citation")
    require("exact active antenna and cable" in connectors["CON-RF-GNSS"]["Release_Blockers"], "GNSS external antenna/cable blocker was lost")
    require("PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv" in connectors["CON-RF-LORA"]["Notes"], "LoRa connector freeze lacks authority citation")
    require("no-stub" in connectors["CON-RF-LORA"]["Notes"], "LoRa connector no-stub rule was lost")
    for key in ("CON-SIM1", "CON-SIM2"):
        sim = connectors[key]
        require(sim["Board_MPN"] == "TE_2336582-1", f"{key} is not the selected 4FF connector")
        require("Nano-SIM" in sim["Function"], f"{key} is not explicitly nano-SIM/4FF")
        require("PROCUREMENT_RISK" in sim["Status"], f"{key} procurement risk was lost")
        require("-40..85" in sim["Temperature_C"], f"{key} does not meet -40..+70 ambient requirement")
    require("never substitute 3FF" in connectors["CON-SIM1"]["Notes"], "explicit 3FF/micro-SIM prohibition is missing")

    print("EVT-PRE-20 Rev.A component/connector/environment/T5838-AAD/PWR12-INA226 freeze consistency: PASS")


if __name__ == "__main__":
    main()
