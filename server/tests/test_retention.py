"""Retention of the event store (docs/SERVER_RETENTION_2026-10-03.md): each table goes after its own term, a day per
transaction, audio files with their rows; the fusion's bearing queries bounded to the time index give the same
answer as before; the periodic runner, its settings and what /api/v1/health reports."""
import asyncio
import os
import sqlite3
import time
import uuid
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from station import retention
from station.retention import RetentionRunner, RetentionSettings
from station.store import DAY_US, TRACK_SPAN_MAX_US, EventStore

NOW = 1_800_000_000_000_000                      # 2027-01-15, the clock of the fixtures
TRUSTED = "GNSS_TIME_TRUSTED"


def ago(days: float) -> int:
    return NOW - int(days * DAY_US)


def fill(store: EventStore, days: float, tag: int) -> None:
    """One episode's worth of rows in every retained table, ``days`` old; ``tag`` keeps the keys apart."""
    t = ago(days)
    trk = f"TRK-{tag:016x}-1"
    with store._conn() as c:
        c.executemany("INSERT INTO bearings VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      [(1, tag, t + i * 500_000, 100, 10, 150, 0.8, 7, TRUSTED, t, 0) for i in range(4)])
        c.executemany("INSERT INTO track_points VALUES(?,?,?)", [(trk, t + i * 1_000_000, "{}") for i in range(3)])
        c.execute("INSERT INTO fused_tracks VALUES(?,?,?,?,?,?,?)", (trk, f"AIR_{tag}", t, t + 2_000_000, "[1, 2]", 3, t))
        c.execute("INSERT INTO track_members VALUES(?,?,?,?)", (1, tag, trk, 0))
        c.execute("INSERT INTO alert_tracks VALUES(?,?,?,?)", (trk, f"ALR-{tag}", t, t))
        c.execute("INSERT INTO alert_episodes VALUES(?,?,?,?,?,?,?,?)", (f"ALR-{tag}", "pilot1", t, t, "alert", "[1]", "{}", t + 1))
        c.execute("INSERT INTO system_events VALUES(?,?,?,?)", (f"AIR_{tag}", t, "AIR_WARNING", "{}"))
        c.execute("INSERT INTO detections(event_id,station_id,event_time_us,class_label,payload) VALUES(?,?,?,?,?)", (tag, 1, t, "PISTON_UAV", "{}"))
        c.execute("INSERT INTO security_events VALUES(?,?,?,?)", (tag, 1, t, "{}"))
        c.execute("INSERT INTO mqtt_detection_ingress VALUES(?,?,?,?,?,?,1)", (tag.to_bytes(8, "big"), 1, 7, tag, t, bytes(32)))
        c.execute("INSERT INTO commands(command_id,station_id,created_us,expires_us,command,payload) VALUES(?,?,?,?,?,?)",
                  (str(uuid.uuid4()), 1, t, t + 900_000_000, "CMD_REQUEST_AUDIO", "{}"))
        c.execute("INSERT INTO alert_outbox(msg_id,tenant,type,created_us,message) VALUES(?,?,?,?,?)", (f"m{tag}", "pilot1", "bearing", t, "{}"))
    folder = store.audio_root / "1" / str(tag)
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("pre", "post"):
        path = folder / f"{name}.wav"
        path.write_bytes(b"RIFF")
        store.complete_audio_segment(station_id=1, command_id=f"c{tag}", segment=0, segment_name=name, event_id=tag,
                                     path=str(path), sample_rate=8000, start_time_us=t, sha256=bytes(32), duration_ms=1000, now_us=t)


def counts(store: EventStore) -> dict[str, int]:
    tables = ("bearings", "track_points", "fused_tracks", "track_members", "alert_tracks", "alert_episodes", "system_events",
              "detections", "security_events", "mqtt_detection_ingress", "commands", "alert_outbox", "audio")
    with store._conn() as c:
        return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def test_each_table_goes_after_its_own_term_and_the_rest_stays(tmp_path):
    store = EventStore(tmp_path / "r.sqlite3")
    for days, tag in ((100, 1), (60, 2), (20, 3), (1, 4)):
        fill(store, days, tag)
    with store._conn() as c:                                              # an alert still open 100 days later stays
        c.execute("INSERT INTO alert_episodes VALUES(?,?,?,?,?,?,?,NULL)", ("ALR-open", "pilot1", ago(100), ago(100), "alert", "[1]", "{}"))
        c.execute("INSERT INTO audio_parts VALUES(?,?,?,?,?,?,?,?,?,?,?)", (1, "c-old", 0, 0, 9, 3, 8000, ago(3), bytes(32), b"x", ago(3)))
        c.execute("INSERT INTO station_tenants VALUES(1,'pilot1',?)", (ago(100),))
        c.execute("INSERT INTO alert_cursors VALUES('mqtt:alerts',5,?)", (ago(100),))
    foreign = tmp_path / "elsewhere.wav"
    foreign.write_bytes(b"RIFF")
    with store._conn() as c:                                              # a row pointing outside audio_root is never unlinked
        c.execute("INSERT INTO audio(event_id,station_id,segment,path,codec,sample_rate,created_us) VALUES(?,?,?,?,?,?,?)",
                  (99, 1, "pre", str(foreign), "pcm16-wav", 8000, ago(100)))
    before = counts(store)
    assert before["bearings"] == 16 and before["audio"] == 9 and before["alert_episodes"] == 5

    removed = store.cleanup(90, audio_retention_days=30, outbox_days=30, now_us=NOW)

    after = counts(store)
    assert removed["bearings"] == 4 and after["bearings"] == 12                # 100 days: gone; 60, 20, 1: kept
    for table in ("track_points", "fused_tracks", "system_events", "detections", "security_events", "mqtt_detection_ingress", "commands"):
        assert removed[table] >= 1 and after[table] == before[table] - removed[table], table
    assert after["detections"] == 3 and after["commands"] == 3 and after["mqtt_detection_ingress"] == 3
    assert removed["track_members"] == 1 and removed["alert_tracks"] == 1 and after["track_members"] == 3
    assert removed["alert_episodes"] == 1 and after["alert_episodes"] == 4            # the open one stays
    assert removed["alert_outbox"] == 2 and after["alert_outbox"] == 2                # 100 and 60 days: beyond 30
    assert removed["audio"] == 5 and removed["audio_files"] == 4 and after["audio"] == 4
    assert removed["audio_parts"] == 1
    assert not (store.audio_root / "1" / "1").exists() and not (store.audio_root / "1" / "2").exists()
    assert (store.audio_root / "1" / "3" / "pre.wav").is_file() and (store.audio_root / "1" / "4" / "post.wav").is_file()
    assert foreign.is_file()
    with store._conn() as c:
        assert c.execute("SELECT COUNT(*) FROM station_tenants").fetchone()[0] == 1
        assert c.execute("SELECT seq FROM alert_cursors WHERE consumer='mqtt:alerts'").fetchone()[0] == 5
        assert c.execute("SELECT COUNT(*) FROM alert_episodes WHERE ended_us IS NULL").fetchone()[0] == 1
    # nothing left to remove: the second run is a no-op, the audio root stays
    assert all(v == 0 for v in store.cleanup(90, audio_retention_days=30, outbox_days=30, now_us=NOW).values())
    assert store.audio_root.is_dir()


def test_a_day_per_transaction_gives_the_same_result_as_one_sweep(tmp_path):
    a, b = EventStore(tmp_path / "a" / "events.sqlite3"), EventStore(tmp_path / "b" / "events.sqlite3")   # separate audio roots
    for store in (a, b):
        for days, tag in ((400, 1), (200, 2), (95, 3), (91, 4), (89, 5), (10, 6)):
            fill(store, days, tag)
    daily = a.cleanup(90, audio_retention_days=30, outbox_days=30, now_us=NOW)
    sweep = b.cleanup(90, audio_retention_days=30, outbox_days=30, now_us=NOW, step_us=10_000 * DAY_US)
    assert daily == sweep and daily["detections"] == 4 and counts(a) == counts(b)
    # the real cutoff, not the day grid, decides: a row 89 days old survives, one 91 days old does not
    with a._conn() as c:
        assert sorted(r[0] for r in c.execute("SELECT event_id FROM detections")) == [5, 6]


def test_cleanup_defaults_use_the_wall_clock_and_the_documented_terms(tmp_path):
    store = EventStore(tmp_path / "d.sqlite3")
    now = int(time.time() * 1e6)
    with store._conn() as c:
        c.executemany("INSERT INTO alert_outbox(msg_id,tenant,type,created_us,message) VALUES(?,?,?,?,?)",
                      [("old", "p", "bearing", now - 31 * DAY_US, "{}"), ("kept", "p", "bearing", now - 29 * DAY_US, "{}")])
        c.executemany("INSERT INTO bearings VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      [(1, 1, now - 91 * DAY_US, 1, 1, 1, 0.5, 7, TRUSTED, now, 0), (1, 1, now - 89 * DAY_US, 1, 1, 1, 0.5, 7, TRUSTED, now, 0)])
    removed = store.cleanup()
    assert removed["alert_outbox"] == 1 and removed["bearings"] == 1
    with store._conn() as c:
        assert c.execute("SELECT msg_id FROM alert_outbox").fetchone()[0] == "kept"


def reference_tracks(rows, since, until):
    """bearing_tracks computed in Python over every row, the way the unbounded query did it."""
    by = {}
    for station, track, t, trust in rows:
        if trust in ("GNSS_TIME_TRUSTED", "HOLDOVER"):
            by.setdefault((station, track), []).append(t)
    out = [{"station_id": s, "track_event_id": k, "first_us": min(v), "last_us": max(v), "samples": len(v)}
           for (s, k), v in by.items() if max(v) >= since and min(v) <= until]
    return sorted(out, key=lambda r: r["first_us"])


def test_bounded_bearing_queries_answer_like_the_unbounded_ones(tmp_path):
    store = EventStore(tmp_path / "b.sqlite3")
    since, until = NOW, NOW + 60_000_000
    rows = []
    def track(station, track_id, start, n, trust=TRUSTED):
        for i in range(n):
            rows.append((station, track_id, start + i * 500_000, trust))
    track(1, 0x10, since - 3 * TRACK_SPAN_MAX_US, 600)                     # long gone
    track(1, 0x11, since - TRACK_SPAN_MAX_US // 2 - 10_000_000, 120)        # ended just before the window
    track(2, 0x12, since - 5_000_000, 40)                                   # starts before since, ends inside: overlaps
    track(3, 0x13, since + 10_000_000, 20)                                  # inside
    track(1, 0x14, since + 10_000_000, 20, trust="UNTRUSTED")              # inside but untrusted: never listed
    track(4, 0x15, until + 1_000_000, 20)                                   # starts after until
    track(2, 0x16, since - 20_000_000, 10, trust="HOLDOVER")               # holdover counts as trusted
    with store._conn() as c:
        c.executemany("INSERT INTO bearings VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      [(s, k, t, 1, 1, 1, 0.5, 7, trust, t, 0) for s, k, t, trust in rows])
    got = store.bearing_tracks(since, until)
    assert got == reference_tracks(rows, since, until)
    assert {r["track_event_id"] for r in got} == {0x12, 0x13}
    latest = store.latest_bearing_times(since - 30_000_000)
    assert latest == {2: since - 5_000_000 + 39 * 500_000, 3: since + 10_000_000 + 19 * 500_000, 4: until + 1_000_000 + 19 * 500_000}
    with store._conn() as c:                                              # both read the time index, not the whole table
        for sql in (f"SELECT station_id,MAX(time_us) FROM bearings INDEXED BY idx_bearing_time WHERE time_us>=? AND time_trust IN (?) GROUP BY station_id",):
            plan = " ".join(r[-1] for r in c.execute("EXPLAIN QUERY PLAN " + sql, (since, TRUSTED)))
            assert "idx_bearing_time" in plan and "SCAN" not in plan.split("idx_bearing_time")[0]


def test_settings_from_env():
    assert RetentionSettings.from_env({}) == RetentionSettings(90, 30, 30, 86400.0)
    s = RetentionSettings.from_env({"ZS_RETENTION_DAYS": "120", "ZS_AUDIO_RETENTION_DAYS": "7", "ZS_ALERT_OUTBOX_DAYS": "14",
                                    "ZS_RETENTION_INTERVAL_S": "3600"})
    assert (s.events_days, s.audio_days, s.outbox_days, s.interval_s) == (120, 7, 14, 3600.0)
    assert RetentionSettings.from_env({"ZS_RETENTION_INTERVAL_S": "0", "ZS_RETENTION_DAYS": " "}).interval_s == 0
    for bad in ({"ZS_RETENTION_DAYS": "0"}, {"ZS_AUDIO_RETENTION_DAYS": "x"}, {"ZS_RETENTION_INTERVAL_S": "-1"}):
        with pytest.raises(ValueError):
            RetentionSettings.from_env(bad)


def test_runner_reports_runs_and_errors_and_keeps_going(tmp_path):
    store = EventStore(tmp_path / "r.sqlite3")
    fill(store, 100, 1)
    runner = RetentionRunner(RetentionSettings(interval_s=0.02))
    removed = runner.run_once(store, now_us=NOW)
    assert removed["bearings"] == 4 and runner.status()["last_run"]["removed"] == removed
    assert runner.status()["settings"]["events_days"] == 90 and runner.status()["last_run"]["duration_s"] >= 0

    class Broken:
        def cleanup(self, *a, **k):
            raise sqlite3.OperationalError("database is locked")
    with pytest.raises(sqlite3.OperationalError):
        runner.run_once(Broken())
    assert runner.status()["last_run"]["error"].startswith("OperationalError")

    stores = [Broken(), store, store]                                     # the loop survives a failed run
    calls = []
    def store_of():
        calls.append(1)
        return stores[min(len(calls) - 1, 2)]
    async def drive():
        stop = asyncio.Event()
        task = asyncio.create_task(runner.run_forever(store_of, stop))
        deadline = time.monotonic() + 5
        while len(calls) < 3 and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        stop.set()
        await asyncio.wait_for(task, 2)
    asyncio.run(drive())
    assert len(calls) >= 3 and "removed" in runner.status()["last_run"]


def test_health_reports_storage_and_the_retention_run(tmp_path, monkeypatch):
    import app as app_module
    import station.router as router
    store = EventStore(tmp_path / "events.sqlite3")
    fill(store, 100, 1)
    monkeypatch.setattr(router, "store", store)
    runner = app_module.retention_runner
    monkeypatch.setattr(runner, "settings", replace(runner.settings, interval_s=3600))
    with TestClient(app_module.app) as client:                            # the lifespan starts the periodic cleanup
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            body = client.get("/api/v1/health").json()
            if body["retention"]["last_run"]:
                break
            time.sleep(0.02)
    assert body["status"] == "ok" and body["retention"]["settings"]["interval_s"] == 3600
    assert body["retention"]["last_run"]["removed"]["bearings"] == 0          # the fixture lives in 2027: nothing is old
    storage = body["storage"]
    assert storage["database_bytes"] > 0 and storage["audio_files"] == 2 and storage["audio_bytes"] == 8
    assert storage["disk_free_bytes"] > 0
    assert store.storage_usage() == storage                                  # cached for a minute
