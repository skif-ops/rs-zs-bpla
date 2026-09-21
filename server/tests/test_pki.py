"""PKI tests: offline root -> server issuing CA -> server + station certificates.

Runs entirely in a temporary directory; nothing touches server/data.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from pki import ca as pki
from pki.cli import main as cli
from pki.mosquitto import render_acl, render_listener_conf
from pki.registry import DEFAULT_TENANT_BY_LOT, Registry

ROOT_PW = b"root-passphrase-for-tests"


@pytest.fixture
def issuing(tmp_path: Path) -> pki.IssuingCa:
    root = pki.create_root(ROOT_PW)
    key_pem, csr_pem = pki.create_issuing_request(None)
    cert_pem = pki.sign_issuing(root.key_pem, ROOT_PW, root.cert_pem, csr_pem)
    return pki.IssuingCa.load(key_pem, None, cert_pem, root.cert_pem)


# ------------------------------------------------------------ chain

def test_root_and_issuing_chain_verifies(issuing):
    pki.verify_chain(issuing.cert, issuing.root_cert, issuing.root_cert)
    bc = issuing.cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    assert bc.ca and bc.path_length == 0
    root_bc = issuing.root_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    assert root_bc.ca and root_bc.path_length == 1


def test_root_key_requires_passphrase():
    root = pki.create_root(ROOT_PW)
    with pytest.raises(Exception):
        pki.key_from_pem(root.key_pem, b"wrong-passphrase-xx")
    with pytest.raises(pki.PkiError):
        pki.create_root(b"short")


def test_issuing_load_rejects_foreign_key(issuing):
    other_key, _ = pki.create_issuing_request(None)
    with pytest.raises(pki.PkiError):
        pki.IssuingCa.load(other_key, None, pki.cert_to_pem(issuing.cert), pki.cert_to_pem(issuing.root_cert))


def test_issuing_cert_not_signed_by_wrong_root(issuing):
    other_root = pki.create_root(ROOT_PW)
    with pytest.raises(pki.PkiError):
        pki.verify_chain(issuing.cert, pki.cert_from_pem(other_root.cert_pem), pki.cert_from_pem(other_root.cert_pem))


# ------------------------------------------------------------ server cert

def test_server_certificate_has_san_and_server_auth(issuing):
    key_pem, cert_pem = issuing.issue_server(["muhoed.example.ru"], ["10.20.30.40"])
    cert = pki.cert_from_pem(cert_pem)
    pki.verify_chain(cert, issuing.cert, issuing.root_cert)
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert san.get_values_for_type(x509.DNSName) == ["muhoed.example.ru"]
    assert [str(i) for i in san.get_values_for_type(x509.IPAddress)] == ["10.20.30.40"]
    eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert ExtendedKeyUsageOID.SERVER_AUTH in eku
    assert len(pki.fingerprint_sha256(cert)) == 32
    with pytest.raises(pki.PkiError):
        issuing.issue_server([], [])


# ------------------------------------------------------------ station cert

def test_station_csr_signed_with_serial_cn_and_lot(issuing):
    key_pem, csr_pem = pki.make_station_csr("DIO-EVT-021")
    cert = pki.cert_from_pem(issuing.sign_station_csr(csr_pem, "DIO-EVT-021"))
    pki.verify_chain(cert, issuing.cert, issuing.root_cert)
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "DIO-EVT-021"
    assert cert.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)[0].value == "EVT-LOT-2"
    eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert ExtendedKeyUsageOID.CLIENT_AUTH in eku and ExtendedKeyUsageOID.SERVER_AUTH not in eku
    # the private key stays wherever it was generated; the CSR path never sees it
    key = serialization.load_pem_private_key(key_pem, None)
    assert key.public_key().public_numbers() == cert.public_key().public_numbers()


def test_station_csr_cn_must_match_requested_serial(issuing):
    _, csr_pem = pki.make_station_csr("DIO-EVT-001")
    with pytest.raises(pki.PkiError):
        issuing.sign_station_csr(csr_pem, "DIO-EVT-002")


def test_serial_scheme_two_lots_plus_bench():
    assert pki.lot_for_serial("DIO-EVT-001") == "EVT-LOT-1"
    assert pki.lot_for_serial("DIO-EVT-020") == "EVT-LOT-1"
    assert pki.lot_for_serial("DIO-EVT-021") == "EVT-LOT-2"
    assert pki.lot_for_serial("DIO-EVT-040") == "EVT-LOT-2"
    assert pki.lot_for_serial("DIO-EVT-B01") == "BENCH"
    assert pki.station_id_for_serial("DIO-EVT-B01") == 901
    assert pki.station_id_for_serial("DIO-EVT-037") == 37
    for bad in ("DIO-EVT-041", "DIO-EVT-000", "DIO-EVT-1", "station01", "DIO-EVT-B02"):
        with pytest.raises(pki.PkiError):
            pki.lot_for_serial(bad)


# ------------------------------------------------------------ revocation

def test_revocation_lands_in_crl(issuing, tmp_path):
    reg = Registry(tmp_path / "r.sqlite3")
    reg.add("DIO-EVT-005")
    _, csr = pki.make_station_csr("DIO-EVT-005")
    cert = pki.cert_from_pem(issuing.sign_station_csr(csr, "DIO-EVT-005"))
    reg.mark_provisioned("DIO-EVT-005", cert.serial_number, pki.fingerprint_sha256(cert).hex(), "2029-01-01T00:00:00+00:00")
    reg.mark_commissioned("DIO-EVT-005")
    reg.revoke("DIO-EVT-005", "lost in the field")
    crl = x509.load_pem_x509_crl(issuing.build_crl(reg.revoked_cert_serials()))
    assert crl.is_signature_valid(issuing.key.public_key())
    assert crl.get_revoked_certificate_by_serial_number(cert.serial_number) is not None
    assert reg.get("DIO-EVT-005").status == "revoked"
    # re-provisioning after revocation is allowed; revoking twice is not
    with pytest.raises(pki.PkiError):
        reg.revoke("DIO-EVT-005", "again")
    _, csr2 = pki.make_station_csr("DIO-EVT-005")
    cert2 = pki.cert_from_pem(issuing.sign_station_csr(csr2, "DIO-EVT-005"))
    reg.mark_provisioned("DIO-EVT-005", cert2.serial_number, pki.fingerprint_sha256(cert2).hex(), "2029-01-01T00:00:00+00:00")
    assert reg.get("DIO-EVT-005").status == "provisioned"


# ------------------------------------------------------------ registry + ACL

def test_registry_registers_41_units_with_tenants(tmp_path):
    reg = Registry(tmp_path / "r.sqlite3")
    rows = reg.add_all_lots()
    assert len(rows) == 41
    assert len(reg.add_all_lots()) == 41  # idempotent
    lots = {r.lot for r in rows}
    assert lots == {"EVT-LOT-1", "EVT-LOT-2", "BENCH"}
    assert {r.tenant for r in rows} == set(DEFAULT_TENANT_BY_LOT.values())
    assert len({r.station_id for r in rows}) == 41
    with pytest.raises(pki.PkiError):
        reg.add("DIO-EVT-001")
    with pytest.raises(pki.PkiError):
        reg.mark_commissioned("DIO-EVT-001")  # not provisioned yet
    with pytest.raises(pki.PkiError):
        reg.revoke("DIO-EVT-001", "no cert")


def test_acl_only_lists_active_stations_and_isolates_tenants(tmp_path):
    reg = Registry(tmp_path / "r.sqlite3")
    reg.add_all_lots()
    reg.mark_provisioned("DIO-EVT-003", 123, "ab" * 32, "2029-01-01T00:00:00+00:00")
    reg.mark_provisioned("DIO-EVT-025", 124, "cd" * 32, "2029-01-01T00:00:00+00:00")
    reg.mark_provisioned("DIO-EVT-B01", 125, "ef" * 32, "2029-01-01T00:00:00+00:00")
    reg.mark_provisioned("DIO-EVT-007", 126, "aa" * 32, "2029-01-01T00:00:00+00:00")
    reg.revoke("DIO-EVT-007", "returned")
    acl = render_acl(reg)
    assert "user DIO-EVT-003\ntopic write zs/v1/pilot1/3/up" in acl
    assert "user DIO-EVT-025\ntopic write zs/v1/pilot2/25/up" in acl
    assert "user DIO-EVT-B01\ntopic write zs/v1/bench/901/up" in acl
    assert "topic read zs/v1/pilot1/3/down" in acl and "topic read zs/v1/pilot1/3/receipt" in acl
    assert "user DIO-EVT-007" not in acl            # revoked
    assert "user DIO-EVT-004" not in acl            # never provisioned
    assert "topic read zs/v1/pilot1/+/up" in acl and "topic write zs/v1/pilot2/+/down" in acl
    conf = render_listener_conf()
    assert "allow_anonymous false" in conf and "require_certificate true" in conf and "crlfile" in conf


# ------------------------------------------------------------ full CLI workflow

def test_cli_end_to_end(tmp_path, monkeypatch):
    offline = tmp_path / "offline"
    server = tmp_path / "server_pki"
    monkeypatch.setenv("ZS_PKI_ROOT_PASSPHRASE", ROOT_PW.decode())
    monkeypatch.setenv("ZS_PKI_ISSUING_PASSPHRASE", "issuing-pass-123")

    assert cli(["root-init", "--out", str(offline)]) == 0
    assert cli(["root-init", "--out", str(offline)]) == 2            # refuses to overwrite
    if os.name != "nt":  # POSIX mode bits; Windows protects the file via ACLs instead
        assert oct(os.stat(offline / "root" / "root.key.pem").st_mode & 0o777) == "0o600"

    assert cli(["issuing-request", "--pki", str(server)]) == 0
    assert cli(["issuing-sign", "--root", str(offline / "root"), "--csr", str(server / "issuing" / "issuing.csr.pem"),
                "--out", str(offline / "issuing.crt.pem")]) == 0
    assert cli(["issuing-install", "--pki", str(server), "--cert", str(offline / "issuing.crt.pem"),
                "--root-cert", str(offline / "root" / "root.crt.pem")]) == 0
    assert (server / "issuing" / "ca-chain.pem").exists() and (server / "issuing" / "crl.pem").exists()
    assert not (server / "root" / "root.key.pem").exists()          # root key never lands on the server

    assert cli(["server-cert", "--pki", str(server), "--dns", "muhoed.example.ru", "--ip", "10.20.30.40"]) == 0
    assert cli(["bridge-cert", "--pki", str(server)]) == 0
    bridge = pki.cert_from_pem((server / "server" / "bridge.crt.pem").read_bytes())
    assert bridge.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "bridge"
    assert cli(["station-add", "--pki", str(server), "--all-lots"]) == 0
    assert cli(["station-keygen", "--pki", str(server), "DIO-EVT-B01"]) == 2      # needs explicit flag
    assert cli(["station-keygen", "--pki", str(server), "DIO-EVT-B01", "--allow-server-side-key"]) == 0

    # a real station: key on the fixture, only the CSR reaches the server
    key_pem, csr_pem = pki.make_station_csr("DIO-EVT-012")
    (tmp_path / "012.csr").write_bytes(csr_pem)
    assert cli(["station-sign", "--pki", str(server), "DIO-EVT-012", "--csr", str(tmp_path / "012.csr")]) == 0
    assert not (server / "stations" / "DIO-EVT-012" / "DIO-EVT-012.key.pem").exists()
    assert cli(["station-sign", "--pki", str(server), "DIO-EVT-012", "--csr", str(tmp_path / "012.csr")]) == 2  # already active

    assert cli(["bundle", "--pki", str(server), "--mqtt-host", "muhoed.example.ru", "--mqtt-port", "8883"]) == 0
    bundle = json.loads((server / "bundle" / "bundle.json").read_text())
    assert bundle["schema"] == "dioneya-pki-bundle-v1" and len(bundle["server_fingerprint_sha256"]) == 64
    assert bundle["tenant_by_lot"] == DEFAULT_TENANT_BY_LOT
    assert cli(["station-package", "--pki", str(server), "DIO-EVT-012", "--out", str(tmp_path / "eol")]) == 0
    pkg = json.loads((tmp_path / "eol" / "DIO-EVT-012" / "station.json").read_text())
    assert pkg["station_id"] == 12 and pkg["tenant"] == "pilot1" and pkg["mqtt_port"] == 8883
    assert not (tmp_path / "eol" / "DIO-EVT-012" / "station.key.pem").exists()

    # the station certificate validates against the chain mosquitto will use
    chain = x509.load_pem_x509_certificates((server / "issuing" / "ca-chain.pem").read_bytes())
    station_cert = pki.cert_from_pem((server / "stations" / "DIO-EVT-012" / "DIO-EVT-012.crt.pem").read_bytes())
    pki.verify_chain(station_cert, chain[0], chain[1])

    assert cli(["station-commission", "--pki", str(server), "DIO-EVT-012", "--detail", "site A"]) == 0
    assert cli(["station-revoke", "--pki", str(server), "DIO-EVT-B01", "--reason", "bench rebuilt"]) == 0
    crl = x509.load_pem_x509_crl((server / "issuing" / "crl.pem").read_bytes())
    assert len(list(crl)) == 1
    assert cli(["mosquitto-acl", "--pki", str(server), "--out", str(tmp_path / "acl.conf")]) == 0
    acl = (tmp_path / "acl.conf").read_text()
    assert "user DIO-EVT-012" in acl and "user DIO-EVT-B01" not in acl
    assert cli(["list", "--pki", str(server), "--status", "commissioned"]) == 0
    assert cli(["audit", "--pki", str(server)]) == 0
