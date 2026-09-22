"""``python -m pki.cli`` -- Muhoed PKI administration.

Directory layout (``--pki DIR``, default ``server/data/pki``)::

    root/root.crt.pem            root certificate (public)      [server + offline]
    root/root.key.pem            root private key (encrypted)   [OFFLINE MACHINE ONLY]
    issuing/issuing.key.pem      issuing key, 0600              [server]
    issuing/issuing.csr.pem      request carried to the root    [server -> offline]
    issuing/issuing.crt.pem      issuing certificate            [offline -> server]
    issuing/ca-chain.pem         issuing + root                 [server, mosquitto cafile]
    issuing/crl.pem              current CRL                    [server, mosquitto crlfile]
    server/server.key.pem        mosquitto/HTTPS key, 0600
    server/server.crt.pem        mosquitto/HTTPS certificate
    stations/<SERIAL>/           csr.pem, <SERIAL>.crt.pem (and key only for bench/fixture keygen)
    registry.sqlite3             station registry + audit
    bundle/                      ca-chain.pem, server-fingerprint.txt, bundle.json (for app/QR/EOL)

Passphrases come from ``ZS_PKI_ROOT_PASSPHRASE`` / ``ZS_PKI_ISSUING_PASSPHRASE``
or an interactive prompt; they are never accepted on the command line.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import ca as pki
from .mosquitto import render_acl, render_listener_conf
from .registry import Registry

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "data" / "pki"


def _passphrase(env: str, prompt: str, confirm: bool = False, required: bool = True) -> bytes | None:
    value = os.environ.get(env)
    if value is None:
        if not sys.stdin.isatty():
            if required:
                raise pki.PkiError(f"set {env} or run interactively")
            return None
        value = getpass.getpass(prompt)
        if confirm and getpass.getpass("Repeat: ") != value:
            raise pki.PkiError("passphrases differ")
    if not value and required:
        raise pki.PkiError("empty passphrase not allowed")
    return value.encode() if value else None


def _issuing(d: Path) -> pki.IssuingCa:
    pw = _passphrase("ZS_PKI_ISSUING_PASSPHRASE", "Issuing CA key passphrase (empty if none): ", required=False)
    return pki.IssuingCa.load(
        (d / "issuing" / "issuing.key.pem").read_bytes(), pw,
        (d / "issuing" / "issuing.crt.pem").read_bytes(),
        (d / "root" / "root.crt.pem").read_bytes(),
    )


def _registry(d: Path) -> Registry:
    return Registry(d / "registry.sqlite3")


def _write_crl(d: Path, issuing: pki.IssuingCa, reg: Registry) -> Path:
    out = d / "issuing" / "crl.pem"
    pki._write_public(out, issuing.build_crl(reg.revoked_cert_serials()))
    return out


# ------------------------------------------------------------- commands

def cmd_root_init(a):
    d = Path(a.out)
    if (d / "root" / "root.key.pem").exists():
        raise pki.PkiError("root already exists; refusing to overwrite")
    pw = _passphrase("ZS_PKI_ROOT_PASSPHRASE", "New root passphrase (>=12 chars): ", confirm=True)
    m = pki.create_root(pw)
    pki._write_private(d / "root" / "root.key.pem", m.key_pem)
    pki._write_public(d / "root" / "root.crt.pem", m.cert_pem)
    print(f"root CA created in {d/'root'} -- keep root.key.pem OFFLINE, copy only root.crt.pem to the server")


def cmd_issuing_request(a):
    d = Path(a.pki)
    if (d / "issuing" / "issuing.key.pem").exists() and not a.force:
        raise pki.PkiError("issuing key exists; use --force to create a new one (old certificates will stop validating)")
    pw = _passphrase("ZS_PKI_ISSUING_PASSPHRASE", "Issuing CA key passphrase (empty = unencrypted, protected by 0600 only): ",
                     confirm=True, required=False)
    key_pem, csr_pem = pki.create_issuing_request(pw)
    pki._write_private(d / "issuing" / "issuing.key.pem", key_pem)
    pki._write_public(d / "issuing" / "issuing.csr.pem", csr_pem)
    print(f"issuing key + CSR written; carry {d/'issuing'/'issuing.csr.pem'} to the offline root machine")


def cmd_issuing_sign(a):
    r = Path(a.root)
    pw = _passphrase("ZS_PKI_ROOT_PASSPHRASE", "Root passphrase: ")
    cert = pki.sign_issuing((r / "root.key.pem").read_bytes(), pw, (r / "root.crt.pem").read_bytes(),
                            Path(a.csr).read_bytes())
    pki._write_public(Path(a.out), cert)
    print(f"issuing certificate written to {a.out}; carry it back to the server together with root.crt.pem")


def cmd_issuing_install(a):
    d = Path(a.pki)
    root_pem = Path(a.root_cert).read_bytes()
    cert_pem = Path(a.cert).read_bytes()
    pki._write_public(d / "root" / "root.crt.pem", root_pem)
    pki._write_public(d / "issuing" / "issuing.crt.pem", cert_pem)
    issuing = _issuing(d)  # verifies key<->cert and chain
    pki._write_public(d / "issuing" / "ca-chain.pem", issuing.chain_pem())
    reg = _registry(d)
    _write_crl(d, issuing, reg)
    print("issuing CA installed and verified; ca-chain.pem and an empty crl.pem written")


def cmd_server_cert(a):
    d = Path(a.pki)
    issuing = _issuing(d)
    key_pem, cert_pem = issuing.issue_server(a.dns or [], a.ip or [])
    pki._write_private(d / "server" / "server.key.pem", key_pem)
    pki._write_public(d / "server" / "server.crt.pem", cert_pem)
    fp = pki.fingerprint_sha256(pki.cert_from_pem(cert_pem)).hex()
    print(f"server certificate written; SHA-256 fingerprint (pin this in stations): {fp}")


def cmd_bridge_cert(a):
    d = Path(a.pki)
    key_pem, cert_pem = _issuing(d).issue_bridge()
    pki._write_private(d / "server" / "bridge.key.pem", key_pem)
    pki._write_public(d / "server" / "bridge.crt.pem", cert_pem)
    print("bridge client certificate written to server/bridge.*.pem (ZS_MQTT_CERT / ZS_MQTT_KEY)")


def cmd_station_add(a):
    reg = _registry(Path(a.pki))
    rows = reg.add_all_lots() if a.all_lots else [reg.add(a.serial, a.note or "")]
    for r in rows:
        print(f"{r.serial} station_id={r.station_id} lot={r.lot} tenant={r.tenant} status={r.status}")


def _issue_station(d: Path, issuing: pki.IssuingCa, reg: Registry, serial: str, csr_pem: bytes) -> Path:
    cert_pem = issuing.sign_station_csr(csr_pem, serial)
    cert = pki.cert_from_pem(cert_pem)
    sdir = d / "stations" / serial
    pki._write_public(sdir / "csr.pem", csr_pem)
    pki._write_public(sdir / f"{serial}.crt.pem", cert_pem)
    reg.mark_provisioned(serial, cert.serial_number, pki.fingerprint_sha256(cert).hex(),
                         cert.not_valid_after_utc.isoformat())
    return sdir


def cmd_station_sign(a):
    d = Path(a.pki)
    issuing, reg = _issuing(d), _registry(d)
    sdir = _issue_station(d, issuing, reg, a.serial, Path(a.csr).read_bytes())
    print(f"{a.serial} provisioned; certificate in {sdir}")


def cmd_station_keygen(a):
    if not a.allow_server_side_key:
        raise pki.PkiError("station keys belong on the station/EOL fixture; pass --allow-server-side-key only for the bench unit")
    d = Path(a.pki)
    issuing, reg = _issuing(d), _registry(d)
    key_pem, csr_pem = pki.make_station_csr(a.serial)
    sdir = _issue_station(d, issuing, reg, a.serial, csr_pem)
    pki._write_private(sdir / f"{a.serial}.key.pem", key_pem)
    print(f"{a.serial} key+certificate generated in {sdir} (server-side key: bench/fixture use only)")


def cmd_station_commission(a):
    reg = _registry(Path(a.pki))
    r = reg.mark_commissioned(a.serial, a.detail or "")
    print(f"{r.serial} status={r.status} commissioned_at={r.commissioned_at}")


def cmd_station_revoke(a):
    d = Path(a.pki)
    issuing, reg = _issuing(d), _registry(d)
    r = reg.revoke(a.serial, a.reason)
    out = _write_crl(d, issuing, reg)
    print(f"{r.serial} revoked; CRL updated at {out} -- reload mosquitto and regenerate the ACL")


def cmd_crl(a):
    d = Path(a.pki)
    print(_write_crl(d, _issuing(d), _registry(d)))


def cmd_mosquitto_acl(a):
    text = render_acl(_registry(Path(a.pki)))
    if a.out:
        Path(a.out).write_text(text)
        print(f"ACL written to {a.out}")
    else:
        sys.stdout.write(text)


def cmd_mosquitto_conf(a):
    text = render_listener_conf(a.cert_dir)
    if a.out:
        Path(a.out).write_text(text)
        print(f"listener config written to {a.out}")
    else:
        sys.stdout.write(text)


def cmd_bundle(a):
    d = Path(a.pki)
    issuing, reg = _issuing(d), _registry(d)
    server_cert = pki.cert_from_pem((d / "server" / "server.crt.pem").read_bytes())
    out = Path(a.out) if a.out else d / "bundle"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ca-chain.pem").write_bytes(issuing.chain_pem())
    (out / "server-fingerprint.txt").write_text(pki.fingerprint_sha256(server_cert).hex() + "\n")
    (out / "bundle.json").write_text(pki.bundle_json(issuing.root_cert, issuing.cert, server_cert,
                                                     a.mqtt_host, a.mqtt_port, reg.tenant_by_lot))
    print(f"bundle written to {out}")


def cmd_station_package(a):
    """Everything the EOL fixture loads into one station's BG95: cert, chain, endpoint data."""
    d = Path(a.pki)
    reg = _registry(d)
    r = reg.get(a.serial)
    if r.status not in ("provisioned", "commissioned"):
        raise pki.PkiError(f"{a.serial} has no active certificate")
    bundle = json.loads((d / "bundle" / "bundle.json").read_text())
    out = Path(a.out) / a.serial
    out.mkdir(parents=True, exist_ok=True)
    (out / "station.crt.pem").write_bytes((d / "stations" / a.serial / f"{a.serial}.crt.pem").read_bytes())
    (out / "ca-chain.pem").write_bytes((d / "bundle" / "ca-chain.pem").read_bytes())
    (out / "station.json").write_text(json.dumps({
        "serial": r.serial, "station_id": r.station_id, "lot": r.lot, "tenant": r.tenant,
        "mqtt_host": bundle["mqtt_host"], "mqtt_port": bundle["mqtt_port"],
        "server_fingerprint_sha256": bundle["server_fingerprint_sha256"],
        "ca_reference": bundle["ca_reference"], "topic_prefix": "zs/v1",
        "cert_not_after": r.cert_not_after,
        "pairing_secret_b32": reg.ensure_pairing_secret(a.serial),
    }, indent=2))
    print(f"station package for {a.serial} written to {out} (private key is NOT included by design)")


