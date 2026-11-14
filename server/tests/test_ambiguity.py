"""Two targets of one type and engine note (station/track_hypotheses.py): their rays cross in ghost points, and
geometry alone tells them apart.  Three stations do: only the rays of one target meet in one point.  Two stations
hearing both targets cannot, and no track is formed while the other pairing of their rays is not refuted.  A track a
triple confirmed may go on with two of its stations for a while; its points are then ``ambiguous`` (dioneya.alert/1
``track.ambiguous``): only the continuity of the track says which crossing is the target."""

import math

import cbor2
import numpy as np

from tests.test_alert_api import feed_stations, target_b
from tests.test_bearing_fusion import ARRIVALS, C, FRAME, STATIONS, bridge, detection, event_id, feed, in_time, publish, truth  # noqa: F401


def second(te: float) -> np.ndarray:
    """A target of the same type 600 m north of truth()'s."""
    return truth(te) + np.array([0.0, 600.0, 30.0])


def two_like_targets(station: int, sigma: float = 1.5, until_s: float | None = None) -> list[dict]:
    """One bearing per target and window (bearing batch schema 2): the target of truth() and second(), engine notes
    185 and 187 Hz (the same type); bearings up to until_s (scene seconds) only, when given."""
    rng = np.random.default_rng(90 + station)
    p = np.array(STATIONS[station])
    rows = []
    for ta in ARRIVALS:
        if until_s is not None and ta > until_s:
            break
        for target, f0 in ((truth, 185.0), (second, 187.0)):
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


def feed_like(store, service, streams: dict[int, list[bytes]]) -> None:
    for s in streams:
        assert publish(store, service, s, detection(s, int(ARRIVALS[0] * 1e6)), "up") == "stored"
    for s, b in in_time(streams):
        assert publish(store, service, s, b) == "stored"


def all_points(store) -> list[dict]:
    return [p for t in store.list_tracks() for p in store.get_track(t["track_id"])["track_points"]]


def miss(p: dict) -> float:
    """Distance of a point to the nearer target."""
    xy = np.array(FRAME.to_enu(p["lat"], p["lon"], p["alt_msl_m"])[:2])
    return min(float(np.linalg.norm(xy - t(p["time_us"] * 1e-6)[:2])) for t in (truth, second))


def test_one_target_is_not_ambiguous(bridge):  # noqa: F811
    store, service = bridge
    feed(store, service, (1, 2, 3))
    points = all_points(store)
    assert len(points) >= 45 and not any(p["ambiguous"] for p in points)


def test_targets_told_apart_by_note_are_not_ambiguous(bridge):  # noqa: F811
    store, service = bridge
    feed_stations(store, service, (1, truth, 1, 110.0), (3, target_b, 1, 240.0), (2, truth, 1, 104.0), (4, target_b, 1, 252.0))
    points = all_points(store)
    assert len(points) >= 40 and not any(p["ambiguous"] for p in points)


def test_three_stations_tell_like_targets_apart(bridge):  # noqa: F811
    store, service = bridge
    feed_like(store, service, {s: batches2(s, two_like_targets(s)) for s in (1, 2, 3)})
    assert len(store.list_tracks()) == 2
    points = all_points(store)
    assert len(points) >= 80 and max(miss(p) for p in points) < 300.0          # no ghost point
    assert not any(p["ambiguous"] for p in points)


def test_two_stations_hearing_like_targets_form_no_track(bridge):  # noqa: F811
    """Stations 1 and 2 each hear both targets: rays 1-1 and 2-2, or 1-2 and 2-1, explain them alike."""
    store, service = bridge
    feed_like(store, service, {s: batches2(s, two_like_targets(s)) for s in (1, 2)})
    assert store.list_tracks() == []
    assert not [m for m in store.list_alerts(0, limit=10000) if m["type"] == "track.update"]


def test_a_confirmed_track_goes_on_with_two_stations_for_a_while_marked_ambiguous(bridge):  # noqa: F811
    store, service = bridge
    until = ARRIVALS[0] + 30.0                                       # station 3 stops hearing them after 30 s
    feed_like(store, service, {1: batches2(1, two_like_targets(1)), 2: batches2(2, two_like_targets(2)),
                               3: batches2(3, two_like_targets(3, until_s=until))})
    points = all_points(store)
    triple = [p for p in points if p["stations"] == [1, 2, 3]]
    pair = [p for p in points if p["stations"] == [1, 2]]
    assert len(triple) >= 20 and not any(p["ambiguous"] for p in triple)
    assert pair and all(p["ambiguous"] for p in pair)
    assert max(miss(p) for p in points) < 300.0
    from station.track_hypotheses import CONTINUE_S
    from station.track_segments import ACTIVE_S
    last_triple = max(p["time_us"] for p in triple) * 1e-6
    # no longer than the confirmation lasts: station 3's segment is active ACTIVE_S after its last bearing
    assert max(p["time_us"] for p in pair) * 1e-6 <= until + ACTIVE_S + CONTINUE_S + 1.0
    updates = [m["track"] for m in store.list_alerts(0, limit=10000) if m["type"] == "track.update"]
    assert any(u["ambiguous"] for u in updates) and last_triple < until
