#!/usr/bin/env python3
"""Generate one EVT station P-256 private key and CSR on an isolated EOL workstation.

The private key never leaves the selected output directory.  The command prints
only public identifiers and hashes.  Existing files are never overwritten.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


SERIAL_RE = re.compile(r"^DIO-EVT-(0[0-3][0-9]|040|B01)$")


def station_identity(serial: str) -> tuple[int, str]:
    """Return station ID and lot for a physical EVT serial."""
    if serial == "DIO-EVT-B01":
        return 901, "BENCH"
    match = SERIAL_RE.fullmatch(serial)
    if match is None or not match.group(1).isdigit():
        raise ValueError("serial must be DIO-EVT-001..040 or DIO-EVT-B01")
    number = int(match.group(1))
    if number == 0:
        raise ValueError("DIO-EVT-000 is reserved")
    return number, "EVT-LOT-1" if number <= 20 else "EVT-LOT-2"


def make_station_csr(serial: str, lot: str) -> tuple[bytes, bytes]:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Dioneya"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, lot),
            x509.NameAttribute(NameOID.COMMON_NAME, serial),
        ]
    )
    csr = x509.CertificateSigningRequestBuilder().subject_name(subject).sign(key, hashes.SHA256())
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return key_pem, csr.public_bytes(serialization.Encoding.PEM)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exclusive_write(path: Path, data: bytes, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if private:
        os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a local P-256 key and CSR for one physical EVT station")
    parser.add_argument("serial", help="DIO-EVT-001..040 or DIO-EVT-B01")
    parser.add_argument("--out", required=True, type=Path, help="protected per-unit output directory")
    args = parser.parse_args()

    serial = args.serial.strip().upper()
    if serial.startswith("DIO-TWIN-"):
        parser.error("digital-twin serials are forbidden")
    try:
        station_id, lot = station_identity(serial)
    except ValueError as exc:
        parser.error(str(exc))
    output = args.out.resolve()
    key_path = output / f"{serial}.key.pem"
    csr_path = output / f"{serial}.csr.pem"
    metadata_path = output / f"{serial}.csr.json"
    for path in (key_path, csr_path, metadata_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing EOL material: {path}")

    key_pem, csr_pem = make_station_csr(serial, lot)
    csr = x509.load_pem_x509_csr(csr_pem)
    if not csr.is_signature_valid:
        raise ValueError("generated CSR signature is invalid")
    common_names = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(common_names) != 1 or common_names[0].value != serial:
        raise ValueError("generated CSR CN does not match serial")
    public_der = csr.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    metadata = {
        "schema": 1,
        "serial": serial,
        "station_id": station_id,
        "lot": lot,
        "algorithm": "ECDSA P-256 / SHA-256",
        "created_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "csr_file": csr_path.name,
        "csr_sha256": digest(csr_pem),
        "public_key_spki_sha256": digest(public_der),
        "private_key_file": key_path.name,
        "private_key_created_locally": True,
        "private_key_sent_to_server": False,
    }

    try:
        exclusive_write(key_path, key_pem, private=True)
        exclusive_write(csr_path, csr_pem)
        exclusive_write(metadata_path, (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    except Exception:
        for path in (metadata_path, csr_path, key_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise

    print(f"serial: {serial}; station_id: {station_id}; lot: {lot}")
    print(f"private key: {key_path} (never upload or add to Git)")
    print(f"CSR: {csr_path}; sha256: {metadata['csr_sha256']}")
    print(f"public key SPKI sha256: {metadata['public_key_spki_sha256']}")
    if os.name == "nt":
        print("Windows: verify the output directory ACL before continuing; chmod is not an ACL substitute")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
