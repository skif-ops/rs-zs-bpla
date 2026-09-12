#!/usr/bin/env python3
"""QG-1 traceability check for atomic installation-position persistence."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    header = read("firmware/include/zs_installation_store.h")
    source = read("firmware/src/zs_installation_store.c")
    test = read("firmware/tests/test_installation_store.c")
    cmake = read("firmware/CMakeLists.txt")
    target = read("firmware/targets/evt_pre_20/target_status.yaml")
    protocol = read("protocols/POSITION_TIME_TRUST_REV_A.md")
    decisions = read("docs/DECISION_LOG.csv")
    requirements = read("docs/REQUIREMENTS_TRACEABILITY.csv")
    ci = read(".github/workflows/ci.yml")

    for token in (
        "ZS_INSTALLATION_STORE_SLOT_COUNT 2u",
        "ZS_INSTALLATION_STORE_SLOT_BYTES 96u",
        "commissioning_hash",
        "physical_service_mode",
        "authenticated_role",
        "recommission",
    ):
        require(token in header, f"installation store interface missing {token}")
    for token in (
        "RECORD_CRC_OFFSET",
        "RECORD_COMMIT_OFFSET",
        "crc32",
        "generation_newer",
        "ZS_INSTALLATION_STORE_VERSION_REJECTED",
        "ZS_INSTALLATION_STORE_VERIFY_FAILED",
    ):
        require(token in source, f"atomic persistence guard missing {token}")
    for token in (
        "Body written, atomic commit marker missing",
        "ZS_INSTALLATION_STORE_AUTH_REQUIRED",
        "ZS_INSTALLATION_STORE_LOCKED",
        "ZS_INSTALLATION_STORE_VERSION_REJECTED",
        "Corrupt hash payload without updating CRC",
    ):
        require(token in test, f"installation store QG-2 case missing {token}")
    require("zs_installation_store_tests" in cmake and "installation_store" in cmake,
            "installation persistence test is not bound to CMake/CTest")
    require("PORTABLE_ATOMIC_DUAL_SLOT_QG1_QG2_PASS_FLASH_BINDING_PENDING" in target,
            "target status overclaims or omits the portable storage increment")
    require("CRC не заменяет" in protocol and "STM32 Flash binding" in protocol,
            "position persistence boundary is not documented")
    require("DEC-018" in decisions, "authoritative installation-position decision missing")
    require("REQ-POS-001" in requirements, "installation persistence traceability missing")
    require("validate_installation_store_contract.py" in ci, "installation QG-1 is not bound to CI")

    print("Installation position store QG-1 PASS")
    print("atomic two-slot record, authorization gate and flash-binding boundary traced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
