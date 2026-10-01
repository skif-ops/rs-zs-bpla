"""event_id = boot_id<<32 | seq_no is unique within one station only (ICD).

Stations booted the same number of times send equal event_id for their first detections; the server must keep each of
them, put them into one track and one system event, and tell their system events, tracks and security events apart.
A database made with the old schema (event_id alone as the primary key) is migrated in place.
"""
from __future__ import annotations

import hashlib
import sqlite3

import cbor2
import pytest

from station.schemas import SecurityEventMessage, StationPosition
from station.service import StationFusionService
from station.store import EventStore
from tests.test_bearing_fusion import ARRIVALS, observe, position, publish

SHARED = (5 << 32) | 1                     # boot 5, sequence 1: every station's first detection after the 5th boot


def detection(station: int, time_us: int, event_id: int = SHARED) -> bytes:
    lat, lon, alt = position(station)
    return cbor2.dumps({0: 4, 1: 2, 2: station, 3: event_id & 0xFFFFFFFF, 4: event_id >> 32, 5: event_id, 6: time_us,
                        7: 0, 8: {0: int(round(lat * 1e7)), 1: int(round(lon * 1e7)), 2: int(round(alt * 10)), 4: 1, 5: 200},
                        10: {}, 12: {}, 13: {}, 14: {}}, canonical=True)


def batches(station: int, rows: list[dict], event_id: int = SHARED) -> list[bytes]:
    out = []
    for k in range(0, len(rows), 2):
        chunk = rows[k:k + 2]
        base = chunk[0]["time_us"]
        out.append(cbor2.dumps({0: 1, 1: 7, 2: station, 3: 5, 4: event_id, 5: base, 6: 1, 7: 1,
                                8: [[(r["time_us"] - base) // 1000, int(round(r["azimuth_deg"] * 100)) % 36000,
                                     int(round(r["elevation_deg"] * 100)), int(round(r["sigma_deg"] * 100)), 200, 8]
                                    for r in chunk]}, canonical=True))
    return out


@pytest.fixture
def bridge(tmp_path):
    store = EventStore(tmp_path / "k.sqlite3")
    return store, StationFusionService(store)


def test_equal_event_ids_of_three_stations_make_one_track_and_one_event(bridge):
    store, service = bridge
    stations = (3, 2, 1)
    for s in stations:
        assert publish(store, service, s, detection(s, int(ARRIVALS[0] * 1e6)), "up") == "stored"
    streams = {s: batches(s, observe(s, ARRIVALS)) for s in stations}
    for k in range(max(len(v) for v in streams.values())):
        for s in stations:
            if k < len(streams[s]):
                assert publish(store, service, s, streams[s][k]) == "stored"

    with store._conn() as c:
        rows = c.execute("SELECT station_id, event_id, system_event_id FROM detections ORDER BY station_id").fetchall()
    assert [(r["station_id"], r["event_id"]) for r in rows] == [(1, SHARED), (2, SHARED), (3, SHARED)]
    events = {r["system_event_id"] for r in rows}
    assert events == {f"AIR_ALERT-{SHARED:016x}-1"}, events          # all three linked, the id names station 1
    event = store.get_event(f"AIR_ALERT-{SHARED:016x}-1")
    assert sorted(zip(event["source_station_ids"], event["source_event_ids"])) == [(1, SHARED), (2, SHARED), (3, SHARED)]

    (summary,) = store.list_tracks()
    assert summary["track_id"] == f"TRK-{SHARED:016x}-1" and summary["stations"] == [1, 2, 3], summary
    track = store.get_track(summary["track_id"])
    assert sorted((m["station_id"], m["track_event_id"]) for m in track["members"]) == [(1, SHARED), (2, SHARED), (3, SHARED)]
    assert track["system_event_id"] == f"AIR_ALERT-{SHARED:016x}-1"


def test_redelivery_and_conflict_are_judged_per_station(bridge):
    store, service = bridge
    t = int(ARRIVALS[0] * 1e6)
    assert publish(store, service, 1, detection(1, t), "up") == "stored"
    assert publish(store, service, 2, detection(2, t), "up") == "stored"          # same event_id, other station
    assert publish(store, service, 2, detection(2, t), "up") == "duplicate"       # QoS 1 redelivery
    with pytest.raises(ValueError, match="conflicting reuse"):                     # station 2 reusing its own event_id
        publish(store, service, 2, detection(2, t + 1_000_000), "up")


def test_security_events_of_two_stations_with_equal_event_id_are_both_kept(tmp_path):
    store = EventStore(tmp_path / "s.sqlite3")
    for s in (1, 2):
        store.save_security(SecurityEventMessage(station_id=s, seq_no=1, boot_id=5, event_id=SHARED, event_time_us=1_800_000_000_000_000 + s,
                                                 station=StationPosition(lat_e7=550000000, lon_e7=370000000, alt_dm=1500), reason="tilt"))
    with store._conn() as c:
        assert [tuple(r) for r in c.execute("SELECT station_id, event_id FROM security_events ORDER BY station_id")] == [(1, SHARED), (2, SHARED)]


