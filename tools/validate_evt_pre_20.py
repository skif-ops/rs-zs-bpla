#!/usr/bin/env python3
"""Validate locked EVT-PRE-20 configuration and hardware baseline using stdlib only."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SERIALS = [f"DIO-EVT-{index:03d}" for index in range(1, 21)]


def read_csv(relative_path: str) -> list[dict[str, str]]:
    path = ROOT / relative_path
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_csv_shapes() -> None:
    for path in sorted(ROOT.rglob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.reader(source))
        require(bool(rows), f"empty CSV: {path.relative_to(ROOT)}")
        width = len(rows[0])
        for line_number, row in enumerate(rows[1:], start=2):
            require(
                len(row) == width,
                f"CSV width mismatch: {path.relative_to(ROOT)}:{line_number}",
            )


def validate_lot() -> None:
    lot = read_csv("manufacturing/LOT_SERIAL_REGISTER.csv")
    require([row["Serial"] for row in lot] == EXPECTED_SERIALS, "lot serial range mismatch")
    require(len({row["Serial"] for row in lot}) == 20, "lot serials are not unique")
    require(
        all(row["Housing_Technology"] == "VACUUM_CASTING_PRIMARY" for row in lot),
        "not all 20 units use the primary vacuum-casting allocation",
    )
    require(all(row["APN_Mode"] == "PUBLIC_ONLY" for row in lot), "pilot APN is not PUBLIC_ONLY")
    require(all(row["LoRa_Profile"] == "RU868_LOCKED" for row in lot), "pilot LoRa is not RU868")

    housing = read_csv("manufacturing/HOUSING_LOT_PLAN.csv")
    require([row["Serial"] for row in housing] == EXPECTED_SERIALS, "housing serial range mismatch")
    require(sum(int(row["Primary_Qty"]) for row in housing) == 20, "primary housing total is not 20")
    require(
        sum(int(row["Fallback_Qty_if_Activated"]) for row in housing) == 20,
        "full-lot 3D fallback total is not 20",
    )
    require(all(row["Primary_Process"] == "VACUUM_CASTING" for row in housing), "primary process mismatch")
    require(all(row["Fallback_Process"] == "3D_PRINT" for row in housing), "fallback process mismatch")
    require(
        all(row["Injection_Molding_Scope"] == "SOURCE_DATA_AND_DFM_ONLY" for row in housing),
        "injection molding exceeds source-data-only scope",
    )


def validate_procurement() -> None:
    bom = {row["Item_ID"]: row for row in read_csv("hardware/EVT_PRE_20_BOM_DRAFT.csv")}
    require(bom["HSG-VC"]["Qty_20"] == "20", "BOM vacuum housing quantity is not 20")
    require(bom["HSG-VC"]["Procure_qty"] == "20", "BOM vacuum procurement quantity is not 20")
    require(bom["HSG-3D"]["Procure_qty"] == "0", "3D fallback was ordered before activation")
    require(bom["HSG-IM"]["Procure_qty"] == "0", "injection-molding pilot hardware was ordered")

    rfq = {row["RFQ_ID"]: row for row in read_csv("hardware/CHINA_PROCUREMENT_RFQ.csv")}
    require(rfq["RFQ-017"]["Required_qty"] == "20", "vacuum-casting RFQ quantity is not 20")
    require(rfq["RFQ-018"]["Required_qty"] == "0", "3D fallback procurement is active")
    require(rfq["RFQ-019"]["Required_qty"] == "0", "TPA procurement is active")


def validate_decisions_and_tests() -> None:
    decisions = {row["Decision_ID"]: row for row in read_csv("docs/DECISION_LOG.csv")}
    require(decisions["DEC-014"]["Status"] == "LOCKED", "housing decision is not locked")
    require(decisions["DEC-015"]["Status"] == "LOCKED", "public APN decision is not locked")
    require(decisions["DEC-010"]["Status"] == "SUPERSEDED", "old housing decision remains active")
    require(decisions["DEC-012"]["Status"] == "SUPERSEDED", "old private APN decision remains active")

    inputs = {row["Input_ID"]: row for row in read_csv("docs/OPEN_INPUTS_FOR_FREEZE.csv")}
    require(inputs["IN-004"]["Status"] == "LOCKED", "three housing source packages are not locked")
    require(inputs["IN-005"]["Status"] == "LOCKED", "housing lot allocation is not locked")

    tests = {row["Test_ID"]: row for row in read_csv("tests/EVT_MATRIX.csv")}
    require(tests["EVT-MECH-VC"]["Population"] == "20_of_20", "vacuum housing EVT is not 20 of 20")
    require(tests["EVT-MECH-IM"]["Population"] == "Source_package_only", "TPA test scope is not source-only")
    require("reject private APN" in tests["EVT-CELL-04"]["Method"], "private APN rejection test missing")


def validate_hardware_baseline() -> None:
    baseline = (ROOT / "config/EVT_PRE_20_BASELINE.yaml").read_text(encoding="utf-8")
    target = (ROOT / "firmware/targets/evt_pre_20/target_status.yaml").read_text(encoding="utf-8")
    kicad_readme = (ROOT / "hardware/kicad/README.md").read_text(encoding="utf-8")
    capture_spec = (ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md").read_text(encoding="utf-8")
    gate = (ROOT / "hardware/PCB_DOUBLE_REVIEW_GATE.md").read_text(encoding="utf-8")

    require("mcu_exact_mpn: STM32U585VIT6Q" in baseline, "baseline MCU is not STM32U585VIT6Q")
    require("mcu: STM32U585VIT6Q" in target, "firmware target MCU does not match baseline")
    require("package: LQFP100_14x14" in target, "firmware target package does not match baseline")
    require("STM32U585VIT6Q" in kicad_readme, "KiCad package missing current MCU")
    require("ESP32-C3-MINI-1-N4" in kicad_readme, "KiCad package missing current BLE candidate")
    require("STM32U585VIT6Q" in capture_spec, "capture spec missing current MCU")
    require("Review A" in gate and "Review B" in gate, "double-review PCB gate is incomplete")
    require("FOR_MANUFACTURE" in gate, "PCB release state is not defined")

    bom = {row["Item_ID"]: row for row in read_csv("hardware/EVT_PRE_20_BOM_DRAFT.csv")}
    require(bom["U1"]["MPN"] == "STM32U585VIT6Q", "BOM MCU does not match baseline")
    require(bom["U11"]["MPN"] == "ESP32-C3-MINI-1-N4", "BOM BLE candidate does not match baseline")
    require(bom["MK1"]["MPN"] == "T5838", "BOM microphone does not match baseline")

    harness = read_csv("hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv")
    mic_rows = [row for row in harness if row["Interface"].startswith("MIC")]
    require(len(mic_rows) == 16, "logical microphone harness must contain 4x4 pins")
    for index in range(1, 5):
        rows = [row for row in harness if row["Interface"] == f"MIC{index}"]
        require([row["Pin"] for row in rows] == ["1", "2", "3", "4"], f"MIC{index} pin order mismatch")
        require(rows[0]["Net"] == "1V8_MIC" and rows[1]["Net"] == "GND", f"MIC{index} power pinout mismatch")
        require(rows[2]["Net"] == "PDM_CLK", f"MIC{index} clock pinout mismatch")
        require(rows[3]["Net"] == f"PDM_DATA{index}", f"MIC{index} data pinout mismatch")

    stale_operational_tokens = ["STM32U585ZIT6Q", "nRF52832-class", "BQ24650"]
    for token in stale_operational_tokens:
        require(token not in kicad_readme, f"stale KiCad baseline token remains: {token}")


def validate_policy_text() -> None:
    baseline = (ROOT / "config/EVT_PRE_20_BASELINE.yaml").read_text(encoding="utf-8")
    require("pilot_apn_policy: public_only" in baseline, "baseline public-only APN policy missing")
    require("pilot_primary_quantity: 20" in baseline, "baseline vacuum quantity missing")
    require("pilot_fallback_quantity_if_activated: 20" in baseline, "baseline 3D fallback quantity missing")

    cellular = (ROOT / "config/cellular/dual_sim_apn_profiles.yaml").read_text(encoding="utf-8")
    require("pilot_apn_policy: public_only" in cellular, "cellular public-only policy missing")
    require("allowed_in_pilot: false" in cellular, "private APN is not explicitly disabled")

    android = (
        ROOT / "android/app/src/main/java/ru/dioneya/commissioning/core/StationModels.kt"
    ).read_text(encoding="utf-8")
    require("private_apn_not_allowed_in_pilot" in android, "Android private APN rejection missing")

    operational_files = [
        ROOT / "README.md",
        ROOT / "protocols/CELLULAR_CONNECTIVITY_BASELINE.md",
        ROOT / "manufacturing/LOT_SERIAL_REGISTER.csv",
        ROOT / "tests/EVT_MATRIX.csv",
    ]
    forbidden = [
        "PUBLIC_PRIMARY_PRIVATE_IF_PROVISIONED",
        "10 printed plus 10 vacuum cast",
        "public/private APN failover",
    ]
    for path in operational_files:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            require(token not in text, f"superseded token in {path.relative_to(ROOT)}: {token}")


def main() -> None:
    validate_csv_shapes()
    validate_lot()
    validate_procurement()
    validate_decisions_and_tests()
    validate_hardware_baseline()
    validate_policy_text()
    print("EVT-PRE-20 configuration + hardware baseline: PASS")


if __name__ == "__main__":
    main()
