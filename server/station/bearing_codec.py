"""Bearing stream while tracking (MQTT ICD addendum H): one batch of on-board bearings of the 3+1 array.

The station publishes a batch about once a second on ``zs/v1/{tenant}/{station_id}/bearing`` while its tracking window
is open (after a detection event of a new track): canonical CBOR, message type 7, schema 1 or 2 (firmware
``zs_bearing_batch.h``).  Schema 2 adds a seventh field to every sample, the fundamental of the source the bearing
follows (tenths of a hertz, 0 = not known): a station hearing several targets at once sends one bearing per source and
window (``zs_comb_bearing.h``), and samples of different sources may share a time.  The stream is live data; the
detection events stay the durable record of the track.
"""

from __future__ import annotations

from dataclasses import dataclass

import cbor2

BEARING_BATCH_SCHEMA = 1
BEARING_BATCH_SCHEMA_SOURCES = 2   # samples carry the source's fundamental
SAMPLE_FIELDS = {BEARING_BATCH_SCHEMA: 6, BEARING_BATCH_SCHEMA_SOURCES: 7}
BEARING_BATCH_MESSAGE_TYPE = 7
MAX_BEARING_BATCH_BYTES = 512
MAX_BEARING_SAMPLES = 16

TIME_TRUST = {0: "UNKNOWN", 1: "GNSS_TIME_TRUSTED", 2: "HOLDOVER", 3: "GNSS_TIME_SUSPECT", 4: "UNSYNCED"}


@dataclass(frozen=True)
class BearingSample:
    time_us: int            # wall time of the analysed window's end (base_time_us + dt)
    azimuth_deg: float      # clockwise from north, 0..360
    elevation_deg: float
    sigma_deg: float
    confidence: float       # 0..1
    frames: int             # frames of the 0.5 s window that passed the coherence gate
    f0_hz: float | None = None   # fundamental of the source this bearing follows (schema 2); None = not known

    def as_dict(self) -> dict:
        return {"time_us": self.time_us, "azimuth_deg": self.azimuth_deg, "elevation_deg": self.elevation_deg,
                "sigma_deg": self.sigma_deg, "confidence": self.confidence, "frames": self.frames, "f0_hz": self.f0_hz}


@dataclass(frozen=True)
class BearingBatch:
    station_id: int
    boot_id: int
    track_event_id: int     # the detection event of the track's rising edge
    base_time_us: int
    time_trust: str
    geometry_id: int
    samples: tuple[BearingSample, ...]


def _uint(value: object, bits: int, name: str) -> int:
    if type(value) is not int or not 0 <= value < (1 << bits):
        raise ValueError(f"bearing batch {name} is outside uint{bits} range")
    return value


def _int(value: object, bits: int, name: str) -> int:
    if type(value) is not int or not -(1 << (bits - 1)) <= value < (1 << (bits - 1)):
        raise ValueError(f"bearing batch {name} is outside int{bits} range")
    return value


def decode_bearing_batch(payload: bytes) -> BearingBatch:
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_BEARING_BATCH_BYTES:
        raise ValueError("bearing batch exceeds size limit")
    try:
        obj = cbor2.loads(payload)
    except Exception:
        raise ValueError("invalid bearing batch CBOR") from None
    if not isinstance(obj, dict) or any(type(key) is not int for key in obj) or set(obj) != set(range(9)):
        raise ValueError("invalid bearing batch keys")
    if cbor2.dumps(obj, canonical=True) != payload:
        raise ValueError("bearing batch is not canonical CBOR")
    if obj[0] not in SAMPLE_FIELDS or obj[1] != BEARING_BATCH_MESSAGE_TYPE:
        raise ValueError("unsupported bearing batch version or type")
    fields = SAMPLE_FIELDS[obj[0]]
    station_id = _uint(obj[2], 32, "station_id")
    if station_id == 0:
        raise ValueError("bearing batch station_id must be nonzero")
    track_event_id = _uint(obj[4], 64, "track event_id")
    if track_event_id == 0:
        raise ValueError("bearing batch track event_id must be nonzero")
    base_time_us = _int(obj[5], 64, "base_time_us")
    rows = obj[8]
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_BEARING_SAMPLES:
        raise ValueError("bearing batch holds 1..16 samples")
    samples = []
    last_dt = -1
    for row in rows:
        if not isinstance(row, list) or len(row) != fields:
            raise ValueError(f"bearing sample of schema {obj[0]} must have {fields} fields")
        dt_ms = _uint(row[0], 32, "dt_ms")
        azimuth = _uint(row[1], 16, "azimuth")
        if azimuth > 35999:
            raise ValueError("bearing azimuth is outside 0..35999 hundredths of a degree")
        elevation = _int(row[2], 16, "elevation")
        if not -9000 <= elevation <= 9000:
            raise ValueError("bearing elevation is outside -90..90 degrees")
        sigma = _uint(row[3], 16, "sigma")
        confidence = _uint(row[4], 8, "confidence")
        frames = _uint(row[5], 8, "frames")
        f0_dhz = _uint(row[6], 16, "f0") if fields == 7 else 0
        if dt_ms < last_dt:
            raise ValueError("bearing samples are not in time order")
        last_dt = dt_ms
        samples.append(BearingSample(time_us=base_time_us + dt_ms * 1000, azimuth_deg=azimuth / 100.0,
                                     elevation_deg=elevation / 100.0, sigma_deg=sigma / 100.0,
                                     confidence=round(confidence / 255.0, 4), frames=frames,
                                     f0_hz=f0_dhz / 10.0 if f0_dhz else None))
    return BearingBatch(
        station_id=station_id,
        boot_id=_uint(obj[3], 32, "boot_id"),
        track_event_id=track_event_id,
        base_time_us=base_time_us,
        time_trust=TIME_TRUST.get(_uint(obj[6], 8, "time_trust"), "UNKNOWN"),
        geometry_id=_uint(obj[7], 8, "geometry_id"),
        samples=tuple(samples),
    )
