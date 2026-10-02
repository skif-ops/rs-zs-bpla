"""Points a ghost could explain as well (station/track_fusion.py, ``ambiguous``): a station of the point hears another
target it cannot tell from this one at the same time.  Two targets of one engine note are told apart by geometry
alone, and their rays cross in ghost points; the output API marks such points (dioneya.alert/1 ``track.ambiguous``)."""

import math

import cbor2
import numpy as np

from tests.test_alert_api import feed_station, target_b
from tests.test_bearing_fusion import ARRIVALS, C, STATIONS, bridge, detection, event_id, feed, publish, truth  # noqa: F401


def two_like_targets(station: int, sigma: float = 1.5) -> list[dict]:
    """One bearing per target and window (bearing batch schema 2): the target of truth() and a second one 600 m
    north of it, engine notes 185 and 187 Hz (the same type)."""
    rng = np.random.default_rng(90 + station)
    p = np.array(STATIONS[station])
    rows = []
    for ta in ARRIVALS:
        for target, f0 in ((truth, 185.0), (lambda te: truth(te) + np.array([0.0, 600.0, 30.0]), 187.0)):
            te = ta
            for _ in range(10):
                te = ta - float(np.linalg.norm(target(te) - p)) / C
            v = target(te) - p
            rows.append({"time_us": int(round(ta * 1e6)),
                         "azimuth_deg": (math.degrees(math.atan2(v[0], v[1])) + rng.normal(0, sigma)) % 360.0,
                         "elevation_deg": math.degrees(math.atan2(v[2], math.hypot(v[0], v[1]))) + rng.normal(0, 2.0),
                         "sigma_deg": sigma, "f0_hz": f0})
    return rows


def batches2(station: int, rows: list[dict]) -> list[bytes]:
    out = []
    for k in range(0, len(rows), 4):
        chunk = rows[k:k + 4]
        base = chunk[0]["time_us"]
        out.append(cbor2.dumps({0: 2, 1: 7, 2: station, 3: 7, 4: event_id(station), 5: base, 6: 1, 7: 1,
                                8: [[(r["time_us"] - base) // 1000, int(round(r["azimuth_deg"] * 100)) % 36000,
                                     int(round(r["elevation_deg"] * 100)), int(round(r["sigma_deg"] * 100)), 200, 8,
                                     int(round(r["f0_hz"] * 10))] for r in chunk]}, canonical=True))
    return out


def all_points(store) -> list[dict]:
    return [p for t in store.list_tracks() for p in store.get_track(t["track_id"])["track_points"]]


def test_one_target_is_not_ambiguous(bridge):  # noqa: F811
    store, service = bridge
    feed(store, service, (1, 2, 3))
    points = all_points(store)
    assert len(points) >= 45 and not any(p["ambiguous"] for p in points)


def test_targets_told_apart_by_note_are_not_ambiguous(bridge):  # noqa: F811
    store, service = bridge
    feed_station(store, service, 1, truth, 1, 110.0)
    feed_station(store, service, 3, target_b, 1, 240.0)
    feed_station(store, service, 2, truth, 1, 104.0)
    feed_station(store, service, 4, target_b, 1, 252.0)
    points = all_points(store)
    assert len(points) >= 40 and not any(p["ambiguous"] for p in points)


def test_targets_of_one_type_heard_at_once_are_ambiguous(bridge):  # noqa: F811
    store, service = bridge
    streams = {s: batches2(s, two_like_targets(s)) for s in (1, 2, 3)}
    for s in streams:
        assert publish(store, service, s, detection(s, int(ARRIVALS[0] * 1e6)), "up") == "stored"
    for k in range(max(len(v) for v in streams.values())):
        for s, v in streams.items():
            if k < len(v):
                assert publish(store, service, s, v[k]) == "stored"
    # where a station sees both targets within AMBIGUITY_APART_DEG of each other their rays nearly coincide: a crossing
    # lies near the targets, not far off as a ghost, and the point is not marked
    points = all_points(store)
    assert len(points) >= 40 and sum(p["ambiguous"] for p in points) >= 0.7 * len(points)
    updates = [m["track"] for m in store.list_alerts(0, limit=10000) if m["type"] == "track.update"]
    assert updates and sum(u["ambiguous"] for u in updates) >= 0.7 * len(updates)
