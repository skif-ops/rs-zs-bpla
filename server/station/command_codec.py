"""Canonical signed command and application-ACK CBOR codec."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import time
import uuid

import cbor2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from station.schemas import StationCommand


SCHEMA_VERSION = 1
COMMAND_MESSAGE_TYPE = 4
ACK_MESSAGE_TYPE = 5
MAX_COMMAND_BYTES = 2048
MAX_ACK_BYTES = 128
MAX_COMMAND_TTL_US = 15 * 60 * 1_000_000
COMMAND_CODES = {"CMD_REQUEST_AUDIO": 1, "CMD_REBOOT": 2, "CMD_SET_PARAMS": 3}   # 2, 3: ICD addendum D
COMMAND_NAMES = {value: key for key, value in COMMAND_CODES.items()}
ACK_RESULTS = {0: "OK", 1: "REJECTED", 2: "FAILED", 3: "EXPIRED"}
AUDIO_SEGMENT_CODES = {"pre": 0, "post": 1, "both": 2, "range": 3}
AUDIO_SEGMENT_NAMES = {value: key for key, value in AUDIO_SEGMENT_CODES.items()}
REBOOT_MAX_DELAY_S = 600
PARAMS_MAX = 8
# Runtime parameter whitelist (MQTT_TLS_ICD_v0_1 addendum D, table 2): name -> (id, min, max, default).
# The station re-validates against its own copy; an unknown id or a value out of range rejects the whole command.
STATION_PARAMS = {
    "heartbeat_period_s": (1, 900, 86400, 21600),
    "mic_channel": (2, 0, 3, 0),
    "event_update_windows": (3, 4, 40, 10),
    "comms_degraded_after": (4, 1, 10, 3),
    "gsm_probe_s": (5, 300, 14400, 1800),
    "listen_dwell_s": (6, 1, 10, 3),
}
STATION_PARAM_NAMES = {spec[0]: name for name, spec in STATION_PARAMS.items()}


@dataclass(frozen=True)
class CommandAck:
    station_id: int
    command_id: str
    result_code: int
    completed_time_us: int
    detail_code: int = 0


class CommandSigner:
    """An Ed25519 signing key with a compact, content-derived public key ID."""

    def __init__(self, private_key: Ed25519PrivateKey):
        self._private_key = private_key
        public_raw = private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        self.key_id = hashlib.sha256(public_raw).digest()[:8]

    @classmethod
    def from_pem_file(cls, path: str | Path) -> "CommandSigner":
        key_path = Path(path)
        if not key_path.is_file():
            raise ValueError("command signing key does not exist")
        try:
            key = serialization.load_pem_private_key(
                key_path.read_bytes(),
                password=None,
            )
        except (TypeError, ValueError):
            raise ValueError("invalid unencrypted command signing key") from None
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("command signing key must be Ed25519")
        return cls(key)

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self._private_key.public_key()

    def sign(self, payload: bytes) -> bytes:
        return self._private_key.sign(payload)


def _canonical(obj: object) -> bytes:
    return cbor2.dumps(obj, canonical=True)


def _uuid_bytes(value: str) -> bytes:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ValueError("command_id must be a UUID") from None
    if parsed.int == 0:
        raise ValueError("command_id must not be the nil UUID")
    return parsed.bytes


def _audio_payload_to_wire(payload: dict) -> dict[int, object]:
    allowed = {"event_id", "segment", "start_offset_ms", "duration_ms"}
    if set(payload) - allowed:
        raise ValueError("unsupported audio request payload field")
    event_id = payload.get("event_id")
    segment = payload.get("segment", "both")
    start = payload.get("start_offset_ms")
    duration = payload.get("duration_ms")
    if type(event_id) is not int or not 0 < event_id <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("audio request event_id is outside uint64 range")
    if segment not in AUDIO_SEGMENT_CODES:
        raise ValueError("unsupported audio request segment")
    if start is not None and (
        type(start) is not int or not -0x80000000 <= start <= 0x7FFFFFFF
    ):
        raise ValueError("audio request start_offset_ms is outside int32 range")
    if duration is not None and (
        type(duration) is not int or not 0 < duration <= 0xFFFFFFFF
    ):
        raise ValueError("audio request duration_ms is outside uint32 range")
    if segment == "range":
        if start is None or duration is None:
            raise ValueError("range audio request requires offset and duration")
    elif start is not None or duration is not None:
        raise ValueError("offset and duration are allowed only for range audio request")
    return {0: event_id, 1: AUDIO_SEGMENT_CODES[segment], 2: start, 3: duration}


def _audio_payload_from_wire(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != set(range(4)):
        raise ValueError("invalid audio request payload keys")
    if type(payload[1]) is not int or payload[1] not in AUDIO_SEGMENT_NAMES:
        raise ValueError("unsupported audio request segment code")
    normalized = {
        "event_id": payload[0],
        "segment": AUDIO_SEGMENT_NAMES[payload[1]],
        "start_offset_ms": payload[2],
        "duration_ms": payload[3],
    }
    _audio_payload_to_wire(normalized)
    return normalized


def _int(value: object) -> bool:
    return type(value) is int


def _reboot_payload_to_wire(payload: dict) -> dict[int, object]:
    if set(payload) - {"delay_s"}:
        raise ValueError("unsupported reboot payload field")
    delay = payload.get("delay_s", 30)
    if not _int(delay) or not 0 <= delay <= REBOOT_MAX_DELAY_S:
        raise ValueError("reboot delay_s is outside 0..600")
    return {0: delay}


def _reboot_payload_from_wire(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != {0}:
        raise ValueError("invalid reboot payload keys")
    normalized = {"delay_s": payload[0]}
    _reboot_payload_to_wire(normalized)
    return normalized


def _params_payload_to_wire(payload: dict) -> dict[int, object]:
    if set(payload) - {"reset", "params"}:
        raise ValueError("unsupported set-params payload field")
    reset = payload.get("reset", False)
    params = payload.get("params", {})
    if type(reset) is not bool or not isinstance(params, dict):
        raise ValueError("set-params needs reset: bool and params: map")
    if len(params) > PARAMS_MAX or (not params and not reset):
        raise ValueError("set-params carries 1..8 parameters (or none with reset)")
    wire: dict[int, int] = {}
    for name, value in params.items():
        spec = STATION_PARAMS.get(name)
        if spec is None:
            raise ValueError(f"unknown station parameter: {name}")
        if not _int(value) or not spec[1] <= value <= spec[2]:
            raise ValueError(f"station parameter {name} outside {spec[1]}..{spec[2]}")
        wire[spec[0]] = value
    return {0: reset, 1: wire}


def _params_payload_from_wire(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != {0, 1} or not isinstance(payload[1], dict):
        raise ValueError("invalid set-params payload keys")
    names = {}
    for param_id, value in payload[1].items():
        if param_id not in STATION_PARAM_NAMES:
            raise ValueError(f"unknown station parameter id: {param_id}")
        names[STATION_PARAM_NAMES[param_id]] = value
    normalized = {"reset": payload[0], "params": names}
    _params_payload_to_wire(normalized)
    return normalized


def _command_payload_to_wire(command_name: str, payload: dict) -> dict[int, object]:
    if command_name == "CMD_REQUEST_AUDIO":
        return _audio_payload_to_wire(payload)
    if command_name == "CMD_REBOOT":
        return _reboot_payload_to_wire(payload)
    if command_name == "CMD_SET_PARAMS":
        return _params_payload_to_wire(payload)
    raise ValueError(f"unsupported command: {command_name}")


def _command_payload_from_wire(command_name: str, payload: object) -> dict[str, object]:
    if command_name == "CMD_REQUEST_AUDIO":
        return _audio_payload_from_wire(payload)
    if command_name == "CMD_REBOOT":
        return _reboot_payload_from_wire(payload)
    if command_name == "CMD_SET_PARAMS":
        return _params_payload_from_wire(payload)
    raise ValueError(f"unsupported command: {command_name}")


def _command_unsigned(command: StationCommand, key_id: bytes) -> dict[int, object]:
    if command.command not in COMMAND_CODES:
        raise ValueError(f"unsupported command: {command.command}")
    if type(command.station_id) is not int or not 0 < command.station_id <= 0xFFFFFFFF:
        raise ValueError("station_id is outside uint32 range")
    if type(command.created_time_us) is not int or type(command.expires_time_us) is not int:
        raise ValueError("command validity fields must be integers")
    validity_us = command.expires_time_us - command.created_time_us
    if command.created_time_us < 0 or not 0 < validity_us <= MAX_COMMAND_TTL_US:
        raise ValueError("invalid command validity interval")
    if not isinstance(command.payload, dict):
        raise ValueError("command payload must be a map")
    if len(key_id) != 8:
        raise ValueError("key_id must contain 8 bytes")
    return {
        0: SCHEMA_VERSION,
        1: COMMAND_MESSAGE_TYPE,
        2: command.station_id,
        3: _uuid_bytes(command.command_id),
        4: command.created_time_us,
        5: command.expires_time_us,
        6: COMMAND_CODES[command.command],
        7: _command_payload_to_wire(command.command, command.payload),
        8: key_id,
    }


def encode_signed_command(command: StationCommand, signer: CommandSigner) -> bytes:
    unsigned = _command_unsigned(command, signer.key_id)
    envelope = dict(unsigned)
    envelope[9] = signer.sign(_canonical(unsigned))
    encoded = _canonical(envelope)
    if len(encoded) > MAX_COMMAND_BYTES:
        raise ValueError("signed command exceeds size limit")
    return encoded


def decode_signed_command(
    payload: bytes,
    public_keys: dict[bytes, Ed25519PublicKey],
    *,
    now_us: int | None = None,
) -> StationCommand:
    if len(payload) > MAX_COMMAND_BYTES:
        raise ValueError("signed command exceeds size limit")
    try:
        obj = cbor2.loads(payload)
    except Exception:
        raise ValueError("invalid command CBOR") from None
    if not isinstance(obj, dict) or set(obj) != set(range(10)):
        raise ValueError("invalid command envelope keys")
    if _canonical(obj) != payload:
        raise ValueError("command envelope is not canonical CBOR")
    if obj[0] != SCHEMA_VERSION or obj[1] != COMMAND_MESSAGE_TYPE:
        raise ValueError("unsupported command envelope version or type")
    if not isinstance(obj[8], bytes) or len(obj[8]) != 8:
        raise ValueError("invalid command key_id")
    if not isinstance(obj[9], bytes) or len(obj[9]) != 64:
        raise ValueError("invalid Ed25519 command signature")
    public_key = public_keys.get(obj[8])
    if public_key is None:
        raise ValueError("unknown command signing key")
    unsigned = {key: obj[key] for key in range(9)}
    try:
        public_key.verify(obj[9], _canonical(unsigned))
    except Exception:
        raise ValueError("invalid Ed25519 command signature") from None
    if not isinstance(obj[3], bytes) or len(obj[3]) != 16:
        raise ValueError("invalid command UUID bytes")
    if type(obj[2]) is not int or type(obj[4]) is not int or type(obj[5]) is not int:
        raise ValueError("invalid signed command integer fields")
    if type(obj[6]) is not int or obj[6] not in COMMAND_NAMES:
        raise ValueError("unsupported command code")
    command_name = COMMAND_NAMES[obj[6]]
    command_payload = _command_payload_from_wire(command_name, obj[7])
    try:
        command = StationCommand(
            command_id=str(uuid.UUID(bytes=obj[3])),
            station_id=obj[2],
            command=command_name,
            payload=command_payload,
            created_time_us=obj[4],
            expires_time_us=obj[5],
        )
    except Exception:
        raise ValueError("invalid signed command fields") from None
    _command_unsigned(command, obj[8])
    effective_now = int(time.time() * 1_000_000) if now_us is None else now_us
    if effective_now < command.created_time_us:
        raise ValueError("signed command is not yet valid")
    if effective_now >= command.expires_time_us:
        raise ValueError("signed command has expired")
    return command


def encode_command_ack(ack: CommandAck) -> bytes:
    if type(ack.station_id) is not int or not 0 < ack.station_id <= 0xFFFFFFFF:
        raise ValueError("station_id is outside uint32 range")
    if type(ack.result_code) is not int or ack.result_code not in ACK_RESULTS:
        raise ValueError("unsupported ACK result code")
    if (type(ack.completed_time_us) is not int or ack.completed_time_us < 0 or
            type(ack.detail_code) is not int or not 0 <= ack.detail_code <= 0xFFFF):
        raise ValueError("invalid ACK result fields")
    encoded = _canonical(
        {
            0: SCHEMA_VERSION,
            1: ACK_MESSAGE_TYPE,
            2: ack.station_id,
            3: _uuid_bytes(ack.command_id),
            4: ack.result_code,
            5: ack.completed_time_us,
            6: ack.detail_code,
        }
    )
    if len(encoded) > MAX_ACK_BYTES:
        raise ValueError("command ACK exceeds size limit")
    return encoded


def decode_command_ack(payload: bytes) -> CommandAck:
    if len(payload) > MAX_ACK_BYTES:
        raise ValueError("command ACK exceeds size limit")
    try:
        obj = cbor2.loads(payload)
    except Exception:
        raise ValueError("invalid command ACK CBOR") from None
    if not isinstance(obj, dict) or set(obj) != set(range(7)):
        raise ValueError("invalid command ACK keys")
    if _canonical(obj) != payload:
        raise ValueError("command ACK is not canonical CBOR")
    if obj[0] != SCHEMA_VERSION or obj[1] != ACK_MESSAGE_TYPE:
        raise ValueError("unsupported command ACK version or type")
    if not isinstance(obj[3], bytes) or len(obj[3]) != 16:
        raise ValueError("invalid command ACK UUID bytes")
    if type(obj[4]) is not int or obj[4] not in ACK_RESULTS:
        raise ValueError("unsupported ACK result code")
    if type(obj[2]) is not int or not 0 < obj[2] <= 0xFFFFFFFF:
        raise ValueError("invalid command ACK station_id")
    if type(obj[5]) is not int or obj[5] < 0:
        raise ValueError("invalid command ACK completion time")
    if type(obj[6]) is not int or not 0 <= obj[6] <= 0xFFFF:
        raise ValueError("invalid command ACK detail code")
    return CommandAck(
        station_id=obj[2],
        command_id=str(uuid.UUID(bytes=obj[3])),
        result_code=obj[4],
        completed_time_us=obj[5],
        detail_code=obj[6],
    )
