#!/usr/bin/env python3
"""QG-1 traceability check for durable MQTT event application receipts."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def acl_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("user "):
            current = line.split(maxsplit=1)[1]
            require(current not in sections, f"duplicate MQTT ACL user: {current}")
            sections[current] = []
            continue
        require(current is not None, "MQTT ACL topic precedes user")
        sections[current].append(line)
    return sections


def main() -> int:
    server_codec = read("server/station/event_receipt_codec.py")
    bridge = read("server/station/mqtt_bridge.py")
    store = read("server/station/store.py")
    server_test = read("server/tests/test_event_receipts.py")
    firmware_header = read("firmware/include/zs_event_receipt.h")
    firmware_source = read("firmware/src/zs_event_receipt.c")
    firmware_test = read("firmware/tests/test_event_receipt.c")
    mqtt_header = read("firmware/include/zs_mqtt_event_transport.h")
    mqtt_source = read("firmware/src/zs_mqtt_event_transport.c")
    mqtt_test = read("firmware/tests/test_mqtt_event_transport.c")
    bg95_uplink_header = read("firmware/include/zs_bg95_event_uplink.h")
    bg95_uplink_source = read("firmware/src/zs_bg95_event_uplink.c")
    bg95_uplink_test = read("firmware/tests/test_bg95_event_uplink.c")
    generator = read("tools/generate_event_receipt_vector.py")
    vector = read("firmware/generated/zs_event_receipt_vector.h")
    cmake = read("firmware/CMakeLists.txt")
    ci = read(".github/workflows/ci.yml")
    icd = read("protocols/MQTT_TLS_ICD_v0_1.md")
    requirements = read("docs/REQUIREMENTS_TRACEABILITY.csv")
    target = read("firmware/targets/evt_pre_20/target_status.yaml")
    sections = acl_sections(read("server/deploy/mosquitto/station_acl.conf"))

    for token in (
        "EVENT_RECEIPT_SCHEMA = 1",
        "EVENT_RECEIPT_MESSAGE_TYPE = 6",
        "MAX_EVENT_RECEIPT_BYTES = 128",
        "canonical=True",
        "any(type(key) is not int for key in obj)",
        "payload_sha256",
    ):
        require(token in server_codec, f"server receipt codec contract missing: {token}")

    for token in (
        "mqtt_detection_ingress",
        "wire_sha256 BLOB NOT NULL",
        "processed INTEGER NOT NULL DEFAULT 0",
        "begin_mqtt_detection",
        "complete_mqtt_detection",
        "event_id.to_bytes(8,'big')",
    ):
        require(token in store, f"durable detection-ingress state missing: {token}")

    handle = bridge[bridge.index("def handle_message(") : bridge.index("def main(")]
    for token in (
        "hashlib.sha256(payload).digest()",
        "begin_mqtt_detection",
        "complete_mqtt_detection",
        "build_event_receipt",
        'f"zs/v1/{tenant}/{topic_station_id}/receipt"',
    ):
        require(token in bridge, f"server receipt path missing: {token}")
    require(
        'message.qos != 1 or getattr(message, "retain", False)' in handle,
        "server does not reject non-QoS-1 or retained station delivery",
    )
    require("qos=1" in handle and "retain=False" in handle,
            "server receipt publication is not QoS 1 / non-retained")
    require(
        handle.index("client.publish(") < handle.index("client.ack(message.mid, message.qos)"),
        "broker ACK can precede event receipt publication",
    )

    for token in (
        "test_receipt_is_published_before_broker_ack_and_duplicate_is_idempotent",
        "test_conflicting_event_id_is_discarded_without_receipt",
        "test_receipt_publish_failure_retries_without_reprocessing",
        "test_interrupted_processing_resumes_before_receipt",
        "test_non_qos1_or_retained_detection_is_rejected_before_storage",
        "test_receipt_supports_full_uint64_event_id",
    ):
        require(token in server_test, f"server receipt QG-2 case missing: {token}")

    for token in (
        "ZS_EVENT_RECEIPT_MAX_BYTES 128u",
        "ZS_EVENT_RECEIPT_TOPIC_MAX_BYTES 64u",
        "zs_event_receipt_decode",
        "zs_event_receipt_transport_init",
        "zs_event_receipt_transport_handle",
    ):
        require(token in firmware_header, f"firmware receipt API missing: {token}")
    for token in (
        "byte != 0xa7u",
        "receipt.boot_id != item.boot_id",
        "memcmp(receipt.payload_sha256, item.payload_sha256",
        "qos != ZS_EVENT_RECEIPT_QOS || retained",
        "zs_event_outbox_mark_application_acked",
        "zs_event_outbox_lookup",
    ):
        require(token in firmware_source, f"firmware receipt guard missing: {token}")
    for token in (
        "test_server_vector_applies_after_exact_match",
        "test_topic_delivery_and_receipt_rejections",
        "test_torn_ack_marker_remains_pending",
        "ZS_EVENT_RECEIPT_ALREADY_APPLIED",
    ):
        require(token in firmware_test, f"firmware receipt QG-2 case missing: {token}")
    require("src/zs_event_receipt.c" in cmake and "zs_event_receipt_tests" in cmake,
            "firmware receipt implementation is not bound to CMake/CTest")

    for token in (
        "ZS_MQTT_EVENT_TENANT_MAX_BYTES 32u",
        "ZS_MQTT_EVENT_TOPIC_MAX_BYTES 64u",
        "zs_mqtt_event_transport_init",
        "zs_mqtt_event_transport_prepare",
        "zs_mqtt_event_transport_handle_receipt",
    ):
        require(token in mqtt_header, f"firmware event MQTT API missing: {token}")
    for token in (
        "zs_event_outbox_peek",
        "zs_event_outbox_note_attempt",
        "publication->topic = transport->up_topic",
        "publication->qos = ZS_MQTT_EVENT_QOS",
        "zs_event_receipt_transport_handle",
    ):
        require(token in mqtt_source, f"firmware event MQTT stage missing: {token}")
    require(
        mqtt_source.index("zs_event_outbox_note_attempt")
        < mqtt_source.index("publication->payload ="),
        "event payload can be exposed before durable attempt accounting",
    )
    for token in (
        "test_retry_then_exact_receipt_lifecycle",
        "test_queued_receipt_applies_after_transport_restart",
        "test_receipt_rejection_and_attempt_storage_failure",
        "test_retry_limit_station_and_argument_guards",
        "MQTT PUBACK is deliberately a no-op",
    ):
        require(token in mqtt_test, f"firmware event MQTT QG-2 case missing: {token}")
    require("src/zs_mqtt_event_transport.c" in cmake and
            "zs_mqtt_event_transport_tests" in cmake,
            "firmware event MQTT transport is not bound to CMake/CTest")

    for token in (
        "ZS_BG95_EVENT_UPLINK_WAIT_PROMPT",
        "ZS_BG95_EVENT_UPLINK_WAIT_RESULT",
        "ZS_BG95_EVENT_UPLINK_OUTCOME_BROKER_ACK",
        "zs_bg95_event_uplink_start",
        "zs_bg95_event_uplink_on_prompt",
        "zs_bg95_event_uplink_on_line",
    ):
        require(token in bg95_uplink_header,
                f"BG95 event uplink API missing: {token}")
    for token in (
        '"AT+QMTPUB=%u,%u,1,0,\\\""',
        "uplink->publication.payload_size",
        "uart_write_all(uplink->modem, uplink->publication.payload",
        "topic_is_at_safe",
        "invalidate_modem_transport",
        "zs_mqtt_event_transport_prepare",
        "ZS_BG95_EVENT_UPLINK_OUTCOME_BROKER_ACK",
        "ZS_BG95_EVENT_UPLINK_OUTCOME_PROTOCOL_ERROR",
    ):
        require(token in bg95_uplink_source,
                f"BG95 event uplink invariant missing: {token}")
    for token in (
        "test_fixed_length_binary_publish_and_broker_ack",
        "test_busy_offline_timeout_and_protocol_guards",
        "test_fixed_length_preserves_at_control_bytes",
        "test_uart_failures_preserve_pending_event",
        "Broker ACK is not the server application receipt",
        "memchr(zs_event_receipt_vector_event_payload, 0",
        "memchr(zs_event_receipt_vector_event_payload, 0x1a",
    ):
        require(token in bg95_uplink_test,
                f"BG95 event uplink QG-2 case missing: {token}")
    require("src/zs_bg95_event_uplink.c" in cmake and
            "zs_bg95_event_uplink_tests" in cmake,
            "BG95 event uplink is not bound to CMake/CTest")

    require("encode_event_receipt" in generator and "--check" in generator,
            "server/firmware receipt vector generator is incomplete")
    require("Generated by tools/generate_event_receipt_vector.py" in vector,
            "generated server/firmware receipt vector is absent")

    require(set(sections) == {"bridge"} | {f"station{i:02d}" for i in range(1, 21)},
            "unexpected MQTT ACL identity")
    require(len(sections["bridge"]) == len(set(sections["bridge"])),
            "bridge MQTT ACL contains duplicate rights")
    require(set(sections["bridge"]) == {
        "topic read zs/v1/evt/+/up",
        "topic read zs/v1/evt/+/status",
        "topic write zs/v1/evt/+/down",
        "topic read zs/v1/evt/+/ack",
        "topic write zs/v1/evt/+/receipt",
    }, "bridge MQTT ACL has missing or excessive rights")
    for station_id in range(1, 21):
        rights = sections[f"station{station_id:02d}"]
        require(len(rights) == len(set(rights)),
                f"station {station_id} MQTT ACL contains duplicate rights")
        require(set(rights) == {
            f"topic write zs/v1/evt/{station_id}/up",
            f"topic write zs/v1/evt/{station_id}/status",
            f"topic read zs/v1/evt/{station_id}/down",
            f"topic write zs/v1/evt/{station_id}/ack",
            f"topic read zs/v1/evt/{station_id}/receipt",
        }, f"station {station_id} MQTT ACL has missing or excessive rights")

    for token in (
        "### 2.3 Event application receipt schema 1",
        "payload_sha256",
        "MQTT mutual TLS",
        "receipt",
    ):
        require(token in icd, f"event receipt ICD detail missing: {token}")
    require("PARTIAL_PASS_HOST_OUTBOX_RECEIPT" in requirements,
            "REQ-CELL-003 does not report bounded receipt evidence")
    require(
        "event_application_receipt: PORTABLE_SERVER_FIRMWARE_QG1_QG2_PASS_BG95_BINDING_PENDING"
        in target,
        "target status overclaims or omits portable receipt evidence",
    )
    require("event_receipt_mqtt_binding: MISSING_BLOCKER" in target,
            "target receipt MQTT binding blocker is not explicit")
    require(
        "event_mqtt_uplink_transport: PORTABLE_EXACT_TOPIC_RETRY_RECEIPT_QG1_QG2_PASS_BG95_FIXED_LENGTH_UPLINK_BOUND_RECEIPT_PENDING"
        in target,
        "target status overclaims or omits portable event MQTT evidence",
    )
    require(
        "event_bg95_uplink_binding: PORTABLE_FIXED_LENGTH_BINARY_QMTPUB_QG1_QG2_PASS_TARGET_UART_ROUTING_PENDING"
        in target,
        "target status overclaims or omits BG95 event uplink evidence",
    )
    require(
        "event_mqtt_uplink_binding: PORTABLE_FIXED_LENGTH_BINARY_QMTPUB_QG1_QG2_PASS_TARGET_UART_ROUTING_AND_HARDWARE_BLOCKER"
        in target,
        "target event MQTT uplink binding blocker is not bounded",
    )
    require("validate_event_receipt_contract.py" in ci,
            "event receipt QG-1 is not bound to CI")
    require("audit_event_receipt_technical.py" in ci,
            "event receipt QG-2 is not bound to CI")
    require("generate_event_receipt_vector.py --check" in ci,
            "event receipt vector freshness is not bound to CI")

    print("Event application receipt QG-1: PASS")
    print("scope: canonical server/firmware receipt + fixed-length BG95 uplink; BG95 receipt and target storage remain pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
