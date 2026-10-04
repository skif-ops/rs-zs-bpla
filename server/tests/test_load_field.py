"""tools/load_field.py in short: the pilot-size field (41 stations) for half an hour of a day with every link fault on,
through the bridge path from one process per tenant into one database while a reader asks what the UI asks: every
detection, bearing sample and audio segment stored once, redeliveries answered as duplicates with the same receipt,
nothing left unacknowledged, no locked database for the readers (docs/SERVER_LOAD_FIELD_2026-10-03.md)."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import load_field  # noqa: E402


@pytest.mark.parametrize("count", [3, 20, 40])
def test_bench_scenario_uses_only_virtual_ids_and_one_tenant(count: int):
    stations = load_field.scenario_stations(count, "bench", 1000)
    assert [s.station_id for s in stations] == list(range(1001, 1001 + count))
    assert {s.tenant for s in stations} == {"bench"}
    assert len({s.enu for s in stations}) == count


def test_bench_scenario_rejects_invalid_ids_and_tenant():
    with pytest.raises(ValueError):
        load_field.scenario_stations(40, "pilot1/other", 1000)
    with pytest.raises(ValueError):
        load_field.scenario_stations(40, "bench", 0xFFFFFFFF)


def test_half_an_hour_of_the_field_with_faults(tmp_path: Path):
    args = load_field.build_parser().parse_args(["--out", str(tmp_path / "field"), "--hours", "0.5", "--seed", "1",
                                                 "--restart", "600", "--min-real-time-factor", "3"])
    report = load_field.run(args)
    print(load_field.summary(report))
    failed = [name for name, ok in report["checks"].items() if not ok]
    assert not failed, failed
    assert report["stations"] == 41 and len(report["workers"]) == 3 and report["readers"]
    counts = {k: sum(w["counts"][k] for w in report["workers"]) for k in report["workers"][0]["counts"]}
    assert counts["redelivered"] > 100 and counts["reconnect_redeliveries"] > 50 and counts["restarts"] >= 3
    assert counts["delivered"] > 3000 and counts["audio_requests"] >= 5
    assert report["database"]["detections"] == report["expected"]["detections"] > 50
    assert report["database"]["air_alerts"] > 0 and report["database"]["alert_outbox"] > 0
    saved = json.loads((tmp_path / "field" / "report.json").read_text())
    assert saved["ok"] and saved["checks"] == report["checks"]
