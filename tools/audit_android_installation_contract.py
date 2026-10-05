#!/usr/bin/env python3
"""QG-2 independent audit of the Android/firmware installation hash contract."""
import hashlib
import json
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HASH = "9ad92b04c26e85a7f20c9259469774199348d98cfb47a563160bbab2154cea51"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def independent_hash() -> str:
    payload = bytearray(b"ZS-INSTALLATION-V1")
    payload += bytes((1, 1, 1, 0, 1, 1))
    payload += struct.pack(
        ">IiiiHHHHBBQ",
        1,
        557_550_000,
        376_150_000,
        1_800,
        5,
        25,
        75,
        250,
        3,
        10,
        2_000_000_000_000_001,
    )
    require(len(payload) == 58, "independent Android contract length drift")
    return hashlib.sha256(payload).hexdigest()


def ordered(source: str, tokens: tuple[str, ...]) -> bool:
    offset = 0
    for token in tokens:
        found = source.find(token, offset)
        if found < 0:
            return False
        offset = found + len(token)
    return True


def main() -> int:
    kotlin = (ROOT / "android/app/src/main/java/ru/dioneya/commissioning/core/InstallationCommissioningContract.kt").read_text(encoding="utf-8")
    android_test = (ROOT / "android/app/src/test/java/ru/dioneya/commissioning/core/InstallationCommissioningContractTest.kt").read_text(encoding="utf-8")
    firmware_test = (ROOT / "firmware/tests/test_installation_commissioning.c").read_text(encoding="utf-8")
    status = (ROOT / "android/track_status.yaml").read_text(encoding="utf-8")
    build_evidence = json.loads((ROOT / "android/debug_build_evidence.json").read_text(encoding="utf-8"))
    android_ble = (ROOT / "android/app/src/main/java/ru/dioneya/commissioning/ble/AndroidBleTransport.kt").read_text(encoding="utf-8")
    station_picker = (ROOT / "android/app/src/main/java/ru/dioneya/commissioning/ui/StationPickerActivity.kt").read_text(encoding="utf-8")
    installation_ui = (ROOT / "android/app/src/main/java/ru/dioneya/commissioning/ui/InstallationActivity.kt").read_text(encoding="utf-8")
    server_ui = (ROOT / "android/app/src/main/java/ru/dioneya/commissioning/ui/ServerActivity.kt").read_text(encoding="utf-8")

    require(independent_hash() == EXPECTED_HASH, "independent known-answer hash drift")
    require(EXPECTED_HASH in android_test and EXPECTED_HASH in firmware_test,
            "Android and firmware do not share the controlled known-answer vector")
    require(ordered(kotlin, (
        "buffer.put(DOMAIN)",
        "buffer.put(FORMAT_VERSION)",
        "buffer.put(1.toByte()) // configured",
        "buffer.put(1.toByte()) // locked",
        "buffer.put(coordinateSourceId(position.source))",
        "buffer.put(CONFIGURED_ALTITUDE_SOURCE)",
        "buffer.put(CONFIGURED_POSITION_SOURCE)",
        "buffer.putInt(position.version.toInt())",
        "buffer.putInt(position.latE7)",
        "buffer.putInt(position.lonE7)",
        "buffer.putInt(position.altDm)",
        "buffer.putShort(position.accuracyM.toShort())",
        "buffer.putShort(policy.warningDistanceM.toShort())",
        "buffer.putShort(policy.suspectDistanceM.toShort())",
        "buffer.putShort(policy.grossJumpDistanceM.toShort())",
        "buffer.put(policy.warningConsecutiveFixes.toByte())",
        "buffer.put(policy.suspectConsecutiveFixes.toByte())",
        "buffer.putLong(request.commissionedTimeUs)",
    )), "Android canonical field order differs from firmware contract")
    require("readback.commissioningHashHex.equals(canonicalHashHex(request), ignoreCase = true)" in kotlin,
            "Android does not compare station read-back against its independent digest")
    require("if (!readback.auditCommitted)" in kotlin,
            "Android can accept a read-back without committed audit")
    require("ANDROID_BLE_TRANSPORT_SOURCE_PRESENT_STATION_GATT_HARDWARE_VALIDATION_PENDING" in status and
            "station_gatt_hardware_validation" in status and "RELEASE_NOT_BUILT" in status,
            "Android status must expose source BLE transport while keeping hardware/release gates open")
    require(build_evidence["tasks"] == {"testDebugUnitTest": "PASS", "assembleDebug": "PASS"},
            "Android debug build evidence does not record both required tasks as PASS")
    require(build_evidence["apk"]["release_authorized"] is False and
            build_evidence["apk"]["artifact_retained"] is False,
            "Android debug artifact was incorrectly promoted to a release")
    require("class AndroidBleTransport" in android_ble and ": BleTransport" in android_ble and "BluetoothGattCallback" in android_ble,
            "Android BluetoothGatt transport is missing")
    require("AndroidBleTransport(this, device)" in station_picker and "AndroidBleTransport(this, it)" in installation_ui and
            "AndroidBleTransport(this, it)" in server_ui,
            "Android UI does not wire the source BLE transport into commissioning screens")

    print("Android installation commissioning QG-2 independent technical audit: PASS")
    print("58-byte field order and firmware/Android SHA-256 known-answer agreement verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
