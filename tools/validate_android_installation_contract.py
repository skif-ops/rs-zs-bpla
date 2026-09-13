#!/usr/bin/env python3
"""QG-1 traceability for Android installation-position read-back verification."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    source = read("android/app/src/main/java/ru/dioneya/commissioning/core/InstallationCommissioningContract.kt")
    test = read("android/app/src/test/java/ru/dioneya/commissioning/core/InstallationCommissioningContractTest.kt")
    models = read("android/app/src/main/java/ru/dioneya/commissioning/core/StationModels.kt")
    status = read("android/track_status.yaml")
    architecture = read("android/APP_ARCHITECTURE_v0_1.md")
    requirements = read("android/REQUIREMENTS_v0_1.md")
    project_requirements = read("docs/REQUIREMENTS_TRACEABILITY.csv")
    ci = read(".github/workflows/ci.yml")

    for token in (
        "InstallationCommissioningOperation",
        "InstallationCommissioningRole",
        "commissionedTimeUs",
        "CANONICAL_BYTES = 58",
        'DOMAIN = "ZS-INSTALLATION-V1"',
        'MessageDigest.getInstance("SHA-256")',
        "engineer_role_required_for_position_policy",
        "installation_position_version_not_monotonic",
        "commissioning_hash_mismatch",
        "commissioning_audit_not_committed",
    ):
        require(token in source, f"Android commissioning contract missing {token}")
    require("installation_position_version_overflow" in models,
            "Android position version is not bounded to station uint32")
    for token in (
        "canonicalHashMatchesFirmwareKnownAnswer",
        "acceptsExactCommittedReadback",
        "rejectsModifiedHashAndIncompleteAudit",
        "installerCannotChangePositionTrustPolicy",
        "recommissionRequiresExistingRecordAndMonotonicVersion",
    ):
        require(token in test, f"Android commissioning regression missing {token}")
    require("POSITION_HASH_READBACK_QG1_QG2_PASS" in status,
            "Android track status omits the host result")
    require("ble_service_characteristic_uuids" in status and "station_gatt_prototype" in status,
            "Android track overclaims BLE transport readiness")
    require("58-byte" in architecture and "nRF52840 GATT" in architecture,
            "Android architecture does not preserve the portable/transport boundary")
    require("AND-F-006" in requirements and "Host evidence" in requirements,
            "Android requirement evidence is missing")
    require("REQ-APP-001" in project_requirements and "PARTIAL_PASS_HOST" in project_requirements,
            "project Android traceability is missing")
    require("validate_android_installation_contract.py" in ci,
            "Android commissioning QG-1 is not bound to CI")
    require("audit_android_installation_contract.py" in ci,
            "Android commissioning QG-2 is not bound to CI")

    print("Android installation commissioning QG-1 PASS")
    print("cross-language hash, role/version validation and read-back/audit gates traced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
