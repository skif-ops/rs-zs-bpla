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
    bg95_header = read("firmware/include/zs_bg95.h")
    bg95_source = read("firmware/src/zs_bg95.c")
    bg95_binary_header = read("firmware/include/zs_bg95_mqtt_binary.h")
    bg95_binary_source = read("firmware/src/zs_bg95_mqtt_binary.c")
    mqtt_header = read("firmware/include/zs_mqtt_event_transport.h")
    mqtt_source = read("firmware/src/zs_mqtt_event_transport.c")
    mqtt_test = read("firmware/tests/test_mqtt_event_transport.c")
    bg95_uplink_header = read("firmware/include/zs_bg95_event_uplink.h")
    bg95_uplink_source = read("firmware/src/zs_bg95_event_uplink.c")
    bg95_uplink_test = read("firmware/tests/test_bg95_event_uplink.c")
    bg95_receipt_header = read("firmware/include/zs_bg95_event_receipt.h")
    bg95_receipt_source = read("firmware/src/zs_bg95_event_receipt.c")
    bg95_receipt_test = read("firmware/tests/test_bg95_event_receipt.c")
    bg95_session_header = read("firmware/include/zs_bg95_mqtt_session.h")
    bg95_session_source = read("firmware/src/zs_bg95_mqtt_session.c")
    bg95_session_test = read("firmware/tests/test_bg95_mqtt_session.c")
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
        "zs_bg95_mqtt_uart_write_all",
        "topic_is_at_safe",
        "zs_mqtt_event_transport_prepare",
        "ZS_BG95_EVENT_UPLINK_OUTCOME_BROKER_ACK",
        "ZS_BG95_EVENT_UPLINK_OUTCOME_PROTOCOL_ERROR",
        "zs_bg95_mqtt_invalidate",
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

    for token in (
        "ZS_BG95_EVENT_RECEIPT_WAIT_SUBSCRIBE_RESULT",
        "ZS_BG95_EVENT_RECEIPT_SUBSCRIBED",
        "zs_bg95_event_receipt_subscribe",
        "zs_bg95_event_receipt_on_line",
        "zs_bg95_event_receipt_on_frame",
        "authenticated_server_only_nonretained_route",
        "does not expose MQTT retain",
    ):
        require(token in bg95_receipt_header,
                f"BG95 event receipt API missing: {token}")
    for token in (
        '"AT+QMTSUB=%u,%u,\\\""',
        "modem->mqtt_receive_length_enabled",
        "zs_bg95_mqtt_parse_receive_frame",
        "received.message_id == 0u ? 0u : ZS_MQTT_EVENT_QOS",
        "Retain is not present in +QMTRECV",
        "zs_mqtt_event_transport_handle_receipt",
        "zs_bg95_mqtt_invalidate",
    ):
        require(token in bg95_receipt_source,
                f"BG95 event receipt invariant missing: {token}")
    require("mqtt_receive_length_enabled" in bg95_header and
            'AT+QMTCFG=\\"recv/mode\\",%u,0,1' in bg95_source and
            "m->tls_step < 5u" in bg95_source,
            "BG95 pre-connect length-enabled receive configuration is missing")
    require(bg95_source.index('QMTCFG=\\"recv/mode\\"') <
            bg95_source.index('AT+QMTOPEN='),
            "BG95 receive mode can be configured after MQTT open")
    for token in (
        "zs_bg95_mqtt_parse_receive_frame",
        "reader_unsigned",
        "received->payload_size",
        "result == 0 || result == (int)size",
    ):
        require(token in bg95_binary_header + bg95_binary_source,
                f"shared BG95 binary framing invariant missing: {token}")
    require("src/zs_bg95_mqtt_binary.c" in cmake,
            "shared BG95 binary framing is not bound to CMake")
    for token in (
        "test_subscription_and_binary_receipt_lifecycle",
        "test_length_delimited_payload_preserves_control_bytes",
        "test_frame_topic_client_delivery_and_framing_guards",
        "test_setup_failures_and_policy_guard",
        "changed[17] = 0x00u",
        "changed[18] = 0x22u",
        "changed[19] = 0x0du",
        "changed[20] = 0x0au",
        "changed[21] = 0x1au",
    ):
        require(token in bg95_receipt_test,
                f"BG95 event receipt QG-2 case missing: {token}")
    require("src/zs_bg95_event_receipt.c" in cmake and
            "zs_bg95_event_receipt_tests" in cmake,
            "BG95 event receipt is not bound to CMake/CTest")
    for token in (
        "ZS_BG95_MQTT_SESSION_RX_BYTES 2304u",
        "ZS_BG95_MQTT_OWNER_RECEIPT_SUBSCRIBE",
        "ZS_BG95_MQTT_OWNER_EVENT_UPLINK",
        "ZS_BG95_MQTT_INPUT_RECEIPT",
        "zs_bg95_mqtt_session_feed_uart",
        "Target USART/DMA/ISR ownership",
    ):
        require(token in bg95_session_header,
                f"BG95 MQTT session interface missing: {token}")
    for token in (
        "qmt_frame_length",
        "zs_bg95_event_receipt_on_frame",
        "zs_bg95_event_uplink_on_prompt",
        "session->pending_command",
        "ZS_BG95_MQTT_OWNER_NONE",
    ):
        require(token in bg95_session_source,
                f"BG95 MQTT session routing guard missing: {token}")
    for token in (
        "test_serialized_fragmented_end_to_end_lifecycle",
        "test_binary_payload_and_protocol_guards",
        "test_disconnect_discards_ram_queue_and_resubscribes",
        "ZS_BG95_EVENT_RECEIPT_APPLIED",
        "ZS_EVENT_OUTBOX_EMPTY",
    ):
        require(token in bg95_session_test,
                f"BG95 MQTT session event case missing: {token}")
    require("src/zs_bg95_mqtt_session.c" in cmake and
            "zs_bg95_mqtt_session_tests" in cmake,
            "BG95 MQTT session is not bound to CMake/CTest")

    require("encode_event_receipt" in generator and "--check" in generator,
            "server/firmware receipt vector generator is incomplete")
    require("Generated by tools/generate_event_receipt_vector.py" in vector,
            "generated server/firmware receipt vector is absent")

    # Pilot identity (protocols/MQTT_TLS_ICD_v0_1_ADDENDUM_A_PILOT_IDENTITY.md): certificate CN = serial,
    # DIO-EVT-001..020 -> tenant pilot1 (station_id = number), 021..040 -> pilot2, B01 -> bench/901.
    pilot_units = {f"DIO-EVT-{i:03d}": ("pilot1" if i <= 20 else "pilot2", i) for i in range(1, 41)}
    pilot_units["DIO-EVT-B01"] = ("bench", 901)
    tenants = ("bench", "pilot1", "pilot2")
    require(set(sections) == {"bridge"} | set(pilot_units), "unexpected MQTT ACL identity")
    require(len(sections["bridge"]) == len(set(sections["bridge"])),
            "bridge MQTT ACL contains duplicate rights")
    require(set(sections["bridge"]) == {
        f"topic {op} zs/v1/{tenant}/+/{suffix}"
        for tenant in tenants
        for op, suffix in (("read", "up"), ("read", "status"), ("write", "down"), ("read", "ack"), ("write", "receipt"),
                               ("read", "audio"))                       # audio: addendum B
    }, "bridge MQTT ACL has missing or excessive rights")
    for serial, (tenant, station_id) in pilot_units.items():
        rights = sections[serial]
        require(len(rights) == len(set(rights)),
                f"station {serial} MQTT ACL contains duplicate rights")
        require(set(rights) == {
            f"topic write zs/v1/{tenant}/{station_id}/up",
            f"topic write zs/v1/{tenant}/{station_id}/status",
            f"topic read zs/v1/{tenant}/{station_id}/down",
            f"topic write zs/v1/{tenant}/{station_id}/ack",
            f"topic read zs/v1/{tenant}/{station_id}/receipt",
            f"topic write zs/v1/{tenant}/{station_id}/audio",
        }, f"station {serial} MQTT ACL has missing or excessive rights")

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
        "event_application_receipt: PORTABLE_SERVER_FIRMWARE_BG95_SESSION_ROUTED_QG1_QG2_PASS_TARGET_USART_DMA_RETAIN_POLICY_AND_HARDWARE_PENDING"
        in target,
        "target status overclaims or omits portable receipt evidence",
    )
    require(
        "mqtt_uart_session_binding: PORTABLE_BOUNDED_RAW_UART_FRAMER_SINGLE_TX_OWNER_QG1_QG2_PASS_TARGET_USART_DMA_ISR_CACHE_AND_MODEM_BLOCKER"
        in target and
        "event_receipt_mqtt_binding: PORTABLE_LENGTH_ENABLED_BINARY_QMTRECV_SESSION_ROUTED_QG1_QG2_PASS_TARGET_USART_DMA_RETAIN_POLICY_AND_HARDWARE_BLOCKER"
        in target,
            "target receipt MQTT binding blocker is not explicit")
    require(
        "event_bg95_receipt_binding: PORTABLE_LENGTH_ENABLED_BINARY_QMTRECV_SESSION_ROUTED_QG1_QG2_PASS_TARGET_USART_DMA_RETAIN_POLICY_AND_HARDWARE_PENDING"
        in target,
        "target status overclaims or omits BG95 event receipt evidence",
    )
    require(
        "event_mqtt_uplink_transport: PORTABLE_EXACT_TOPIC_RETRY_RECEIPT_QG1_QG2_PASS_BG95_SESSION_SERIALIZED_HOST_BINDING_TARGET_PENDING"
        in target,
        "target status overclaims or omits portable event MQTT evidence",
    )
    require(
        "event_bg95_uplink_binding: PORTABLE_FIXED_LENGTH_BINARY_QMTPUB_SESSION_SERIALIZED_QG1_QG2_PASS_TARGET_USART_DMA_AND_HARDWARE_PENDING"
        in target,
        "target status overclaims or omits BG95 event uplink evidence",
    )
    require(
        "event_mqtt_uplink_binding: PORTABLE_FIXED_LENGTH_BINARY_QMTPUB_SESSION_SERIALIZED_QG1_QG2_PASS_TARGET_USART_DMA_AND_HARDWARE_BLOCKER"
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
    print("scope: canonical receipt + fixed-length uplink + bounded raw-UART BG95 session routing; target USART-DMA/retain policy/storage remain pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
