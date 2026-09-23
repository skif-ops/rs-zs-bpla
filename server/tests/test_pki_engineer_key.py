"""B.9 session role: per-station engineer key in the PKI registry and the HMAC tag vector shared with the firmware."""

from __future__ import annotations

import pytest

from pki import ca as pki
from pki.cli import main as cli
from pki.registry import Registry


def test_registry_engineer_key_and_role_tag_vector(tmp_path):
    """B.9: per-station engineer key (never on the label), audited export, rotation; the HMAC tag vector shared
    with firmware/tests/test_ble_bridge.c and the Android side."""
    import hashlib, hmac, json, sqlite3
    reg = Registry(tmp_path / "r.sqlite3")
    reg.add_all_lots()
    k1 = reg.ensure_engineer_key("DIO-EVT-003")
    assert len(k1) == 64 and k1 == reg.ensure_engineer_key("DIO-EVT-003") and reg.get("DIO-EVT-003").engineer_key == k1
    k2 = reg.rotate_engineer_key("DIO-EVT-003", "phone lost")
    assert k2 != k1 and reg.get("DIO-EVT-003").engineer_key == k2
    with pytest.raises(pki.PkiError):
        reg.ensure_engineer_key("DIO-EVT-099")
    # the label never carries it
    from pki.label import StationLabel
    lab = StationLabel("DIO-EVT-003", 3, "pilot1", reg.ensure_pairing_secret("DIO-EVT-003"))
    assert k2 not in lab.encode()
    # migration of a registry without the column
    old = tmp_path / "old.sqlite3"
    with sqlite3.connect(old) as c:
        c.executescript("CREATE TABLE stations (serial TEXT PRIMARY KEY, station_id INTEGER NOT NULL UNIQUE, lot TEXT NOT NULL, tenant TEXT NOT NULL, status TEXT NOT NULL, cert_serial_number TEXT, cert_fingerprint_sha256 TEXT, cert_not_after TEXT, created_at TEXT NOT NULL, provisioned_at TEXT, commissioned_at TEXT, revoked_at TEXT, revoke_reason TEXT, note TEXT, pairing_secret TEXT); CREATE TABLE audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, serial TEXT, action TEXT NOT NULL, detail TEXT);")
        c.execute("INSERT INTO stations(serial, station_id, lot, tenant, status, created_at) VALUES ('DIO-EVT-001',1,'EVT-LOT-1','pilot1','created','2026-01-01')")
    assert Registry(old).get("DIO-EVT-001").engineer_key is None and len(Registry(old).ensure_engineer_key("DIO-EVT-001")) == 64
    # CLI: export (audited) and rotation
    pki_dir = tmp_path / "pki"
    assert cli(["station-add", "--pki", str(pki_dir), "--all-lots"]) == 0
    assert cli(["engineer-key", "--pki", str(pki_dir), "DIO-EVT-012", "--to", "ivanov", "--out", str(tmp_path / "eng")]) == 0
    exported = json.loads((tmp_path / "eng" / "DIO-EVT-012.engineer-key.json").read_text())
    r = Registry(pki_dir / "registry.sqlite3")
    assert exported["engineer_key_hex"] == r.get("DIO-EVT-012").engineer_key and exported["context"] == "DIO-ROLE-V1"
    assert any(a["action"] == "engineer_key" and "ivanov" in (a["detail"] or "") for a in r.audit_log())
    assert cli(["engineer-key", "--pki", str(pki_dir), "DIO-EVT-012", "--rotate", "compromised"]) == 0
    assert Registry(pki_dir / "registry.sqlite3").get("DIO-EVT-012").engineer_key != exported["engineer_key_hex"]
    # tag = HMAC-SHA256(key, "DIO-ROLE-V1" || serial || nonce)[:16], vector from test_ble_bridge.c
    key = bytes(range(0xa0, 0xc0))
    nonce = bytes(range(16))
    tag = hmac.new(key, b"DIO-ROLE-V1" + b"DIO-EVT-012" + nonce, hashlib.sha256).digest()[:16]
    assert tag.hex() == "e3f70cf47e0a591490b501d6ba31be7b"
