#!/usr/bin/env python3
"""QG-1 completeness and provenance gate for the EVT-PRE-20 STM32 scaffold."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "firmware/targets/evt_pre_20"
MANIFEST_PATH = TARGET / "stm32_scaffold_manifest.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    require(MANIFEST_PATH.is_file(), "STM32 scaffold manifest missing")
    manifest = load_json(MANIFEST_PATH)
    require(manifest["configuration"] == "EVT-PRE-20", "scaffold configuration mismatch")
    require(manifest["target"] == {
        "mcu": "STM32U585VIT6Q",
        "package": "LQFP100_14x14",
        "device_define": "STM32U585xx",
    }, "scaffold target identity mismatch")

    listed_paths: set[str] = set()
    for item in manifest["files"]:
        relative = item["path"]
        require(relative not in listed_paths, f"duplicate scaffold file: {relative}")
        listed_paths.add(relative)
        path = ROOT / relative
        require(path.is_file(), f"scaffold file missing: {relative}")
        require(sha256(path) == item["sha256"], f"scaffold file hash mismatch: {relative}")

    required_roles = {
        "UPSTREAM_LOCK",
        "PINNED_GCC_STARTUP",
        "PINNED_CMSIS_SYSTEM",
        "UPSTREAM_LICENSE",
        "ENGINEERING_LINKER",
        "MEMORY_EVIDENCE",
        "CUBEMX_PREFLIGHT",
        "CUBEMX_PINOUT_IOC",
        "CUBEMX_DB_LOCK",
    }
    require({item["role"] for item in manifest["files"]} == required_roles, "scaffold role coverage mismatch")

    lock_path = TARGET / "vendor/stm32cubeu5.lock.json"
    lock = load_json(lock_path)
    upstream = manifest["upstream"]
    require(lock["stm32cubeu5"]["release"] == upstream["stm32cubeu5_release"], "CubeU5 release mismatch")
    require(lock["stm32cubeu5"]["commit"] == upstream["stm32cubeu5_commit"], "CubeU5 commit mismatch")
    require(lock["cmsis_device_u5"]["commit"] == upstream["cmsis_device_u5_commit"], "CMSIS commit mismatch")
    require(lock["cmsis_device_u5"]["license"] == "Apache-2.0", "CMSIS license declaration mismatch")
    require(lock["stm32cubeu5"]["tag_signature_status"] == "UNSIGNED_PINNED_BY_OBJECT_AND_COMMIT_SHA", "unsigned upstream tag handling is not explicit")
    require(len(lock["files"]) == 3, "vendor lock must contain startup, system and license")
    for item in lock["files"]:
        destination = ROOT / item["destination"]
        require(destination.is_file(), f"vendor destination missing: {item['destination']}")
        require(sha256(destination) == item["sha256"], f"vendor lock hash mismatch: {item['destination']}")

    cubemx = load_json(TARGET / "cubemx_generation_contract.json")
    require(cubemx["status"] == "PINOUT_IOC_GENERATED_CUBEMX_OPEN_REGENERATE_PENDING", "CubeMX status overclaims readiness")
    require(cubemx["tool"]["version"] == "6.12.0", "CubeMX version is not locked")
    require(cubemx["pin_assignment_count"] == 65, "CubeMX contract pin count mismatch")
    require((ROOT / cubemx["output_ioc"]).is_file(), "generated CubeMX pinout .ioc missing")
    require(cubemx["release_gate"]["status"] == "BLOCKED", "CubeMX preflight release gate missing")

    memory = load_json(TARGET / "stm32_memory_contract.json")
    require(memory["release_gate"]["status"] == "BLOCKED", "engineering memory map must remain blocked")
    require(memory["security_profile"] == "TRUSTZONE_DISABLED_ENGINEERING_BRINGUP_ONLY", "engineering security scope mismatch")

    gates = manifest["quality_gates"]
    require(gates["qg1_completeness"] == "tools/validate_evt_pre_20_stm32_scaffold.py", "QG-1 path mismatch")
    require(gates["qg2_technical"] == "tools/audit_evt_pre_20_stm32_scaffold_technical.py", "QG-2 path mismatch")
    require(manifest["release_gate"]["status"] == "BLOCKED", "incomplete STM32 target must remain blocked")
    require(len(manifest["release_gate"]["remaining_blockers"]) == 8, "remaining blocker list is incomplete")

    status = (TARGET / "target_status.yaml").read_text(encoding="utf-8")
    require("status: TARGET_PORT_REQUIRED" in status, "target prematurely claims completion")
    require("do_not_release: true" in status, "target release block missing")
    require("stm32_scaffold_manifest.json" in status, "target status does not reference STM32 scaffold")

    print("EVT-PRE-20 STM32 scaffold QG-1 completeness/provenance: PASS")
    print(f"- {len(listed_paths)} scaffold files hash-bound; upstream release and CMSIS commit pinned")


if __name__ == "__main__":
    main()
