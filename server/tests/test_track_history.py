"""History of a fused track (station/track_fusion.py, ``recompute``): the points shown before stay where the members
cannot give points any more, and fresh points replace them where they can.  A station's last bearings serve emission
times up to MAX_NEAREST_S after them less the sound's travel time, so a target passing close to a station whose
bearings end gives a fresh point at an emission time later than the station's last bearing; that point must replace
the one shown before, not be stored next to it (one point per time: a UNIQUE key of the store)."""

import numpy as np

from fusion.bearing_fusion import MAX_NEAREST_S, TrackPoint
from station import track_fusion
from station.store import EventStore
from tests.test_bearing_fusion import T0, batches, bridge, detection, observe, publish  # noqa: F401


def road(te: float) -> np.ndarray:
    """45 m/s north along a road 40 m east of station 1, at 120 m, closest to it 20 s after T0."""
    return np.array([40.0, -900.0 + 45.0 * (te - T0), 120.0])


STATION1 = [T0 + 0.5 * k for k in range(1, 38)]       # its bearings end 1.5 s before the target is closest to it
STATION2 = [T0 + 0.5 * k for k in range(1, 81)]


def test_a_point_after_a_stations_last_bearing_replaces_the_one_shown_before(bridge):  # noqa: F811
    store, service = bridge
    streams = {1: batches(1, observe(1, STATION1, target=road)), 2: batches(2, observe(2, STATION2, target=road))}
    for s in streams:
        assert publish(store, service, s, detection(s, int(T0 * 1e6)), "up") == "stored"
    order = [(s, v[k]) for k in range(max(len(v) for v in streams.values())) for s, v in streams.items() if k < len(v)]
    for s, b in order:
        assert publish(store, service, s, b) == "stored"
    (summary,) = store.list_tracks()
    track_id = summary["track_id"]
    last_us = int(round(STATION1[-1] * 1e6))
    times = [p["time_us"] for p in store.get_track(track_id)["track_points"]]
    late = [t for t in times if last_us < t <= last_us + MAX_NEAREST_S * 1e6]
    assert late, times                                   # the case at hand: a point after station 1's last bearing
    assert len(times) == len(set(times)) and times == sorted(times)
    service.tracks.recompute(track_id)                   # a redelivered batch changes nothing
    assert [p["time_us"] for p in store.get_track(track_id)["track_points"]] == times


def test_fresh_points_win_over_old_ones_of_the_same_time_whatever_the_spans(tmp_path, monkeypatch):
    """No two points of a track share a time even where the member spans do not cover a fresh point's time (here: no
    member bearings at all) and the fusion returned one time twice."""
    store = EventStore(tmp_path / "h.sqlite3")
    t0 = int(T0 * 1e6)

    def point(dt_s: int, alt: float) -> TrackPoint:
        return TrackPoint(t0 + dt_s * 1_000_000, 55.0, 37.0, alt, 50.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0, 30.0, (1, 2))

    store.replace_track("TRK-h", [], None, [point(10, 100.0).as_dict(), point(11, 100.0).as_dict()])
    monkeypatch.setattr(track_fusion, "fuse", lambda stations: [point(11, 200.0), point(11, 200.0), point(12, 200.0)])
    track_fusion.BearingTrackFusion(store).recompute("TRK-h")
    points = store.get_track("TRK-h")["track_points"]
    assert [(p["time_us"] - t0, p["alt_msl_m"]) for p in points] == [(10_000_000, 100.0), (11_000_000, 200.0), (12_000_000, 200.0)]
