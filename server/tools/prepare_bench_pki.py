#!/usr/bin/env python3
"""Create a fresh, isolated PKI and broker config for DIO-TWIN-001..040.

Run on the operator workstation. Copy only OUT/deploy to the bench VPS;
OUT/offline-root contains the encrypted root key and must remain offline.
The command refuses to overwrite an existing output directory.
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pki import ca  # noqa: E402
from pki.mosquitto import render_acl, render_listener_conf  # noqa: E402
from pki.registry import Registry  # noqa: E402


def prepare(out: Path) -> None:
    if out.exists():
        raise FileExistsError(f"refusing to overwrite {out}")
    offline = out / "offline-root"
    deploy = out / "deploy"
    pki = deploy / "server" / "data" / "pki"
    config = deploy / "config"
    tls = config / "tls"

    passphrase = secrets.token_urlsafe(32).encode("ascii")
    root = ca.create_root(passphrase)
    ca._write_private(offline / "root.key.pem", root.key_pem)
    ca._write_private(offline / "root-passphrase.txt", passphrase + b"\n")
    ca._write_public(offline / "root.crt.pem", root.cert_pem)

    issuing_key, csr = ca.create_issuing_request(None)
    issuing_cert = ca.sign_issuing(root.key_pem, passphrase, root.cert_pem, csr)
    issuer = ca.IssuingCa.load(issuing_key, None, issuing_cert, root.cert_pem)
    ca._write_private(pki / "issuing" / "issuing.key.pem", issuing_key)
    ca._write_public(pki / "issuing" / "issuing.crt.pem", issuing_cert)
    ca._write_public(pki / "root" / "root.crt.pem", root.cert_pem)
    ca._write_public(tls / "ca-chain.pem", issuer.chain_pem())

    server_key, server_cert = issuer.issue_server(["mqtt", "localhost"], ["127.0.0.1"])
    bridge_key, bridge_cert = issuer.issue_bridge("bridge-bench")
    ca._write_private(tls / "server.key.pem", server_key)
    ca._write_public(tls / "server.crt.pem", server_cert)
    ca._write_private(tls / "bridge-bench.key.pem", bridge_key)
    ca._write_public(tls / "bridge-bench.crt.pem", bridge_cert)

    signer = Ed25519PrivateKey.generate()
    ca._write_private(tls / "command-signing-bench.key", signer.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    ca._write_public(tls / "command-signing-bench.pub", signer.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw))

    registry = Registry(pki / "registry.sqlite3")
    for number in range(1, 41):
        serial = f"DIO-TWIN-{number:03d}"
        row = registry.add(serial, "digital twin; bench only")
        if row.station_id != 9000 + number or row.tenant != "bench":
            raise ValueError(f"unexpected registry mapping for {serial}")
        key, request = ca.make_station_csr(serial)
        certificate = issuer.sign_station_csr(request, serial)
        station_dir = pki / "stations" / serial
        ca._write_private(station_dir / f"{serial}.key.pem", key)
        ca._write_public(station_dir / f"{serial}.crt.pem", certificate)
        cert = ca.cert_from_pem(certificate)
        registry.mark_provisioned(serial, cert.serial_number,
                                  ca.fingerprint_sha256(cert).hex(), cert.not_valid_after_utc.isoformat())

    ca._write_public(tls / "crl.pem", issuer.build_crl([]))
    ca._write_public(config / "station_acl.conf", render_acl(registry).encode())
    ca._write_public(config / "mosquitto.conf", render_listener_conf().encode())
    print(f"Prepared {len(registry.active())} bench identities (9001..9040).")
    print(f"Copy only {deploy} to the isolated bench host; retain {offline} offline.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
