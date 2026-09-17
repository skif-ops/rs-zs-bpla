import os

import pytest
from pydantic import ValidationError

from station.cbor_codec import decode_heartbeat_obj
from station.schemas import CellularTelemetry, HeartbeatMessage, StationPosition
from station.store import EventStore


def compact_heartbeat() -> dict:
    return {
        0: 1,
        1: 3,
        2: 424242,
        3: 1_780_000_000_000_000,
        4: {0: 557550800, 1: 376176300, 2: 1560, 3: 8, 4: 1, 5: 1},
        5: {0: 3, 1: 12, 2: 80, 3: True, 4: 65, 12: 1, 13: 1},
        6: {0: 81, 1: 12750, 2: 18100, 3: 245, 4: 12750, 5: -500, 6: 6375, 7: 0},
        7: {0: 0, 1: 0, 2: -72, 3: 90, 4: 0},
        8: "evt-pre-20-test",
        9: "model-test",
        10: "EVT-PRE-20-Rev.A",
        11: True,
        12: {
            0: "250011234567890",
            1: "89701012345678901234",
            2: "25001",
            3: "Test Operator",
            4: "network.apn",
            5: "10.10.0.2.255.255.255.0",
            6: "10.10.0.1",
            7: "1.1.1.1",
            8: "8.8.8.8",
            9: 7,
            10: 2,
            11: True,
        },
    }


def test_compact_heartbeat_decodes_full_cellular_identity():
    heartbeat = decode_heartbeat_obj(compact_heartbeat())
    assert heartbeat.station_id == 424242
    assert heartbeat.station.position_source == "configured_install"
    assert heartbeat.power.monitor_valid
    assert heartbeat.cellular is not None
    assert heartbeat.cellular.imsi == "250011234567890"
    assert heartbeat.cellular.iccid == "89701012345678901234"
    assert heartbeat.cellular.apn_source == "NETWORK"
    assert heartbeat.cellular.settings_valid


@pytest.mark.parametrize(
    ("field", "value"),
    [("imsi", "25001"), ("imsi", "25001X234567890"), ("iccid", "89701012")],
)
def test_cellular_identity_validation_rejects_malformed_values(field: str, value: str):
    values = {
        "imsi": "250011234567890",
        "iccid": "89701012345678901234",
        "apn": "network.apn",
        "local_address": "10.10.0.2",
        "gateway": "10.10.0.1",
        "primary_dns": "1.1.1.1",
        "apn_source": "NETWORK",
        "settings_valid": True,
    }
    values[field] = value
    with pytest.raises(ValidationError):
        CellularTelemetry(**values)


@pytest.mark.parametrize(
    ("key", "value"),
    [(0, 250011234567890), (9, "7"), (10, 99), (11, "true")],
)
def test_compact_cellular_fields_fail_closed_on_wrong_wire_types(key: int, value):
    payload = compact_heartbeat()
    payload[12][key] = value
    with pytest.raises((ValidationError, ValueError)):
        decode_heartbeat_obj(payload)


def test_store_keeps_full_identity_internally_and_redacts_general_listing(tmp_path):
    store = EventStore(tmp_path / "cellular.sqlite3")
    heartbeat = decode_heartbeat_obj(compact_heartbeat())
    store.upsert_station(heartbeat)

    internal = store.get_station_heartbeat(heartbeat.station_id)
    assert internal is not None and internal.cellular is not None
    assert internal.cellular.imsi == "250011234567890"
    assert internal.cellular.iccid == "89701012345678901234"

    public = store.list_stations()[0]["cellular"]
    assert "imsi" not in public and "iccid" not in public
    assert public["imsi_redacted"] == "250...7890"
    assert public["iccid_redacted"] == "8970...1234"
    if os.name == "posix":
        assert (store.path.stat().st_mode & 0o777) == 0o600


def test_legacy_heartbeat_does_not_erase_stored_cellular_identity(tmp_path):
    store = EventStore(tmp_path / "preserve.sqlite3")
    initial = decode_heartbeat_obj(compact_heartbeat())
    store.upsert_station(initial)
    store.upsert_station(
        HeartbeatMessage(
            station_id=initial.station_id,
            time_us=initial.time_us + 1,
            station=StationPosition(lat_e7=0, lon_e7=0, alt_dm=0),
        )
    )
    saved = store.get_station_heartbeat(initial.station_id)
    assert saved is not None and saved.cellular is not None
    assert saved.cellular.imsi == "250011234567890"
