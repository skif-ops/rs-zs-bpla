#!/usr/bin/env python3
"""QG-1 completeness and provenance validation for the generated CubeMX IOC."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "firmware/targets/evt_pre_20"
IOC = TARGET / "dioneya_evt_pre_20_rev_a.ioc"
MANIFEST = TARGET / "target_contract_manifest.json"
CONTRACT = TARGET / "cubemx_generation_contract.json"
DB_LOCK = TARGET / "vendor/stm32cubemx_db.lock.json"
PIN_SOURCES = (
    ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv",
    ROOT / "hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv",
)

PIN_NAME_OVERRIDES = {
    "PC14": "PC14-OSC32_IN (PC14)",
    "PC15": "PC15-OSC32_OUT (PC15)",
    "PA13": "PA13 (JTMS/SWDIO)",
    "PA14": "PA14 (JTCK/SWCLK)",
    "PA15": "PA15 (JTDI)",
    "PH3": "PH3-BOOT0",
}

EXTI_NETS = {
    "LORA_DIO1": 2,
    "ACCEL_INT": 6,
    "TAMPER_IN": 7,
    "MIC_WAKE": 8,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in PIN_SOURCES:
        with path.open(encoding="utf-8-sig", newline="") as source:
            rows.extend(csv.DictReader(source))
    return rows


def parse_ioc(path: Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    duplicates: list[str] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw or raw.startswith("#"):
            continue
        require("=" in raw, f"invalid IOC line {line_number}: {raw}")
        key, value = raw.split("=", 1)
        if key in values:
            duplicates.append(key)
        values[key] = value
    return values, duplicates


def property_key(pin_name: str, property_name: str) -> str:
    return f"{pin_name.replace(' ', r'\ ')}.{property_name}"


def expected_signal(row: dict[str, str]) -> str:
    if row["Net"] in EXTI_NETS:
        return f"GPXTI{EXTI_NETS[row['Net']]}"
    if row["CubeMX_Signal"] == "GPIO":
        return "GPIO_Input" if row["Direction_at_MCU"] == "IN" else "GPIO_Output"
    if row["CubeMX_Signal"] == "TIM2_CH1":
        return "S_TIM2_CH1"
    return row["CubeMX_Signal"]


def main() -> None:
    for path in (*PIN_SOURCES, IOC, MANIFEST, CONTRACT, DB_LOCK):
        require(path.is_file(), f"required CubeMX contract file missing: {path.relative_to(ROOT)}")

    rows = load_rows()
    require(len(rows) == 67, f"expected 67 source pin assignments, got {len(rows)}")
    values, duplicates = parse_ioc(IOC)
    require(not duplicates, f"duplicate IOC keys: {duplicates}")

    require(values["Mcu.CPN"] == "STM32U585VIT6Q", "IOC exact CPN mismatch")
    require(values["Mcu.Name"] == "STM32U585VITxQ", "IOC device database name mismatch")
    require(values["Mcu.Package"] == "LQFP100", "IOC package mismatch")
    require(values["Mcu.ContextProject"] == "TrustZoneDisabled", "IOC engineering context mismatch")
    require(values["MxCube.Version"] == "6.12.0", "IOC CubeMX version mismatch")
    require(values["MxDb.Version"] == "DB.6.0.120", "IOC database version mismatch")

    mcu_pins = [
        value
        for key, value in sorted(
            ((key, value) for key, value in values.items() if key.startswith("Mcu.Pin") and key[7:].isdigit()),
            key=lambda item: int(item[0][7:]),
        )
    ]
    require(int(values["Mcu.PinsNb"]) == len(mcu_pins), "IOC Mcu.PinsNb mismatch")
    require(len(mcu_pins) == 71, f"expected 67 physical and 4 virtual pins, got {len(mcu_pins)}")
    require(len(set(mcu_pins)) == len(mcu_pins), "IOC Mcu.Pin list contains duplicates")

    for row in rows:
        pin_name = PIN_NAME_OVERRIDES.get(row["MCU_Pin"], row["MCU_Pin"])
        require(pin_name in mcu_pins, f"IOC pin list missing {pin_name}")
        require(values.get(property_key(pin_name, "GPIO_Label")) == row["Net"], f"IOC label mismatch for {row['Net']}")
        require(values.get(property_key(pin_name, "Locked")) == "true", f"IOC pin not locked: {row['Net']}")
        require(values.get(property_key(pin_name, "Signal")) == expected_signal(row), f"IOC signal mismatch for {row['Net']}")

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    db_lock = json.loads(DB_LOCK.read_text(encoding="utf-8"))
    require(contract["status"] == "PINOUT_IOC_GENERATED_CUBEMX_OPEN_REGENERATE_PENDING", "CubeMX contract status mismatch")
    require(contract["pin_assignment_count"] == len(rows), "CubeMX contract pin count mismatch")
    require(contract["database"]["tag"] == db_lock["tag"], "CubeMX DB tag provenance mismatch")
    require(contract["database"]["commit"] == db_lock["commit"], "CubeMX DB commit provenance mismatch")
    require(contract["database"]["device_file_sha256"] == db_lock["device_file_sha256"], "CubeMX device XML hash mismatch")
    require(db_lock["commit"] == "f4ec11f00e762e37ffc4020f6d4f20d225bc061d", "unexpected CubeMX DB commit")
    require(db_lock["device_file_sha256"] == "4349055dfd06e6eb2dce1a440c44a995ad7c924e28435ede119a7d4bb10f556d", "unexpected device XML hash")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    outputs = {item["path"]: item["sha256"] for item in manifest["generated_outputs"]}
    ioc_relative = str(IOC.relative_to(ROOT))
    require(outputs.get(ioc_relative) == sha256(IOC), "target manifest IOC hash mismatch")
    sources = {item["path"]: item["sha256"] for item in manifest["source_inputs"]}
    for path in (*PIN_SOURCES, CONTRACT, DB_LOCK):
        relative = str(path.relative_to(ROOT))
        require(sources.get(relative) == sha256(path), f"target manifest source hash mismatch: {relative}")
    require(manifest["cubemx"]["status"] == "GENERATED_PINOUT_CANDIDATE_OPEN_REGENERATE_REQUIRED", "manifest overclaims CubeMX validation")
    require(manifest["release_gate"]["status"] == "BLOCKED", "generated IOC removed release block")

    print("EVT-PRE-20 CubeMX IOC QG-1 completeness/provenance: PASS")
    print("- 67/67 source assignments represented; CubeMX 6.12.0 DB.6.0.120 provenance hash-bound")


if __name__ == "__main__":
    main()