def _label(reg: Registry, serial: str):
    from .label import StationLabel
    r = reg.get(serial)
    return StationLabel(r.serial, r.station_id, r.tenant, reg.ensure_pairing_secret(serial))


def cmd_label_qr(a):
    """Label QR for one station: SVG (and PNG when Pillow is present) + the payload text."""
    from .label import render_svg
    reg = _registry(Path(a.pki))
    lab = _label(reg, a.serial)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{a.serial}.svg").write_text(render_svg(lab), encoding="utf-8")
    (out / f"{a.serial}.txt").write_text(lab.encode() + "\n", encoding="ascii")
    if a.png:
        try:
            import qrcode
            qrcode.make(lab.encode(), error_correction=qrcode.constants.ERROR_CORRECT_M).save(out / f"{a.serial}.png")
        except ImportError:
            print("PNG skipped: Pillow is not installed (SVG written)")
    print(f"label for {a.serial} written to {out} ({lab.encode()})")


def cmd_label_sheet(a):
    """A4 sheet with labels for every registered station (or one lot)."""
    from .label import render_sheet_svg
    reg = _registry(Path(a.pki))
    rows = reg.list(lot=a.lot)
    if not rows:
        raise pki.PkiError("no stations registered")
    labels = [_label(reg, r.serial) for r in rows]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_sheet_svg(labels, columns=a.columns), encoding="utf-8")
    print(f"label sheet with {len(labels)} stations written to {out}")


