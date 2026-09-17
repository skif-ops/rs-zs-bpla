import hashlib
from pathlib import Path
from types import SimpleNamespace

import cbor2
import pytest

from station.cbor_codec import decode_detection_cbor
from station.event_receipt_codec import (
    EventReceipt,
    decode_event_receipt,
    encode_event_receipt,
)
from station.mqtt_bridge import build_event_receipt, handle_message, process_message
from station.service import StationFusionService
from station.store import EventStore


def detection_payload(
    *,
    station_id: int = 17,
    boot_id: int = 9,
    seq_no: int = 5,
    event_id: int = 42,
) -> bytes:
    return cbor2.dumps(
        {
            0: 4,
            1: 2,
            2: station_id,
            3: seq_no,
            4: boot_id,
            5: event_id,
            6: 1_700_000,
            7: 0,
            8: {},
            10: {},
            12: {},
            13: {},
            14: {},
        },
        canonical=True,
    )


class ReceiptClient:
    def __init__(self, publish_rc: int = 0):
        self.publish_rc = publish_rc
        self.actions = []

    def publish(self, topic, payload, qos, retain):
        self.actions.append(("publish", topic, payload, qos, retain))
        return SimpleNamespace(rc=self.publish_rc)

    def ack(self, mid, qos):
        self.actions.append(("mqtt_ack", mid, qos))


class CountingFusion:
    def __init__(self, service: StationFusionService):
        self.service = service
        self.calls = 0

    def ingest(self, detection):
        self.calls += 1
        return self.service.ingest(detection)


class FailOnceFusion(CountingFusion):
    def ingest(self, detection):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary fusion failure")
        return self.service.ingest(detection)


def mqtt_message(payload: bytes, *, mid: int = 1, qos: int = 1, retain: bool = False):
    return SimpleNamespace(
        topic="zs/v1/evt/17/up",
        payload=payload,
        mid=mid,
        qos=qos,
        retain=retain,
    )


def test_event_receipt_codec_is_canonical_and_strict():
    receipt = EventReceipt(17, 9, 5, 42, bytes(range(32)))
    encoded = encode_event_receipt(receipt)
    assert len(encoded) <= 128
    assert decode_event_receipt(encoded) == receipt
    assert cbor2.dumps(cbor2.loads(encoded), canonical=True) == encoded

    noncanonical = b"\xa7\x18\x00\x01" + encoded[3:]
    with pytest.raises(ValueError, match="canonical"):
        decode_event_receipt(noncanonical)
    with pytest.raises(ValueError, match="keys"):
        decode_event_receipt(cbor2.dumps({0: 1}, canonical=True))
    boolean_key = cbor2.dumps(
        {False: 1, 1: 6, 2: 17, 3: 9, 4: 5, 5: 42, 6: bytes(32)},
        canonical=True,
    )
    with pytest.raises(ValueError, match="keys"):
        decode_event_receipt(boolean_key)
    with pytest.raises(ValueError, match="SHA-256"):
        encode_event_receipt(EventReceipt(17, 9, 5, 42, b"short"))
    with pytest.raises(ValueError, match="uint64"):
        encode_event_receipt(EventReceipt(17, 9, 5, 0, bytes(32)))


def test_receipt_is_published_before_broker_ack_and_duplicate_is_idempotent(
    tmp_path: Path,
):
    store = EventStore(tmp_path / "events.sqlite3")
    fusion = CountingFusion(StationFusionService(store))
    client = ReceiptClient()
    payload = detection_payload()

    assert handle_message(
        client,
        mqtt_message(payload, mid=11),
        "evt",
        True,
        event_store=store,
        fusion_service=fusion,
    ) is True
    assert [action[0] for action in client.actions] == ["publish", "mqtt_ack"]
    _, topic, receipt_payload, qos, retain = client.actions[0]
    assert topic == "zs/v1/evt/17/receipt"
    assert qos == 1 and retain is False
    assert decode_event_receipt(receipt_payload) == EventReceipt(
        17, 9, 5, 42, hashlib.sha256(payload).digest()
    )
    assert fusion.calls == 1

    client.actions.clear()
    assert handle_message(
        client,
        mqtt_message(payload, mid=12),
        "evt",
        True,
        event_store=store,
        fusion_service=fusion,
    ) is True
    assert [action[0] for action in client.actions] == ["publish", "mqtt_ack"]
    assert fusion.calls == 1


