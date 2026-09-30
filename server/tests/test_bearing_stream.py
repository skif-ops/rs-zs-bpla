"""Bearing stream while tracking (MQTT ICD addendum H): codec against the firmware golden vector, the bridge route,
idempotent storage and the link from a track to its system event."""

from types import SimpleNamespace

import cbor2
import pytest

from pki.mosquitto import station_topics
from station.bearing_codec import decode_bearing_batch
from station.mqtt_bridge import handle_message, process_message, station_id_from_topic
from station.service import StationFusionService
from station.store import EventStore

# firmware/tests/test_bearing_stream.c encodes the same batch to these bytes (zs_bearing_batch_encode)
GOLDEN = bytes.fromhex(
    "a90001010702110305041b0000000500000001051b0006651729573c2006010701088386001931561907d018b418e608861901f419319e19"
    "07c118af18e508861903e81931cf3895190384188005"
)
TRACK = (5 << 32) | 1
TOPIC = "zs/v1/pilot1/17/bearing"


def batch(changes: dict | None = None) -> dict:
    obj = {0: 1, 1: 7, 2: 17, 3: 5, 4: TRACK, 5: 1_800_000_012_500_000, 6: 1, 7: 1,
           8: [[0, 12630, 2000, 180, 230, 8], [500, 12702, 1985, 175, 229, 8], [1000, 12751, -150, 900, 128, 5]]}
    obj.update(changes or {})
    return obj


def test_golden_vector_matches_the_firmware():
    assert cbor2.dumps(batch(), canonical=True) == GOLDEN
    b = decode_bearing_batch(GOLDEN)
    assert (b.station_id, b.boot_id, b.track_event_id, b.time_trust, b.geometry_id) == (17, 5, TRACK, "GNSS_TIME_TRUSTED", 1)
    assert [s.time_us for s in b.samples] == [1_800_000_012_500_000, 1_800_000_013_000_000, 1_800_000_013_500_000]
    assert [s.azimuth_deg for s in b.samples] == [126.3, 127.02, 127.51]
    assert b.samples[2].elevation_deg == -1.5 and b.samples[2].sigma_deg == 9.0 and b.samples[2].frames == 5
    assert b.samples[0].confidence == pytest.approx(230 / 255, abs=1e-4)


@pytest.mark.parametrize("obj,reason", [
    (batch({1: 6}), "type"),
    (batch({2: 0}), "station_id"),
    (batch({4: 0}), "track event_id"),
    (batch({8: []}), "1..16 samples"),
    (batch({8: [[0, 36000, 0, 1, 1, 1]]}), "azimuth"),
    (batch({8: [[0, 100, 9001, 1, 1, 1]]}), "elevation"),
    (batch({8: [[500, 100, 0, 1, 1, 1], [0, 100, 0, 1, 1, 1]]}), "time order"),
    (batch({8: [[0, 100, 0, 1, 1]]}), "six fields"),
    (batch({8: [[0, 100, 0, 1, 1, 1]] * 17}), "1..16 samples"),
])
def test_invalid_batches_are_refused(obj, reason):
    with pytest.raises(ValueError, match=reason):
        decode_bearing_batch(cbor2.dumps(obj, canonical=True))


def test_non_canonical_and_foreign_keys_are_refused():
    with pytest.raises(ValueError, match="canonical"):
        decode_bearing_batch(_non_canonical())
    extra = batch()
    extra[9] = 1
    with pytest.raises(ValueError, match="keys"):
        decode_bearing_batch(cbor2.dumps(extra, canonical=True))
    with pytest.raises(ValueError, match="size"):
        decode_bearing_batch(b"")


def _non_canonical() -> bytes:
    # station_id 17 in a two-byte head (0x18 0x11) instead of the shortest form
    return GOLDEN.replace(bytes([0x02, 0x11]), bytes([0x02, 0x18, 0x11]), 1)


def test_bearing_topic_and_acl():
    assert station_id_from_topic(TOPIC, "pilot1") == (17, "bearing")
    row = SimpleNamespace(tenant="pilot1", station_id=17)
    assert ("write", "zs/v1/pilot1/17/bearing") in station_topics(row)


def detection(event_id: int = TRACK, station_id: int = 17, time_us: int = 1_800_000_012_000_000) -> bytes:
    return cbor2.dumps({0: 4, 1: 2, 2: station_id, 3: event_id & 0xFFFFFFFF, 4: event_id >> 32, 5: event_id, 6: time_us, 7: 0,
                        8: {4: 1, 5: 200}, 10: {}, 12: {}, 13: {}, 14: {}}, canonical=True)


def test_bridge_stores_bearings_once_and_links_them_to_the_system_event(tmp_path):
    store = EventStore(tmp_path / "t.sqlite3")
    service = StationFusionService(store)
    q = service.bus.subscribe()
    assert process_message("zs/v1/pilot1/17/up", detection(), "pilot1", True, event_store=store, fusion_service=service) == "stored"
    assert process_message(TOPIC, GOLDEN, "pilot1", True, event_store=store, fusion_service=service) == "stored"
    assert process_message(TOPIC, GOLDEN, "pilot1", True, event_store=store, fusion_service=service) == "duplicate"   # QoS 1 redelivery
    rows = store.list_bearings(track_event_id=TRACK)
    assert [r["azimuth_deg"] for r in rows] == [126.3, 127.02, 127.51]
    system_event_id = rows[0]["system_event_id"]
    assert system_event_id and all(r["system_event_id"] == system_event_id for r in rows)
    assert store.list_bearings(system_event_id=system_event_id) == rows
    assert store.list_bearings(station_id=17, since_us=1_800_000_013_000_000) == rows[1:]
    live = [q.get_nowait() for _ in range(q.qsize())]
    bearing_msgs = [m for m in live if isinstance(m, dict) and m.get("type") == "bearings"]
    assert len(bearing_msgs) == 1 and bearing_msgs[0]["system_event_id"] == system_event_id and len(bearing_msgs[0]["samples"]) == 3


def test_bridge_refuses_a_batch_for_another_station(tmp_path):
    store = EventStore(tmp_path / "t.sqlite3")
    with pytest.raises(ValueError, match="station_id mismatch"):
        process_message("zs/v1/pilot1/18/bearing", GOLDEN, "pilot1", True, event_store=store, fusion_service=StationFusionService(store))


class Client:
    def __init__(self):
        self.acks = []

    def publish(self, *a, **k):
        raise AssertionError("a bearing batch is not answered")

    def ack(self, mid, qos):
        self.acks.append((mid, qos))


def test_handle_message_acknowledges_valid_and_malformed_batches(tmp_path):
    store = EventStore(tmp_path / "t.sqlite3")
    service = StationFusionService(store)
    client = Client()
    ok = SimpleNamespace(topic=TOPIC, payload=GOLDEN, qos=1, retain=False, mid=1)
    bad = SimpleNamespace(topic=TOPIC, payload=b"\xa0", qos=1, retain=False, mid=2)
    assert handle_message(client, ok, "pilot1", True, event_store=store, fusion_service=service)
    assert not handle_message(client, bad, "pilot1", True, event_store=store, fusion_service=service)
    assert client.acks == [(1, 1), (2, 1)]          # malformed input is acknowledged and discarded (no poison loop)
    assert len(store.list_bearings()) == 3 and store.list_bearings()[0]["system_event_id"] is None   # no detection yet
