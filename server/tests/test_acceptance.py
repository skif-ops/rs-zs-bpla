"""Acceptance metrics (decision 5): a synthetic trial on the scene of the fusion tests.  Stations 1 and 2 hear the
piston UAV of pass P1 and stream bearings (the real bridge path, fused into a track); station 3, 700 m off its line,
misses it; a helicopter passes far away (no opportunity); station 3 raises a false alarm after the passes and station
2 one in the quiet period.  Every number the report gives is checked against what the scene was built with."""

import json
import math
import wave

import cbor2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from fusion.bearing_fusion import intersect
from station import acceptance as acc
from station import geometry_coverage as geo
from tests.test_bearing_fusion import C, FRAME, STATIONS, T0, bridge, feed, position, publish, truth  # noqa: F401

US = 1_000_000


def _iso(t_s: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t_s, timezone.utc).isoformat().replace("+00:00", "Z")


def _track(fn, t_from: float, t_to: float, step: float = 1.0) -> list[dict]:
    rows = []
    for k in range(int(round((t_to - t_from) / step)) + 1):
        t = t_from + k * step
        lat, lon, alt = FRAME.to_geodetic(*fn(t))
        rows.append({"time": int(round(t * US)), "lat": lat, "lon": lon, "alt_msl_m": alt})
    return rows


def _heli(te: float) -> np.ndarray:
    return np.array([8000.0, -2000.0 + 30.0 * (te - T0), 300.0])


def _detection(station: int, time_us: int, class_id: int, eid: int) -> bytes:
    lat, lon, alt = position(station)
    return cbor2.dumps({0: 4, 1: 2, 2: station, 3: eid & 0xFFFFFFFF, 4: eid >> 32, 5: eid, 6: time_us, 7: 0,
                        8: {0: int(round(lat * 1e7)), 1: int(round(lon * 1e7)), 2: int(round(alt * 10)), 4: class_id, 5: 200},
                        10: {}, 12: {}, 13: {}, 14: {}}, canonical=True)


def _wav(path, amplitude: float, seconds: float = 30.0, rate: int = 8000):
    n = int(seconds * rate)
    x = (amplitude * 32767.0 * np.sin(2 * np.pi * 1000.0 * np.arange(n) / rate)).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(x.tobytes())


@pytest.fixture
def trial(bridge, tmp_path):  # noqa: F811
    store, service = bridge
    feed(store, service, (1, 2))                                  # rising edges at T0 + 10 s, bearings 10..69.5 s
    publish(store, service, 1, _detection(1, int((T0 + 20) * US), 1, (7 << 32) | 101), "up")       # keep-alive: PISTON_UAV
    publish(store, service, 1, _detection(1, int((T0 + 30) * US), 1, (7 << 32) | 102), "up")
    publish(store, service, 2, _detection(2, int((T0 + 25) * US), 12, (7 << 32) | 103), "up")      # station 2 then says HELICOPTER
    publish(store, service, 2, _detection(2, int((T0 + 35) * US), 12, (7 << 32) | 107), "up")
    publish(store, service, 3, _detection(3, int((T0 + 600) * US), 15, (7 << 32) | 104), "up")     # false: BIRDS
    publish(store, service, 3, _detection(3, int((T0 + 620) * US), 15, (7 << 32) | 105), "up")     # the same episode
    publish(store, service, 2, _detection(2, int((T0 + 900) * US), 10, (7 << 32) | 106), "up")     # false, quiet period
    # uploaded audio of station 1's keep-alive at +20 s: 30 s "post" segment, a 1 kHz tone at -40 dBFS
    wav = tmp_path / "s1_post.wav"
    _wav(wav, 0.01)
    store.complete_audio_segment(station_id=1, command_id="c1", segment=1, segment_name="post", event_id=(7 << 32) | 101,
                                 path=str(wav), sample_rate=8000, start_time_us=int((T0 + 19) * US), sha256=b"\0" * 32,
                                 duration_ms=30000, now_us=int(T0 * US))
    doc = {
        "format": "dioneya.trial/1", "name": "синтетика",
        "window": {"since": _iso(T0 - 60), "until": _iso(T0 + 1200)},
        "stations": [{"station_id": s, "lat": position(s)[0], "lon": position(s)[1], "alt_msl_m": position(s)[2]} for s in (1, 2)]
                    + [{"station_id": 3}],                         # position from the store (its detection)
        "passes": [{"pass_id": "P1", "class": "PISTON_UAV", "track": _track(truth, T0 - 5, T0 + 75)},
                   {"pass_id": "H1", "class": "HELICOPTER", "track_csv": "h1.csv"}],
        "quiet": [{"since": int((T0 + 800) * US), "until": int((T0 + 1000) * US)}],
        "levels": [{"station_id": 1, "time": int((T0 + 10) * US), "spl_db": 52.5}, {"station_id": 1, "time": int((T0 + 30) * US), "spl_db": 61.0}],
    }
    with open(tmp_path / "h1.csv", "w", encoding="utf-8") as f:
        f.write("time,lat,lon,alt_msl_m\n")
        for r in _track(_heli, T0, T0 + 120, 5.0):
            f.write(f"{_iso(r['time'] / US)},{r['lat']},{r['lon']},{r['alt_msl_m']}\n")
    path = tmp_path / "trial.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return store, acc.load_trial(path, store), path


