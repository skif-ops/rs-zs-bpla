"""nRF52840 MCUboot image-signing key for the BLE bridge (firmware/targets/nrf52840_ble).

MCUboot (NCS sysbuild) signs the application image with an ECDSA P-256 private key given as
``SB_CONFIG_BOOT_SIGNATURE_KEY_FILE``; the bootloader embeds the matching public key, so every
station of a lot accepts only images signed with this key.  The key is generated here so it lives
with the rest of the pilot material (``<pki>/nrf-boot/``) and its fingerprint is recorded in the
bundle for traceability.  imgtool needs the private key unencrypted at build time, hence 0600 and
no passphrase; keep the PKI directory itself protected.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from . import ca as pki

KEY_FILE = "nrf-boot.key.pem"
PUB_FILE = "nrf-boot.pub.pem"
META_FILE = "nrf-boot.json"


@dataclass(frozen=True)
class NrfBootKey:
    directory: Path
    public_fingerprint_hex: str   # SHA-256 over the DER SubjectPublicKeyInfo, as MCUboot's imgtool computes it

    @property
    def key_path(self) -> Path:
        return self.directory / KEY_FILE


def public_fingerprint(public_key: ec.EllipticCurvePublicKey) -> str:
    der = public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def create(pki_dir: Path, force: bool = False) -> NrfBootKey:
    d = Path(pki_dir) / "nrf-boot"
    key_path = d / KEY_FILE
    if key_path.exists() and not force:
        raise pki.PkiError(f"{key_path} exists; pass --force to replace it (all fielded nRF images become unsignable)")
    key = ec.generate_private_key(ec.SECP256R1())
    pki._write_private(key_path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
    pub = key.public_key()
    pki._write_public(d / PUB_FILE, pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    meta = {"curve": "secp256r1", "use": "mcuboot image signature, nrf52840_ble", "public_sha256": public_fingerprint(pub)}
    pki._write_public(d / META_FILE, (json.dumps(meta, indent=2) + "\n").encode("ascii"))
    return NrfBootKey(d, meta["public_sha256"])


def load(pki_dir: Path) -> NrfBootKey:
    d = Path(pki_dir) / "nrf-boot"
    key_path = d / KEY_FILE
    if not key_path.exists():
        raise pki.PkiError(f"{key_path} missing; run nrf-boot-key first")
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
        raise pki.PkiError(f"{key_path} is not an ECDSA P-256 key")
    return NrfBootKey(d, public_fingerprint(key.public_key()))
