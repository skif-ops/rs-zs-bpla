#!/usr/bin/env python3
"""QG-1 completeness and traceability for local installation commissioning."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    header = read("firmware/include/zs_installation_commissioning.h")
    source = read("firmware/src/zs_installation_commissioning.c")
    sha = read("firmware/src/zs_sha256.c")
    test = read("firmware/tests/test_installation_commissioning.c")
    cmake = read("firmware/CMakeLists.txt")
    target = read("firmware/targets/evt_pre_20/target_status.yaml")
    ble_icd = read("protocols/BLE_GATT_OTA_ICD_v0_1.md")
    position = read("protocols/POSITION_TIME_TRUST_REV_A.md")
    decisions = read("docs/DECISION_LOG.csv")
    requirements = read("docs/REQUIREMENTS_TRACEABILITY.csv")
    ci = read(".github/workflows/ci.yml")

    for token in (
        "ZS_INSTALLATION_SERVICE_WINDOW_MS UINT32_C(600000)",
        "ZS_COMMISSIONING_ORIGIN_BLE_LOCAL",
        "ZS_COMMISSIONING_ROLE_INSTALLER",
        "ZS_COMMISSIONING_ROLE_ENGINEER",
        "ZS_COMMISSIONING_AUDIT_INTENT",
        "ZS_COMMISSIONING_AUDIT_COMMITTED",
        "ZS_COMMISSIONING_AUDIT_FINALIZE_FAILED",
    ):
        require(token in header, f"commissioning interface missing {token}")
    for token in (
        "ZS_COMMISSIONING_LOCAL_BLE_REQUIRED",
        "ble_secure_connections",
        "peer_identity_verified",
        "ZS_COMMISSIONING_POLICY_ROLE_REQUIRED",
        "zs_installation_record_compute_hash",
        "zs_installation_store_commit",
        "zs_installation_store_load",
    ):
        require(token in source, f"commissioning guard missing {token}")
    require("round_constants[64]" in sha and "zs_sha256_final" in sha,
            "portable SHA-256 implementation is incomplete")
    for token in (
        "ZS_COMMISSIONING_ORIGIN_MQTT_REMOTE",
        "ZS_COMMISSIONING_ORIGIN_HTTPS_REMOTE",
        "ZS_COMMISSIONING_SERVICE_MODE_REQUIRED",
        "ZS_COMMISSIONING_AUDIT_REQUIRED",
        "ZS_COMMISSIONING_AUDIT_FINALIZE_FAILED",
        "canonical record hash: 9ad92b04c26e85a7f20c9259469774199348d98cfb47a563160bbab2154cea51",
    ):
        require(token in test, f"commissioning regression missing {token}")
    require("zs_installation_commissioning_tests" in cmake and
            "installation_commissioning" in cmake,
            "commissioning test is not bound to CMake/CTest")
    require("PORTABLE_LOCAL_BLE_GUARD_QG1_QG2_PASS_NRF_GATT_PENDING" in target,
            "target status overclaims or omits portable commissioning")
    require("станционный SHA-256" in ble_icd and "nRF52840/GATT binding" in ble_icd,
            "BLE ICD does not define the portable/target boundary")
    require("58-байт" in position and "audit finalize" in position,
            "position protocol does not trace canonical hash and audit failure")
    require("DEC-030" in decisions, "commissioning boundary decision missing")
    require("REQ-BLE-001" in requirements and "PARTIAL_PASS_HOST" in requirements,
            "BLE commissioning traceability is missing")
    require("validate_installation_commissioning_contract.py" in ci,
            "commissioning QG-1 is not bound to CI")
    require("audit_installation_commissioning_technical.py" in ci,
            "commissioning QG-2 is not bound to CI")

    print("Installation commissioning QG-1 PASS")
    print("local BLE, role, service-window, station hash, read-back and audit boundaries traced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