def cmd_server_qr(a):
    """QR with the server profile (host/ports, CA reference, pinned fingerprint) for the installer app."""
    from .server_qr import ServerProfile
    d = Path(a.pki)
    profile = ServerProfile.from_bundle(d / "bundle" / "bundle.json", https_port=a.https_port, topic_prefix=a.topic_prefix)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    text = profile.encode()
    (out / "server-profile.txt").write_text(text + "\n", encoding="ascii")
    try:
        import qrcode
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        modules = qr.get_matrix()
        n = len(modules)
        px = 40.0 / n
        cells = "".join(f'<rect x="{x * px:.3f}" y="{y * px:.3f}" width="{px:.3f}" height="{px:.3f}"/>'
                        for y, row in enumerate(modules) for x, dark in enumerate(row) if dark)
        (out / "server-profile.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="44mm" height="52mm" viewBox="0 0 44 52">'
            '<rect width="44" height="52" fill="white"/>'
            f'<g transform="translate(2,2)" fill="black">{cells}</g>'
            f'<text x="22" y="46.5" font-family="monospace" font-size="2.6" text-anchor="middle">{profile.host}:{profile.mqtt_port}  {profile.ca_reference}</text>'
            f'<text x="22" y="49.5" font-family="monospace" font-size="2.0" text-anchor="middle">sha256 {profile.fingerprint_hex[:32]}…</text></svg>',
            encoding="utf-8")
        if a.png:
            qrcode.make(text, error_correction=qrcode.constants.ERROR_CORRECT_M).save(out / "server-profile.png")
    except ImportError:
        print("SVG/PNG skipped: qrcode is not installed (payload text written)")
    print(f"server profile QR written to {out} ({text})")


