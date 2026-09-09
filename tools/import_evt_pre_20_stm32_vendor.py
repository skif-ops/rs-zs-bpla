#!/usr/bin/env python3
"""Import or verify pinned STM32U585 CMSIS startup sources for EVT-PRE-20."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "firmware/targets/evt_pre_20/vendor/stm32cubeu5.lock.json"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_lock() -> dict[str, object]:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def source_commit(source_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def verify_local(lock: dict[str, object]) -> None:
    for item in lock["files"]:
        destination = ROOT / item["destination"]
        require(destination.is_file(), f"vendored STM32 file missing: {item['destination']}")
        require(sha256(destination.read_bytes()) == item["sha256"], f"vendored STM32 hash mismatch: {item['destination']}")


def import_files(lock: dict[str, object], source_root: Path) -> None:
    expected_commit = lock["cmsis_device_u5"]["commit"]
    require(source_root.is_dir(), f"CMSIS source root missing: {source_root}")
    require(source_commit(source_root) == expected_commit, "CMSIS checkout is not the pinned commit")

    for item in lock["files"]:
        source = source_root / item["source_path"]
        require(source.is_file(), f"pinned source file missing: {item['source_path']}")
        payload = source.read_bytes()
        require(sha256(payload) == item["sha256"], f"upstream hash mismatch: {item['source_path']}")
        destination = ROOT / item["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, help="pinned cmsis-device-u5 checkout to import")
    parser.add_argument("--check", action="store_true", help="verify committed vendor files only")
    args = parser.parse_args()
    require(args.source_root is not None or args.check, "use --source-root to import or --check to verify")

    lock = load_lock()
    if args.source_root is not None:
        import_files(lock, args.source_root.resolve())
    verify_local(lock)
    print("EVT-PRE-20 pinned STM32 CMSIS vendor files: PASS")
    print(f"- cmsis-device-u5 {lock['cmsis_device_u5']['commit']}; {len(lock['files'])} files hash-verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
