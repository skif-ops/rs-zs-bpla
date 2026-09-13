#!/usr/bin/env python3
"""QG-2 independent runtime audit of signed downstream and ACK handling."""

from __future__ import annotations

from contextlib import redirect_stderr
import io
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from station.command_codec import (  # noqa: E402
    CommandAck,
    CommandSigner,
    decode_signed_command,
    encode_command_ack,
)
from station.mqtt_bridge import handle_message, process_message, publish_due_commands  # noqa: E402
from station.store import EventStore  # noqa: E402


class CaptureClient:
    def __init__(self, rc: int = 0):
        self.rc = rc
        self.messages: list[tuple[str, bytes, int, bool]] = []

    def publish(self, topic, payload, qos, retain):
        self.messages.append((topic, payload, qos, retain))
        return SimpleNamespace(rc=self.rc)

    def ack(self, mid, qos):
        self.messages.append(("ACK", b"", mid, qos))


class TransientFailureStore:
    def ack_command(self, *args):
        raise RuntimeError("temporary storage failure")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_value_error(action, text: str) -> None:
    try:
        action()
    except ValueError as exc:
        require(text in str(exc), f"unexpected rejection: {exc}")
    else:
        raise AssertionError(f"expected rejection containing: {text}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="zs-command-qg2-") as directory:
        store = EventStore(Path(directory) / "events.sqlite3")
        signer = CommandSigner(Ed25519PrivateKey.generate())
        client = CaptureClient()
        command = store.create_command(
            17,
            "CMD_REQUEST_AUDIO",
            {"event_id": 991, "segment": "both"},
            ttl_us=10_000_000,
        )
        first_us = command.created_time_us + 1

        require(
            publish_due_commands(
                client,
                "evt",
                signer,
                now_us=first_us,
                retry_after_us=1_000_000,
                event_store=store,
            ) == (1, 0),
            "first QoS publication failed",
        )
        topic, payload, qos, retain = client.messages[-1]
        require(topic == "zs/v1/evt/17/down", "down topic mismatch")
        require(qos == 1 and retain is False, "QoS/retain contract mismatch")
        decoded = decode_signed_command(
            payload,
            {signer.key_id: signer.public_key},
            now_us=first_us,
        )
        require(decoded.command_id == command.command_id, "signed UUID mismatch")

        tampered = cbor2.loads(payload)
        tampered[7]["event_id"] = 992
        expect_value_error(
            lambda: decode_signed_command(
                cbor2.dumps(tampered, canonical=True),
                {signer.key_id: signer.public_key},
                now_us=first_us,
            ),
            "signature",
        )
        require(
            publish_due_commands(
                client,
                "evt",
                signer,
                now_us=first_us + 999_999,
                retry_after_us=1_000_000,
                event_store=store,
            ) == (0, 0),
            "command retried before the deadline",
        )
        require(
            publish_due_commands(
                client,
                "evt",
                signer,
                now_us=first_us + 1_000_000,
                retry_after_us=1_000_000,
                event_store=store,
            ) == (1, 0),
            "command was not retried without application ACK",
        )

        spoofed_ack = encode_command_ack(
            CommandAck(18, command.command_id, 0, first_us + 1_100_000)
        )
        expect_value_error(
            lambda: process_message(
                "zs/v1/evt/17/ack",
                spoofed_ack,
                "evt",
                True,
                event_store=store,
            ),
            "mismatch",
        )
        valid_ack = encode_command_ack(
            CommandAck(17, command.command_id, 0, first_us + 1_200_000)
        )
        require(
            process_message(
                "zs/v1/evt/17/ack",
                valid_ack,
                "evt",
                True,
                event_store=store,
            ) == "acked",
            "valid ACK was not persisted",
        )
        require(
            process_message(
                "zs/v1/evt/17/ack",
                valid_ack,
                "evt",
                True,
                event_store=store,
            ) == "duplicate",
            "duplicate ACK is not idempotent",
        )
        require(
            not store.due_commands(first_us + 3_000_000, 1_000_000),
            "ACKed command remained eligible for retry",
        )
        with store._conn() as connection:
            row = connection.execute(
                "SELECT acked,ack_result,ack_detail,completed_us,publish_count "
                "FROM commands WHERE command_id=?",
                (command.command_id,),
            ).fetchone()
        require(row["acked"] == 1 and row["ack_result"] == 0,
                "ACK outcome was not stored")
        require(row["completed_us"] == first_us + 1_200_000,
                "ACK completion time mismatch")
        require(row["publish_count"] == 2, "retry counter mismatch")
        require(
            publish_due_commands(
                CaptureClient(),
                "evt",
                None,
                now_us=first_us,
                retry_after_us=1_000_000,
                event_store=store,
            ) == (0, 0),
            "missing key did not disable downstream",
        )

        inbound = SimpleNamespace(
            topic="zs/v1/evt/17/ack",
            payload=valid_ack,
            mid=77,
            qos=1,
        )
        transient_client = CaptureClient()
        error_log = io.StringIO()
        with redirect_stderr(error_log):
            require(
                handle_message(
                    transient_client,
                    inbound,
                    "evt",
                    True,
                    event_store=TransientFailureStore(),
                ) is False,
                "transient storage failure was not surfaced",
            )
        require(not transient_client.messages,
                "transient failure was incorrectly MQTT-acknowledged")
        require(error_log.getvalue().strip() == "MQTT processing error: RuntimeError",
                "transient error log is absent or exposes exception details")

    print("MQTT signed command transport QG-2: PASS")
    print("scope: host runtime simulation; broker, firmware target and hardware evidence remain pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
