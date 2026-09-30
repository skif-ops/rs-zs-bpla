"""Firmware update over MQTT (MQTT_TLS_ICD_v0_1 addendum F): release manifest and its offline Ed25519 signature,
the image information block, the fwreq/fw messages, the release repository and the bridge's answer to a request.

The release key is not the command key: the server that signs commands only forwards a manifest and a signature
made offline (``python -m pki.cli fw-sign``); the station checks them against the release keys compiled into
its firmware."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import struct
import uuid

import cbor2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SIGN_DOMAIN = b"DIO-FW-V1"
MANIFEST_SCHEMA = 1
MANIFEST_MAX_BYTES = 96
TARGET_STM32_APP = 1
TARGET_NRF52 = 2
TARGET_MODEL = 3                     # station classifier model package (addendum I, station/model_codec.py)
TARGETS = {TARGET_STM32_APP: "stm32-app", TARGET_NRF52: "nrf52", TARGET_MODEL: "model"}
FW_INFO_OFFSET = 0x400
FW_INFO_BYTES = 32
FW_INFO_MAGIC = 0x464F4944          # "DIOF" little-endian
FW_INFO_FORMAT = 1
STM32_IMAGE_CAPACITY = 1016 * 1024  # one bank minus the boot record page
MESSAGE_SCHEMA = 1
REQUEST_MESSAGE_TYPE = 8
CHUNK_MESSAGE_TYPE = 9
CHUNK_BYTES = 1024
REQUEST_MAX_BYTES = 48
SERVE_WINDOW_US = 24 * 3600 * 1_000_000
UPDATE_COMMAND = "CMD_UPDATE_FIRMWARE"
REJECT_DETAILS = {1: "not supported (no release key)", 2: "manifest or signature", 3: "wrong target",
                  4: "version not newer (model: already active)", 5: "image too large", 6: "another update running",
                  7: "running image still on trial"}
FAIL_DETAILS = {1: "flash error", 2: "SHA-256 mismatch", 3: ".fw_info mismatch (model: package check)", 4: "download stalled"}


def _canonical(obj: object) -> bytes:
    return cbor2.dumps(obj, canonical=True)


def _uint32(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 0xFFFFFFFF:
        raise ValueError(f"{name} is outside uint32 range")
    return value


@dataclass(frozen=True)
class FirmwareInfo:
    target: int
    version: int


def build_fw_info(target: int, version: int) -> bytes:
    return struct.pack("<IHHI20x", FW_INFO_MAGIC, FW_INFO_FORMAT, target, version)


def parse_fw_info(image: bytes) -> FirmwareInfo:
    if len(image) < FW_INFO_OFFSET + FW_INFO_BYTES:
        raise ValueError("image is too short for the .fw_info block")
    magic, fmt, target, version = struct.unpack_from("<IHHI", image, FW_INFO_OFFSET)
    if magic != FW_INFO_MAGIC or fmt != FW_INFO_FORMAT or version == 0:
        raise ValueError("image carries no valid .fw_info block at offset 0x400")
    return FirmwareInfo(target=target, version=version)


@dataclass(frozen=True)
class Manifest:
    target: int
    version: int
    size: int
    sha256: bytes

    def encode(self) -> bytes:
        _uint32(self.target, "target", 1)
        _uint32(self.version, "version", 1)
        _uint32(self.size, "size", 1)
        if not isinstance(self.sha256, bytes) or len(self.sha256) != 32:
            raise ValueError("manifest sha256 must contain 32 bytes")
        encoded = _canonical({0: MANIFEST_SCHEMA, 1: self.target, 2: self.version, 3: self.size, 4: self.sha256})
        if len(encoded) > MANIFEST_MAX_BYTES:
            raise ValueError("manifest exceeds its size limit")
        return encoded


def decode_manifest(raw: bytes) -> Manifest:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MANIFEST_MAX_BYTES:
        raise ValueError("manifest must be 1..96 bytes")
    try:
        obj = cbor2.loads(raw)
    except Exception:
        raise ValueError("invalid manifest CBOR") from None
    if not isinstance(obj, dict) or set(obj) != set(range(5)) or _canonical(obj) != raw:
        raise ValueError("manifest is not the canonical five-key map")
    if obj[0] != MANIFEST_SCHEMA:
        raise ValueError("unsupported manifest schema")
    manifest = Manifest(target=obj[1], version=obj[2], size=obj[3], sha256=obj[4])
    manifest.encode()
    return manifest


def manifest_for_image(image: bytes) -> Manifest:
    info = parse_fw_info(image)
    return Manifest(target=info.target, version=info.version, size=len(image), sha256=hashlib.sha256(image).digest())


def release_key_id(public_raw: bytes) -> bytes:
    return hashlib.sha256(public_raw).digest()[:8]


class ReleaseSigner:
    """The offline release key (Ed25519): signs "DIO-FW-V1" || manifest."""

    def __init__(self, private_key: Ed25519PrivateKey):
        self._key = private_key
        self.public_raw = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.key_id = release_key_id(self.public_raw)

    @classmethod
    def from_pem_file(cls, path: str | Path) -> "ReleaseSigner":
        key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("release key must be Ed25519")
        return cls(key)

    @property
    def public_key_hex(self) -> str:
        return self.public_raw.hex()

    def sign(self, manifest_bytes: bytes) -> bytes:
        return self._key.sign(SIGN_DOMAIN + manifest_bytes)


def verify_release(manifest_bytes: bytes, key_id: bytes, signature: bytes, public_keys: list[bytes]) -> Manifest:
    """The station's check (zs_fw_update_check) minus target/version/size: key known, signature valid."""
    manifest = decode_manifest(manifest_bytes)
    for raw in public_keys:
        if release_key_id(raw) == key_id:
            try:
                Ed25519PublicKey.from_public_bytes(raw).verify(signature, SIGN_DOMAIN + manifest_bytes)
            except Exception:
                raise ValueError("invalid release signature") from None
            return manifest
    raise ValueError("unknown release key")


