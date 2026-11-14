"""Compact heartbeat schema 2: the optional detector-health map (key 13) from zs_station_pipeline."""
import pytest

from station.cbor_codec import decode_heartbeat_obj
from station.schemas import DetectorHealth, HeartbeatMessage
from station.store import EventStore
from tests_core.test_cellular_telemetry import compact_heartbeat


def detector_map() -> dict:
    return {0: 7, 1: 3600, 2: 7190, 3: 2, 4: 120, 5: 45, 6: 300, 7: 13, 8: 0, 9: 1, 10: 187, 11: 3}


def test_schema2_decodes_detector_health():
    obj = compact_heartbeat()
    obj[0] = 2
    obj[13] = detector_map()
    hb = decode_heartbeat_obj(obj)
    assert hb.cellular is not None and hb.cellular.imsi == "250011234567890"   # everything of schema 1 still there
    assert hb.detector == DetectorHealth(
        boot_id=7, uptime_s=3600, windows=7190, windows_dropped=2, confirmed_windows=120, suspect_windows=45,
        engine_windows=300, events_emitted=13, events_refused=0, outbox_pending=1, window_max_ms=187, presence_level="CONFIRMED",
    )


def test_schema2_without_the_map_and_schema1_have_no_detector():
    obj = compact_heartbeat()
    obj[0] = 2
    assert decode_heartbeat_obj(obj).detector is None
    obj = compact_heartbeat()
    obj[13] = detector_map()            # schema 1 ignores key 13
    assert decode_heartbeat_obj(obj).detector is None


def test_unknown_presence_level_and_bad_boot_id_fail_closed():
    obj = compact_heartbeat()
    obj[0] = 2
    obj[13] = {**detector_map(), 11: 9}
    assert decode_heartbeat_obj(obj).detector.presence_level == "NONE"
    obj[13] = {**detector_map(), 0: "7"}
    with pytest.raises(ValueError):
        decode_heartbeat_obj(obj)
    obj[0] = 3
    with pytest.raises(ValueError):
        decode_heartbeat_obj(obj)


def test_store_round_trips_detector_health(tmp_path):
    store = EventStore(tmp_path / "events.sqlite3")
    obj = compact_heartbeat()
    obj[0] = 2
    obj[13] = detector_map()
    hb = decode_heartbeat_obj(obj)
    store.upsert_station(hb)
    stored = store.get_station_heartbeat(hb.station_id)
    assert stored is not None and stored.detector is not None
    assert stored.detector.boot_id == 7 and stored.detector.presence_level == "CONFIRMED"
    # an older firmware's schema-1 heartbeat after it keeps the record valid (detector simply absent)
    store.upsert_station(decode_heartbeat_obj(compact_heartbeat()))
    assert store.get_station_heartbeat(hb.station_id).detector is None
    assert HeartbeatMessage.model_validate_json(stored.model_dump_json()).detector == stored.detector
