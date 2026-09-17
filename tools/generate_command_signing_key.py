#!/usr/bin/env python3
"""Generate an Ed25519 command keypair without overwriting existing material."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def exclusive_write(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as target:
        target.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    args = parser.parse_args()
    if args.private == args.public:
        raise SystemExit("private and public output paths must differ")
    if args.private.exists() or args.public.exists():
        raise SystemExit("refusing to overwrite existing command key material")

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    exclusive_write(args.private, private_pem, 0o600)
    try:
        exclusive_write(args.public, public_raw, 0o644)
    except Exception:
        args.private.unlink(missing_ok=True)
        raise
    print(f"Generated Ed25519 command keypair: {args.private}, {args.public}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