def test_trial_file(trial):
    store, t, _ = trial
    assert t.name == "синтетика" and sorted(t.stations) == [1, 2, 3]
    assert np.allclose(t.stations[2] - t.stations[1], [900.0, 0.0, 0.0], atol=0.5)
    assert np.allclose(t.stations[3] - t.stations[1], [450.0, 700.0, 0.0], atol=0.5)  # from the store
    p1, h1 = t.passes
    assert p1.target_class == "PISTON_UAV" and h1.target_class == "HELICOPTER" and len(h1.t_us) == 25
    assert np.allclose(p1.position((T0 + 12.5) * US) - t.stations[1], truth(T0 + 12.5), atol=0.5)
    assert p1.position((T0 - 6) * US) is None and p1.position((T0 - 6) * US, 2 * US) is not None
    assert acc.parse_time_us("2027-01-15T10:00:00+03:00") == acc.parse_time_us("2027-01-15T07:00:00Z")


@pytest.mark.parametrize("change, match", [
    ({"format": "x"}, "not a dioneya.trial/1"),
    ({"window": {"since": "2027-01-01T00:00:00", "until": "2027-01-02T00:00:00Z"}}, "no time zone"),
    ({"passes": [{"pass_id": "A", "class": "DRONE", "track": []}]}, "is not one of"),
    ({"passes": [{"pass_id": "A", "class": "PISTON_UAV", "track": [{"time": 1, "lat": 55, "lon": 37, "alt_msl_m": 1}]}]}, "two points"),
    ({"stations": [{"station_id": 99}]}, "no position"),
    ({"stations": []}, "no stations"),
])
def test_bad_trial_files(trial, tmp_path, change, match):
    store, _, path = trial
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc.update(change)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(acc.TrialError, match=match):
        acc.load_trial(bad, store)


