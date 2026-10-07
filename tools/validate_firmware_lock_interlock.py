#!/usr/bin/env python3
"""Fail closed if the EVT-PRE-20 bench release can enable firmware locking."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "firmware/targets/evt_pre_20/release"
BENCH_PROFILE = RELEASE / "option_bytes_bench_rev_a.json"
INTERLOCK = RELEASE / "firmware_lock_interlock_rev_a.json"
CONTRACT = RELEASE / "bench_release_contract.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    bench = load(BENCH_PROFILE)
    policy = load(INTERLOCK)
    contract = load(CONTRACT)

    require(bench.get("irreversible_changes_allowed") is False, "bench profile permits irreversible changes")
    controls = bench.get("controls", {})
    require(controls.get("readout_protection", {}).get("value") == "0xAA", "bench RDP must remain Level 0")
    for name in (
        "trustzone",
        "boot_lock",
        "write_protection",
        "proprietary_code_readout_protection",
    ):
        require(controls.get(name, {}).get("value") == "disabled", f"bench {name} must remain disabled")
    require(controls.get("boot0_source", {}).get("value") == "BOOT0 pin", "BOOT0 recovery must remain available")

    require(policy.get("status") == "LOCK_FORBIDDEN_HARDWARE_VALIDATION_PENDING", "interlock must fail closed")
    release_gate = policy.get("lock_release_requirements", {})
    for field in (
        "separate_release_id_required",
        "separate_option_byte_profile_required",
        "bench_profile_must_not_be_modified_into_lock_profile",
        "approved_numeric_hardware_limits_required",
        "production_key_and_recovery_policy_required",
        "two_person_release_approval_required",
    ):
        require(release_gate.get(field) is True, f"missing release lock gate: {field}")
    require(release_gate.get("target_hardware_qualification_result") == "PASS", "hardware qualification PASS is required")
    require(release_gate.get("full_regression_result") == "PASS", "full regression PASS is required")
    require(release_gate.get("open_mandatory_items_allowed") is False, "OPEN mandatory items must block locking")
    require(release_gate.get("failed_mandatory_items_allowed") is False, "FAIL mandatory items must block locking")
    require(len(release_gate.get("required_hardware_evidence", [])) >= 10, "hardware evidence list is incomplete")

    station_gate = policy.get("per_station_requirements", {})
    require(station_gate.get("eol_result") == "PASS", "per-station EOL PASS is required")
    require(station_gate.get("lock_applied_only_after_station_pass") is True, "station lock ordering is unsafe")
    require(station_gate.get("post_lock_readback_boot_and_connectivity_test_required") is True, "post-lock check is required")

    contract_gate = contract.get("firmware_lock_interlock", {})
    require(contract.get("hardware_validation_required") is True, "bench contract must retain hardware validation")
    require(contract_gate.get("status") == policy["status"], "contract and interlock status differ")
    require(contract_gate.get("locking_enabled_in_release") is False, "bench release must not enable locking")
    require(contract_gate.get("policy") == INTERLOCK.name, "bench contract references the wrong interlock")

    print("EVT-PRE-20 firmware lock interlock: PASS")
    print("bench release locking enabled: NO")
    print("hardware qualification required before production lock: YES")
    print("per-station EOL PASS required before lock: YES")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError) as exc:
        print(f"EVT-PRE-20 firmware lock interlock: FAIL: {exc}")
        raise SystemExit(1) from exc
