"""Bearing fusion (ICD addendum H, decision 2): bearings of two or more stations become the points of one target
track.  Synthetic stations watch a target flying past; the batches go through the real bridge route
(process_message) as the stations would publish them."""

import math

import cbor2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from fusion.bearing_fusion import StationBearings, fuse
from fusion.geodesy import EnuFrame
from station.mqtt_bridge import process_message
from station.service import StationFusionService
from station.store import EventStore

FRAME = EnuFrame(55.0, 37.0, 150.0)
C = 343.0
T0 = 1_800_000_000.0                       # wall seconds of the scene start
STATIONS = {1: (0.0, 0.0, 0.0), 2: (900.0, 0.0, 0.0), 3: (450.0, 700.0, 0.0)}


def truth(te: float) -> np.ndarray:
    """The target: 45 m/s east-south-east at 250 m, passing north of the stations."""
    t = te - T0
    return np.array([-800.0 + 45.0 * t, 1500.0 - 5.0 * t, 250.0])


def observe(station: int, arrivals_s, sigma: float = 1.5, seed: int = 1, target=truth) -> list[dict]:
    """Bearings heard at each arrival time (the sound left the target range / c earlier), with noise."""
    rng = np.random.default_rng(seed + station)
    p = np.array(STATIONS[station])
    rows = []
    for ta in arrivals_s:
        te = ta
        for _ in range(10):
            te = ta - float(np.linalg.norm(target(te) - p)) / C
        v = target(te) - p
        az = math.degrees(math.atan2(v[0], v[1])) % 360.0
        el = math.degrees(math.atan2(v[2], math.hypot(v[0], v[1])))
        rows.append({"time_us": int(round(ta * 1e6)), "azimuth_deg": (az + rng.normal(0, sigma)) % 360.0,
                     "elevation_deg": el + rng.normal(0, 1.5 * sigma), "sigma_deg": sigma})
    return rows


def position(station: int) -> tuple[float, float, float]:
    return FRAME.to_geodetic(*STATIONS[station])


def horizontal_errors(points) -> np.ndarray:
    return np.array([np.linalg.norm(FRAME.to_enu(p.lat, p.lon, p.alt_msl_m)[:2] - truth(p.time_us * 1e-6)[:2]) for p in points])


ARRIVALS = [T0 + 10 + 0.5 * k for k in range(120)]


