"""Replay of the target's movement without a map (decision 3): one call gives the stations, the fused track and the
bearings in metres around the stations; the page draws them.  The scene is the synthetic one of the fusion tests."""

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from station.replay import MAX_WINDOW_US, TRACK_MARGIN_US, ReplayError, build_replay, replay_sources
from tests.test_bearing_fusion import ARRIVALS, FRAME, STATIONS, bridge, feed, truth  # noqa: F401  (bridge is a fixture)


@pytest.fixture
def fused(bridge):  # noqa: F811
    store, service = bridge
    feed(store, service, (1, 2))
    (summary,) = store.list_tracks()
    return store, summary


def test_replay_of_a_track_in_local_metres(fused):
    store, summary = fused
    r = build_replay(store, track_id=summary["track_id"])
    assert r["window"]["since_us"] == summary["first_time_us"] - TRACK_MARGIN_US
    assert r["window"]["until_us"] == summary["last_time_us"] + TRACK_MARGIN_US
    assert r["window"]["since_us"] <= r["window"]["first_us"] < r["window"]["last_us"] <= r["window"]["until_us"]
    # the origin is the stations' mean: the two stations sit at -+450 m east of it
    stations = {s["station_id"]: s for s in r["stations"]}
    assert sorted(stations) == [1, 2]
    assert stations[1]["e"] == pytest.approx(-450.0, abs=1.0) and stations[2]["e"] == pytest.approx(450.0, abs=1.0)
    assert abs(stations[1]["n"]) < 1.0 and abs(stations[1]["u"]) < 1.0
    (track,) = r["tracks"]
    assert track["track_id"] == summary["track_id"] and track["stations"] == [1, 2]
    assert len(track["points"]) == summary["points"]
    times = [p["t_us"] for p in track["points"]]
    assert times == sorted(times)
    # points in the replay frame follow the truth (shifted by the origin: station 1 is at the scene's 0, 0)
    offset = np.array(STATIONS[1][:2]) - np.array([stations[1]["e"], stations[1]["n"]])
    errs = [np.linalg.norm(np.array([p["e"], p["n"]]) + offset - truth(p["t_us"] * 1e-6)[:2]) for p in track["points"]]
    assert np.median(errs) < 80.0
    p = track["points"][len(track["points"]) // 2]
    assert p["speed_mps"] == pytest.approx(math.hypot(p["ve"], p["vn"]), abs=0.2)
    assert p["h_err_m"] > 0 and p["crossing_deg"] >= 10.0 and p["stations"] == [1, 2]
    # every bearing of both stations in the window, heard at arrival time
    assert len(r["bearings"]) == 2 * len(ARRIVALS)
    assert {b["station_id"] for b in r["bearings"]} == {1, 2}
    assert all(0.0 <= b["azimuth_deg"] < 360.0 and b["sigma_deg"] > 0 for b in r["bearings"])


def test_replay_of_an_event_and_of_explicit_times(fused):
    store, summary = fused
    by_event = build_replay(store, system_event_id=summary["system_event_id"])
    assert [t["track_id"] for t in by_event["tracks"]] == [summary["track_id"]]
    assert by_event["window"]["since_us"] <= summary["first_time_us"] - TRACK_MARGIN_US
    explicit = build_replay(store, since_us=summary["first_time_us"], until_us=summary["first_time_us"] + 10_000_000)
    assert len(explicit["tracks"]) == 1                          # a track overlapping the window
    assert all(summary["first_time_us"] <= b["t_us"] <= summary["first_time_us"] + 10_000_000 for b in explicit["bearings"])
    far = build_replay(store, since_us=1, until_us=1_000_000)   # nothing there
    assert far["stations"] == [] and far["tracks"] == [] and far["bearings"] == [] and far["origin"] is None


def test_replay_errors(fused):
    store, summary = fused
    for kwargs, msg in [({"track_id": "TRK-none"}, "track not found"),
                        ({"system_event_id": "AIR_ALERT-none"}, "event not found"),
                        ({}, "give track_id"),
                        ({"since_us": 10, "until_us": 10}, "empty time window"),
                        ({"since_us": 0, "until_us": MAX_WINDOW_US + 1}, "longer than 30 minutes")]:
        with pytest.raises(ReplayError, match=msg):
            build_replay(store, **kwargs)


def test_replay_sources(fused):
    store, summary = fused
    src = replay_sources(store)
    assert [t["track_id"] for t in src["tracks"]] == [summary["track_id"]]
    assert summary["system_event_id"] in [e["system_event_id"] for e in src["events"]]
    assert all(e["event_type"] in ("AIR_ALERT", "AIR_WARNING") for e in src["events"])


def test_replay_api_and_page(fused, monkeypatch):
    store, summary = fused
    import station.router as router
    from app import app
    monkeypatch.setattr(router, "store", store)
    client = TestClient(app)
    r = client.get("/api/v1/replay", params={"track_id": summary["track_id"]})
    assert r.status_code == 200 and r.json()["tracks"][0]["track_id"] == summary["track_id"]
    assert client.get("/api/v1/replay", params={"system_event_id": summary["system_event_id"]}).status_code == 200
    assert client.get("/api/v1/replay", params={"track_id": "TRK-none"}).status_code == 404
    assert client.get("/api/v1/replay").status_code == 400
    assert client.get("/api/v1/replay", params={"since_us": 0, "until_us": MAX_WINDOW_US + 1}).status_code == 400
    src = client.get("/api/v1/replay/sources", params={"limit": 1000}).json()
    assert [t["track_id"] for t in src["tracks"]] == [summary["track_id"]]
    page = client.get("/replay")
    assert page.status_code == 200
    assert 'id="replay-canvas"' in page.text and "/static/js/replay.js" in page.text and 'href="/replay"' in page.text
    assert client.get("/static/js/replay.js").status_code == 200