def cmd_nrf_boot_key(a):
    """ECDSA P-256 signing key for the nRF52840 bridge images (MCUboot, firmware/targets/nrf52840_ble)."""
    from . import nrf_boot_key
    k = nrf_boot_key.create(Path(a.pki), force=a.force) if not a.show else nrf_boot_key.load(Path(a.pki))
    print(f"nRF boot key: {k.key_path}")
    print(f"public key sha256: {k.public_fingerprint_hex}")
    print(f'build: west build -b evt_pre_20_ble firmware/targets/nrf52840_ble -- -DSB_CONFIG_BOOT_SIGNATURE_KEY_FILE=\\"{k.key_path.as_posix()}\\"')


def cmd_pairing_secret_rotate(a):
    reg = _registry(Path(a.pki))
    reg.rotate_pairing_secret(a.serial, a.reason)
    print(f"pairing secret of {a.serial} rotated; reprint the label and reload the station package")


def cmd_list(a):
    reg = _registry(Path(a.pki))
    for r in reg.list(lot=a.lot, status=a.status):
        print(f"{r.serial:12s} id={r.station_id:<4d} {r.lot:10s} {r.tenant:8s} {r.status:12s} "
              f"cert_until={r.cert_not_after or '-'}")


def cmd_audit(a):
    for e in _registry(Path(a.pki)).audit_log(a.limit):
        print(f"{e['at']} {e['serial'] or '-':12s} {e['action']:10s} {e['detail'] or ''}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m pki.cli", description="Muhoed PKI administration")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        sp = sub.add_parser(name, **kw)
        sp.set_defaults(fn=fn)
        return sp

    s = add("root-init", cmd_root_init, help="[offline] create the root CA");                  s.add_argument("--out", required=True)
    s = add("issuing-request", cmd_issuing_request, help="[server] create issuing key + CSR");  s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("--force", action="store_true")
    s = add("issuing-sign", cmd_issuing_sign, help="[offline] sign the issuing CSR with the root")
    s.add_argument("--root", required=True); s.add_argument("--csr", required=True); s.add_argument("--out", required=True)
    s = add("issuing-install", cmd_issuing_install, help="[server] install issuing cert + root cert")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("--cert", required=True); s.add_argument("--root-cert", required=True)
    s = add("server-cert", cmd_server_cert, help="[server] issue the mosquitto/HTTPS certificate")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("--dns", action="append"); s.add_argument("--ip", action="append")
    s = add("bridge-cert", cmd_bridge_cert, help="[server] issue the MQTT bridge client certificate (CN=bridge)"); s.add_argument("--pki", default=str(DEFAULT_DIR))
    s = add("station-add", cmd_station_add, help="register a serial or all 41 units")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("serial", nargs="?"); s.add_argument("--all-lots", action="store_true"); s.add_argument("--note")
    s = add("station-sign", cmd_station_sign, help="sign a station CSR (key stays on the station/fixture)")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("serial"); s.add_argument("--csr", required=True)
    s = add("station-keygen", cmd_station_keygen, help="bench/fixture only: generate key+cert on the server")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("serial"); s.add_argument("--allow-server-side-key", action="store_true")
    s = add("station-commission", cmd_station_commission, help="mark a station commissioned on site")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("serial"); s.add_argument("--detail")
    s = add("station-revoke", cmd_station_revoke, help="revoke a station certificate and refresh the CRL")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("serial"); s.add_argument("--reason", required=True)
    s = add("crl", cmd_crl, help="rewrite issuing/crl.pem");                                  s.add_argument("--pki", default=str(DEFAULT_DIR))
    s = add("mosquitto-acl", cmd_mosquitto_acl, help="render station_acl.conf from the registry")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("--out")
    s = add("mosquitto-conf", cmd_mosquitto_conf, help="render the TLS listener config")
    s.add_argument("--cert-dir", default="/mosquitto/certs"); s.add_argument("--out")
    s = add("bundle", cmd_bundle, help="export ca-chain, server fingerprint and bundle.json for app/QR/EOL")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("--mqtt-host", required=True); s.add_argument("--mqtt-port", type=int, default=8883); s.add_argument("--out")
    s = add("station-package", cmd_station_package, help="export one station's cert+chain+endpoint for the EOL fixture")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("serial"); s.add_argument("--out", required=True)
    s = add("label-qr", cmd_label_qr, help="render the enclosure label QR (SVG/PNG) for one station")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("serial"); s.add_argument("--out", required=True); s.add_argument("--png", action="store_true")
    s = add("label-sheet", cmd_label_sheet, help="render an A4 SVG sheet of labels for all (or one lot's) stations")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("--out", required=True); s.add_argument("--lot"); s.add_argument("--columns", type=int, default=4)
    s = add("server-qr", cmd_server_qr, help="render the server profile QR (host, ports, CA, fingerprint) for the installer app")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("--out", required=True); s.add_argument("--https-port", type=int, default=0)
    s.add_argument("--topic-prefix", default="zs/v1"); s.add_argument("--png", action="store_true")
    s = add("nrf-boot-key", cmd_nrf_boot_key, help="create (or --show) the MCUboot signing key for the nRF52840 bridge images")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("--force", action="store_true"); s.add_argument("--show", action="store_true")
    s = add("pairing-secret-rotate", cmd_pairing_secret_rotate, help="generate a new label secret for a station (reprint + reload)")
    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("serial"); s.add_argument("--reason", required=True)
    s = add("list", cmd_list, help="list stations");                                           s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("--lot"); s.add_argument("--status")
    s = add("audit", cmd_audit, help="print the audit log");                                    s.add_argument("--pki", default=str(DEFAULT_DIR)); s.add_argument("--limit", type=int, default=200)

    a = p.parse_args(argv)
    try:
        a.fn(a)
    except pki.PkiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
