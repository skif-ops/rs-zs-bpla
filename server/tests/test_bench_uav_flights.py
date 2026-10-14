"""Controlled bench flight plans: station groups and wide-hearing geometry."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from bench_uav_flights import WIDE_TARGETS, heard, make_passes, plan, wide_stations  # noqa: E402


def test_wide_hearing_flight_is_heard_by_five_distinct_stations():
    stations = wide_stations()
    assert [station.station_id for station in stations] == [9010, 9011, 9012, 9013, 9014]
    (flight,) = make_passes(1, 1_000_000, 30, WIDE_TARGETS)
    for second in range(31):
        assert sum(heard(station, flight, float(second)) for station in stations) == 5

    published = plan([(1, stations, WIDE_TARGETS)], 30, 0)
    assert published["scenarios"][0]["station_ids"] == [9010, 9011, 9012, 9013, 9014]
