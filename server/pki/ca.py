"""Internal PKI for the Muhoed server (Dioneya EVT, 2 lots x 20 stations + 1 bench).

Trust structure
---------------
* ``root``    -- offline root CA "Dioneya Root CA".  The private key is created
  and kept off the server (encrypted PEM, passphrase required).  Only the
  certificate is copied to the server.
* ``issuing`` -- online issuing CA "Dioneya Issuing CA 1" signed by the root.
  Its key lives on the server (0600, service user) and signs the MQTT server
  certificate and every station certificate.  Compromise of the server means
  revoking the issuing CA and re-issuing stations; the root stays intact.
* ``server``  -- TLS server certificate for mosquitto/HTTPS with SAN
  (hostnames and/or IP literals the stations will connect to).
* station     -- client certificate, CN = station serial (mosquitto
  ``use_identity_as_username``), OU = lot.  The private key is generated on the
  station or on the EOL fixture; the server only signs a CSR.  A server-side
  station key is allowed only for the bench unit and must be requested
  explicitly.

Algorithms: ECDSA P-256 / SHA-256 everywhere (BG95 mbedTLS handshake stays
small); root validity 15 years, issuing 5, server 2, station 3.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ORG_NAME = "Dioneya"
ROOT_CN = "Dioneya Root CA"
ISSUING_CN = "Dioneya Issuing CA 1"

ROOT_DAYS = 15 * 365
ISSUING_DAYS = 5 * 365
SERVER_DAYS = 2 * 365
STATION_DAYS = 3 * 365
CRL_DAYS = 30

SERIAL_RE = re.compile(r"^DIO-EVT-(0[0-3][0-9]|040|B01)$")
LOT_BY_SERIAL = (("EVT-LOT-1", range(1, 21)), ("EVT-LOT-2", range(21, 41)))
BENCH_SERIAL = "DIO-EVT-B01"
BENCH_LOT = "BENCH"
BENCH_STATION_ID = 901


class PkiError(RuntimeError):
    pass


# ---------------------------------------------------------------- helpers

def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _name(cn: str, ou: str | None = None) -> x509.Name:
    attrs = [x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORG_NAME)]
    if ou:
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, ou))
    attrs.append(x509.NameAttribute(NameOID.COMMON_NAME, cn))
    return x509.Name(attrs)


def new_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def key_to_pem(key: ec.EllipticCurvePrivateKey, passphrase: bytes | None) -> bytes:
    enc = serialization.BestAvailableEncryption(passphrase) if passphrase else serialization.NoEncryption()
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, enc)


def key_from_pem(data: bytes, passphrase: bytes | None) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(data, password=passphrase)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise PkiError("only ECDSA P-256 keys are accepted")
    return key


def cert_to_pem(cert: x509.Certificate) -> bytes:
    return cert.public_bytes(serialization.Encoding.PEM)


def cert_from_pem(data: bytes) -> x509.Certificate:
    return x509.load_pem_x509_certificate(data)


def fingerprint_sha256(cert: x509.Certificate) -> bytes:
    """SHA-256 over the DER certificate: this is the `server_fingerprint` the station pins."""
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).digest()


def station_id_for_serial(serial: str) -> int:
    if serial == BENCH_SERIAL:
        return BENCH_STATION_ID
    m = SERIAL_RE.match(serial)
    if not m or not m.group(1).isdigit():
        raise PkiError(f"invalid station serial {serial!r}")
    n = int(m.group(1))
    if n == 0:
        raise PkiError("serial 000 is reserved")
    return n


def lot_for_serial(serial: str) -> str:
    if serial == BENCH_SERIAL:
        return BENCH_LOT
    n = station_id_for_serial(serial)
    for lot, numbers in LOT_BY_SERIAL:
        if n in numbers:
            return lot
    raise PkiError(f"serial {serial} is outside the two 20-station lots")


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(path, 0o600)


def _write_public(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.chmod(path, 0o644)


def _serial_number() -> int:
    return int.from_bytes(secrets.token_bytes(16), "big") >> 1  # positive, < 2^127


def _builder(subject: x509.Name, issuer: x509.Name, public_key, days: int) -> x509.CertificateBuilder:
    now = _now()
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
    )


# ------------------------------------------------------------- root CA

@dataclass
class RootMaterial:
    key_pem: bytes  # encrypted PKCS#8
    cert_pem: bytes


def create_root(passphrase: bytes) -> RootMaterial:
    if len(passphrase) < 12:
        raise PkiError("root passphrase must be at least 12 characters")
    key = new_key()
    name = _name(ROOT_CN)
    cert = (
        _builder(name, name, key.public_key(), ROOT_DAYS)
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(
            x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                          data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                          encipher_only=False, decipher_only=False),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return RootMaterial(key_to_pem(key, passphrase), cert_to_pem(cert))


# ---------------------------------------------------------- issuing CA

def create_issuing_request(passphrase: bytes | None) -> tuple[bytes, bytes]:
    """Generates the issuing CA key (on the server) and a CSR to carry to the offline root."""
    key = new_key()
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(_name(ISSUING_CN))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key_to_pem(key, passphrase), csr.public_bytes(serialization.Encoding.PEM)


def sign_issuing(root_key_pem: bytes, root_passphrase: bytes, root_cert_pem: bytes, csr_pem: bytes) -> bytes:
    """Run on the offline machine: root signs the issuing CA CSR."""
    root_key = key_from_pem(root_key_pem, root_passphrase)
    root_cert = cert_from_pem(root_cert_pem)
    csr = x509.load_pem_x509_csr(csr_pem)
    if not csr.is_signature_valid:
        raise PkiError("issuing CSR signature invalid")
    if csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value != ISSUING_CN:
        raise PkiError("issuing CSR has unexpected subject")
    cert = (
        _builder(csr.subject, root_cert.subject, csr.public_key(), ISSUING_DAYS)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                          data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                          encipher_only=False, decipher_only=False),
            critical=True,
        )
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
        .sign(root_key, hashes.SHA256())
    )
    return cert_to_pem(cert)


@dataclass
class IssuingCa:
    key: ec.EllipticCurvePrivateKey
    cert: x509.Certificate
    root_cert: x509.Certificate

    @classmethod
    def load(cls, key_pem: bytes, passphrase: bytes | None, cert_pem: bytes, root_cert_pem: bytes) -> "IssuingCa":
        key = key_from_pem(key_pem, passphrase)
        cert = cert_from_pem(cert_pem)
        root = cert_from_pem(root_cert_pem)
        if cert.public_key().public_numbers() != key.public_key().public_numbers():
            raise PkiError("issuing key does not match issuing certificate")
        verify_chain(cert, root, root)
        return cls(key, cert, root)

    def chain_pem(self) -> bytes:
        return cert_to_pem(self.cert) + cert_to_pem(self.root_cert)

    # ---- server certificate
    def issue_server(self, hostnames: Iterable[str], ips: Iterable[str]) -> tuple[bytes, bytes]:
        hostnames = [h.strip() for h in hostnames if h.strip()]
        ips = [i.strip() for i in ips if i.strip()]
        if not hostnames and not ips:
            raise PkiError("server certificate needs at least one hostname or IP")
        sans: list[x509.GeneralName] = [x509.DNSName(h) for h in hostnames]
        sans += [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
        key = new_key()
        cn = hostnames[0] if hostnames else ips[0]
        cert = (
            _builder(_name(cn, "Muhoed"), self.cert.subject, key.public_key(), SERVER_DAYS)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(
                x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                              data_encipherment=False, key_agreement=True, key_cert_sign=False, crl_sign=False,
                              encipher_only=False, decipher_only=False),
                critical=True,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()), critical=False)
            .sign(self.key, hashes.SHA256())
        )
        return key_to_pem(key, None), cert_to_pem(cert)

    # ---- station certificate from CSR
    def sign_station_csr(self, csr_pem: bytes, serial: str) -> bytes:
        csr = x509.load_pem_x509_csr(csr_pem)
        if not csr.is_signature_valid:
            raise PkiError("station CSR signature invalid")
        if not isinstance(csr.public_key(), ec.EllipticCurvePublicKey):
            raise PkiError("station key must be ECDSA P-256")
        cn = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if not cn or cn[0].value != serial:
            raise PkiError(f"CSR common name must equal station serial {serial}")
        lot = lot_for_serial(serial)
        cert = (
            _builder(_name(serial, lot), self.cert.subject, csr.public_key(), STATION_DAYS)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                              data_encipherment=False, key_agreement=True, key_cert_sign=False, crl_sign=False,
                              encipher_only=False, decipher_only=False),
                critical=True,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()), critical=False)
            .sign(self.key, hashes.SHA256())
        )
        return cert_to_pem(cert)

    # ---- CRL
    def build_crl(self, revoked: Iterable[tuple[int, dt.datetime]]) -> bytes:
        now = _now()
        b = (
            x509.CertificateRevocationListBuilder()
            .issuer_name(self.cert.subject)
            .last_update(now)
            .next_update(now + dt.timedelta(days=CRL_DAYS))
        )
        for cert_serial, when in revoked:
            b = b.add_revoked_certificate(
                x509.RevokedCertificateBuilder().serial_number(cert_serial).revocation_date(when).build()
            )
        return b.sign(self.key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)

    def issue_bridge(self, cn: str = "bridge") -> tuple[bytes, bytes]:
        """Client certificate for the server-side MQTT bridge (mosquitto user = CN)."""
        if cn != "bridge":
            raise PkiError("bridge certificate CN must be 'bridge' (ACL user)")
        key = new_key()
        cert = (
            _builder(_name(cn, "Muhoed"), self.cert.subject, key.public_key(), SERVER_DAYS)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                              data_encipherment=False, key_agreement=True, key_cert_sign=False, crl_sign=False,
                              encipher_only=False, decipher_only=False),
                critical=True,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()), critical=False)
            .sign(self.key, hashes.SHA256())
        )
        return key_to_pem(key, None), cert_to_pem(cert)


def make_station_csr(serial: str) -> tuple[bytes, bytes]:
    """Key + CSR generation for the bench unit or an EOL fixture without on-device keygen."""
    station_id_for_serial(serial)
    key = new_key()
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(_name(serial, lot_for_serial(serial)))
        .sign(key, hashes.SHA256())
    )
    return key_to_pem(key, None), csr.public_bytes(serialization.Encoding.PEM)


# ---------------------------------------------------------- verification

def verify_chain(leaf: x509.Certificate, issuer: x509.Certificate, root: x509.Certificate) -> None:
    """Signature + validity + CA constraints; raises PkiError on any failure."""
    now = _now()
    for cert, signer, name in ((leaf, issuer, "leaf"), (issuer, root, "issuer")):
        if cert.issuer != signer.subject:
            raise PkiError(f"{name}: issuer name mismatch")
        try:
            cert.verify_directly_issued_by(signer)
        except Exception as exc:  # noqa: BLE001
            raise PkiError(f"{name}: signature invalid ({exc})") from exc
        if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
            raise PkiError(f"{name}: outside validity period")
    for ca in (issuer, root):
        bc = ca.extensions.get_extension_for_class(x509.BasicConstraints).value
        if not bc.ca:
            raise PkiError("issuer is not a CA certificate")


def bundle_json(root_cert: x509.Certificate, issuing_cert: x509.Certificate, server_cert: x509.Certificate,
                mqtt_host: str, mqtt_port: int, tenant_by_lot: dict[str, str]) -> str:
    """What the Android app / QR / EOL fixture receives: chain, pinning data and endpoint."""
    return json.dumps(
        {
            "schema": "dioneya-pki-bundle-v1",
            "generated_at": _now().isoformat(),
            "root_cn": ROOT_CN,
            "root_not_after": root_cert.not_valid_after_utc.isoformat(),
            "issuing_cn": ISSUING_CN,
            "issuing_not_after": issuing_cert.not_valid_after_utc.isoformat(),
            "server_cn": server_cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value,
            "server_not_after": server_cert.not_valid_after_utc.isoformat(),
            "server_fingerprint_sha256": fingerprint_sha256(server_cert).hex(),
            "ca_reference": "dioneya-root",
            "mqtt_host": mqtt_host,
            "mqtt_port": mqtt_port,
            "tenant_by_lot": tenant_by_lot,
        },
        ensure_ascii=False,
        indent=2,
    )
