from pathlib import Path

from station.schemas import DetectionMessage, GnssStatus, HeartbeatMessage, StationPosition
from station.service import StationFusionService
from station.store import EventStore


def test_configured_position_is_not_overwritten_by_live_gnss(tmp_path: Path):
    store = EventStore(tmp_path / "position_guard.sqlite3")
    configured = StationPosition(
        lat_e7=557_550_000,
        lon_e7=376_150_000,
        alt_dm=1800,
        pos_accuracy_m=5,
        altitude_source="configured_msl",
        position_source="configured_install",
    )
    store.upsert_station(
        HeartbeatMessage(
            station_id=7001,
            time_us=1_000_000,
            station=configured,
            gnss=GnssStatus(position_trust="CONFIGURED_OK", time_trust="GNSS_TIME_TRUSTED", pps_ok=True),
        )
    )

    drifted = DetectionMessage(
        schema_ver=3,
        station_id=7001,
        seq_no=1,
        event_id=123,
        event_time_us=1_500_000,
        station=StationPosition(
            lat_e7=557_650_000,
            lon_e7=376_150_000,
            alt_dm=1800,
            position_source="gnss_live",
        ),
        gnss=GnssStatus(fix_type=3, position_delta_m=1113),
    )

    service = StationFusionService(store)
    service.ingest(drifted)
    saved = store.recent_detections(1_500_000, 10)[0]

    assert saved.station.position_source == "configured_install"
    assert saved.station.lat_e7 == configured.lat_e7
    assert saved.station.lon_e7 == configured.lon_e7
    assert saved.gnss.position_suspect
    assert saved.gnss.position_trust == "CONFIGURED_SUSPECT"


def test_live_heartbeat_cannot_replace_configured_station_position(tmp_path: Path):
    store = EventStore(tmp_path / "heartbeat_guard.sqlite3")
    configured = StationPosition(
        lat_e7=557_550_000,
        lon_e7=376_150_000,
        alt_dm=1800,
        position_source="configured_install",
    )
    store.upsert_station(HeartbeatMessage(station_id=7001, time_us=1, station=configured))

    live = StationPosition(
        lat_e7=558_000_000,
        lon_e7=376_500_000,
        alt_dm=1900,
        position_source="gnss_live",
    )
    store.upsert_station(HeartbeatMessage(station_id=7001, time_us=2, station=live))

    saved = store.get_station_heartbeat(7001)
    assert saved is not None
    assert saved.station.position_source == "configured_install"
    assert saved.station.lat_e7 == configured.lat_e7
    assert saved.gnss_observed is not None
    assert saved.gnss_observed.lat_e7 == live.lat_e7
