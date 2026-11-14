#!/usr/bin/env python3
"""Fail closed when the current EVT-PRE-20 bench package is incomplete or unsafe."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import tempfile
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


ROOT = Path(__file__).resolve().parents[1]
RELEASE_ID = "EVT_PRE_20_BENCH_RELEASE_2026111201"
DEFAULT_PACKAGE = ROOT / "outputs" / RELEASE_ID
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


def find_one(package: Path, name: str) -> Path:
    matches = [path for path in package.rglob(name) if path.is_file()]
    if len(matches) != 1:
        fail(f"expected one {name}, found {len(matches)}")
    return matches[0]


def prepare_package(path: Path) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if path.is_dir():
        return path, None
    if not path.is_file() or path.suffix.lower() != ".zip":
        fail(f"package directory or ZIP archive is required: {path}")
    temporary = tempfile.TemporaryDirectory(prefix="evt-pre-20-release-")
    destination = Path(temporary.name)
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            parts = PurePosixPath(member.filename).parts
            if not parts or PurePosixPath(member.filename).is_absolute() or ".." in parts:
                fail(f"unsafe ZIP member: {member.filename!r}")
        archive.extractall(destination)
    candidates = [
        candidate.parent
        for candidate in destination.rglob("release_manifest.json")
        if (candidate.parent / "SHA256SUMS.txt").is_file()
    ]
    if len(candidates) != 1:
        fail(f"ZIP must contain exactly one release package root, found {len(candidates)}")
    return candidates[0], temporary


def verify_file_set(package: Path, manifest: dict) -> int:
    manifest_path = package / "release_manifest.json"
    sums_path = package / "SHA256SUMS.txt"
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
        if relative in sums:
            fail(f"duplicate SHA256SUMS path: {relative}")
        sums[relative] = digest
    wanted_sums = {relative: item["sha256"] for relative, item in recorded.items()}
    wanted_sums["release_manifest.json"] = sha256(manifest_path)
    if sums != wanted_sums:
        fail("SHA256SUMS content differs from release manifest")
    return len(recorded)


def scan_private_material(package: Path) -> None:
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


def verify_stm32(package: Path, contract: dict) -> None:
    image = find_one(package, "2026111201.bin")
    manifest_path = find_one(package, "2026111201.manifest.cbor")
    signature_path = find_one(package, "2026111201.sig")
    public_key_path = find_one(package, "release_public_key.hex")
    summary_path = find_one(package, "signing_summary.json")
    signature = signature_path.read_bytes()
    if len(signature) != 72:
        fail("STM32 signature file must contain 8-byte key id and 64-byte signature")
    public_raw = bytes.fromhex(public_key_path.read_text(encoding="ascii").strip())
    if hashlib.sha256(public_raw).digest()[:8] != signature[:8]:
        fail("STM32 release key ID mismatch")
    manifest = manifest_path.read_bytes()
    try:
        Ed25519PublicKey.from_public_bytes(public_raw).verify(signature[8:], b"DIO-FW-V1" + manifest)
    except Exception as exc:
        raise ValueError("invalid STM32 release signature") from exc
    if len(manifest) != 52 or manifest[:7] != b"\xa5\x00\x01\x01\x01\x02\x1a" or manifest[11:13] != b"\x03\x1a" or manifest[17:20] != b"\x04\x58\x20":
        fail("STM32 manifest is not the canonical release map")
    version = int.from_bytes(manifest[7:11], "big")
    size = int.from_bytes(manifest[13:17], "big")
    manifest_hash = manifest[20:52]
    if version != 2026111201:
        fail("STM32 manifest target or version mismatch")
    if size != image.stat().st_size or manifest_hash.hex() != sha256(image):
        fail("STM32 image does not match its signed manifest")
    image_bytes = image.read_bytes()
    if len(image_bytes) < 0x420:
        fail("STM32 image is too short for .fw_info")
    magic, format_version, target, image_version = struct.unpack_from("<IHHI", image_bytes, 0x400)
    if magic != 0x464F4944 or format_version != 1 or target != 1 or image_version != 2026111201:
        fail("STM32 .fw_info target or version mismatch")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("private_key_in_output") is not False:
        fail("STM32 signing summary does not exclude the private key")
    if summary.get("release_key_id_hex") != signature[:8].hex():
        fail("STM32 key ID mismatch")
    if summary.get("release_public_key_hex") != public_raw.hex():
        fail("STM32 public key mismatch")
    if sha256(image) != contract["stm32"]["expected_image_sha256"]:
        fail("STM32 fixed release hash mismatch")


def verify_nrf52840(package: Path, contract: dict) -> None:
    signed_image = find_one(package, "zephyr.signed.bin")
    merged_hex = find_one(package, "merged.hex")
    public_key = serialization.load_pem_public_key(find_one(package, "nrf-boot.pub.pem").read_bytes())
    public_der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    fingerprint = hashlib.sha256(public_der).hexdigest()
    if fingerprint != contract["nrf52840"]["public_key_fingerprint_sha256"]:
        fail("nRF52840 public key fingerprint mismatch")
    if sha256(signed_image) != contract["nrf52840"]["expected_signed_image_sha256"]:
        fail("nRF52840 signed image hash mismatch")
    if sha256(merged_hex) != contract["nrf52840"]["expected_merged_hex_sha256"]:
        fail("nRF52840 merged HEX hash mismatch")
    if contract["nrf52840"].get("signature_verified") is not True:
        fail("nRF52840 signature verification evidence is not PASS")


def verify_android(package: Path, contract: dict) -> None:
    apk = find_one(package, "Dioneya_Commissioning_0.1.1_bench_20261112.apk")
    evidence = json.loads(find_one(package, "release_build_evidence.json").read_text(encoding="utf-8"))
    if sha256(apk) != contract["android"]["apk_sha256"]:
        fail("Android APK hash mismatch")
    if evidence.get("release_id") != RELEASE_ID:
        fail("Android evidence release ID mismatch")
    expected_tasks = {"testDebugUnitTest", "assembleRelease", "apksignerVerify"}
    if set(evidence.get("tasks", {})) != expected_tasks or any(
        not str(value).startswith("PASS") for value in evidence["tasks"].values()
    ):
        fail("Android build or signing task is not PASS")
    if evidence.get("apk", {}).get("sha256") != contract["android"]["apk_sha256"]:
        fail("Android evidence hash mismatch")
    if evidence.get("signer", {}).get("certificate_sha256") != contract["android"]["signer_certificate_sha256"]:
        fail("Android signer certificate mismatch")


def verify_safety_gates(package: Path, contract: dict) -> None:
    pending = json.loads(find_one(package, "HARDWARE_PENDING.json").read_text(encoding="utf-8"))
    interlock = json.loads(find_one(package, "firmware_lock_interlock_rev_a.json").read_text(encoding="utf-8"))
    if pending.get("status") != "HARDWARE_VALIDATION_PENDING":
        fail("hardware-pending gate is missing")
    if pending.get("field_lora_profile_in_package") is not False:
        fail("field LoRa profile must not be present")
    if pending.get("firmware_lock_allowed") is not False:
        fail("firmware lock must remain forbidden")
    if interlock.get("status") != "LOCK_FORBIDDEN_HARDWARE_VALIDATION_PENDING":
        fail("firmware lock interlock status mismatch")
    if contract.get("hardware_validation_required") is not True:
        fail("release contract does not retain hardware validation")
    find_one(package, "verify_package.ps1")
    find_one(package, "ПРОВЕРИТЬ_КОМПЛЕКТ.bat")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", nargs="?", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args()
    package, temporary = prepare_package(args.package.resolve())
    manifest_path = package / "release_manifest.json"
    sums_path = package / "SHA256SUMS.txt"
    if not manifest_path.is_file() or not sums_path.is_file():
        fail("release_manifest.json and SHA256SUMS.txt are required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("release_id") != RELEASE_ID:
        fail("wrong release ID")
    if manifest.get("status") != "READY_TO_FLASH_HARDWARE_VALIDATION_PENDING":
        fail("wrong release status")
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("source_commit", ""))):
        fail("source commit is missing or malformed")
    recorded_count = verify_file_set(package, manifest)
    scan_private_material(package)

    contract = json.loads(find_one(package, "bench_release_contract_2026111201.json").read_text(encoding="utf-8"))
    if contract.get("release_id") != RELEASE_ID or contract.get("status") != manifest["status"]:
        fail("release contract mismatch")
    verify_stm32(package, contract)
    verify_nrf52840(package, contract)
    verify_android(package, contract)
    verify_safety_gates(package, contract)

    print(f"EVT-PRE-20 bench release validation: PASS ({recorded_count} files)")
    print("STM32 Ed25519 release signature: PASS")
    print("nRF52840 key fingerprint and fixed hashes: PASS")
    print("Android release build and signer evidence: PASS")
    print("private material scan: PASS")
    print("hardware and firmware-lock gates retained: PASS")
    if temporary is not None:
        temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