def test_conflicting_event_id_is_discarded_without_receipt(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    fusion = CountingFusion(StationFusionService(store))
    first = detection_payload(seq_no=5, event_id=50)
    conflict = detection_payload(seq_no=6, event_id=50)
    assert process_message(
        "zs/v1/evt/17/up",
        first,
        "evt",
        True,
        event_store=store,
        fusion_service=fusion,
    ) == "stored"

    client = ReceiptClient()
    assert handle_message(
        client,
        mqtt_message(conflict, mid=20),
        "evt",
        True,
        event_store=store,
        fusion_service=fusion,
    ) is False
    assert client.actions == [("mqtt_ack", 20, 1)]
    assert fusion.calls == 1


def test_receipt_publish_failure_retries_without_reprocessing(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    fusion = CountingFusion(StationFusionService(store))
    payload = detection_payload(event_id=60)
    failed = ReceiptClient(publish_rc=4)
    assert handle_message(
        failed,
        mqtt_message(payload, mid=30),
        "evt",
        True,
        event_store=store,
        fusion_service=fusion,
    ) is False
    assert [action[0] for action in failed.actions] == ["publish"]

    retry = ReceiptClient()
    assert handle_message(
        retry,
        mqtt_message(payload, mid=31),
        "evt",
        True,
        event_store=store,
        fusion_service=fusion,
    ) is True
    assert [action[0] for action in retry.actions] == ["publish", "mqtt_ack"]
    assert fusion.calls == 1


def test_interrupted_processing_resumes_before_receipt(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    fusion = FailOnceFusion(StationFusionService(store))
    payload = detection_payload(event_id=70)
    first = ReceiptClient()
    assert handle_message(
        first,
        mqtt_message(payload, mid=40),
        "evt",
        True,
        event_store=store,
        fusion_service=fusion,
    ) is False
    assert first.actions == []

    second = ReceiptClient()
    assert handle_message(
        second,
        mqtt_message(payload, mid=41),
        "evt",
        True,
        event_store=store,
        fusion_service=fusion,
    ) is True
    assert [action[0] for action in second.actions] == ["publish", "mqtt_ack"]
    assert fusion.calls == 2


@pytest.mark.parametrize("qos,retain", [(0, False), (2, False), (1, True)])
def test_non_qos1_or_retained_detection_is_rejected_before_storage(
    tmp_path: Path, qos: int, retain: bool
):
    store = EventStore(tmp_path / "events.sqlite3")
    fusion = CountingFusion(StationFusionService(store))
    client = ReceiptClient()
    assert handle_message(
        client,
        mqtt_message(detection_payload(event_id=80), qos=qos, retain=retain),
        "evt",
        True,
        event_store=store,
        fusion_service=fusion,
    ) is False
    assert all(action[0] != "publish" for action in client.actions)
    assert fusion.calls == 0


def test_receipt_supports_full_uint64_event_id(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    fusion = CountingFusion(StationFusionService(store))
    event_id = 0xFFFFFFFFFFFFFFFF
    payload = detection_payload(event_id=event_id)
    assert process_message(
        "zs/v1/evt/17/up",
        payload,
        "evt",
        True,
        event_store=store,
        fusion_service=fusion,
    ) == "stored"
    topic, receipt_payload = build_event_receipt(
        "zs/v1/evt/17/up", payload, "evt"
    )
    assert topic == "zs/v1/evt/17/receipt"
    assert decode_event_receipt(receipt_payload).event_id == event_id
    with store._conn() as connection:
        assert connection.execute("SELECT COUNT(*) FROM detections").fetchone()[0] == 1
