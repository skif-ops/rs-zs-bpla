"""v0.3 station_secrets bundle export: engineer key from the registry, ICCIDs, command public key; audited."""

from __future__ import annotations

import json

import pytest

from pki import ca as pki
from pki.cli import main as cli
from pki.registry import Registry


def test_station_secrets_export(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    pki_dir = tmp_path / "pki"
    assert cli(["station-add", "--pki", str(pki_dir), "--all-lots"]) == 0
    key = Ed25519PrivateKey.generate()
    pem = tmp_path / "cmd.pem"
    pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    out = tmp_path / "bundles"
    assert cli(["station-secrets", "--pki", str(pki_dir), "DIO-EVT-012", "--out", str(out), "--to", "petrov",
                "--iccid1", "89701012345678901234", "--iccid2", "89702012345678901234", "--command-signing-key", str(pem)]) == 0
    b = json.loads((out / "DIO-EVT-012.station-secrets.json").read_text())
    reg = Registry(pki_dir / "registry.sqlite3")
    assert b["serial"] == "DIO-EVT-012" and b["context"] == "DIO-SECRETS-V1"
    assert b["engineer_key_hex"] == reg.get("DIO-EVT-012").engineer_key and len(b["engineer_key_hex"]) == 64
    assert b["iccid1"] == "89701012345678901234" and b["iccid2"] == "89702012345678901234"
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert b["command_public_key_hex"] == pub.hex() and len(pub) == 32
    assert any(a["action"] == "station_secrets" and "petrov" in (a["detail"] or "") and "iccid2" in (a["detail"] or "") for a in reg.audit_log())
    # ICCIDs only, no engineer key; bad ICCID and an empty bundle are refused
    assert cli(["station-secrets", "--pki", str(pki_dir), "DIO-EVT-012", "--out", str(out), "--no-engineer-key", "--iccid1", "89701012345678901234"]) == 0
    b2 = json.loads((out / "DIO-EVT-012.station-secrets.json").read_text())
    assert "engineer_key_hex" not in b2 and b2["iccid1"] == "89701012345678901234" and "iccid2" not in b2
    assert cli(["station-secrets", "--pki", str(pki_dir), "DIO-EVT-012", "--out", str(out), "--iccid1", "12ab"]) != 0
    assert cli(["station-secrets", "--pki", str(pki_dir), "DIO-EVT-012", "--out", str(out), "--no-engineer-key"]) != 0
