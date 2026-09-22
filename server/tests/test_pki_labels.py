"""Station label QR and pairing-secret tests (protocols/STATION_LABEL_QR_v0_1.md)."""

from __future__ import annotations

import pytest

from pki import ca as pki
from pki.cli import main as cli
from pki.registry import Registry


def test_label_payload_crc_and_roundtrip():
    from pki.label import StationLabel, crc16_ccitt, new_pairing_secret, secret_bytes
    assert crc16_ccitt(b"123456789") == 0x29B1                      # CRC-16/CCITT-FALSE check value
    known = StationLabel("DIO-EVT-012", 12, "pilot1", "JBSWY3DPEHPK3PXPJBSWY3DPEH")
    text = known.encode()
    assert text == "DIO1;S=DIO-EVT-012;ID=12;T=pilot1;K=JBSWY3DPEHPK3PXPJBSWY3DPEH;C=C5A3"   # shared with the Android known-answer test
    assert StationLabel.decode(text) == known
    assert StationLabel.decode("  " + text + "\n") == known
    for bad in (text[:-1] + "4", text.replace("ID=12", "ID=13"), text.replace("DIO1", "DIO2"), text.replace(";C=", ""),
                text.replace("pilot1", "pilot 1"), "DIO1;S=DIO-EVT-041;ID=41;T=pilot2;K=JBSWY3DPEHPK3PXPJBSWY3DPEH;C=0000"):
        with pytest.raises(pki.PkiError):
            StationLabel.decode(bad)
    s = new_pairing_secret()
    assert len(s) == 26 and len(secret_bytes(s)) == 16 and s != new_pairing_secret()
    bench = StationLabel("DIO-EVT-B01", 901, "bench", s)
    assert StationLabel.decode(bench.encode()) == bench


def test_registry_pairing_secret_and_label_commands(tmp_path, monkeypatch):
    # Rendering needs `qrcode`, which lives in requirements-pki.txt (admin tool / muhoed-pki.exe),
    # not in the server runtime lock: the full-server job skips this test, the PKI job runs it.
    pytest.importorskip("qrcode")
    from pki.label import StationLabel
    reg = Registry(tmp_path / "r.sqlite3")
    reg.add_all_lots()
    s1 = reg.ensure_pairing_secret("DIO-EVT-003")
    assert s1 == reg.ensure_pairing_secret("DIO-EVT-003") and reg.get("DIO-EVT-003").pairing_secret == s1
    s2 = reg.rotate_pairing_secret("DIO-EVT-003", "label lost")
    assert s2 != s1 and reg.get("DIO-EVT-003").pairing_secret == s2
    with pytest.raises(pki.PkiError):
        reg.ensure_pairing_secret("DIO-EVT-099")
    # an old registry without the column is migrated on open
    import sqlite3
    old = tmp_path / "old.sqlite3"
    with sqlite3.connect(old) as c:
        c.executescript("CREATE TABLE stations (serial TEXT PRIMARY KEY, station_id INTEGER NOT NULL UNIQUE, lot TEXT NOT NULL, tenant TEXT NOT NULL, status TEXT NOT NULL, cert_serial_number TEXT, cert_fingerprint_sha256 TEXT, cert_not_after TEXT, created_at TEXT NOT NULL, provisioned_at TEXT, commissioned_at TEXT, revoked_at TEXT, revoke_reason TEXT, note TEXT); CREATE TABLE audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, serial TEXT, action TEXT NOT NULL, detail TEXT);")
        c.execute("INSERT INTO stations(serial, station_id, lot, tenant, status, created_at) VALUES ('DIO-EVT-001',1,'EVT-LOT-1','pilot1','created','2026-01-01')")
    migrated = Registry(old)
    assert migrated.get("DIO-EVT-001").pairing_secret is None
    assert len(migrated.ensure_pairing_secret("DIO-EVT-001")) == 26
    # CLI: label for one station and a sheet for a lot
    pki_dir = tmp_path / "pki"
    assert cli(["station-add", "--pki", str(pki_dir), "--all-lots"]) == 0
    assert cli(["label-qr", "--pki", str(pki_dir), "DIO-EVT-012", "--out", str(tmp_path / "labels")]) == 0
    svg = (tmp_path / "labels" / "DIO-EVT-012.svg").read_text()
    payload = (tmp_path / "labels" / "DIO-EVT-012.txt").read_text().strip()
    lab = StationLabel.decode(payload)
    assert lab.serial == "DIO-EVT-012" and lab.station_id == 12 and lab.tenant == "pilot1"
    assert svg.startswith("<svg") and "DIO-EVT-012  id 12  pilot1" in svg and svg.count("<rect") > 300
    assert cli(["label-sheet", "--pki", str(pki_dir), "--out", str(tmp_path / "sheet.svg"), "--lot", "EVT-LOT-2"]) == 0
    sheet = (tmp_path / "sheet.svg").read_text()
    assert sheet.count("DIO-EVT-0") == 20 and 'width="210mm"' in sheet
    assert cli(["pairing-secret-rotate", "--pki", str(pki_dir), "DIO-EVT-012", "--reason", "reprint"]) == 0
    assert StationLabel.decode((tmp_path / "labels" / "DIO-EVT-012.txt").read_text()).pairing_secret_b32 != \
        Registry(pki_dir / "registry.sqlite3").get("DIO-EVT-012").pairing_secret


