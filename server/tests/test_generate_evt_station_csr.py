from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/generate_evt_station_csr.py"
VERIFY_TOOL = ROOT / "tools/verify_evt_station_certificate.py"


def test_generates_matching_p256_key_and_csr_without_overwrite(tmp_path):
    out = tmp_path / "DIO-EVT-012"
    first = subprocess.run(
        [sys.executable, str(TOOL), "DIO-EVT-012", "--out", str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    key_pem = (out / "DIO-EVT-012.key.pem").read_bytes()
    csr_pem = (out / "DIO-EVT-012.csr.pem").read_bytes()
    metadata = json.loads((out / "DIO-EVT-012.csr.json").read_text(encoding="utf-8"))
    key = serialization.load_pem_private_key(key_pem, password=None)
    csr = x509.load_pem_x509_csr(csr_pem)
    assert csr.is_signature_valid
    assert csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "DIO-EVT-012"
    assert csr.public_key().public_numbers() == key.public_key().public_numbers()
    assert metadata["station_id"] == 12 and metadata["lot"] == "EVT-LOT-1"
    assert "PRIVATE KEY" not in first.stdout
    assert metadata["private_key_created_locally"] is True
    assert metadata["private_key_sent_to_server"] is False

    again = subprocess.run(
        [sys.executable, str(TOOL), "DIO-EVT-012", "--out", str(out)],
        capture_output=True,
        text=True,
    )
    assert again.returncode != 0 and "refusing to overwrite" in again.stderr


def test_rejects_digital_twin_serial(tmp_path):
    result = subprocess.run(
        [sys.executable, str(TOOL), "DIO-TWIN-001", "--out", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "digital-twin serials are forbidden" in result.stderr


def test_verifies_station_certificate_key_and_chain(tmp_path):
    sys.path.insert(0, str(ROOT / "server"))
    from pki import ca as pki

    serial = "DIO-EVT-021"
    out = tmp_path / serial
    subprocess.run([sys.executable, str(TOOL), serial, "--out", str(out)], check=True)
    root = pki.create_root(b"root-passphrase-for-tool-test")
    issuing_key, issuing_csr = pki.create_issuing_request(None)
    issuing_cert = pki.sign_issuing(root.key_pem, b"root-passphrase-for-tool-test", root.cert_pem, issuing_csr)
    issuing = pki.IssuingCa.load(issuing_key, None, issuing_cert, root.cert_pem)
    station_cert = issuing.sign_station_csr((out / f"{serial}.csr.pem").read_bytes(), serial)
    cert_path = out / "station.crt.pem"
    chain_path = out / "ca-chain.pem"
    cert_path.write_bytes(station_cert)
    chain_path.write_bytes(issuing.chain_pem())

    result = subprocess.run(
        [
            sys.executable,
            str(VERIFY_TOOL),
            serial,
            "--key",
            str(out / f"{serial}.key.pem"),
            "--cert",
            str(cert_path),
            "--ca-chain",
            str(chain_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "verification: PASS" in result.stdout
    assert "EVT-LOT-2" in result.stdout
    assert "Dioneya Issuing CA 1" in result.stdout

    wrong_key_dir = tmp_path / "wrong"
    subprocess.run([sys.executable, str(TOOL), "DIO-EVT-022", "--out", str(wrong_key_dir)], check=True)
    mismatch = subprocess.run(
        [
            sys.executable,
            str(VERIFY_TOOL),
            serial,
            "--key",
            str(wrong_key_dir / "DIO-EVT-022.key.pem"),
            "--cert",
            str(cert_path),
            "--ca-chain",
            str(chain_path),
        ],
        capture_output=True,
        text=True,
    )
    assert mismatch.returncode != 0
    assert "does not match" in mismatch.stderr