OLD_SCHEMA = """
CREATE TABLE detections(event_id INTEGER PRIMARY KEY, station_id INTEGER NOT NULL, event_time_us INTEGER NOT NULL, class_label TEXT NOT NULL, payload TEXT NOT NULL, system_event_id TEXT);
CREATE INDEX idx_det_time ON detections(event_time_us);
CREATE INDEX idx_det_station ON detections(station_id, event_time_us);
CREATE TABLE security_events(event_id INTEGER PRIMARY KEY, station_id INTEGER NOT NULL, created_us INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE TABLE mqtt_detection_ingress(event_key BLOB PRIMARY KEY, station_id INTEGER NOT NULL, boot_id INTEGER NOT NULL, seq_no INTEGER NOT NULL, event_time_us INTEGER NOT NULL, wire_sha256 BLOB NOT NULL, processed INTEGER NOT NULL DEFAULT 0 CHECK(processed IN (0,1)));
"""


def test_old_database_is_migrated_and_keeps_its_rows(tmp_path):
    path = tmp_path / "old.sqlite3"
    t = int(ARRIVALS[0] * 1e6)
    old = EventStore(tmp_path / "scratch.sqlite3")                     # only to produce a valid detection payload
    service = StationFusionService(old)
    publish(old, service, 1, detection(1, t), "up")
    with old._conn() as c:
        det = dict(c.execute("SELECT * FROM detections").fetchone())
    wire = detection(1, t)
    with sqlite3.connect(path) as c:
        c.executescript(OLD_SCHEMA)
        c.execute("INSERT INTO detections VALUES(?,?,?,?,?,?)", (det["event_id"], 1, det["event_time_us"], det["class_label"],
                                                                 det["payload"], "AIR_WARNING-old"))
        c.execute("INSERT INTO security_events VALUES(?,?,?,?)", (SHARED, 1, t, "{}"))
        c.execute("INSERT INTO mqtt_detection_ingress VALUES(?,?,?,?,?,?,1)", (SHARED.to_bytes(8, "big"), 1, 5, 1, t,
                                                                               hashlib.sha256(wire).digest()))
    store = EventStore(path)
    with store._conn() as c:
        for table, key in (("detections", ["event_id", "station_id"]), ("security_events", ["event_id", "station_id"]),
                           ("mqtt_detection_ingress", ["event_key", "station_id"])):
            assert sorted(r["name"] for r in c.execute(f"PRAGMA table_info({table})") if r["pk"]) == key, table
        assert {r["name"] for r in c.execute("PRAGMA index_list(detections)")} >= {"idx_det_time", "idx_det_station"}
        assert c.execute("SELECT system_event_id FROM detections WHERE station_id=1").fetchone()[0] == "AIR_WARNING-old"
        assert c.execute("SELECT COUNT(*) FROM security_events").fetchone()[0] == 1
        assert not c.execute("SELECT name FROM sqlite_master WHERE name LIKE '%before_station_key'").fetchall()
    service = StationFusionService(store)
    assert publish(store, service, 1, wire, "up") == "duplicate"               # the old ingress row still answers
    assert publish(store, service, 2, detection(2, t), "up") == "stored"       # and the shared event_id is free for 2
    EventStore(path)                                                           # reopening an up-to-date database
    with store._conn() as c:
        assert c.execute("SELECT COUNT(*) FROM detections").fetchone()[0] == 2


def test_an_interrupted_migration_leaves_the_old_database_as_it_was(tmp_path):
    """The three tables move in one transaction: a failure on the second one (here a leftover table blocks its rename)
    rolls the first one back too, and the next start migrates everything."""
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as c:
        c.executescript(OLD_SCHEMA)
        c.execute("INSERT INTO detections VALUES(?,?,?,?,?,?)", (SHARED, 1, 1, "ELECTRIC_UAV", "{}", None))
        c.execute("CREATE TABLE security_events_before_station_key(x)")
    with pytest.raises(sqlite3.OperationalError):
        EventStore(path)
    with sqlite3.connect(path) as c:
        assert [r[1] for r in c.execute("PRAGMA table_info(detections)") if r[5]] == ["event_id"]   # still the old key
        assert c.execute("SELECT COUNT(*) FROM detections").fetchone()[0] == 1
        assert not c.execute("SELECT name FROM sqlite_master WHERE name='detections_before_station_key'").fetchall()
        c.execute("DROP TABLE security_events_before_station_key")
    store = EventStore(path)
    with store._conn() as c:
        assert sorted(r["name"] for r in c.execute("PRAGMA table_info(detections)") if r["pk"]) == ["event_id", "station_id"]
        assert c.execute("SELECT COUNT(*) FROM detections").fetchone()[0] == 1
