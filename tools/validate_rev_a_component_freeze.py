#!/usr/bin/env python3
"""Cross-check EVT-PRE-20 Rev.A component/connector freeze tables.

This gate validates internal consistency only. It does not turn pending parts into a
manufacturing release and intentionally preserves environment/procurement/RF blockers.
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
        "X1": "SiT1552AI-JE-DCC-32.768D",
    }
    for ref, mpn in expected_main.items():
        require(ref in main_parts, f"missing main component {ref}")
        require(main_parts[ref]["MPN"] == mpn, f"{ref} MPN mismatch")

    require("nRF52840" in main_parts["U11"]["Package_or_Module"], "U11 is not identified as nRF52840")
    text = "\n".join((ROOT / p).read_text(encoding="utf-8") for p in (
        "hardware/POWER_COMPONENT_FREEZE_REV_A.csv",
        "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv",
        "hardware/CONNECTOR_FREEZE_REV_A.csv",
    ))
    require("ESP32-C3" not in text, "ESP32-C3 reappeared in active Rev.A freeze tables")

    require(connectors["CON-MIC"]["Board_MPN"].startswith("JST_BM04B-GHS-TBT"), "MIC connector is not JST GH")
    require(connectors["CON-MIC"]["Mating_Housing_MPN"] == "JST_GHR-04V-S", "MIC mating housing mismatch")
    require(connectors["CON-MIC"]["Terminal_MPN"] == "JST_SSHL-002T-P0.2", "MIC terminal mismatch")
    require(connectors["CON-003"]["Board_MPN"] == "Molex_430450213", "battery input header mismatch")
    require(connectors["CON-003"]["Mating_Housing_MPN"] == "Molex_430250200", "battery input housing mismatch")
    for key in ("CON-RF-CELL", "CON-RF-GNSS", "CON-RF-LORA"):
        require("U.FL" in connectors[key]["Board_MPN"], f"{key} is not U.FL")
    for key in ("CON-SIM1", "CON-SIM2"):
        require(connectors[key]["Board_MPN"] == "TE_2336582-1", f"{key} is not the selected 4FF connector")
        require("Nano-SIM" in connectors[key]["Function"], f"{key} is not explicitly nano-SIM")
        require("PROCUREMENT_RISK" in connectors[key]["Status"], f"{key} procurement risk was lost")
    require("3FF" not in text and "micro-SIM" not in text, "3FF/micro-SIM must not enter Rev.A connector freeze")

    # Environmental range IN-006 is still open. Parts limited to +85 C must remain
    # explicitly blocked/pending rather than appearing as fully released.
    inputs = {r["Input_ID"]: r for r in rows("docs/OPEN_INPUTS_FOR_FREEZE.csv")}
    if inputs.get("IN-006", {}).get("Status") == "OPEN":
        for status in (
            main_parts["U11"]["Status"],
            main_parts["U13"]["Status"],
            connectors["CON-USB"]["Status"],
            connectors["CON-SIM1"]["Status"],
        ):
            require("PENDING" in status or "RISK" in status, "85 C-limited part incorrectly appears fully released")

    print("EVT-PRE-20 Rev.A component/connector freeze consistency: PASS")


if __name__ == "__main__":
    main()
