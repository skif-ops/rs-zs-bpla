import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from station.command_codec import (
    CommandAck,
    CommandSigner,
    decode_signed_command,
    encode_command_ack,
)
from station.mqtt_bridge import handle_message, process_message, publish_due_commands
from station.store import EventStore


class FakeClient:
    def __init__(self, rc=0):
        self.rc = rc
        self.messages = []

    def publish(self, topic, payload, qos, retain):
        self.messages.append((topic, payload, qos, retain))
        return SimpleNamespace(rc=self.rc)


class AckCaptureClient:
    def __init__(self):
        self.acks = []

    def ack(self, mid, qos):
        self.acks.append((mid, qos))


class FailingAckStore:
    def ack_command(self, *args):
        raise RuntimeError("temporary database failure")


def test_qos1_command_retries_until_station_bound_application_ack(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    key = CommandSigner(Ed25519PrivateKey.generate())
    client = FakeClient()
    command = store.create_command(
        17,
        "CMD_REQUEST_AUDIO",
        {"event_id": 42, "segment": "both"},
        ttl_us=10_000_000,
    )
    first_us = command.created_time_us + 1

    assert publish_due_commands(
        client,
        "pilot",
        key,
        now_us=first_us,
        retry_after_us=1_000_000,
        event_store=store,
    ) == (1, 0)
    topic, payload, qos, retain = client.messages[-1]
    assert topic == "zs/v1/pilot/17/down"
    assert qos == 1 and retain is False
    decoded = decode_signed_command(
        payload,
        {key.key_id: key.public_key},
        now_us=first_us,
    )
    assert decoded.command_id == command.command_id

    assert publish_due_commands(
        client,
        "pilot",
        key,
        now_us=first_us + 999_999,
        retry_after_us=1_000_000,
        event_store=store,
    ) == (0, 0)
    assert publish_due_commands(
        client,
        "pilot",
        key,
        now_us=first_us + 1_000_000,
        retry_after_us=1_000_000,
        event_store=store,
    ) == (1, 0)

    wrong_topic_ack = encode_command_ack(
        CommandAck(18, command.command_id, 0, first_us + 1_100_000)
    )
    with pytest.raises(ValueError, match="mismatch"):
        process_message(
            "zs/v1/pilot/17/ack",
            wrong_topic_ack,
            "pilot",
            True,
            event_store=store,
        )

    ack = encode_command_ack(
        CommandAck(17, command.command_id, 0, first_us + 1_200_000)
    )
    assert process_message(
        "zs/v1/pilot/17/ack",
        ack,
        "pilot",
        True,
        event_store=store,
    ) == "acked"
    assert process_message(
        "zs/v1/pilot/17/ack",
        ack,
        "pilot",
        True,
        event_store=store,
    ) == "duplicate"
    assert store.due_commands(first_us + 2_500_000, 1_000_000) == []


def test_publish_failure_and_missing_signer_do_not_advance_queue(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    key = CommandSigner(Ed25519PrivateKey.generate())
    command = store.create_command(7, "CMD_REQUEST_AUDIO", {"event_id": 1})
    now_us = command.created_time_us + 1
    assert publish_due_commands(
        FakeClient(),
        "pilot",
        None,
        now_us=now_us,
        retry_after_us=1_000_000,
        event_store=store,
    ) == (0, 0)
    assert publish_due_commands(
        FakeClient(rc=4),
        "pilot",
        key,
        now_us=now_us,
        retry_after_us=1_000_000,
        event_store=store,
    ) == (0, 1)
    assert [item.command_id for item in store.due_commands(now_us, 1_000_000)] == [
        command.command_id
    ]


@pytest.mark.parametrize("station_id", [False, 0, -1, 0x1_0000_0000])
def test_command_store_rejects_station_id_outside_uint32(tmp_path: Path, station_id: int):
    store = EventStore(tmp_path / "events.sqlite3")
    with pytest.raises(ValueError, match="uint32"):
        store.create_command(station_id, "CMD_REQUEST_AUDIO", {"event_id": 1})


def test_command_store_rejects_ttl_above_protocol_maximum(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    with pytest.raises(ValueError, match="1..15 minutes"):
        store.create_command(
            17,
            "CMD_REQUEST_AUDIO",
            {"event_id": 1},
            ttl_us=15 * 60 * 1_000_000 + 1,
        )


def test_ack_cannot_complete_command_owned_by_another_station(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    command = store.create_command(17, "CMD_REQUEST_AUDIO", {"event_id": 1})
    ack = encode_command_ack(
        CommandAck(18, command.command_id, 0, command.created_time_us + 1)
    )
    with pytest.raises(ValueError, match="ownership"):
        process_message(
            "zs/v1/pilot/18/ack",
            ack,
            "pilot",
            True,
            event_store=store,
        )


def test_unknown_ack_is_rejected(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    ack = encode_command_ack(
        CommandAck(
            17,
            "12345678-1234-5678-1234-567812345678",
            0,
            1,
        )
    )
    with pytest.raises(ValueError, match="unknown command"):
        process_message(
            "zs/v1/pilot/17/ack",
            ack,
            "pilot",
            True,
            event_store=store,
        )


def test_manual_mqtt_ack_occurs_after_store_and_invalid_input_is_dropped(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    command = store.create_command(17, "CMD_REQUEST_AUDIO", {"event_id": 1})
    payload = encode_command_ack(
        CommandAck(17, command.command_id, 0, command.created_time_us + 1)
    )
    message = SimpleNamespace(
        topic="zs/v1/pilot/17/ack",
        payload=payload,
        mid=91,
        qos=1,
    )
    client = AckCaptureClient()
    assert handle_message(
        client,
        message,
        "pilot",
        True,
        event_store=store,
    ) is True
    assert client.acks == [(91, 1)]

    invalid = SimpleNamespace(
        topic="zs/v1/pilot/18/ack",
        payload=payload,
        mid=92,
        qos=1,
    )
    assert handle_message(
        client,
        invalid,
        "pilot",
        True,
        event_store=store,
    ) is False
    assert client.acks[-1] == (92, 1)


def test_transient_store_failure_is_not_mqtt_acked():
    payload = encode_command_ack(
        CommandAck(17, "12345678-1234-5678-1234-567812345678", 0, 1)
    )
    message = SimpleNamespace(
        topic="zs/v1/pilot/17/ack",
        payload=payload,
        mid=93,
        qos=1,
    )
    client = AckCaptureClient()
    assert handle_message(
        client,
        message,
        "pilot",
        True,
        event_store=FailingAckStore(),
    ) is False
    assert client.acks == []


def test_legacy_command_table_is_migrated_without_losing_pending_command(tmp_path: Path):
    database = tmp_path / "legacy.sqlite3"
    command_id = "12345678-1234-5678-1234-567812345678"
    created_us = int(time.time() * 1_000_000)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE commands(command_id TEXT PRIMARY KEY, station_id INTEGER NOT NULL, "
            "created_us INTEGER NOT NULL, command TEXT NOT NULL, payload TEXT NOT NULL, "
            "delivered INTEGER NOT NULL DEFAULT 0, acked INTEGER NOT NULL DEFAULT 0)"
        )
        connection.execute(
            "INSERT INTO commands(command_id,station_id,created_us,command,payload) "
            "VALUES(?,?,?,?,?)",
            (command_id, 17, created_us, "CMD_REQUEST_AUDIO", '{"event_id": 1}'),
        )

    store = EventStore(database)
    due = store.due_commands(created_us + 1, retry_after_us=1_000_000)
    assert [item.command_id for item in due] == [command_id]
    assert due[0].expires_time_us > created_us
    with store._conn() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(commands)")}
    assert {
        "expires_us",
        "last_publish_us",
        "publish_count",
        "ack_result",
        "ack_detail",
        "completed_us",
    } <= columns
