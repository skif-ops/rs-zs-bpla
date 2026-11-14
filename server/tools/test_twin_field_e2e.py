#!/usr/bin/env python3
"""Three station twins in one field, one target, the real Muhoed path (CI: the station-twin-field job of ci/jobs.json,
ci/twin_field.sh; CTest `station_twin_field` runs it where the server dependencies are installed).

Stations 17 (0, 0) and 18 (1200, 0) know their position from their GNSS receivers, station 19 (600, 1000) from its
installation record; all three boot for the 5th time, so their first events share event_id 5:1.  The target flies
east-south-east at 46 m/s, 200 m above the stations, passing 1.2 km north of 19.  Checked on the server side:
  - every station's detections carry its position (the firmware fills the station map; GNSS live / installation);
  - equal event_id of different stations are kept apart (detections, system event, track id);
  - one fused track of all three stations, its points close to the truth and within their reported error;
  - the tracking windows hold while the target is heard (no window closes on the time limit of the old 120 s);
  - the acceptance metrics: Pd 3/3, the class of the synthetic electric multirotor, no false alarms, bearing error.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import twin_field  # noqa: E402

STATIONS = [twin_field.FieldStation(17, (0.0, 0.0, 0.0)), twin_field.FieldStation(18, (1200.0, 0.0, 0.0)),
            twin_field.FieldStation(19, (600.0, 1000.0, 0.0), installed=True)]
TARGET = (-2500.0, 2200.0, 200.0, 45.0, -10.0, 0.0)
SECONDS = 180
SHARED_EVENT = (5 << 32) | 1


def main() -> int:
    try:
        import numpy  # noqa: F401
        import paho.mqtt.client  # noqa: F401
        import pydantic  # noqa: F401
    except ImportError:
        print("SKIP: the server dependencies are not installed (pip install -r server/requirements.lock.txt)")
        return 77
    if not twin_field.TWIN.exists():
        print(f"SKIP: {twin_field.TWIN} not built")
        return 77
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        logs = twin_field.run_twins(STATIONS, TARGET, SECONDS, out)
        store, results = twin_field.ingest(STATIONS, out)
        assert set(results) <= {("up", "stored"), ("bearing", "stored"), ("status", "stored"), ("up", "duplicate")}, results
        assert results[("up", "stored")] >= 30 and results[("bearing", "stored")] >= 200, results

        # positions: the firmware's station map, GNSS live for 17 and 18, the installation record for 19
        from station.schemas import DetectionMessage
        with store._conn() as c:
            rows = c.execute("SELECT station_id, event_id, payload FROM detections ORDER BY station_id, event_time_us").fetchall()
        firsts = {}
        for r in rows:
            firsts.setdefault(r["station_id"], DetectionMessage.model_validate_json(r["payload"]))
        assert sorted(firsts) == [17, 18, 19], sorted(firsts)
        for st in STATIONS:
            d = firsts[st.station_id]
            lat, lon, alt = twin_field.geodetic(*st.enu)
            err = math_dist(d.station.lat, d.station.lon, lat, lon)
            assert err < 1.0 and abs(d.station.alt_m - alt) < 0.5, (st, d.station, err)
            assert d.station.position_source == ("configured_install" if st.installed else "gnss_live"), d.station
            assert d.event_id == SHARED_EVENT, (st.station_id, hex(d.event_id))      # the same event_id at every station
            hb = store.get_station_heartbeat(st.station_id)
            assert hb is not None and math_dist(hb.station.lat, hb.station.lon, lat, lon) < 1.0, hb

        # one fused track of all three stations; its id names the earliest (event_id, station) pair
        (summary,) = store.list_tracks()
        assert summary["stations"] == [17, 18, 19] and summary["track_id"] == f"TRK-{SHARED_EVENT:016x}-17", summary
        duration_s = (summary["last_time_us"] - summary["first_time_us"]) / 1e6
        assert duration_s >= 130.0, duration_s                      # beyond the old 120 s window limit
        for sid, log in logs.items():
            assert "window closed (time limit)" not in log, f"station {sid}: a tracking window closed on the time limit"
        with store._conn() as c:
            linked = c.execute("SELECT station_id, system_event_id FROM detections WHERE event_id=?",
                               (SHARED_EVENT,)).fetchall()
        assert sorted(r["station_id"] for r in linked) == [17, 18, 19] and all(r["system_event_id"] for r in linked), \
            [tuple(r) for r in linked]

        # the acceptance report of the run
        result = twin_field.report(store, twin_field.write_trial(STATIONS, TARGET, SECONDS, "ELECTRIC_UAV", out), out,
                                   max_range_m=5000.0, assoc_range_m=6000.0)
        s = result["summary"]["ALL"]
        assert s["opportunities"] == 3 and s["detected"] == 3 and s["p_correct_class_first"] == 1.0, s
        assert result["false_alarms"]["episodes"] == 0, result["false_alarms"]
        b = s["bearing_error"]
        assert b["n"] >= 500 and b["rms_deg"] < 3.0, b
        loc = result["localization"]
        assert loc["false_points"] == 0 and loc["horizontal_error_m"]["median"] < 60.0, loc
        assert loc["within_reported_error"] >= 0.8, loc
        print(f"field of 3 twins: {len(rows)} detections (event_id 5:1 at every station), {summary['points']} fused points over "
              f"{duration_s:.0f} s, track {summary['track_id']}; Pd {s['detected']}/{s['opportunities']}, first report at "
              f"{s['first_report_range_m']['median']:.0f} m, class right {s['p_correct_class_first']:.0%}, false episodes 0; "
              f"bearing RMS {b['rms_deg']:.2f} deg; track median {loc['horizontal_error_m']['median']:.0f} m, "
              f"90 % {loc['horizontal_error_m']['p90']:.0f} m, within the reported error {loc['within_reported_error']:.0%}")
    return 0


def math_dist(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    return math.hypot((lat1 - lat2) * twin_field.M_PER_DEG, (lon1 - lon2) * twin_field.M_PER_DEG * math.cos(math.radians(lat1)))


if __name__ == "__main__":
    raise SystemExit(main())
