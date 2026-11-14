"""LoRa uplink frames (LORA_UPLINK_ICD_v0_1) — the server/gateway side of firmware/src/zs_lora_frame.c.

Event frame (38 bytes, little-endian): type 0x10, profile_id u16 (regional profile), station_id u32, boot_id u32, seq_no u32, time_s u32,
time_ms u16, class_id u8, confidence u8, presence_level u8, f0_hz u16, battery_mv u16, battery_pct u8,
flags u8, tag[8] = HMAC-SHA256(key, bytes[0:30])[:8].  ACK (21 bytes): type 0x90, station_id, boot_id,
seq_no, tag[8] = HMAC-SHA256(key, bytes[0:13] + b"ACK")[:8].  key = SHA-256(b"DIO-LORA-V1" + engineer_key).
"""
from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass

EVENT_TYPE = 0x10
ACK_TYPE = 0x90
EVENT_FRAME_BYTES = 38
ACK_FRAME_BYTES = 21
TAG_BYTES = 8
KEY_CONTEXT = b"DIO-LORA-V1"
FLAG_RETRY = 0x01
FLAG_GSM_DEGRADED = 0x02

_EVENT = struct.Struct("<BHIIIIHBBBHHBB")   # 30 bytes before the tag


@dataclass(frozen=True)
class LoraEvent:
    profile_id: int
    station_id: int
    boot_id: int
    seq_no: int
    time_s: int
    time_ms: int
    class_id: int
    confidence_u8: int
    presence_level: int
    f0_hz: int
    battery_mv: int
    battery_pct: int
    flags: int

    @property
    def event_id(self) -> int:
        return (self.boot_id << 32) | self.seq_no

    @property
    def event_time_us(self) -> int:
        return self.time_s * 1_000_000 + self.time_ms * 1000


def derive_key(engineer_key: bytes) -> bytes:
    if len(engineer_key) != 32:
        raise ValueError("engineer key must be 32 bytes")
    return hashlib.sha256(KEY_CONTEXT + engineer_key).digest()


def _tag(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()[:TAG_BYTES]


def encode_event(e: LoraEvent, key: bytes) -> bytes:
    if e.station_id == 0 or not 0 <= e.presence_level <= 3:
        raise ValueError("invalid LoRa event")
    head = _EVENT.pack(EVENT_TYPE, e.profile_id, e.station_id, e.boot_id, e.seq_no, e.time_s, e.time_ms, e.class_id, e.confidence_u8,
                       e.presence_level, e.f0_hz, e.battery_mv, e.battery_pct, e.flags)
    return head + _tag(key, head)


def decode_event(frame: bytes, key: bytes) -> LoraEvent:
    if len(frame) != EVENT_FRAME_BYTES or frame[0] != EVENT_TYPE:
        raise ValueError("not a LoRa event frame")
    if not hmac.compare_digest(_tag(key, frame[:30]), frame[30:]):
        raise ValueError("LoRa event tag mismatch")
    f = _EVENT.unpack(frame[:30])
    e = LoraEvent(*f[1:])
    if e.station_id == 0 or e.presence_level > 3:
        raise ValueError("invalid LoRa event fields")
    return e


def encode_ack(station_id: int, boot_id: int, seq_no: int, key: bytes) -> bytes:
    if station_id == 0:
        raise ValueError("station_id must be non-zero")
    head = struct.pack("<BIII", ACK_TYPE, station_id, boot_id, seq_no)
    return head + _tag(key, head + b"ACK")


def decode_ack(frame: bytes, key: bytes) -> tuple[int, int, int]:
    if len(frame) != ACK_FRAME_BYTES or frame[0] != ACK_TYPE:
        raise ValueError("not a LoRa ack frame")
    if not hmac.compare_digest(_tag(key, frame[:13] + b"ACK"), frame[13:]):
        raise ValueError("LoRa ack tag mismatch")
    _, station_id, boot_id, seq_no = struct.unpack("<BIII", frame[:13])
    return station_id, boot_id, seq_no


def airtime_ms(payload_bytes: int, sf: int, bandwidth_hz: int, cr_denominator: int = 5) -> float:
    """Semtech AN1200.13 time on air (explicit header, CRC, 8-symbol preamble, LDRO for SF11/12 at 125 kHz)."""
    import math
    tsym = 2 ** sf / bandwidth_hz
    ldro = 1 if (sf >= 11 and bandwidth_hz <= 125_000) else 0
    n = max(math.ceil((8 * payload_bytes - 4 * sf + 28 + 16) / (4 * (sf - 2 * ldro))), 0)
    return ((8 + 4.25) * tsym + (8 + n * cr_denominator) * tsym) * 1000.0