def command_payload(manifest_bytes: bytes, key_id: bytes, signature: bytes) -> dict[str, str]:
    """The JSON payload of a CMD_UPDATE_FIRMWARE command (command_codec turns it into key 7)."""
    return {"manifest": manifest_bytes.hex(), "release_key_id": key_id.hex(), "signature": signature.hex()}


def payload_to_wire(payload: dict) -> dict[int, bytes]:
    if not isinstance(payload, dict) or set(payload) != {"manifest", "release_key_id", "signature"}:
        raise ValueError("firmware update payload carries exactly manifest, release_key_id, signature")
    try:
        manifest = bytes.fromhex(payload["manifest"])
        key_id = bytes.fromhex(payload["release_key_id"])
        signature = bytes.fromhex(payload["signature"])
    except (TypeError, ValueError):
        raise ValueError("firmware update payload fields must be hex") from None
    decode_manifest(manifest)
    if len(key_id) != 8 or len(signature) != 64:
        raise ValueError("release key id is 8 bytes and the signature 64")
    return {0: manifest, 1: key_id, 2: signature}


def payload_from_wire(obj: object) -> dict[str, str]:
    if not isinstance(obj, dict) or set(obj) != {0, 1, 2} or not all(isinstance(obj[k], bytes) for k in obj):
        raise ValueError("invalid firmware update payload keys")
    payload = command_payload(obj[0], obj[1], obj[2])
    payload_to_wire(payload)
    return payload


# ---- fwreq / fw ----

@dataclass(frozen=True)
class FirmwareRequest:
    station_id: int
    command_id: bytes
    offset: int
    length: int


def encode_request(request: FirmwareRequest) -> bytes:
    _check_head(request.station_id, request.command_id, request.offset)
    if type(request.length) is not int or not 0 < request.length <= CHUNK_BYTES:
        raise ValueError("request length is 1..1024")
    return _canonical({0: MESSAGE_SCHEMA, 1: REQUEST_MESSAGE_TYPE, 2: request.station_id, 3: request.command_id,
                       4: request.offset, 5: request.length})


def _check_head(station_id: int, command_id: bytes, offset: int) -> None:
    _uint32(station_id, "station_id", 1)
    _uint32(offset, "offset")
    if not isinstance(command_id, bytes) or len(command_id) != 16 or not any(command_id):
        raise ValueError("command_id must be a non-nil 16-byte UUID")


def _decode_message(raw: bytes, message_type: int, limit: int) -> dict:
    if len(raw) > limit:
        raise ValueError("firmware message exceeds its size limit")
    try:
        obj = cbor2.loads(raw)
    except Exception:
        raise ValueError("invalid firmware message CBOR") from None
    if not isinstance(obj, dict) or set(obj) != set(range(6)) or _canonical(obj) != raw:
        raise ValueError("firmware message is not the canonical six-key map")
    if obj[0] != MESSAGE_SCHEMA or obj[1] != message_type:
        raise ValueError("unsupported firmware message schema or type")
    _check_head(obj[2], obj[3], obj[4])
    return obj


def decode_request(raw: bytes) -> FirmwareRequest:
    obj = _decode_message(raw, REQUEST_MESSAGE_TYPE, REQUEST_MAX_BYTES)
    request = FirmwareRequest(station_id=obj[2], command_id=obj[3], offset=obj[4], length=obj[5])
    encode_request(request)
    return request


