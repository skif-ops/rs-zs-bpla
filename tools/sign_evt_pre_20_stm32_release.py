#!/usr/bin/env python3
"""Create a signed STM32 EVT-PRE-20 release set without copying the private key."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from station import firmware_codec as fw  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    image_path = args.image.resolve()
    key_path = args.private_key.resolve()
    output = args.output.resolve()
    if not image_path.is_file() or not key_path.is_file():
        raise FileNotFoundError("image or signing key is missing")

    image = image_path.read_bytes()
    manifest = fw.manifest_for_image(image)
    if manifest.target != fw.TARGET_STM32_APP or manifest.version != args.version:
        raise ValueError("image .fw_info target or version does not match the requested release")

    signer = fw.ReleaseSigner.from_pem_file(key_path)
    manifest_bytes = manifest.encode()
    signature = signer.sign(manifest_bytes)
    fw.verify_release(manifest_bytes, signer.key_id, signature, [signer.public_raw])

    output.mkdir(parents=True, exist_ok=True)
    image_out = output / f"{args.version}.bin"
    manifest_out = output / f"{args.version}.manifest.cbor"
    signature_out = output / f"{args.version}.sig"
    shutil.copy2(image_path, image_out)
    manifest_out.write_bytes(manifest_bytes)
    signature_out.write_bytes(signer.key_id + signature)
    (output / "release_public_key.hex").write_text(signer.public_key_hex + "\n", encoding="ascii")
    summary = {
        "schema": 1,
        "target": "stm32-app",
        "version": args.version,
        "image_bytes": len(image),
        "image_sha256": sha256(image_out),
        "manifest_sha256": sha256(manifest_out),
        "signature_file_sha256": sha256(signature_out),
        "release_key_id_hex": signer.key_id.hex(),
        "release_public_key_hex": signer.public_key_hex,
        "private_key_in_output": False,
    }
    (output / "signing_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"STM32 release {args.version} signed and verified")
    print(f"image SHA-256: {summary['image_sha256']}")
    print(f"key id: {summary['release_key_id_hex']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