def test_server_profile_qr_payload_and_command(tmp_path, monkeypatch):
    from pki.server_qr import ServerProfile
    known = ServerProfile("muhoed.example.ru", 8883, 443, "dioneya-root", "ab" * 32)
    text = known.encode()
    assert text == ("DIOS1;H=muhoed.example.ru:8883;P=443;CA=dioneya-root;F=" + "ab" * 32 + ";T=zs/v1;C=F27A")   # shared with Android
    assert ServerProfile.decode(text) == known
    v6 = ServerProfile("[2001:db8::10]", 8883, 0, "dioneya-root", "cd" * 32)
    assert ServerProfile.decode(v6.encode()) == v6
    for bad in (text[:-1] + "B", text.replace("DIOS1", "DIOS2"), text.replace(";T=zs/v1", ""), text.replace("8883", "88831")):
        with pytest.raises(pki.PkiError):
            ServerProfile.decode(bad)
    with pytest.raises(pki.PkiError):
        ServerProfile("muhoed.example.ru", 8883, 443, "dioneya-root", "zz" * 32).encode()
    # end to end through the CLI: root -> issuing -> server cert -> bundle -> server-qr
    pytest.importorskip("qrcode")
    offline, server = tmp_path / "offline", tmp_path / "pki"
    monkeypatch.setenv("ZS_PKI_ROOT_PASSPHRASE", "root-passphrase-for-tests")
    monkeypatch.setenv("ZS_PKI_ISSUING_PASSPHRASE", "issuing-pass-123")
    assert cli(["root-init", "--out", str(offline)]) == 0
    assert cli(["issuing-request", "--pki", str(server)]) == 0
    assert cli(["issuing-sign", "--root", str(offline / "root"), "--csr", str(server / "issuing" / "issuing.csr.pem"), "--out", str(offline / "issuing.crt.pem")]) == 0
    assert cli(["issuing-install", "--pki", str(server), "--cert", str(offline / "issuing.crt.pem"), "--root-cert", str(offline / "root" / "root.crt.pem")]) == 0
    assert cli(["server-cert", "--pki", str(server), "--dns", "muhoed.example.ru"]) == 0
    assert cli(["bundle", "--pki", str(server), "--mqtt-host", "muhoed.example.ru"]) == 0
    assert cli(["server-qr", "--pki", str(server), "--out", str(tmp_path / "qr"), "--https-port", "443"]) == 0
    profile = ServerProfile.decode((tmp_path / "qr" / "server-profile.txt").read_text())
    fp = (server / "bundle" / "server-fingerprint.txt").read_text().strip()
    assert profile.host == "muhoed.example.ru" and profile.mqtt_port == 8883 and profile.https_port == 443 and profile.fingerprint_hex == fp
    assert (tmp_path / "qr" / "server-profile.svg").read_text().startswith("<svg")


def test_nrf_boot_key_create_show_and_refuse_overwrite(tmp_path, capsys):
    from pki import nrf_boot_key
    cli(["nrf-boot-key", "--pki", str(tmp_path)])
    out = capsys.readouterr().out
    k = nrf_boot_key.load(tmp_path)
    assert k.key_path.exists() and (tmp_path / "nrf-boot" / "nrf-boot.pub.pem").exists()
    assert oct(k.key_path.stat().st_mode & 0o777) == "0o600"
    assert k.public_fingerprint_hex in out and "SB_CONFIG_BOOT_SIGNATURE_KEY_FILE" in out
    meta = (tmp_path / "nrf-boot" / "nrf-boot.json").read_text()
    assert k.public_fingerprint_hex in meta and "secp256r1" in meta
    assert cli(["nrf-boot-key", "--pki", str(tmp_path)]) == 2         # refuses to replace a fielded key without --force
    assert nrf_boot_key.load(tmp_path).public_fingerprint_hex == k.public_fingerprint_hex
    cli(["nrf-boot-key", "--pki", str(tmp_path), "--show"])
    assert k.public_fingerprint_hex in capsys.readouterr().out
    cli(["nrf-boot-key", "--pki", str(tmp_path), "--force"])
    assert nrf_boot_key.load(tmp_path).public_fingerprint_hex != k.public_fingerprint_hex
