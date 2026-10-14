"""Controlled bench flight plans: station groups, wide-hearing geometry and the real fusion path."""
from pathlib import Path
import random
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
from load_field import bearing_payload, detection_payload  # noqa: E402
from station.mqtt_bridge import process_message  # noqa: E402
from station.service import StationFusionService  # noqa: E402
from station.store import EventStore  # noqa: E402


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


def test_final_episode_fuses_two_distinct_tracks_with_all_five_stations(tmp_path):
    """Regression for the fourth episode: two sources at every station must not create a Cartesian backlog or ghosts."""
    store = EventStore(tmp_path / "five-by-two.sqlite3")
    service = StationFusionService(store)
    stations = wide_stations()
    start_us = 1_800_000_000_000_000
    flights = make_passes(2, start_us, 40, FIVE_STATION_TWO_TARGETS)
    boot_id = 77
    rng = random.Random(20261014)
    events = {}

    for station in stations:
        for flight in flights:
            event_id = (boot_id << 32) | (station.station_id * 10 + flight.index)
            events[station.station_id, flight.index] = event_id
            payload = detection_payload(station, flight, 0.0, seq_no=event_id & 0xFFFFFFFF,
                                        boot_id=boot_id, event_id=event_id, rng=rng)
            assert process_message(f"zs/v1/bench/{station.station_id}/up", payload, "bench", True,
                                   event_store=store, fusion_service=service) == "stored"

    for second in range(41):
        for flight in flights:
            for station in stations:
                payload = bearing_payload(station, flight, float(second), boot_id=boot_id,
                                          track_event_id=events[station.station_id, flight.index], rng=rng)
                assert process_message(f"zs/v1/bench/{station.station_id}/bearing", payload, "bench", True,
                                       event_store=store, fusion_service=service) == "stored"

    tracks = store.list_tracks(limit=20)
    assert len(tracks) == 2
    assert all(track["stations"] == [9010, 9011, 9012, 9013, 9014] for track in tracks)
    assert all(track["points"] >= 7 for track in tracks)
    assert service.tracks.direct_path_steps > 0
    assert service.tracks.fast_path_steps > 0
