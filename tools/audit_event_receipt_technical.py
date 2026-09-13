#!/usr/bin/env python3
"""QG-2 independent runtime audit of MQTT event application receipts."""

from __future__ import annotations

from contextlib import redirect_stderr
import hashlib
import io
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import cbor2


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from station.event_receipt_codec import (  # noqa: E402
    EventReceipt,
    decode_event_receipt,
    encode_event_receipt,
)
from station.mqtt_bridge import handle_message  # noqa: E402
from station.service import StationFusionService  # noqa: E402
from station.store import EventStore  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def detection_payload(*, seq_no: int = 5, event_id: int = 42) -> bytes:
    return cbor2.dumps(
        {
            0: 4,
            1: 2,
            2: 17,
            3: seq_no,
            4: 9,
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


class CaptureClient:
    def __init__(self, publish_rc: int = 0):
        self.publish_rc = publish_rc
        self.actions: list[tuple] = []

    def publish(self, topic, payload, qos, retain):
        self.actions.append(("publish", topic, payload, qos, retain))
        return SimpleNamespace(rc=self.publish_rc)

    def ack(self, mid, qos):
        self.actions.append(("mqtt_ack", mid, qos))


class CountingFusion:
    def __init__(self, store: EventStore):
        self.service = StationFusionService(store)
        self.calls = 0

    def ingest(self, detection):
        self.calls += 1
        return self.service.ingest(detection)


def message(payload: bytes, mid: int = 1):
    return SimpleNamespace(
        topic="zs/v1/evt/17/up",
        payload=payload,
        mid=mid,
        qos=1,
        retain=False,
    )


def c_array(header: str, name: str) -> bytes:
    match = re.search(
        rf"static const uint8_t {re.escape(name)}\[(\d+)\] = \{{(.*?)\n\}};",
        header,
        re.DOTALL,
    )
    require(match is not None, f"generated receipt vector array missing: {name}")
    value = bytes(
        int(token, 16)
        for token in re.findall(r"0x([0-9a-fA-F]{2})u", match.group(2))
    )
    require(len(value) == int(match.group(1)), f"receipt vector size mismatch: {name}")
    return value


def audit_vector() -> None:
    header = (ROOT / "firmware/generated/zs_event_receipt_vector.h").read_text(
        encoding="utf-8"
    )
    event_payload = c_array(header, "zs_event_receipt_vector_event_payload")
    digest = c_array(header, "zs_event_receipt_vector_payload_sha256")
    receipt_payload = c_array(header, "zs_event_receipt_vector_payload")
    require(event_payload == detection_payload(), "firmware event vector payload drift")
    require(hashlib.sha256(event_payload).digest() == digest,
            "firmware event vector SHA-256 mismatch")
    require(
        receipt_payload == encode_event_receipt(EventReceipt(17, 9, 5, 42, digest)),
        "firmware receipt vector differs from server encoder",
    )
    require(
        decode_event_receipt(receipt_payload) == EventReceipt(17, 9, 5, 42, digest),
        "firmware receipt vector semantic mismatch",
    )


def audit_firmware_runtime() -> None:
    compiler = shutil.which("cc") or shutil.which("gcc")
    require(compiler is not None, "host C compiler is unavailable")
    tests = (
        (
            "zs_mqtt_event_transport_tests",
            (
                "firmware/tests/test_mqtt_event_transport.c",
                "firmware/src/zs_mqtt_event_transport.c",
                "firmware/src/zs_event_receipt.c",
                "firmware/src/zs_event_outbox.c",
                "firmware/src/zs_protocol.c",
                "firmware/src/zs_cbor.c",
                "firmware/src/zs_sha256.c",
            ),
        ),
        (
            "zs_nor_event_outbox_tests",
            (
                "firmware/tests/test_nor_event_outbox.c",
                "firmware/src/zs_nor_event_outbox.c",
                "firmware/src/zs_nor.c",
                "firmware/src/zs_event_outbox.c",
                "firmware/src/zs_protocol.c",
                "firmware/src/zs_cbor.c",
                "firmware/src/zs_sha256.c",
            ),
        ),
        (
            "zs_nor_storage_layout_tests",
            (
                "firmware/tests/test_nor_storage_layout.c",
                "firmware/src/zs_nor_storage_layout.c",
                "firmware/src/zs_nor_archive.c",
                "firmware/src/zs_nor_command_journal.c",
                "firmware/src/zs_nor_event_outbox.c",
                "firmware/src/zs_nor.c",
                "firmware/src/zs_archive.c",
                "firmware/src/zs_command_journal.c",
                "firmware/src/zs_command.c",
                "firmware/src/zs_event_outbox.c",
                "firmware/src/zs_protocol.c",
                "firmware/src/zs_cbor.c",
                "firmware/src/zs_sha256.c",
            ),
        ),
        (
            "zs_bg95_event_uplink_tests",
            (
                "firmware/tests/test_bg95_event_uplink.c",
                "firmware/src/zs_bg95_event_uplink.c",
                "firmware/src/zs_bg95_mqtt_binary.c",
                "firmware/src/zs_bg95.c",
                "firmware/src/zs_mqtt_event_transport.c",
                "firmware/src/zs_event_receipt.c",
                "firmware/src/zs_event_outbox.c",
                "firmware/src/zs_protocol.c",
                "firmware/src/zs_cbor.c",
                "firmware/src/zs_sha256.c",
            ),
        ),
        (
            "zs_bg95_event_receipt_tests",
            (
                "firmware/tests/test_bg95_event_receipt.c",
                "firmware/src/zs_bg95_event_receipt.c",
                "firmware/src/zs_bg95_mqtt_binary.c",
                "firmware/src/zs_bg95.c",
                "firmware/src/zs_mqtt_event_transport.c",
                "firmware/src/zs_event_receipt.c",
                "firmware/src/zs_event_outbox.c",
                "firmware/src/zs_protocol.c",
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
    )
    with tempfile.TemporaryDirectory(prefix="zs-event-fw-qg2-") as directory:
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
                    f"firmware test compile failed ({test_name}): {result.stderr}")
            result = subprocess.run(
                [str(binary)], check=False, capture_output=True, text=True
            )
            require(result.returncode == 0,
                    f"firmware test failed ({test_name}): {result.stderr}")
            require(f"{test_name}: OK" in result.stdout,
                    f"firmware test did not report success: {test_name}")


def main() -> int:
    audit_vector()
    audit_firmware_runtime()
    with tempfile.TemporaryDirectory(prefix="zs-receipt-qg2-") as directory:
        store = EventStore(Path(directory) / "events.sqlite3")
        fusion = CountingFusion(store)
        payload = detection_payload()

        first = CaptureClient()
        require(
            handle_message(
                first,
                message(payload, 11),
                "evt",
                True,
                event_store=store,
                fusion_service=fusion,
            ),
            "first detection processing failed",
        )
        require([action[0] for action in first.actions] == ["publish", "mqtt_ack"],
                "receipt was not queued before broker ACK")
        _, topic, encoded, qos, retain = first.actions[0]
        require(topic == "zs/v1/evt/17/receipt", "receipt topic mismatch")
        require(qos == 1 and retain is False, "receipt QoS/retain mismatch")
        require(
            decode_event_receipt(encoded)
            == EventReceipt(17, 9, 5, 42, hashlib.sha256(payload).digest()),
            "receipt is not bound to exact detection bytes",
        )

        duplicate = CaptureClient()
        require(
            handle_message(
                duplicate,
                message(payload, 12),
                "evt",
                True,
                event_store=store,
                fusion_service=fusion,
            ),
            "exact duplicate did not receive idempotent receipt",
        )
        require(fusion.calls == 1, "exact duplicate repeated fusion side effects")

        conflict = CaptureClient()
        with redirect_stderr(io.StringIO()):
            accepted = handle_message(
                conflict,
                message(detection_payload(seq_no=6), 13),
                "evt",
                True,
                event_store=store,
                fusion_service=fusion,
            )
        require(not accepted, "conflicting event identity was accepted")
        require([action[0] for action in conflict.actions] == ["mqtt_ack"],
                "conflicting event received a receipt or remained poison-pending")

        fail_payload = detection_payload(event_id=43)
        failed_publish = CaptureClient(publish_rc=4)
        with redirect_stderr(io.StringIO()):
            accepted = handle_message(
                failed_publish,
                message(fail_payload, 14),
                "evt",
                True,
                event_store=store,
                fusion_service=fusion,
            )
        require(not accepted, "failed receipt publication incorrectly ACKed ingress")
        require([action[0] for action in failed_publish.actions] == ["publish"],
                "failed receipt publication reached broker ACK")
        retry = CaptureClient()
        require(
            handle_message(
                retry,
                message(fail_payload, 15),
                "evt",
                True,
                event_store=store,
                fusion_service=fusion,
            ),
            "processed event could not republish its receipt",
        )
        require(fusion.calls == 2, "receipt retry repeated fusion side effects")

        max_payload = detection_payload(event_id=0xFFFFFFFFFFFFFFFF)
        maximum = CaptureClient()
        require(
            handle_message(
                maximum,
                message(max_payload, 16),
                "evt",
                True,
                event_store=store,
                fusion_service=fusion,
            ),
            "full uint64 event ID was not processed",
        )
        receipt = decode_event_receipt(maximum.actions[0][2])
        require(receipt.event_id == 0xFFFFFFFFFFFFFFFF,
                "full uint64 event ID was truncated")

    print("Event application receipt QG-2 independent runtime audit: PASS")
    print("- server runtime plus bounded raw-UART BG95 session, fixed-length uplink, binary receipt, erase-isolated NOR lifecycle and shared non-overlap binding verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
