"""Audio upload over MQTT (MQTT_TLS_ICD v0.1 addendum B): the bridge side of ``zs/v1/{tenant}/{station}/audio``.

Every chunk is checked against the command it answers (a ``CMD_REQUEST_AUDIO`` this server issued to the same
station, for the same event and one of the requested segments), then kept in the store until its segment is
complete.  A complete segment is verified (SHA-256 of the IMA-ADPCM blocks), decoded and written as a WAV file
(temporary name, then an atomic rename); the audio row and the removal of the parts are one transaction, so a crash
in between replays the last chunk (the MQTT ACK comes after processing) and completes the segment again.

Parts survive a bridge restart: an in-memory assembler would lose the chunks the broker already delivered, the
station would not send them again, and its ACK OK would claim audio the server never stored.
"""
from __future__ import annotations

import hashlib
import os
import time
import uuid
from pathlib import Path

from station.audio_chunk_codec import SEGMENT_NAMES, decode_chunk, decode_segment, pcm_to_wav

MAX_SAMPLE_RATE = 48_000
MAX_PENDING_PARTS_PER_STATION = 2048      # ~6 MB of ADPCM: several full requests ("both" = 314 parts)
AUDIO_COMMAND = "CMD_REQUEST_AUDIO"


def requested_segments(payload: dict) -> set[int]:
    """Segment numbers (0 pre, 1 post) a CMD_REQUEST_AUDIO payload asks for; a range is one segment by its offset."""
    segment = payload.get("segment", "both")
    if segment == "pre":
        return {0}
    if segment == "post":
        return {1}
    if segment == "both":
        return {0, 1}
    if segment == "range":
        return {0} if int(payload.get("start_offset_ms") or 0) < 0 else {1}
    return set()


def ingest_audio_chunk(payload: bytes, topic_station_id: int, *, event_store, audio_root: Path | None = None,
                       now_us: int | None = None) -> str:
    """'stored' / 'duplicate' / 'already' / 'complete'.  ValueError: the chunk is invalid or not ours (discard)."""
    chunk = decode_chunk(payload)
    if chunk.station_id != topic_station_id:
        raise ValueError("station_id mismatch between topic and audio chunk")
    if chunk.sample_rate > MAX_SAMPLE_RATE:
        raise ValueError("audio chunk sample rate out of range")
    command_id = str(uuid.UUID(bytes=chunk.command_id))
    command = event_store.command_record(command_id)
    if command is None or command["command"] != AUDIO_COMMAND:
        raise ValueError("audio chunk references an unknown audio request")
    if command["station_id"] != chunk.station_id:
        raise ValueError("audio chunk ownership mismatch")
    if int(command["payload"].get("event_id", 0)) != chunk.event_id:
        raise ValueError("audio chunk event does not match its request")
    if chunk.segment not in requested_segments(command["payload"]):
        raise ValueError("audio chunk segment was not requested")
    now = int(time.time() * 1e6) if now_us is None else now_us
    name = SEGMENT_NAMES[chunk.segment]
    status, parts = event_store.add_audio_part(
        station_id=chunk.station_id, command_id=command_id, segment=chunk.segment, segment_name=name,
        chunk_index=chunk.chunk_index, chunk_count=chunk.chunk_count, event_id=chunk.event_id,
        sample_rate=chunk.sample_rate, start_time_us=chunk.segment_start_time_us, sha256=chunk.segment_sha256,
        data=chunk.data, now_us=now, max_pending_parts=MAX_PENDING_PARTS_PER_STATION)
    if status != "complete":
        return status
    adpcm = b"".join(parts or [])
    if hashlib.sha256(adpcm).digest() != chunk.segment_sha256:
        event_store.drop_audio_parts(chunk.station_id, command_id, chunk.segment)
        raise ValueError("audio segment digest mismatch")
    pcm = decode_segment(adpcm, chunk.sample_rate)
    root = Path(audio_root if audio_root is not None else event_store.audio_root)
    folder = root / str(chunk.station_id) / str(chunk.event_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.wav"
    tmp = folder / f".{name}.wav.{os.getpid()}.tmp"
    tmp.write_bytes(pcm_to_wav(pcm, chunk.sample_rate))
    os.replace(tmp, path)
    event_store.complete_audio_segment(
        station_id=chunk.station_id, command_id=command_id, segment=chunk.segment, segment_name=name,
        event_id=chunk.event_id, path=str(path), sample_rate=chunk.sample_rate,
        start_time_us=chunk.segment_start_time_us, sha256=chunk.segment_sha256,
        duration_ms=len(pcm) * 1000 // chunk.sample_rate, now_us=now)
    return "complete"