def encode_chunk(station_id: int, command_id: bytes, offset: int, data: bytes) -> bytes:
    _check_head(station_id, command_id, offset)
    if not isinstance(data, bytes) or not 0 < len(data) <= CHUNK_BYTES:
        raise ValueError("chunk data is 1..1024 bytes")
    return _canonical({0: MESSAGE_SCHEMA, 1: CHUNK_MESSAGE_TYPE, 2: station_id, 3: command_id, 4: offset, 5: data})


def decode_chunk(raw: bytes) -> tuple[int, bytes, int, bytes]:
    obj = _decode_message(raw, CHUNK_MESSAGE_TYPE, CHUNK_BYTES + 48)
    if not isinstance(obj[5], bytes) or not 0 < len(obj[5]) <= CHUNK_BYTES:
        raise ValueError("chunk data is 1..1024 bytes")
    return obj[2], obj[3], obj[4], obj[5]


# ---- release repository ----

@dataclass(frozen=True)
class Release:
    manifest: Manifest
    manifest_bytes: bytes
    key_id: bytes
    signature: bytes
    image: bytes

    def command_payload(self) -> dict[str, str]:
        return command_payload(self.manifest_bytes, self.key_id, self.signature)


class ReleaseRepository:
    """``<version>.bin``, ``<version>.manifest.cbor`` and ``<version>.sig`` (8-byte key id + 64-byte signature) per
    release; every load re-checks size and SHA-256 of the image against the manifest."""

    NAME = re.compile(r"^([1-9][0-9]*)\.manifest\.cbor$")
    manifest_for = staticmethod(manifest_for_image)   # the model repository (station/model_codec.py) swaps it

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def add(self, image: bytes, signer: ReleaseSigner) -> Release:
        manifest = self.manifest_for(image)
        manifest_bytes = manifest.encode()
        signature = signer.sign(manifest_bytes)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{manifest.version}.bin").write_bytes(image)
        (self.root / f"{manifest.version}.manifest.cbor").write_bytes(manifest_bytes)
        (self.root / f"{manifest.version}.sig").write_bytes(signer.key_id + signature)
        return Release(manifest, manifest_bytes, signer.key_id, signature, image)

    def get(self, version: int) -> Release | None:
        if type(version) is not int or version <= 0:
            return None
        paths = [self.root / f"{version}{suffix}" for suffix in (".bin", ".manifest.cbor", ".sig")]
        if not all(p.is_file() for p in paths):
            return None
        image, manifest_bytes, sig = (p.read_bytes() for p in paths)
        manifest = decode_manifest(manifest_bytes)
        if (manifest.version != version or manifest.size != len(image) or hashlib.sha256(image).digest() != manifest.sha256
                or len(sig) != 72):
            raise ValueError(f"release {version} is inconsistent")
        return Release(manifest, manifest_bytes, sig[:8], sig[8:], image)

    def versions(self) -> list[int]:
        if not self.root.is_dir():
            return []
        return sorted(int(m.group(1)) for p in self.root.iterdir() if (m := self.NAME.match(p.name)))


def serve_request(payload: bytes, topic_station_id: int, *, event_store, repository: ReleaseRepository | None,
                  now_us: int, model_repository: ReleaseRepository | None = None) -> tuple[FirmwareRequest, bytes] | None:
    """The bridge's answer to a fwreq (addendum F §2): the chunk, or None (dropped silently) when the command is not
    an unacknowledged CMD_UPDATE_FIRMWARE of this station from the last 24 h, the release is unknown or the range
    leaves the image.  A manifest of target 3 is served from the model repository (addendum I).  A malformed request
    raises ValueError."""
    request = decode_request(payload)
    if request.station_id != topic_station_id:
        raise ValueError("station_id mismatch between topic and firmware request")
    if repository is None and model_repository is None:
        return None
    record = event_store.command_record(str(uuid.UUID(bytes=request.command_id)))
    if (record is None or record["command"] != UPDATE_COMMAND or record["station_id"] != request.station_id or
            record["acked"] or now_us - record["created_us"] > SERVE_WINDOW_US):
        return None
    wanted = decode_manifest(bytes.fromhex(record["payload"]["manifest"]))
    source = model_repository if wanted.target == TARGET_MODEL else repository
    if source is None:
        return None
    release = source.get(wanted.version)
    if release is None or release.manifest != wanted:
        return None
    if request.offset + request.length > wanted.size:
        return None
    data = release.image[request.offset:request.offset + request.length]
    return request, encode_chunk(request.station_id, request.command_id, request.offset, data)
