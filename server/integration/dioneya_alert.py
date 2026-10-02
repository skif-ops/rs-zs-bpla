"""Messages of the output API ``dioneya.alert/1`` (decision 7 of docs/ZVOOK_COMPARISON_DECISIONS_2026-09-30.md;
protocols/DIONEYA_ALERT_API_v1.md, JSON Schema protocols/schemas/dioneya.alert.1.schema.json).

Every message is one JSON object with a common envelope::

    {"schema": "dioneya.alert/1", "seq": 17, "msg_id": "track.update:TRK-...:1790000012000000",
     "type": "track.update", "tenant": "pilot1", "alert_id": "ALR-pilot1-...",
     "time": "2026-09-30T20:00:12.000Z", "created": "2026-09-30T20:00:15.412Z", "track": {...}}

``seq`` is the position in the server's outbox (added when the message is read, the order of delivery), ``msg_id``
is deterministic (the same fact always gives the same id: a consumer drops a repeated one), ``time`` is the time the
data describe (emission time of a track point, arrival time of a bearing), ``created`` when the server made the
message.  Times are UTC, RFC 3339 with milliseconds; coordinates WGS-84 degrees, heights above mean sea level in
metres; directions in degrees clockwise from true north.
"""
from __future__ import annotations

from datetime import datetime, timezone

SCHEMA = "dioneya.alert/1"
TYPES = ("alert.start", "alert.update", "alert.end", "track.update", "track.end", "bearing", "heartbeat")
BEARING_RANGE_M = 5000.0          # a single-station bearing is drawn as a line this long (the fusion range)


def iso(time_us: int) -> str:
    dt = datetime.fromtimestamp(time_us / 1e6, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def envelope(msg_type: str, msg_id: str, tenant: str, alert_id: str | None, time_us: int, created_us: int, **body) -> dict:
    if msg_type not in TYPES:
        raise ValueError(f"unknown message type {msg_type}")
    return {"schema": SCHEMA, "msg_id": msg_id, "type": msg_type, "tenant": tenant, "alert_id": alert_id,
            "time": iso(time_us), "created": iso(created_us), **body}


def heartbeat(last_seq: int, now_us: int, tenant: str | None = None) -> dict:
    """Liveness on an idle channel: not stored, ``seq`` is the last message the channel has delivered."""
    return {"schema": SCHEMA, "seq": last_seq, "msg_id": f"heartbeat:{now_us}", "type": "heartbeat",
            "tenant": tenant, "alert_id": None, "time": iso(now_us), "created": iso(now_us)}


def station(station_id: int, position: tuple[float, float, float] | None) -> dict:
    lat, lon, alt = position if position else (None, None, None)
    return {"station_id": station_id, "lat": None if lat is None else round(lat, 7),
            "lon": None if lon is None else round(lon, 7), "alt_msl_m": None if alt is None else round(alt, 1)}


def alert_object(episode: dict, stations: list[dict], tracks: list[str]) -> dict:
    return {"level": episode["level"], "started": iso(episode["started_us"]),
            "ended": iso(episode["ended_us"]) if episode.get("ended_us") else None,
            "stations": stations, "class": episode["class"], "tracks": tracks}


def track_object(track_id: str, point: dict, *, first_us: int, points: int, stations: list[int], klass: dict,
                 ended_us: int | None = None, end_reason: str | None = None) -> dict:
    return {
        "track_id": track_id,
        "position": {"lat": round(point["lat"], 7), "lon": round(point["lon"], 7), "alt_msl_m": round(point["alt_msl_m"], 1)},
        "error": {"horizontal_m": round(point["horizontal_error_m"], 1), "vertical_m": round(point["vertical_error_m"], 1)},
        "velocity": {"speed_mps": round(point["speed_mps"], 1), "course_deg": round(point["course_deg"], 1),
                     "east_mps": round(point["vx_east_mps"], 2), "north_mps": round(point["vy_north_mps"], 2),
                     "up_mps": round(point["vz_up_mps"], 2)},
        "class": klass,
        "stations": stations,
        "crossing_deg": round(point["crossing_deg"], 1),
        "ambiguous": bool(point.get("ambiguous", False)),
        "first": iso(first_us),
        "points": points,
        "ended": iso(ended_us) if ended_us else None,
        "end_reason": end_reason,
    }


def bearing_object(station_obj: dict, track_event_id: int, sample: dict, klass: dict) -> dict:
    return {"station": station_obj, "track_event_id": f"{track_event_id:016x}",
            "azimuth_deg": round(sample["azimuth_deg"], 2), "elevation_deg": round(sample["elevation_deg"], 2),
            "sigma_deg": round(sample["sigma_deg"], 2), "range_max_m": BEARING_RANGE_M, "class": klass}