def test_metrics_of_the_synthetic_trial(trial):
    store, t, _ = trial
    r = acc.evaluate(store, t, acc.Criteria(audio_cal_dbfs_at_94=-20.0))
    piston, heli, everything = r["summary"]["PISTON_UAV"], r["summary"]["HELICOPTER"], r["summary"]["ALL"]
    # Pd: stations 1 and 2 heard P1, station 3 (707 m slant at closest) did not; the helicopter came no closer than 6 km
    assert (piston["opportunities"], piston["detected"], piston["pd"]) == (3, 2, pytest.approx(2 / 3, abs=1e-4))
    assert piston["pd_ci95"] == acc.wilson(2, 3) == (pytest.approx(0.2077, abs=1e-3), pytest.approx(0.9385, abs=1e-3))
    assert (heli["passes"], heli["opportunities"], heli["pd"]) == (1, 0, None)
    pairs = {(p["pass_id"], p["station_id"]): p for p in r["station_passes"]}
    s1, s3 = pairs[("P1", 1)], pairs[("P1", 3)]
    assert s3["opportunity"] and not s3["detected"] and s3["cpa_m"] == pytest.approx(707.0, abs=5.0)
    assert not pairs[("H1", 1)]["opportunity"]
    # the first report of station 1 is its rising edge at +10 s: the target was where the sound left it
    te = s1["first_report_us"] / US
    for _ in range(10):
        te = T0 + 10 - np.linalg.norm(truth(te)) / C
    assert s1["first_range_m"] == pytest.approx(float(np.linalg.norm(truth(te))), abs=1.0)
    # classification: both rising edges say PISTON_UAV; station 1 keeps it, station 2 then says HELICOPTER twice
    assert (s1["first_label"], s1["majority_label"], s1["detections"]) == ("PISTON_UAV", "PISTON_UAV", 3)
    s2 = pairs[("P1", 2)]
    assert (s2["first_label"], s2["majority_label"], s2["detections"]) == ("PISTON_UAV", "HELICOPTER", 3)
    assert r["confusion"] == {"PISTON_UAV": {"PISTON_UAV": 2}}
    assert piston["p_correct_class_first"] == 1.0 and piston["p_correct_class_majority"] == 0.5
    # range bins: the three opportunities are all within 1 km of closest approach
    bins = {b["bin"]: b for b in everything["pd_by_cpa_range"]}
    assert sum(b["opportunities"] for b in bins.values()) == 3
    assert everything["range_at_pd_m"] is None or everything["range_at_pd_m"] >= 500
    # bearings: 2 x 120 with sigma 1.5 deg of noise, against the exact truth
    be = piston["bearing_error"]
    assert be["n"] == 240
    assert be["rms_deg"] == pytest.approx(1.5, abs=0.3) and abs(be["bias_deg"]) < 0.4
    assert 0.55 < be["within_sigma"] < 0.8
    assert be["elevation_rms_deg"] == pytest.approx(2.25, abs=0.5)
    assert sum(b["n"] for b in piston["bearing_error_by_elevation"]) == 240
    lo, hi = piston["elevation_heard_deg"]
    assert 5.0 < lo < hi < 30.0
    # false alarms: station 3 one episode of two BIRDS detections, station 2 one ROAD_TRAFFIC in the quiet period
    fa = r["false_alarms"]
    assert (fa["episodes"], fa["detections"]) == (2, 3)
    assert fa["by_station"] == {"1": 0, "2": 1, "3": 1} and fa["by_label"] == {"BIRDS": 2, "ROAD_TRAFFIC": 1}
    assert fa["station_hours"] == pytest.approx(3 * 1260 / 3600, abs=1e-3)
    assert fa["per_station_hour"] == pytest.approx(2 / (3 * 1260 / 3600), abs=1e-3)
    assert fa["false_share"] == pytest.approx(2 / (2 + 2), abs=1e-4)
    assert fa["quiet"]["episodes"] == 1 and fa["quiet"]["station_hours"] == pytest.approx(3 * 200 / 3600, abs=1e-3)
    # fused points of stations 1 and 2 against the truth
    loc = r["localization"]
    assert loc["points"] >= 50 and loc["false_points"] == 0
    assert loc["horizontal_error_m"]["median"] < 80.0 and loc["within_reported_error"] > 0.3
    # levels: the reference meter at the first report (+10 s) and the uploaded audio at the keep-alive (+20 s)
    assert s1["reference_spl_at_first_db"] == 52.5 and s1["reference_spl_max_db"] == 61.0
    assert s1["audio_level_at_detection"] == {"dbfs": pytest.approx(-40.0, abs=0.2), "spl_db": pytest.approx(74.0, abs=0.2)}
    assert piston["audio_level_at_detection_spl_db"]["min"] == pytest.approx(74.0, abs=0.2)
    # geometry along P1: north of the 900 m baseline the two (three) stations give points
    (gp1,) = [p for p in r["passes"] if p["pass_id"] == "P1"]
    assert gp1["geometry_share"]["position"] > 0.8
    assert r["geometry"]["share"]["position"] > 0.2 and r["geometry"]["share"]["blind_geometry"] > 0.0
    # the report reads
    text = acc.markdown(r)
    assert "PISTON_UAV" in text and "Ложные тревоги" in text and "Точность пеленга" in text


def test_exclusions_and_operating_windows(trial, tmp_path):
    store, _, path = trial
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["exclude"] = [{"since": int((T0 + 590) * US), "until": int((T0 + 630) * US), "station_id": 3, "note": "посторонний"}]
    doc["stations"][1]["operating"] = [{"since": int((T0 + 100) * US), "until": int((T0 + 1200) * US)}]   # station 2 started late
    p = tmp_path / "t2.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    r = acc.evaluate(store, acc.load_trial(p, store))
    assert r["false_alarms"]["by_station"] == {"1": 0, "2": 1, "3": 0}
    assert ("P1", 2) not in {(x["pass_id"], x["station_id"]) for x in r["station_passes"] if x["opportunity"]}
    assert r["summary"]["PISTON_UAV"]["opportunities"] == 2 and r["summary"]["PISTON_UAV"]["detected"] == 1
    assert r["reports_outside_operation"] > 0


def test_wilson():
    assert acc.wilson(0, 0) is None
    lo, hi = acc.wilson(77, 100)
    assert lo == pytest.approx(0.6784, abs=1e-3) and hi == pytest.approx(0.8416, abs=1e-3)
    assert acc.wilson(10, 10)[1] == 1.0 and acc.wilson(0, 10)[0] == 0.0


