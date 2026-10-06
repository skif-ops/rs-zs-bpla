#!/usr/bin/env python3
"""Fail closed when the EVT-PRE-20 bench package is incomplete or unsafe."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = ROOT / "outputs/EVT_PRE_20_BENCH_RELEASE_2026100501"
PRIVATE_NAME = re.compile(r"(^|[._-])(private|password|secret|keystore)([._-]|$)", re.IGNORECASE)
FORBIDDEN_SUFFIXES = {".key", ".p12", ".pfx", ".jks", ".keystore"}
FORBIDDEN_BYTES = (
    b"BEGIN PRIVATE KEY",
    b"BEGIN ENCRYPTED PRIVATE KEY",
    b"BEGIN EC PRIVATE KEY",
    b"BEGIN RSA PRIVATE KEY",
    b"storePassword=",
    b"keyPassword=",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", nargs="?", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args()
    package = args.package.resolve()
    manifest_path = package / "release_manifest.json"
    sums_path = package / "SHA256SUMS.txt"
    if not manifest_path.is_file() or not sums_path.is_file():
        fail("release_manifest.json and SHA256SUMS.txt are required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("release_id") != "EVT_PRE_20_BENCH_RELEASE_2026100501":
        fail("wrong release id")
    if manifest.get("status") != "READY_TO_FLASH_HARDWARE_VALIDATION_PENDING":
        fail("wrong release status")

    recorded = {item["path"]: item for item in manifest.get("files", [])}
    actual = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and path.name not in {"release_manifest.json", "SHA256SUMS.txt"}
    }
    if actual != set(recorded):
        fail(f"package file set differs from manifest: missing={set(recorded)-actual}, extra={actual-set(recorded)}")
    for relative, item in recorded.items():
        path = package / relative
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            fail(f"hash or size mismatch: {relative}")

    sums: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if separator != "  " or not re.fullmatch(r"[0-9a-f]{64}", digest):
            fail(f"malformed SHA256SUMS line: {line!r}")
        sums[relative] = digest
    wanted_sums = {relative: item["sha256"] for relative, item in recorded.items()}
    wanted_sums["release_manifest.json"] = sha256(manifest_path)
    if sums != wanted_sums:
        fail("SHA256SUMS content differs from release manifest")

    for path in package.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(package).as_posix()
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or PRIVATE_NAME.search(path.name):
            fail(f"private-material filename is forbidden: {relative}")
        with path.open("rb") as source:
            sample = source.read(2 * 1024 * 1024)
        for marker in FORBIDDEN_BYTES:
            if marker in sample:
                fail(f"private-material marker {marker!r} in {relative}")

    sys.path.insert(0, str(ROOT / "server"))
    from station import firmware_codec  # pylint: disable=import-outside-toplevel

    contract = manifest["contract"]
    image = (package / "01_STM32/dioneya_evt_pre_20_2026100501.signed.bin").read_bytes()
    manifest_bytes = (package / "01_STM32/2026100501.manifest.cbor").read_bytes()
    signature_file = (package / "01_STM32/2026100501.sig").read_bytes()
    if len(signature_file) != 72:
        fail("STM32 signature file must contain 8-byte key id and 64-byte signature")
    public_raw = bytes.fromhex(contract["stm32"]["public_key_hex"])
    decoded = firmware_codec.verify_release(
        manifest_bytes, signature_file[:8], signature_file[8:], [public_raw]
    )
    if decoded.target != firmware_codec.TARGET_STM32_APP or decoded.version != 2026100501:
        fail("STM32 manifest target or version mismatch")
    if decoded.size != len(image) or decoded.sha256.hex() != sha256(package / "01_STM32/dioneya_evt_pre_20_2026100501.signed.bin"):
        fail("STM32 image does not match its signed manifest")

    fixed_hashes = {
        "01_STM32/dioneya_evt_pre_20_2026100501.signed.bin": contract["stm32"]["expected_image_sha256"],
        "02_NRF52840/nrf52840_ble_0.1.0+2026100501.signed.bin": contract["nrf52840"]["expected_signed_image_sha256"],
        "02_NRF52840/merged.hex": contract["nrf52840"]["expected_merged_hex_sha256"],
    }
    for relative, wanted in fixed_hashes.items():
        if sha256(package / relative) != wanted:
            fail(f"fixed release hash mismatch: {relative}")

    sbom = json.loads((package / "03_ANDROID/android.cdx.json").read_text(encoding="utf-8"))
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.6":
        fail("Android CycloneDX 1.6 SBOM missing")
    if len(sbom.get("components", [])) != 3:
        fail("Android runtime dependency inventory is incomplete")

    hardware = json.loads((package / "HARDWARE_PENDING.json").read_text(encoding="utf-8"))
    if hardware.get("status") != "HARDWARE_VALIDATION_REQUIRED" or not hardware.get("items"):
        fail("hardware-pending gate is missing")
    print(f"EVT-PRE-20 bench release validation: PASS ({len(recorded)} files)")
    print("STM32 Ed25519 release signature: PASS")
    print("private material scan: PASS")
    print("hardware gate retained: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
