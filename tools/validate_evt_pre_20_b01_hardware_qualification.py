#!/usr/bin/env python3
"""Validate the B01 qualification template and fail closed on lock eligibility."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = ROOT / "manufacturing/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.json"
CONTRACT = ROOT / "firmware/targets/evt_pre_20/release/bench_release_contract.json"
INTERLOCK = ROOT / "firmware/targets/evt_pre_20/release/firmware_lock_interlock_rev_a.json"
REQUIRED_TEST_IDS = {
    "HQ-ID-01", "HQ-STM-01", "HQ-STM-02", "HQ-STM-03", "HQ-NRF-01",
    "HQ-IPC-01", "HQ-AUD-01", "HQ-AUD-02", "HQ-STO-01", "HQ-CELL-01",
    "HQ-CELL-02", "HQ-GNSS-01", "HQ-LORA-01", "HQ-PWR-01", "HQ-ENV-01",
    "HQ-BLE-01", "HQ-PKI-01", "HQ-EOL-01", "HQ-REC-01", "HQ-REG-01",
    "HQ-LIM-01", "HQ-SIGN-01",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_structure(record: dict, contract: dict, interlock: dict) -> None:
    require(record.get("schema") == 1, "unsupported qualification schema")
    require(record.get("protocol_id") == "EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A", "unexpected protocol ID")
    unit = record.get("unit", {})
    require(unit == {"serial": "DIO-EVT-B01", "station_id": 901, "tenant": "bench"}, "unexpected B01 identity")
    release = record.get("release", {})
    require(release.get("release_id") == contract.get("release_id"), "release ID differs from bench contract")
    require(release.get("release_code") == contract.get("station_release_code"), "release code differs from bench contract")
    require(release.get("stm32_target") == contract["stm32"]["target"], "STM32 target differs")
    require(release.get("stm32_image_sha256") == contract["stm32"]["expected_image_sha256"], "STM32 image hash differs")
    require(release.get("nrf52840_target") == contract["nrf52840"]["target"], "nRF52840 target differs")
    require(release.get("nrf52840_signed_image_sha256") == contract["nrf52840"]["expected_signed_image_sha256"], "nRF signed hash differs")
    require(release.get("nrf52840_merged_hex_sha256") == contract["nrf52840"]["expected_merged_hex_sha256"], "nRF merged hash differs")
    require(release.get("option_byte_profile") == contract["stm32"]["option_byte_profile"], "option-byte profile differs")

    tests = record.get("tests", [])
    ids = [item.get("id") for item in tests]
    require(len(ids) == len(set(ids)), "duplicate qualification test ID")
    require(set(ids) == REQUIRED_TEST_IDS, "qualification test matrix is incomplete or has unknown IDs")
    allowed = set(record.get("allowed_test_statuses", []))
    require(allowed == {"NOT_RUN", "OPEN", "PASS", "FAIL", "HOLD", "N/A"}, "unexpected status vocabulary")
    for item in tests:
        require(item.get("mandatory") is True, f"{item.get('id')}: mandatory gate was relaxed")
        require(item.get("status") in allowed, f"{item.get('id')}: invalid status")
        require(bool(item.get("test_ru")) and bool(item.get("test_en")), f"{item.get('id')}: bilingual test text is required")
        require(bool(item.get("approved_limit")), f"{item.get('id')}: pass criterion is missing")

    inventory = record.get("evidence_inventory", [])
    require(len(inventory) >= 10, "evidence inventory is incomplete")
    require(all(item.get("required") is True for item in inventory), "required evidence was relaxed")
    require(interlock.get("status") == "LOCK_FORBIDDEN_HARDWARE_VALIDATION_PENDING", "firmware interlock is not fail-closed")


def validate_template(record: dict) -> None:
    decision = record.get("decision", {})
    require(decision.get("overall_status") == "NOT_RUN", "template overall status must be NOT_RUN")
    require(decision.get("lock_authorization") == "DENIED", "template must deny firmware locking")
    require(decision.get("approved_numeric_limits") is False, "template cannot pre-approve numeric limits")
    require(decision.get("full_regression_result") == "NOT_RUN", "template cannot pre-approve regression")
    require(all(item.get("status") == "NOT_RUN" for item in record["tests"]), "template test rows must start as NOT_RUN")
    require(all(item.get("status") == "NOT_RUN" for item in record["evidence_inventory"]), "template evidence rows must start as NOT_RUN")
    for field in ("release_approver", "quality_approver", "production_release_id", "production_option_byte_profile"):
        require(not decision.get(field), f"template must not prefill {field}")


def validate_authorization(record: dict) -> None:
    decision = record.get("decision", {})
    require(all(item["status"] == "PASS" for item in record["tests"]), "every mandatory qualification test must be PASS")
    for item in record["tests"]:
        require(bool(item.get("measurement")), f"{item['id']}: measurement/result is empty")
        require("pending" not in str(item.get("approved_limit", "")).lower(), f"{item['id']}: approved limit is still pending")
        require(bool(item.get("evidence")), f"{item['id']}: evidence path is empty")
        require(SHA256.fullmatch(str(item.get("evidence_sha256", ""))) is not None, f"{item['id']}: evidence SHA-256 is invalid")
        require(bool(item.get("operator")) and bool(item.get("reviewer")), f"{item['id']}: operator and reviewer are required")
        require(item.get("operator") != item.get("reviewer"), f"{item['id']}: operator and reviewer must be distinct")
        require(bool(item.get("timestamp_utc")), f"{item['id']}: timestamp is empty")
    for item in record["evidence_inventory"]:
        require(item.get("status") == "PASS", f"{item['id']}: evidence item is not PASS")
        require(bool(item.get("path")), f"{item['id']}: path is empty")
        require(SHA256.fullmatch(str(item.get("sha256", ""))) is not None, f"{item['id']}: SHA-256 is invalid")
    require(decision.get("overall_status") == "PASS", "overall qualification result must be PASS")
    require(decision.get("approved_numeric_limits") is True, "numeric hardware limits are not approved")
    require(decision.get("full_regression_result") == "PASS", "full regression result must be PASS")
    release_approver = str(decision.get("release_approver", "")).strip()
    quality_approver = str(decision.get("quality_approver", "")).strip()
    require(bool(release_approver) and bool(quality_approver), "two named approvers are required")
    require(release_approver != quality_approver, "release and quality approvers must be distinct")
    production_release_id = str(decision.get("production_release_id", "")).strip()
    production_profile = str(decision.get("production_option_byte_profile", "")).strip()
    require(bool(production_release_id), "separate production release ID is required")
    require(production_release_id != record["release"]["release_id"], "production release ID must differ from the bench release")
    require(bool(production_profile), "separate production option-byte profile is required")
    require(production_profile != record["release"]["option_byte_profile"], "production option-byte profile must differ from the bench profile")
    require(decision.get("lock_authorization") == "ELIGIBLE_FOR_SEPARATE_PRODUCTION_PROFILE", "authorization state is not eligible")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, default=QUALIFICATION)
    parser.add_argument("--authorize-lock", action="store_true")
    args = parser.parse_args()
    record = load(args.record)
    contract = load(CONTRACT)
    interlock = load(INTERLOCK)
    validate_structure(record, contract, interlock)
    if args.authorize_lock:
        validate_authorization(record)
        print("B01 qualification authorization gate: PASS")
        print("eligible for a separate production protection profile: YES")
    else:
        validate_template(record)
        print("B01 hardware qualification template: PASS")
        print("hardware tests complete: NO")
        print("firmware locking authorized: NO")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError) as exc:
        print(f"B01 qualification gate: FAIL: {exc}")
        raise SystemExit(1) from exc
