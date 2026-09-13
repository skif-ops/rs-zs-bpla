#!/usr/bin/env python3
"""QG-2 independent runtime audit of signed downstream and ACK handling."""

from __future__ import annotations

from contextlib import redirect_stderr
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from station.command_codec import (  # noqa: E402
    CommandAck,
    CommandSigner,
    decode_command_ack,
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


def c_array(header: str, name: str) -> bytes:
    match = re.search(
        rf"static const uint8_t {re.escape(name)}\[(\d+)\] = \{{(.*?)\n\}};",
        header,
        re.DOTALL,
    )
    require(match is not None, f"generated vector array is missing: {name}")
    value = bytes(
        int(token, 16)
        for token in re.findall(r"0x([0-9a-fA-F]{2})u", match.group(2))
    )
    require(
        len(value) == int(match.group(1)),
        f"generated vector size mismatch: {name}",
    )
    return value


def audit_firmware_vector() -> None:
    header = (ROOT / "firmware/generated/zs_command_vector.h").read_text(
        encoding="utf-8"
    )
    payload = c_array(header, "zs_command_vector_payload")
    signed_cbor = c_array(header, "zs_command_vector_signed_cbor")
    public_raw = c_array(header, "zs_command_vector_public_key")
    key_id = c_array(header, "zs_command_vector_key_id")
    signature = c_array(header, "zs_command_vector_signature")
    ack_payload = c_array(header, "zs_command_vector_ack")
    envelope = cbor2.loads(payload)
    require(cbor2.dumps(envelope, canonical=True) == payload,
            "firmware vector envelope is not canonical CBOR")
    require(
        cbor2.dumps({key: envelope[key] for key in range(9)}, canonical=True)
        == signed_cbor,
        "firmware vector signed bytes do not match its envelope",
    )
    require(envelope[8] == key_id and envelope[9] == signature,
            "firmware vector key/signature fields do not match")
    require(hashlib.sha256(public_raw).digest()[:8] == key_id,
            "firmware vector key ID is not bound to its public key")
    Ed25519PublicKey.from_public_bytes(public_raw).verify(signature, signed_cbor)
    decoded = decode_signed_command(
        payload,
        {key_id: Ed25519PublicKey.from_public_bytes(public_raw)},
        now_us=1_500_000,
    )
    require(
        decoded.station_id == 17
        and decoded.payload
        == {
            "event_id": 42,
            "segment": "both",
            "start_offset_ms": None,
            "duration_ms": None,
        },
        "firmware vector semantic payload mismatch",
    )
    ack = decode_command_ack(ack_payload)
    require(
        ack
        == CommandAck(
            station_id=17,
            command_id="12345678-1234-5678-1234-567812345678",
            result_code=0,
            completed_time_us=1_750_000,
            detail_code=0,
        ),
        "firmware ACK vector semantic payload mismatch",
    )


def audit_firmware_bg95_runtime() -> None:
    compiler = shutil.which("cc") or shutil.which("gcc")
    require(compiler is not None, "host C compiler is unavailable")
    tests = (
        (
            "zs_bg95_command_transport_tests",
            (
                "firmware/tests/test_bg95_command_transport.c",
                "firmware/src/zs_bg95_command_transport.c",
                "firmware/src/zs_bg95_mqtt_binary.c",
                "firmware/src/zs_bg95.c",
                "firmware/src/zs_mqtt_command_transport.c",
                "firmware/src/zs_command_channel.c",
                "firmware/src/zs_command_trust.c",
                "firmware/src/zs_command_journal.c",
                "firmware/src/zs_command.c",
                "firmware/src/zs_cbor.c",
                "firmware/src/zs_sha256.c",
            ),
        ),
        (
            "zs_bg95_mqtt_session_tests",
            (
                "firmware/tests/test_bg95_mqtt_session.c",
                "firmware/src/zs_bg95_mqtt_session.c",
                "firmware/src/zs_bg95_command_transport.c",
                "firmware/src/zs_bg95_event_receipt.c",
                "firmware/src/zs_bg95_event_uplink.c",
                "firmware/src/zs_bg95_mqtt_binary.c",
                "firmware/src/zs_bg95.c",
                "firmware/src/zs_mqtt_command_transport.c",
                "firmware/src/zs_command_channel.c",
                "firmware/src/zs_command_trust.c",
                "firmware/src/zs_command_journal.c",
                "firmware/src/zs_command.c",
                "firmware/src/zs_mqtt_event_transport.c",
                "firmware/src/zs_event_receipt.c",
                "firmware/src/zs_event_outbox.c",
                "firmware/src/zs_protocol.c",
                "firmware/src/zs_cbor.c",
                "firmware/src/zs_sha256.c",
            ),
        ),
        (
            "zs_nor_command_journal_tests",
            (
                "firmware/tests/test_nor_command_journal.c",
                "firmware/src/zs_nor_command_journal.c",
                "firmware/src/zs_nor.c",
                "firmware/src/zs_command_journal.c",
                "firmware/src/zs_command.c",
                "firmware/src/zs_cbor.c",
                "firmware/src/zs_sha256.c",
            ),
        ),
    )
    with tempfile.TemporaryDirectory(prefix="zs-command-fw-qg2-") as directory:
        for test_name, sources in tests:
            binary = Path(directory) / test_name
            result = subprocess.run(
                [
                    compiler,
                    "-std=gnu11",
                    "-Wall",
                    "-Wextra",
                    "-Wpedantic",
                    "-Werror",
                    "-O2",
                    "-UNDEBUG",
                    f"-I{ROOT / 'firmware/include'}",
                    f"-I{ROOT / 'firmware/generated'}",
                    *(str(ROOT / source) for source in sources),
                    "-lm",
                    "-o",
                    str(binary),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            require(result.returncode == 0,
                    f"{test_name} compile failed: {result.stderr}")
            result = subprocess.run(
                [str(binary)], check=False, capture_output=True, text=True
            )
            require(result.returncode == 0,
                    f"{test_name} failed: {result.stderr}")
            require(f"{test_name}: OK" in result.stdout,
                    f"{test_name} did not report success")


def main() -> int:
    audit_firmware_vector()
    audit_firmware_bg95_runtime()
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
        tampered[7][0] = 992
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
    print("scope: host runtime + signed vector + erase-isolated NOR journal + BG95 bounded raw-UART session/fixed ACK; target crypto/storage partition/USART-DMA/retain policy/hardware remain pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
