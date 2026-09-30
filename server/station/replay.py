"""Replay of a target's movement without a map (decision 3 of docs/ZVOOK_COMPARISON_DECISIONS_2026-09-30.md).

One call gathers everything the replay page needs for a time window: the stations, the fused tracks (their points)
and every station's bearings, all in one local east/north/up frame in metres around the stations, so the page draws a
metric plane without map tiles.  The window comes from a fused track, a system event or explicit times.

Bearing times are arrival times at the station (the sound heard then); track point times are emission times (where
the target was).  The page shows both as they are: a ray at time t points where the target was range / c earlier.
"""
from __future__ import annotations

import numpy as np

from fusion.geodesy import EnuFrame

MAX_WINDOW_US = 30 * 60 * 1_000_000        # one replay covers at most half an hour
TRACK_MARGIN_US = 15_000_000               # bearings heard up to ~15 s (5 km of sound) around the track's points
EVENT_WINDOW_US = 150_000_000              # an event without fused track: its detections' time +- 2.5 min


class ReplayError(ValueError):
    pass


def _window(store, track_id: str | None, system_event_id: str | None, since_us: int | None, until_us: int | None):
    if track_id:
        track = store.get_track(track_id)
        if track is None:
            raise ReplayError("track not found")
        if track["first_time_us"] is None:
            raise ReplayError("track has no points yet")
        return track["first_time_us"] - TRACK_MARGIN_US, track["last_time_us"] + TRACK_MARGIN_US
    if system_event_id:
        event = store.get_event(system_event_id)
        if event is None:
            raise ReplayError("event not found")
        tracks = [t for t in store.list_tracks(system_event_id=system_event_id) if t["first_time_us"] is not None]
        bearings = store.list_bearings(system_event_id=system_event_id, limit=50000)
        times = [t["first_time_us"] for t in tracks] + [t["last_time_us"] for t in tracks] + [b["time_us"] for b in bearings]
        if times:
            return min(times) - TRACK_MARGIN_US, max(times) + TRACK_MARGIN_US
        created = int(event["created_time_us"])
        return created - EVENT_WINDOW_US // 2, created + EVENT_WINDOW_US // 2
    if since_us is None or until_us is None:
        raise ReplayError("give track_id, system_event_id or since_us and until_us")
    return since_us, until_us


def build_replay(store, *, track_id: str | None = None, system_event_id: str | None = None,
                 since_us: int | None = None, until_us: int | None = None) -> dict:
    t0, t1 = _window(store, track_id, system_event_id, since_us, until_us)
    if t1 <= t0:
        raise ReplayError("empty time window")
    if t1 - t0 > MAX_WINDOW_US:
        raise ReplayError("time window longer than 30 minutes")
    bearings = store.list_bearings(since_us=t0, until_us=t1, limit=50000)
    tracks = [store.get_track(t["track_id"]) for t in store.list_tracks(since_us=t0, until_us=t1, limit=50)]
    tracks = [t for t in tracks if t and t["track_points"]]
    # station positions: from the detection of one of the station's tracks, else the heartbeat
    station_tracks: dict[int, int | None] = {}
    for b in bearings:
        station_tracks.setdefault(b["station_id"], b["track_event_id"])
    for t in tracks:
        for m in t["members"]:
            station_tracks.setdefault(m["station_id"], m["track_event_id"])
    positions = {s: store.station_position(s, e) for s, e in sorted(station_tracks.items())}
    positions = {s: p for s, p in positions.items() if p}
    if positions:
        lat0 = float(np.mean([p[0] for p in positions.values()]))
        lon0 = float(np.mean([p[1] for p in positions.values()]))
        alt0 = float(np.mean([p[2] for p in positions.values()]))
    elif tracks:
        first = tracks[0]["track_points"][0]
        lat0, lon0, alt0 = first["lat"], first["lon"], 0.0
    else:
        return {"window": {"since_us": t0, "until_us": t1}, "origin": None, "stations": [], "tracks": [], "bearings": []}
    frame = EnuFrame(lat0, lon0, alt0)

    def enu(lat, lon, alt):
        e, n, u = frame.to_enu(lat, lon, alt)
        return round(float(e), 1), round(float(n), 1), round(float(u), 1)

    stations = []
    for s, (lat, lon, alt) in positions.items():
        e, n, u = enu(lat, lon, alt)
        stations.append({"station_id": s, "lat": lat, "lon": lon, "alt_msl_m": alt, "e": e, "n": n, "u": u})
    out_tracks = []
    for t in tracks:
        points = []
        for p in t["track_points"]:
            e, n, u = enu(p["lat"], p["lon"], p["alt_msl_m"])
            points.append({"t_us": p["time_us"], "e": e, "n": n, "u": u, "alt_msl_m": round(p["alt_msl_m"], 1),
                           "h_err_m": p["horizontal_error_m"], "v_err_m": p["vertical_error_m"],
                           "ve": round(p["vx_east_mps"], 2), "vn": round(p["vy_north_mps"], 2),
                           "speed_mps": round(p["speed_mps"], 1), "course_deg": round(p["course_deg"], 1),
                           "crossing_deg": p["crossing_deg"], "stations": p["stations"]})
        out_tracks.append({"track_id": t["track_id"], "system_event_id": t["system_event_id"], "stations": t["stations"],
                           "points": points})
    out_bearings = [{"station_id": b["station_id"], "track_event_id": b["track_event_id"], "t_us": b["time_us"],
                     "azimuth_deg": b["azimuth_deg"], "elevation_deg": b["elevation_deg"], "sigma_deg": b["sigma_deg"],
                     "time_trust": b["time_trust"]}
                    for b in bearings if b["station_id"] in positions]
    times = [b["t_us"] for b in out_bearings] + [p["t_us"] for t in out_tracks for p in t["points"]]
    return {
        "window": {"since_us": t0, "until_us": t1,
                   "first_us": min(times) if times else t0, "last_us": max(times) if times else t1},
        "origin": {"lat": lat0, "lon": lon0, "alt_msl_m": alt0},
        "stations": stations,
        "tracks": out_tracks,
        "bearings": out_bearings,
    }


def replay_sources(store, limit: int = 50) -> dict:
    """What can be replayed: recent fused tracks and recent system events."""
    events = [e for e in store.list_events(limit) if e.get("event_type") in ("AIR_ALERT", "AIR_WARNING")]
    return {"tracks": store.list_tracks(limit=limit),
            "events": [{"system_event_id": e["system_event_id"], "event_type": e["event_type"],
                        "created_time_us": e["created_time_us"], "classification_label": e.get("classification_label"),
                        "stations": e.get("source_station_ids", [])} for e in events]}