def test_geometry_matches_the_fusion():
    st = np.array([STATIONS[1], STATIONS[2]])
    pts = np.array([[450.0, 1500.0, 250.0], [-3000.0, 0.0, 200.0], [450.0, 200.0, 250.0], [20000.0, 0.0, 200.0]])
    code, h_err, crossing, count = geo.assess(st, pts, range_m=5000.0, sigma_deg=2.0)
    assert list(code) == [geo.OK, geo.BLIND, geo.OK, geo.OUT] and list(count) == [2, 2, 2, 0]
    assert crossing[1] < 1.0 and math.isnan(h_err[1])
    # the error of a point is the one bearing_fusion.intersect gives for exact rays weighted by range
    for k in (0, 2):
        az = [math.degrees(math.atan2(pts[k, 0] - s[0], pts[k, 1] - s[1])) for s in st]
        rng = [float(np.hypot(*(pts[k, :2] - s[:2]))) for s in st]
        xyz, cov, _ = intersect(st, az, [0.0, 0.0], [2.0, 2.0], rng)
        assert np.allclose(xyz[:2], pts[k, :2], atol=1e-6)
        assert h_err[k] == pytest.approx(math.sqrt(np.trace(cov)), rel=1e-6)
    one = geo.assess(st, np.array([[-3000.0, 0.0]]), range_m=3500.0, sigma_deg=2.0, height_m=200.0)
    assert one[0][0] == geo.SINGLE                                   # only station 1 within 3.5 km


def test_coverage_grid():
    st = np.array([STATIONS[1], STATIONS[2], STATIONS[3]])
    g = geo.coverage_grid(st, range_m=1500.0, sigma_deg=3.0, height_m=200.0)
    assert g["nx"] * g["ny"] == len(g["codes"]) == len(g["h_err_m"]) <= geo.MAX_CELLS
    assert sum(g["share"].values()) == pytest.approx(1.0, abs=1e-3)
    # the cell over the middle of the triangle has a point, the far corner none
    def cell(e, n):
        i = int((n - g["n0"]) / g["step_m"] + 0.5)
        j = int((e - g["e0"]) / g["step_m"] + 0.5)
        return g["codes"][i * g["nx"] + j]
    assert cell(450.0, 250.0) == str(geo.OK) and cell(g["e0"], g["n0"]) == str(geo.OUT)
    with pytest.raises(ValueError):
        geo.coverage_grid(np.zeros((0, 3)), range_m=1.0, sigma_deg=1.0)
    big = geo.coverage_grid(st, range_m=5000.0, sigma_deg=3.0, step_m=5.0)
    assert big["nx"] * big["ny"] <= geo.MAX_CELLS and big["step_m"] > 5.0


def test_coverage_route(bridge, monkeypatch):  # noqa: F811
    from app import app
    import station.router as router

    store, service = bridge
    feed(store, service, (1, 2))
    monkeypatch.setattr(router, "store", store)
    client = TestClient(app)
    lat0, lon0, alt0 = position(1)
    r = client.get("/api/v1/geometry/coverage", params={"station_ids": "1,2", "range_m": 3000, "sigma_deg": 2,
                                                        "origin_lat": lat0, "origin_lon": lon0, "origin_alt": alt0})
    assert r.status_code == 200
    g = r.json()
    assert [s["station_id"] for s in g["stations"]] == [1, 2]
    assert g["stations"][1]["e"] == pytest.approx(900.0, abs=1.0) and g["share"]["blind_geometry"] > 0
    assert client.get("/api/v1/geometry/coverage", params={"station_ids": "9", "range_m": 3000}).status_code == 404
    assert client.get("/api/v1/geometry/coverage", params={"station_ids": "1", "range_m": 0}).status_code == 422


def test_cli(trial, tmp_path, capsys):
    import importlib.util
    from pathlib import Path

    store, _, path = trial
    spec = importlib.util.spec_from_file_location("acceptance_metrics", Path(__file__).resolve().parents[1] / "tools" / "acceptance_metrics.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    out_json, out_md = tmp_path / "r.json", tmp_path / "r.md"
    assert cli.main(["report", "--db", str(store.path), "--trial", str(path), "--json", str(out_json), "--md", str(out_md),
                     "--audio-cal-dbfs", "-20"]) == 0
    r = json.loads(out_json.read_text(encoding="utf-8"))
    assert r["summary"]["PISTON_UAV"]["detected"] == 2 and "Метрики приёмки" in out_md.read_text(encoding="utf-8")
    cal = tmp_path / "cal.wav"
    _wav(cal, 0.1, seconds=5.0)
    assert cli.main(["calibrate", "--wav", str(cal)]) == 0
    assert "-20.0" in capsys.readouterr().out
    assert cli.main(["report", "--db", str(store.path), "--trial", str(tmp_path / "missing.json")]) == 2
