"""History of a fused track (station/track_hypotheses.py): points are added once a second of emission time and never
rewritten.  A target passing close to a station whose bearings end is the case where a station's last bearings
serve emission times after them (fusion/bearing_fusion.py, MAX_NEAREST_S): still one point per time, in time order,
and a redelivered batch changes nothing."""

import numpy as np

from station.store import EventStore
from tests.test_bearing_fusion import T0, batches, bridge, detection, in_time, observe, publish  # noqa: F401


def road(te: float) -> np.ndarray:
    """45 m/s north along a road 40 m east of station 1, at 120 m, closest to it 20 s after T0."""
    return np.array([40.0, -900.0 + 45.0 * (te - T0), 120.0])


STATION1 = [T0 + 0.5 * k for k in range(1, 38)]       # its bearings end 1.5 s before the target is closest to it
STATION2 = [T0 + 0.5 * k for k in range(1, 81)]


def test_a_close_pass_gives_one_point_per_time_and_redelivery_changes_nothing(bridge):  # noqa: F811
    store, service = bridge
    streams = {1: batches(1, observe(1, STATION1, target=road)), 2: batches(2, observe(2, STATION2, target=road))}
    for s in streams:
        assert publish(store, service, s, detection(s, int(T0 * 1e6)), "up") == "stored"
    for s, b in in_time(streams):
        assert publish(store, service, s, b) == "stored"
    (summary,) = store.list_tracks()
    points = store.get_track(summary["track_id"])["track_points"]
    times = [p["time_us"] for p in points]
    assert len(times) >= 10 and times == sorted(set(times))
    assert summary["points"] == len(points) and summary["first_time_us"] == times[0] and summary["last_time_us"] == times[-1]
    for s, v in streams.items():
        assert publish(store, service, s, v[3]) == "duplicate"           # QoS 1 redelivery
    assert store.get_track(summary["track_id"])["track_points"] == points


def test_appended_points_keep_one_point_per_time_and_the_summary(tmp_path):
    store = EventStore(tmp_path / "h.sqlite3")
    t0 = int(T0 * 1e6)

    def point(dt_s: int, alt: float, stations: list[int]) -> dict:
        return {"time_us": t0 + dt_s * 1_000_000, "lat": 55.0, "lon": 37.0, "alt_msl_m": alt, "stations": stations}

    store.append_track_points("TRK-h", None, [point(10, 100.0, [1, 2]), point(11, 100.0, [1, 2])])
    store.append_track_points("TRK-h", "AIR_ALERT-x", [point(11, 200.0, [1, 3]), point(12, 200.0, [1, 3])])
    track = store.get_track("TRK-h")
    assert [(p["time_us"] - t0, p["alt_msl_m"]) for p in track["track_points"]] == [(10_000_000, 100.0), (11_000_000, 200.0), (12_000_000, 200.0)]
    assert track["points"] == 3 and track["stations"] == [1, 2, 3] and track["system_event_id"] == "AIR_ALERT-x"
    assert (track["first_time_us"], track["last_time_us"]) == (t0 + 10_000_000, t0 + 12_000_000)
    store.append_track_points("TRK-h", None, [point(13, 200.0, [1, 3])])
    assert store.get_track("TRK-h")["system_event_id"] == "AIR_ALERT-x"   # kept when the new points name none