def test_two_stations_track_the_target_and_the_sound_delay_is_corrected():
    sbs = [StationBearings.from_rows(s, position(s), observe(s, ARRIVALS)) for s in (1, 2)]
    points = fuse(sbs)
    assert len(points) >= 50
    errors = horizontal_errors(points)
    assert np.median(errors) < 80.0, np.median(errors)
    uncorrected = horizontal_errors(fuse(sbs, c=1e9))                  # ignoring the 3..5 s the sound travels
    assert np.median(uncorrected) > 2.0 * np.median(errors)
    middle = points[len(points) // 3: 2 * len(points) // 3]
    assert abs(np.median([p.speed_mps for p in middle]) - math.hypot(45, 5)) < 8.0
    assert abs(np.median([p.course_deg for p in middle]) - 96.3) < 8.0     # atan2(45, -5)
    assert all(p.stations == (1, 2) and p.crossing_deg >= 10.0 for p in points)
    assert np.median([abs(FRAME.to_enu(p.lat, p.lon, p.alt_msl_m)[2] - 250.0) for p in points]) < 60.0


def test_a_third_station_improves_the_track():
    two = horizontal_errors(fuse([StationBearings.from_rows(s, position(s), observe(s, ARRIVALS)) for s in (1, 2)]))
    three = horizontal_errors(fuse([StationBearings.from_rows(s, position(s), observe(s, ARRIVALS)) for s in (1, 2, 3)]))
    assert np.median(three) < np.median(two)


def test_single_station_and_the_baseline_blind_zone_give_no_points():
    assert fuse([StationBearings.from_rows(1, position(1), observe(1, ARRIVALS))]) == []

    def along_baseline(te):                          # far out on the line through stations 1 and 2: parallel rays
        return np.array([-3000.0 - 20.0 * (te - T0), 0.0, 200.0])
    sbs = [StationBearings.from_rows(s, position(s), observe(s, ARRIVALS, target=along_baseline)) for s in (1, 2)]
    assert fuse(sbs) == []


# ---- through the bridge: detections, batches, association, storage ------------------------------------------------

def event_id(station: int) -> int:
    return (7 << 32) | station                      # boot 7, the rising edge of each station's track


def detection(station: int, time_us: int) -> bytes:
    lat, lon, alt = position(station)
    eid = event_id(station)
    return cbor2.dumps({0: 4, 1: 2, 2: station, 3: eid & 0xFFFFFFFF, 4: eid >> 32, 5: eid, 6: time_us, 7: 0,
                        8: {0: int(round(lat * 1e7)), 1: int(round(lon * 1e7)), 2: int(round(alt * 10)), 4: 1, 5: 200},
                        10: {}, 12: {}, 13: {}, 14: {}}, canonical=True)


def batches(station: int, rows: list[dict], trust: int = 1) -> list[bytes]:
    """The station's batches of 2 bearings (one a second), as zs_bearing_batch_encode writes them."""
    out = []
    for k in range(0, len(rows), 2):
        chunk = rows[k:k + 2]
        base = chunk[0]["time_us"]
        out.append(cbor2.dumps({0: 1, 1: 7, 2: station, 3: 7, 4: event_id(station), 5: base, 6: trust, 7: 1,
                                8: [[(r["time_us"] - base) // 1000, int(round(r["azimuth_deg"] * 100)) % 36000,
                                     int(round(r["elevation_deg"] * 100)), int(round(r["sigma_deg"] * 100)), 200, 8]
                                    for r in chunk]}, canonical=True))
    return out


def publish(store, service, station: int, payload: bytes, kind: str = "bearing") -> str:
    return process_message(f"zs/v1/pilot1/{station}/{kind}", payload, "pilot1", True, event_store=store, fusion_service=service)


@pytest.fixture
def bridge(tmp_path):
    store = EventStore(tmp_path / "f.sqlite3")
    return store, StationFusionService(store)


def feed(store, service, stations, arrivals=ARRIVALS, interleave=True):
    streams = {s: batches(s, observe(s, arrivals)) for s in stations}
    for s in stations:
        assert publish(store, service, s, detection(s, int(arrivals[0] * 1e6)), "up") == "stored"
    if interleave:
        order = [(s, v[k]) for k in range(max(len(v) for v in streams.values())) for s, v in streams.items() if k < len(v)]
    else:
        order = [(s, b) for s, v in streams.items() for b in v]
    for s, b in order:
        assert publish(store, service, s, b) == "stored"
    return streams


def test_bridge_forms_one_fused_track_from_two_stations(bridge):
    store, service = bridge
    q = service.bus.subscribe()
    feed(store, service, (1, 2))
    (summary,) = store.list_tracks()
    track = store.get_track(summary["track_id"])
    assert summary["stations"] == [1, 2] and summary["points"] >= 45, summary
    assert sorted((m["station_id"], m["track_event_id"]) for m in track["members"]) == [(1, event_id(1)), (2, event_id(2))]
    errs = [np.linalg.norm(FRAME.to_enu(p["lat"], p["lon"], p["alt_msl_m"])[:2] - truth(p["time_us"] * 1e-6)[:2])
            for p in track["track_points"]]
    assert np.median(errs) < 80.0
    assert track["system_event_id"] and track["system_event_id"].startswith("AIR_")   # the stations' detections
    live = [m for m in (q.get_nowait() for _ in range(q.qsize())) if isinstance(m, dict) and m.get("type") == "track"]
    assert live and live[-1]["track_id"] == summary["track_id"] and live[-1]["last"]["time_us"] == summary["last_time_us"]


def test_arrival_order_and_redelivery_do_not_change_the_track(bridge, tmp_path):
    store, service = bridge
    streams = feed(store, service, (1, 2), interleave=False)           # all of station 1 first, then station 2
    (summary,) = store.list_tracks()
    before = store.get_track(summary["track_id"])["track_points"]
    for s, v in streams.items():
        assert publish(store, service, s, v[5]) == "duplicate"              # QoS 1 redelivery
    assert store.get_track(summary["track_id"])["track_points"] == before
    other = EventStore(tmp_path / "g.sqlite3")
    feed(other, StationFusionService(other), (1, 2), interleave=True)
    assert other.get_track(summary["track_id"])["track_points"] == before   # same id, same points in either order


def test_a_third_station_joins_the_existing_track(bridge):
    store, service = bridge
    feed(store, service, (1, 2))
    (before,) = store.list_tracks()
    late = [t for t in ARRIVALS if t > T0 + 30]                        # station 3 starts tracking later
    assert publish(store, service, 3, detection(3, int(late[0] * 1e6)), "up") == "stored"
    for b in batches(3, observe(3, late)):
        assert publish(store, service, 3, b) == "stored"
    (after,) = store.list_tracks()
    assert after["track_id"] == before["track_id"] and after["stations"] == [1, 2, 3]
    points = store.get_track(after["track_id"])["track_points"]
    assert any(p["stations"] == [1, 2, 3] for p in points)


def test_a_station_looking_elsewhere_does_not_join(bridge):
    store, service = bridge
    feed(store, service, (1, 2))

    def elsewhere(te):                               # another target south of station 3's view of the first one
        return np.array([450.0, 2500.0 - 30.0 * (te - T0), 300.0]) * np.array([1, -1, 1])
    assert publish(store, service, 3, detection(3, int(ARRIVALS[0] * 1e6)), "up") == "stored"
    for b in batches(3, observe(3, ARRIVALS, target=elsewhere)):
        publish(store, service, 3, b)
    (track,) = store.list_tracks()
    assert track["stations"] == [1, 2]
    assert store.track_of_member(3, event_id(3)) is None


def test_untrusted_time_is_not_fused(bridge):
    store, service = bridge
    for s in (1, 2):
        publish(store, service, s, detection(s, int(ARRIVALS[0] * 1e6)), "up")
        for b in batches(s, observe(s, ARRIVALS), trust=4):         # UNSYNCED
            assert publish(store, service, s, b) == "stored"
    assert store.list_tracks() == []


def test_track_api(bridge, monkeypatch):
    store, service = bridge
    feed(store, service, (1, 2))
    import station.router as router
    from app import app
    monkeypatch.setattr(router, "store", store)
    client = TestClient(app)
    (summary,) = client.get("/api/v1/tracks").json()
    full = client.get(f"/api/v1/tracks/{summary['track_id']}").json()
    assert len(full["track_points"]) == summary["points"] and {"lat", "lon", "speed_mps", "course_deg"} <= set(full["track_points"][0])
    assert client.get("/api/v1/tracks", params={"since_us": summary["last_time_us"] + 1}).json() == []
    assert [t["track_id"] for t in client.get(f"/api/v1/events/{summary['system_event_id']}/tracks").json()] == [summary["track_id"]]
    assert client.get("/api/v1/tracks/TRK-none").status_code == 404
