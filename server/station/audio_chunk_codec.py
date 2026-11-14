"""Audio upload over MQTT (MQTT_TLS_ICD_v0_1 addendum B) — the server side of firmware/src/zs_audio_chunk.c.

A segment requested by CMD_REQUEST_AUDIO is the concatenation of the station's independent 1-second IMA-ADPCM
blocks (firmware/src/zs_adpcm.c: 4-byte header predictor/step_index/0, then low-nibble-first codes).  The station
publishes it in chunks of at most 3072 data bytes on ``zs/v1/{tenant}/{station_id}/audio``; every chunk carries the
segment SHA-256.  :class:`AudioAssembler` collects chunks per (station, command, segment), verifies the digest and
returns PCM16 once complete.  The IMA encoder here mirrors the firmware bit-exactly (shared vector).
"""
from __future__ import annotations

import hashlib
import io
import struct
import wave
from dataclasses import dataclass, field

import cbor2

AUDIO_CHUNK_SCHEMA = 1
AUDIO_CHUNK_MESSAGE_TYPE = 7
AUDIO_CHUNK_DATA_MAX = 3072
AUDIO_CHUNK_MAX_BYTES = AUDIO_CHUNK_DATA_MAX + 128
CODEC_IMA_ADPCM_1S = 1
SEGMENT_MAX_CHUNKS = 1024
SEGMENT_NAMES = {0: "pre", 1: "post"}

_INDEX_DELTA = (-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8)
_STEPS = (7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
          130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166,
          1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845,
          8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767)


def _clamp16(v: int) -> int:
    return 32767 if v > 32767 else (-32768 if v < -32768 else v)


def ima_block_bytes(samples: int) -> int:
    return 4 + samples // 2 if samples else 0          # header + ceil((samples - 1) / 2)


def ima_encode_block(pcm: list[int]) -> bytes:
    """Bit-exact mirror of zs_ima_adpcm_encode_block."""
    pred, idx = pcm[0], 0
    out = bytearray(struct.pack("<hBB", pcm[0], 0, 0))
    pending = None
    for s in pcm[1:]:
        diff, code = s - pred, 0
        if diff < 0:
            code, diff = 8, -diff
        step = _STEPS[idx]
        delta = step >> 3
        if diff >= step:
            code |= 4; diff -= step; delta += step
        if diff >= step >> 1:
            code |= 2; diff -= step >> 1; delta += step >> 1
        if diff >= step >> 2:
            code |= 1; delta += step >> 2
        pred = _clamp16(pred - delta if code & 8 else pred + delta)
        idx = min(88, max(0, idx + _INDEX_DELTA[code]))
        if pending is None:
            pending = code
        else:
            out.append(pending | (code << 4)); pending = None
    if pending is not None:
        out.append(pending)
    return bytes(out)


