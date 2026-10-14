"""Controlled bench flight plans: station groups and wide-hearing geometry."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from bench_uav_flights import (  # noqa: E402
    FIVE_STATION_TWO_TARGETS,
    TARGETS,
    WIDE_TARGETS,
    heard,
    make_passes,
    plan,
    stations_for_scenario,
    wide_stations,
)


def test_wide_hearing_flight_is_heard_by_five_distinct_stations():
    stations = wide_stations()
    assert [station.station_id for station in stations] == [9010, 9011, 9012, 9013, 9014]
    (flight,) = make_passes(1, 1_000_000, 30, WIDE_TARGETS)
    for second in range(31):
        assert sum(heard(station, flight, float(second)) for station in stations) == 5

    published = plan([(1, stations, WIDE_TARGETS)], 30, 0)
    assert published["scenarios"][0]["station_ids"] == [9010, 9011, 9012, 9013, 9014]


def test_evt_pre_20_sequence_has_four_bounded_episodes():
    scenarios = [
        *((count, stations_for_scenario(count), TARGETS) for count in (1, 2, 3)),
        (2, wide_stations(), FIVE_STATION_TWO_TARGETS),
    ]

    published = plan(scenarios, 40, 10)

    assert published["gap_s"] == 10
    assert [scenario["uavs"] for scenario in published["scenarios"]] == [1, 2, 3, 2]
    assert [scenario["duration_s"] for scenario in published["scenarios"]] == [40] * 4
    assert [scenario["station_ids"] for scenario in published["scenarios"]] == [
        [9001, 9002, 9003],
        [9004, 9005, 9006],
        [9007, 9008, 9009],
        [9010, 9011, 9012, 9013, 9014],
    ]


def test_both_targets_in_final_episode_are_heard_by_all_five_stations():
    stations = wide_stations()
    flights = make_passes(2, 1_000_000, 40, FIVE_STATION_TWO_TARGETS)

    for second in range(41):
        for flight in flights:
            assert sum(heard(station, flight, float(second)) for station in stations) == 5
