#!/usr/bin/env python3
"""Validate release-note identity and require notes for server/firmware changes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "docs/release-notes/RELEASE_INDEX.json"
SERVER_NOTES = Path("server/RELEASE_NOTES.md")
FIRMWARE_NOTES = Path("firmware/RELEASE_NOTES.md")
DEPLOYMENT_STATUS = Path("docs/release-notes/DEPLOYMENT_STATUS.md")
RELEASE_ARCHIVE = Path(
    "releases/evt-pre-20/2026-10-06-rev-e/EVT_PRE_20_BENCH_RELEASE_2026100601.zip"
)


def fail(message: str) -> None:
    raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(relative: Path) -> str:
    path = ROOT / relative
    if not path.is_file():
        fail(f"required file is missing: {relative.as_posix()}")
    return path.read_text(encoding="utf-8")


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def ref_exists(ref: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
    )
    return result.returncode == 0


def validate_content() -> None:
    server_notes = read(SERVER_NOTES)
    firmware_notes = read(FIRMWARE_NOTES)
    deployment = read(DEPLOYMENT_STATUS)
    for name, text in ((SERVER_NOTES, server_notes), (FIRMWARE_NOTES, firmware_notes)):
        if "## Unreleased" not in text:
            fail(f"{name.as_posix()} has no Unreleased section")

    index = json.loads(read(Path("docs/release-notes/RELEASE_INDEX.json")))
    if index.get("schema") != 1:
        fail("release index schema must be 1")

    config = read(Path("server/config.py"))
    match = re.search(r'app_version:\s*str\s*=\s*"([^"]+)"', config)
    if not match or index["server"]["current_version"] != match.group(1):
        fail("server version differs between config.py and RELEASE_INDEX.json")
    server_version = index["server"]["current_version"]
    if server_version not in server_notes or server_version not in deployment:
        fail("current server version is absent from notes or deployment status")

    contract = json.loads(
        read(Path("firmware/targets/evt_pre_20/release/bench_release_contract.json"))
    )
    firmware_index = index["station_firmware"]
    if firmware_index["release_id"] != contract["release_id"]:
        fail("station release id differs from bench release contract")
    if firmware_index["release_code"] != contract["station_release_code"]:
        fail("station release code differs from bench release contract")
    if firmware_index["stm32"]["image_sha256"] != contract["stm32"]["expected_image_sha256"]:
        fail("STM32 image hash differs from bench release contract")
    if firmware_index["nrf52840"]["signed_image_sha256"] != contract["nrf52840"]["expected_signed_image_sha256"]:
        fail("nRF52840 image hash differs from bench release contract")
    if firmware_index["release_id"] not in firmware_notes:
        fail("current station release is absent from firmware release notes")
    lock_gate = contract.get("firmware_lock_interlock", {})
    if firmware_index.get("protection_state") != lock_gate.get("status"):
        fail("firmware protection state differs between release index and bench contract")
    lock_path = firmware_index.get("lock_interlock")
    if not lock_path or Path(lock_path).name != lock_gate.get("policy"):
        fail("firmware lock interlock differs between release index and bench contract")
    lock_policy = json.loads(read(Path(lock_path)))
    if lock_policy.get("status") != firmware_index.get("protection_state"):
        fail("firmware lock interlock status differs from release index")

    archive = ROOT / RELEASE_ARCHIVE
    if not archive.is_file():
        fail(f"release archive is missing: {RELEASE_ARCHIVE.as_posix()}")
    if sha256(archive) != firmware_index["archive_sha256"]:
        fail("bench release archive hash differs from RELEASE_INDEX.json")


def changed_paths(base: str, head: str) -> set[str]:
    if not ref_exists(base) or not ref_exists(head):
        return set()
    return {
        line.replace("\\", "/")
        for line in git("diff", "--name-only", f"{base}...{head}").splitlines()
        if line.strip()
    }


def validate_diff(base: str, head: str) -> None:
    changed = changed_paths(base, head)
    if not changed:
        return

    server_changed = any(
        path.startswith("server/") and not Path(path).name.startswith("RELEASE_NOTES")
        for path in changed
    )
    firmware_changed = any(
        path.startswith("firmware/") and path != FIRMWARE_NOTES.as_posix()
        for path in changed
    )
    if server_changed and SERVER_NOTES.as_posix() not in changed:
        fail("server/ changed without server/RELEASE_NOTES.md")
    if firmware_changed and FIRMWARE_NOTES.as_posix() not in changed:
        fail("firmware/ changed without firmware/RELEASE_NOTES.md")

    release_changed = any(path.startswith("releases/") for path in changed)
    if release_changed and INDEX_PATH.relative_to(ROOT).as_posix() not in changed:
        fail("release artifacts changed without docs/release-notes/RELEASE_INDEX.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()

    validate_content()
    if not args.validate_only and args.base:
        validate_diff(args.base, args.head)
    print("release notes validation: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"release notes validation: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