def ima_decode_block(block: bytes, samples: int) -> list[int]:
    if len(block) != ima_block_bytes(samples):
        raise ValueError("IMA block length does not match the sample count")
    pred = struct.unpack_from("<h", block, 0)[0]
    idx = block[2]
    if idx > 88:
        raise ValueError("IMA step index out of range")
    out = [pred]
    for i in range(1, samples):
        byte = block[4 + (i - 1) // 2]
        code = (byte >> 4) if (i - 1) & 1 else (byte & 0x0F)
        step = _STEPS[idx]
        delta = step >> 3
        if code & 4: delta += step
        if code & 2: delta += step >> 1
        if code & 1: delta += step >> 2
        pred = _clamp16(pred - delta if code & 8 else pred + delta)
        idx = min(88, max(0, idx + _INDEX_DELTA[code]))
        out.append(pred)
    return out


def decode_segment(segment: bytes, sample_rate: int) -> list[int]:
    """Concatenated 1-second blocks -> PCM16 samples."""
    block = ima_block_bytes(sample_rate)
    if sample_rate <= 0 or len(segment) % block:
        raise ValueError("segment is not a whole number of 1-second IMA blocks")
    pcm: list[int] = []
    for off in range(0, len(segment), block):
        pcm.extend(ima_decode_block(segment[off:off + block], sample_rate))
    return pcm


def pcm_to_wav(pcm: list[int], sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sample_rate)
        w.writeframes(struct.pack(f"<{len(pcm)}h", *pcm))
    return buf.getvalue()


@dataclass(frozen=True)
class AudioChunk:
    station_id: int
    command_id: bytes
    event_id: int
    segment: int
    chunk_index: int
    chunk_count: int
    codec: int
    sample_rate: int
    segment_start_time_us: int
    segment_sha256: bytes
    data: bytes


def chunk_count(segment_bytes: int) -> int:
    n = -(-segment_bytes // AUDIO_CHUNK_DATA_MAX)
    return 0 if segment_bytes == 0 or n > SEGMENT_MAX_CHUNKS else n


def encode_chunk(c: AudioChunk) -> bytes:
    _validate(c)
    return cbor2.dumps({0: AUDIO_CHUNK_SCHEMA, 1: AUDIO_CHUNK_MESSAGE_TYPE, 2: c.station_id, 3: c.command_id, 4: c.event_id,
                        5: c.segment, 6: c.chunk_index, 7: c.chunk_count, 8: c.codec, 9: c.sample_rate,
                        10: c.segment_start_time_us, 11: c.segment_sha256, 12: c.data}, canonical=True)


def _validate(c: AudioChunk) -> None:
    if not 0 < c.station_id <= 0xFFFFFFFF or not 0 < c.event_id <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("audio chunk station/event id out of range")
    if not isinstance(c.command_id, bytes) or len(c.command_id) != 16:
        raise ValueError("audio chunk command_id must be 16 bytes")
    if c.segment not in SEGMENT_NAMES or c.codec != CODEC_IMA_ADPCM_1S or c.sample_rate <= 0:
        raise ValueError("audio chunk segment/codec/sample rate invalid")
    if not 0 < c.chunk_count <= SEGMENT_MAX_CHUNKS or not 0 <= c.chunk_index < c.chunk_count:
        raise ValueError("audio chunk index/count invalid")
    if not isinstance(c.segment_sha256, bytes) or len(c.segment_sha256) != 32:
        raise ValueError("audio chunk segment digest must be 32 bytes")
    if not isinstance(c.data, bytes) or not 0 < len(c.data) <= AUDIO_CHUNK_DATA_MAX:
        raise ValueError("audio chunk data size invalid")


def decode_chunk(payload: bytes) -> AudioChunk:
    if not isinstance(payload, bytes) or not 0 < len(payload) <= AUDIO_CHUNK_MAX_BYTES:
        raise ValueError("audio chunk size invalid")
    try:
        obj = cbor2.loads(payload)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("audio chunk is not CBOR") from exc
    if not isinstance(obj, dict) or sorted(obj) != list(range(13)):
        raise ValueError("audio chunk must carry keys 0..12")
    if obj[0] != AUDIO_CHUNK_SCHEMA or obj[1] != AUDIO_CHUNK_MESSAGE_TYPE:
        raise ValueError("audio chunk schema/type mismatch")
    if cbor2.dumps(obj, canonical=True) != payload:
        raise ValueError("audio chunk is not canonical CBOR")
    c = AudioChunk(obj[2], obj[3], obj[4], obj[5], obj[6], obj[7], obj[8], obj[9], obj[10], obj[11], obj[12])
    _validate(c)
    return c


@dataclass
class _Pending:
    first: AudioChunk
    parts: dict[int, bytes] = field(default_factory=dict)


@dataclass(frozen=True)
class AudioSegment:
    station_id: int
    command_id: bytes
    event_id: int
    segment: str
    sample_rate: int
    start_time_us: int
    adpcm: bytes
    pcm: list[int]


class AudioAssembler:
    """Collects chunks; a segment completes once every index arrived and the digest matches.  Chunks whose metadata
    disagrees with the first chunk of their segment are rejected (a new command_id restarts cleanly)."""

    def __init__(self, max_pending: int = 16) -> None:
        self._pending: dict[tuple[int, bytes, int], _Pending] = {}
        self._max = max_pending
        self.duplicates = 0

    def add(self, c: AudioChunk) -> AudioSegment | None:
        key = (c.station_id, c.command_id, c.segment)
        p = self._pending.get(key)
        if p is None:
            if len(self._pending) >= self._max:
                self._pending.pop(next(iter(self._pending)))
            p = self._pending[key] = _Pending(c)
        f = p.first
        if (c.event_id, c.chunk_count, c.codec, c.sample_rate, c.segment_start_time_us, c.segment_sha256) != \
           (f.event_id, f.chunk_count, f.codec, f.sample_rate, f.segment_start_time_us, f.segment_sha256):
            raise ValueError("audio chunk metadata disagrees with its segment")
        if c.chunk_index in p.parts:
            self.duplicates += 1
            return None
        p.parts[c.chunk_index] = c.data
        if len(p.parts) < f.chunk_count:
            return None
        adpcm = b"".join(p.parts[i] for i in range(f.chunk_count))
        del self._pending[key]
        if hashlib.sha256(adpcm).digest() != f.segment_sha256:
            raise ValueError("audio segment digest mismatch")
        return AudioSegment(f.station_id, f.command_id, f.event_id, SEGMENT_NAMES[f.segment], f.sample_rate,
                            f.segment_start_time_us, adpcm, decode_segment(adpcm, f.sample_rate))

    def missing(self, station_id: int, command_id: bytes, segment: int) -> list[int]:
        p = self._pending.get((station_id, command_id, segment))
        return [] if p is None else [i for i in range(p.first.chunk_count) if i not in p.parts]
