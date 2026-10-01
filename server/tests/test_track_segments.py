"""Segments of a station track (station/track_segments.py): a station that switches from one target to another
inside one tracking window feeds two fused tracks, not one that slides between the targets."""

import math
import sqlite3

import numpy as np

from station import track_segments
from station.store import EventStore
from tests.test_bearing_fusion import (ARRIVALS, FRAME, T0, batches, bridge, detection, event_id, observe,  # noqa: F401
                                       publish, truth)


def south(te: float) -> np.ndarray:
    """A second target of the same class: 30 m/s north, west of stations 1 and 3."""
    t = te - T0
    return np.array([-1300.0 + 2.0 * t, -900.0 + 30.0 * t, 200.0])


def rows_of(azimuths, sigma=1.5, step_s=0.5):
    return [{"time_us": int(T0 * 1e6 + k * step_s * 1e6), "azimuth_deg": a % 360.0, "sigma_deg": sigma} for k, a in enumerate(azimuths)]


# ---- split ----------------------------------------------------------------------------------------------------------

def test_one_target_is_one_segment_also_through_a_fast_close_pass():
    # 45 m/s past the station at 120 m: the bearing turns by up to 21 deg/s, smoothly
    t = np.arange(0.0, 60.0, 0.5)
    az = [math.degrees(math.atan2(-1300.0 + 45.0 * x, 120.0)) for x in t]
    rng = np.random.default_rng(3)
    segments = track_segments.split(rows_of(np.array(az) + rng.normal(0.0, 1.5, len(az))))
    assert [len(s.rows) for s in segments] == [len(az)]
    assert segments[0].key == track_segments.FIRST_SEGMENT


def test_single_outliers_are_dropped_not_split():
    az = [300.0 + 0.2 * k for k in range(80)]
    for k in (20, 21, 45, 63):
        az[k] = 120.0 + 37.0 * k                                       # mirror / reflection bearings
    segments = track_segments.split(rows_of(az))
    assert len(segments) == 1 and len(segments[0].rows) == 76


def test_uncertain_bearings_take_no_part():
    # bearings the station gives a sigma of 25 deg (two sources at once) every 5.5 s: within their wide tolerance
    # they joined the segment and tilted its prediction, and the target's next bearings started new segments
    rng = np.random.default_rng(4)
    rows = rows_of([34.0 + 0.6 * k + rng.normal(0.0, 1.5) for k in range(140)])
    for k in range(7, 140, 11):
        rows[k] = dict(rows[k], azimuth_deg=(116.0 if k % 2 else 359.0), sigma_deg=25.0)
    segments = track_segments.split(rows)
    assert [len(s.rows) for s in segments] == [127]


def test_a_switch_to_another_target_starts_a_segment_at_the_switch():
    az = [300.0 + 0.2 * k for k in range(60)] + [130.0 + 0.3 * k for k in range(60)]
    rows = rows_of(az)
    segments = track_segments.split(rows)
    assert [len(s.rows) for s in segments] == [60, 60]
    assert segments[1].key == rows[60]["time_us"] and segments[1].first_us == rows[60]["time_us"]
    assert track_segments.segment_at(segments, rows[70]["time_us"]) is segments[1]


def test_a_stream_alternating_between_two_targets_keeps_two_segments():
    az = [(300.0 + 0.2 * k) if k % 2 == 0 else (130.0 - 0.3 * k) for k in range(120)]
    segments = track_segments.split(rows_of(az))
    assert len(segments) == 2 and sorted(len(s.rows) for s in segments) == [60, 60]   # the waiting ones of B start its segment


def test_the_split_does_not_change_when_more_bearings_arrive():
    az = [300.0 + 0.2 * k for k in range(60)] + [130.0 + 0.3 * k for k in range(60)]
    rows = rows_of(az)
    early = [(s.key, len(s.rows)) for s in track_segments.split(rows[:80])]
    late = [(s.key, len(s.rows)) for s in track_segments.split(rows)]
    assert early[0] == (track_segments.FIRST_SEGMENT, 60) and late[0] == early[0] and late[1][0] == early[1][0]


# ---- through the bridge ---------------------------------------------------------------------------------------------

def test_a_station_switching_targets_feeds_both_tracks(bridge):  # noqa: F811
    store, service = bridge
    half = len(ARRIVALS) // 2
    streams = {
        1: observe(1, ARRIVALS[:half]) + observe(1, ARRIVALS[half:], target=south),   # the north target, then the south one
        2: observe(2, ARRIVALS),                                                      # the north target
        3: observe(3, ARRIVALS, target=south),                                        # the south target
    }
    for s in streams:
        assert publish(store, service, s, detection(s, int(ARRIVALS[0] * 1e6)), "up") == "stored"
    order = [(s, b) for k in range(len(ARRIVALS)) for s, rows in streams.items() for b in batches(s, rows)[k:k + 1]]
    for s, b in order:
        assert publish(store, service, s, b) == "stored"
    every = {t["track_id"]: store.get_track(t["track_id"]) for t in store.list_tracks()}
    tracks = {k: t for k, t in every.items() if t["members"]}
    assert len(tracks) == 2, list(every)
    # a ghost (rays of stations hearing different targets cross near the stations) may have been shown for a few
    # seconds before the better pair took its segment: it stays in the history, short and without members
    ghosts = [t for k, t in every.items() if not t["members"]]
    assert len(ghosts) <= 1 and all(t["last_time_us"] - t["first_time_us"] <= 15_000_000 for t in ghosts), ghosts

    def error(track, target):
        return float(np.median([np.linalg.norm(FRAME.to_enu(p["lat"], p["lon"], p["alt_msl_m"])[:2] - target(p["time_us"] * 1e-6)[:2])
                                for p in track["track_points"]]))

    north = next(t for t in tracks.values() if {m["station_id"] for m in t["members"]} == {1, 2})
    southern = next(t for t in tracks.values() if {m["station_id"] for m in t["members"]} == {1, 3})
    switch_us = streams[1][half]["time_us"]
    assert [m["segment_us"] for m in north["members"] if m["station_id"] == 1] == [track_segments.FIRST_SEGMENT]
    assert [m["segment_us"] for m in southern["members"] if m["station_id"] == 1] == [switch_us]
    assert southern["track_id"] == f"TRK-{event_id(1):016x}-1-{switch_us:x}"            # the later segment's time
    assert error(north, truth) < 80.0 and error(southern, south) < 80.0, (error(north, truth), error(southern, south))
    assert len(southern["track_points"]) >= 20 and len(north["track_points"]) >= 20      # 30 s of two stations each


def test_old_track_members_become_first_segments(tmp_path):
    path = tmp_path / "old.sqlite3"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE track_members(station_id INTEGER NOT NULL, track_event_id INTEGER NOT NULL, track_id TEXT NOT NULL, "
              "PRIMARY KEY(station_id, track_event_id))")
    c.execute("CREATE INDEX idx_member_track ON track_members(track_id)")
    c.execute("INSERT INTO track_members VALUES(1, ?, 'TRK-a'), (2, ?, 'TRK-a')", (event_id(1), event_id(2)))
    c.commit()
    c.close()
    store = EventStore(path)
    assert store.track_members("TRK-a") == [(1, event_id(1), 0), (2, event_id(2), 0)]
    assert store.track_of_member(1, event_id(1)) == "TRK-a" and store.segment_tracks(2, event_id(2)) == {0: "TRK-a"}
    store.add_track_member("TRK-b", 1, event_id(1), 12345)
    assert store.segment_tracks(1, event_id(1)) == {0: "TRK-a", 12345: "TRK-b"}
