#!/usr/bin/env python3
"""Issue a signed RU868 field profile for the installer application."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


DOMAIN = b"DIO-LORA-RF-V1"
MAGIC = 0x46524C44
ALLOWED_FREQUENCIES = {864_100_000, 864_300_000, 864_500_000, 864_700_000,
                       864_900_000, 868_900_000, 869_100_000}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile-version", type=int, required=True)
    parser.add_argument("--valid-from-firmware", type=int, required=True)
    parser.add_argument("--profile-id", type=int, default=1)
    parser.add_argument("--frequency-hz", type=int, default=868_900_000)
    parser.add_argument("--spreading-factor", type=int, default=9)
    parser.add_argument("--tx-dbm", type=int, default=14)
    parser.add_argument("--duty-cycle-ppm", type=int, default=10_000)
    args = parser.parse_args()

    if args.profile_version <= 0 or not 1 <= args.profile_id <= 0xFFFF:
        raise ValueError("profile version and id must be positive")
    if args.frequency_hz not in ALLOWED_FREQUENCIES:
        raise ValueError("frequency is not in the approved RU868 list")
    if not 7 <= args.spreading_factor <= 12 or not -9 <= args.tx_dbm <= 14:
        raise ValueError("spreading factor or output power is outside the firmware limits")
    if not 1 <= args.duty_cycle_ppm <= 10_000:
        raise ValueError("duty cycle must be in the range 1..10000 ppm")

    payload = bytearray(32)
    struct.pack_into("<I", payload, 0, MAGIC)
    payload[4:8] = bytes((1, 2, 1, args.spreading_factor))
    struct.pack_into("<H", payload, 8, args.profile_id)
    payload[10] = args.tx_dbm & 0xFF
    struct.pack_into("<IIIII", payload, 12, args.profile_version, args.frequency_hz, 125_000,
                     args.duty_cycle_ppm, args.valid_from_firmware)

    private_key = serialization.load_pem_private_key(args.private_key.read_bytes(), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("profile signing key must be Ed25519")
    signature = private_key.sign(DOMAIN + payload)
    public_key = private_key.public_key()
    public_key.verify(signature, DOMAIN + payload)
    public_raw = public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    record = bytes(payload) + signature

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(record)
    json_output = output.with_suffix(".json")
    document = {
        "schema": 1,
        "purpose": "Dioneya RU868 field activation",
        "profile_version": args.profile_version,
        "valid_from_firmware": args.valid_from_firmware,
        "profile_id": args.profile_id,
        "frequency_hz": args.frequency_hz,
        "bandwidth_hz": 125_000,
        "spreading_factor": args.spreading_factor,
        "tx_dbm": args.tx_dbm,
        "duty_cycle_ppm": args.duty_cycle_ppm,
        "release_key_id_hex": hashlib.sha256(public_raw).digest()[:8].hex(),
        "profile_sha256": hashlib.sha256(record).hexdigest(),
        "profile_hex": record.hex(),
        "private_key_in_output": False,
    }
    json_output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"LoRa profile v{args.profile_version} signed and verified")
    print(f"binary: {output}")
    print(f"installer package: {json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
