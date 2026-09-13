#!/usr/bin/env python3
"""QG-1 traceability check for signed MQTT command transport."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    codec = read("server/station/command_codec.py")
    bridge = read("server/station/mqtt_bridge.py")
    store = read("server/station/store.py")
    router = read("server/station/router.py")
    acl = read("server/deploy/mosquitto/station_acl.conf")
    compose = read("server/deploy/compose.ubuntu.yml")
    windows_tls = read("server/deploy/compose.windows.tls.yml")
    ubuntu_start = read("server/deploy/scripts/start_ubuntu.sh")
    dockerignore = read("server/.dockerignore")
    gitignore = read(".gitignore")
    production_broker = read("server/deploy/mosquitto/mosquitto.production.conf.example")
    requirements = read("server/requirements.txt")
    lock = read("server/requirements.lock.txt")
    icd = read("protocols/MQTT_TLS_ICD_v0_1.md")
    firmware_contract = read("firmware/BG95_MQTT_TLS_CONTRACT_REV_A.md")
    firmware_header = read("firmware/include/zs_command.h")
    firmware_codec = read("firmware/src/zs_command.c")
    firmware_test = read("firmware/tests/test_command_transport.c")
    journal_header = read("firmware/include/zs_command_journal.h")
    journal_codec = read("firmware/src/zs_command_journal.c")
    journal_test = read("firmware/tests/test_command_journal.c")
    nor_journal_header = read("firmware/include/zs_nor_command_journal.h")
    nor_journal_codec = read("firmware/src/zs_nor_command_journal.c")
    nor_journal_test = read("firmware/tests/test_nor_command_journal.c")
    nor_layout_header = read("firmware/include/zs_nor_storage_layout.h")
    nor_layout_codec = read("firmware/src/zs_nor_storage_layout.c")
    nor_layout_test = read("firmware/tests/test_nor_storage_layout.c")
    core_nor_header = read("firmware/include/zs_nor.h")
    core_nor_codec = read("firmware/src/zs_nor.c")
    core_nor_test = read("firmware/tests/test_nor.c")
    trust_header = read("firmware/include/zs_command_trust.h")
    trust_codec = read("firmware/src/zs_command_trust.c")
    trust_test = read("firmware/tests/test_command_trust.c")
    channel_header = read("firmware/include/zs_command_channel.h")
    channel_codec = read("firmware/src/zs_command_channel.c")
    channel_test = read("firmware/tests/test_command_channel.c")
    transport_header = read("firmware/include/zs_mqtt_command_transport.h")
    transport_codec = read("firmware/src/zs_mqtt_command_transport.c")
    transport_test = read("firmware/tests/test_mqtt_command_transport.c")
    bg95_header = read("firmware/include/zs_bg95.h")
    bg95_binary_header = read("firmware/include/zs_bg95_mqtt_binary.h")
    bg95_binary_codec = read("firmware/src/zs_bg95_mqtt_binary.c")
    bg95_binding_header = read("firmware/include/zs_bg95_command_transport.h")
    bg95_binding_codec = read("firmware/src/zs_bg95_command_transport.c")
    bg95_binding_test = read("firmware/tests/test_bg95_command_transport.c")
    bg95_session_header = read("firmware/include/zs_bg95_mqtt_session.h")
    bg95_session_codec = read("firmware/src/zs_bg95_mqtt_session.c")
    bg95_session_test = read("firmware/tests/test_bg95_mqtt_session.c")
    cmake = read("firmware/CMakeLists.txt")
    vector_generator = read("tools/generate_mqtt_command_vector.py")
    vector_header = read("firmware/generated/zs_command_vector.h")
    target_status = read("firmware/targets/evt_pre_20/target_status.yaml")
    tests = read("server/tests/test_mqtt_commands.py") + read(
        "server/tests/test_command_codec.py"
    )
    ci = read(".github/workflows/ci.yml")

    for token in (
        "Ed25519PrivateKey",
        "canonical=True",
        "MAX_COMMAND_BYTES = 2048",
        "MAX_ACK_BYTES = 128",
        "MAX_COMMAND_TTL_US = 15 * 60 * 1_000_000",
        "COMMAND_MESSAGE_TYPE = 4",
        "ACK_MESSAGE_TYPE = 5",
    ):
        require(token in codec, f"command codec contract missing: {token}")
    require("if signer is None" in bridge, "missing fail-closed signing-key guard")
    require("qos=1" in bridge and "retain=False" in bridge,
            "downstream is not fixed to QoS 1 / retain false")
    require("+/ack" in bridge and "decode_command_ack" in bridge,
            "bridge does not subscribe and decode ACK")
    require("manual_ack_set(True)" in bridge and "client.ack(message.mid, message.qos)" in bridge,
            "inbound QoS acknowledgement is not controlled by durable processing")
    require("retry_after_us" in bridge and "due_commands" in bridge,
            "application-ACK retry loop is absent")
    require("station_mismatch" in bridge and "topic_station_id" in bridge,
            "topic/payload/store station binding is absent")
    require("TENANT_PATTERN" in bridge and "str(station_id) != parts[3]" in bridge,
            "tenant wildcard or canonical uint32 topic guard is absent")

    for token in (
        "expires_us",
        "last_publish_us",
        "publish_count",
        "ack_result",
        "completed_us",
    ):
        require(token in store, f"durable command state missing: {token}")
    require("ack_command(station_id" in router,
            "bench HTTP ACK is not bound to station_id")
    require("cryptography>=46.0.0,<47.0.0" in requirements,
            "reviewed Ed25519 dependency constraint missing")
    require("cryptography==" in lock,
            "Ed25519 dependency missing from hashed runtime lock")

    require("ZS_COMMAND_SIGNING_KEY: /run/tls/command-signing.key" in compose,
            "production compose does not require command signing material")
    require("ZS_COMMAND_SIGNING_KEY: /run/tls/command-signing.key" in windows_tls,
            "Windows TLS compose does not require command signing material")
    require("stat -c '%a' tls/command-signing.key" in ubuntu_start and '"600"' in ubuntu_start,
            "Ubuntu launcher does not enforce owner-only signing-key mode")
    require("deploy/tls/" in dockerignore and "**/*.key" in dockerignore,
            "Docker build context can include private deployment keys")
    require("server/deploy/tls/" in gitignore,
            "generated command key material is not excluded from Git")
    require("require_certificate true" in production_broker and
            "use_identity_as_username true" in production_broker and
            "acl_file /mosquitto/config/station_acl.conf" in production_broker,
            "production broker example is not fail-closed mTLS/ACL")

    sections = {}
    current = None
    for raw_line in acl.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("user "):
            current = line.removeprefix("user ")
            require(current not in sections, f"duplicate ACL user: {current}")
            sections[current] = set()
        else:
            require(current is not None, "ACL rule appears before a user")
            sections[current].add(line)
    require(sections.get("bridge") == {
        "topic read zs/v1/evt/+/up",
        "topic read zs/v1/evt/+/status",
        "topic write zs/v1/evt/+/down",
        "topic read zs/v1/evt/+/ack",
        "topic write zs/v1/evt/+/receipt",
    }, "bridge ACL has missing or excessive rights")
    for station_id in range(1, 21):
        user = f"station{station_id:02d}"
        require(sections.get(user) == {
            f"topic write zs/v1/evt/{station_id}/up",
            f"topic write zs/v1/evt/{station_id}/status",
            f"topic read zs/v1/evt/{station_id}/down",
            f"topic write zs/v1/evt/{station_id}/ack",
            f"topic read zs/v1/evt/{station_id}/receipt",
        }, f"station {station_id} ACL has missing or excessive rights")
    require(set(sections) == {"bridge"} | {f"station{i:02d}" for i in range(1, 21)},
            "unexpected MQTT ACL identity")

    for token in (
        "ZS_COMMAND_MAX_BYTES 2048u",
        "ZS_COMMAND_MAX_TTL_US UINT64_C(900000000)",
        "zs_command_signature_verify_fn",
        "zs_command_dedup_lookup_fn",
        "zs_command_decode_verify",
        "zs_command_encode_ack",
    ):
        require(token in firmware_header, f"firmware command API missing: {token}")
    for token in (
        "workspace[0] = 0xa9u",
        "memset(workspace, 0, signed_size)",
        "ZS_COMMAND_STATUS_TIME_UNTRUSTED",
        "ZS_COMMAND_STATUS_STATION_MISMATCH",
        "ZS_COMMAND_STATUS_SIGNATURE_REJECTED",
        "ZS_COMMAND_STATUS_DEDUP_STORAGE_ERROR",
    ):
        require(token in firmware_codec, f"firmware fail-closed path missing: {token}")
    for token in (
        "test_server_generated_ed25519_vector",
        "ZS_COMMAND_STATUS_DUPLICATE",
        "ZS_COMMAND_STATUS_INVALID_CBOR",
        "ZS_COMMAND_STATUS_INVALID_TTL",
        "zs_command_encode_ack",
    ):
        require(token in firmware_test, f"firmware command QG-2 case missing: {token}")
    require("TEST_PRIVATE_SEED" in vector_generator and
            "private_key.public_key().verify" in vector_generator and
            "--check" in vector_generator,
            "server/firmware deterministic Ed25519 vector generator is incomplete")
    require("Generated by tools/generate_mqtt_command_vector.py" in vector_header and
            "zs_command_vector_ack" in vector_header,
            "generated server/firmware command vector is absent")
    for token in (
        "zs_command_journal_dedup_lookup",
        "zs_command_journal_accept",
        "zs_command_journal_complete",
        "zs_command_journal_encode_ack",
    ):
        require(token in journal_header, f"durable command journal API missing: {token}")
    for token in (
        "JOURNAL_COMMIT_OFFSET",
        "ZS_COMMAND_JOURNAL_STATE_ACCEPTED",
        "ZS_COMMAND_JOURNAL_STATE_COMPLETED",
        "ZS_COMMAND_JOURNAL_CORRUPT",
        "ZS_COMMAND_JOURNAL_CONFLICT",
    ):
        require(token in journal_codec, f"durable journal guard missing: {token}")
    for token in (
        "test_power_loss_recovery",
        "ZS_COMMAND_JOURNAL_FULL",
        "ZS_COMMAND_DEDUP_ERROR",
        "zs_command_vector_ack",
    ):
        require(token in journal_test, f"durable journal QG-2 case missing: {token}")
    for token in (
        "zs_nor_command_journal_adapter_t",
        "zs_nor_command_journal_io_init",
        "one whole erase block",
        "Partition selection and",
    ):
        require(token in nor_journal_header,
                f"command journal NOR adapter API missing: {token}")
    for token in (
        "adapter->slot_count < 2u",
        "geometry.erase_bytes < ZS_COMMAND_JOURNAL_SLOT_BYTES",
        "slot_range",
        "zs_nor_erase",
        "zs_nor_program",
    ):
        require(token in nor_journal_codec,
                f"command journal NOR guard missing: {token}")
    for token in (
        "test_erase_isolation_roundtrip_and_restart",
        "test_torn_commit_is_reusable_without_neighbour_erase",
        "test_partition_and_callback_guards",
        "ZS_COMMAND_JOURNAL_STATE_COMPLETED",
        "fail_program_call = 2u",
    ):
        require(token in nor_journal_test,
                f"command journal NOR QG-2 case missing: {token}")
    for token in (
        "src/zs_nor_command_journal.c",
        "zs_nor_command_journal_tests",
        "nor_command_journal",
    ):
        require(token in cmake,
                f"command journal NOR adapter is absent from CMake: {token}")
    for token in (
        "command_slot_count",
        "command_base_address",
        "command_partition_bytes",
        "outbox_base_address",
        "zs_nor_command_journal_adapter_t command_adapter",
        "zs_nor_probe_info_t nor_probe",
        "zs_nor_storage_bind",
    ):
        require(token in nor_layout_header,
                f"shared command-journal NOR layout API missing: {token}")
    for token in (
        "command_slot_count < 2u",
        "reserved_bytes = command_bytes + outbox_bytes",
        "zs_nor_probe_w25q512jv(nor, &bindings->nor_probe)",
        "out->command_base_address = archive_bytes",
        "out->outbox_base_address = archive_bytes + (uint32_t)command_bytes",
        "zs_nor_command_journal_io_init",
        "out_archive_storage->size_bytes = bindings->layout.command_base_address",
    ):
        require(token in nor_layout_codec,
                f"shared command-journal NOR layout guard missing: {token}")
    for token in (
        "test_slot_counts_remain_target_inputs",
        "test_shared_binding_caps_archive_and_separates_tail",
        "test_shared_binding_failure_is_atomic",
        "command_io.ctx == &bindings.command_adapter",
        "bindings.nor_probe.quad_enabled",
        "bindings.layout.outbox_base_address",
    ):
        require(token in nor_layout_test,
                f"shared command-journal NOR layout QG-2 case missing: {token}")
    require("src/zs_nor_storage_layout.c" in cmake and
            "zs_nor_storage_layout_tests" in cmake,
            "shared command-journal NOR layout is not bound to CMake/CTest")
    require("zs_nor_probe_w25q512jv" in core_nor_header and
            "ZS_NOR_OP_READ_SFDP 0x5au" in core_nor_codec and
            "test_w25q512_probe_fail_closed" in core_nor_test and
            "zs_nor_tests" in cmake,
            "command-journal exposure is not gated by exact NOR boot probe")
    for token in (
        "ZS_COMMAND_TRUST_MAX_KEYS 4u",
        "zs_ed25519_verify_backend_fn",
        "zs_command_trust_init",
        "zs_command_trust_verify",
    ):
        require(token in trust_header, f"command trust-store API missing: {token}")
    for token in (
        "zs_sha256_digest",
        "enabled_count == 0u",
        "bytes_equal(key_id",
        "trust->backend",
    ):
        require(token in trust_codec, f"command trust-store guard missing: {token}")
    for token in (
        "test_enabled_key_and_backend_binding",
        "test_fail_closed_configuration",
        "test_decoder_integration",
        "zs_command_vector_public_key",
    ):
        require(token in trust_test, f"command trust-store QG-2 case missing: {token}")
    for token in (
        "zs_command_execute_fn",
        "ZS_COMMAND_CHANNEL_ACK_READY",
        "ZS_COMMAND_CHANNEL_EXECUTION_RETRY",
        "zs_command_channel_handle",
    ):
        require(token in channel_header, f"portable command channel API missing: {token}")
    for token in (
        "zs_command_decode_verify",
        "zs_command_journal_accept",
        "zs_command_journal_complete",
        "encode_durable_ack",
    ):
        require(token in channel_codec, f"portable command channel stage missing: {token}")
    for token in (
        "test_complete_then_duplicate_ack",
        "test_retry_and_reject_paths",
        "ZS_COMMAND_STATUS_DUPLICATE",
        "zs_command_vector_ack",
    ):
        require(token in channel_test, f"portable command channel QG-2 case missing: {token}")

    for token in (
        "ZS_MQTT_COMMAND_TENANT_MAX_BYTES 32u",
        "ZS_MQTT_COMMAND_TOPIC_MAX_BYTES 64u",
        "zs_mqtt_command_message_t",
        "zs_mqtt_command_transport_init",
        "zs_mqtt_command_transport_handle",
    ):
        require(token in transport_header, f"binary MQTT boundary API missing: {token}")
    for token in (
        "tenant_is_valid",
        "memcmp(message->topic",
        "message->qos != ZS_MQTT_COMMAND_QOS",
        "message->retained",
        "zs_command_channel_handle",
        "publication->payload_size = ack_size",
    ):
        require(token in transport_codec, f"binary MQTT boundary guard missing: {token}")
    for token in (
        "test_binary_down_to_ack",
        "test_topic_and_delivery_rejection",
        "test_result_mapping_without_ack",
        "test_tenant_and_argument_guards",
        "memchr(zs_command_vector_payload, 0",
        "ZS_MQTT_COMMAND_REJECTED_DELIVERY",
    ):
        require(token in transport_test, f"binary MQTT boundary QG-2 case missing: {token}")

    for token in (
        "zs_bg95_mqtt_uart_write_all",
        "zs_bg95_mqtt_parse_receive_frame",
        "zs_bg95_mqtt_parse_subscribe_result",
        "zs_bg95_mqtt_parse_publish_result",
    ):
        require(token in bg95_binary_header,
                f"shared BG95 binary interface missing: {token}")
    for token in (
        "+QMTRECV: ",
        "reader_unsigned",
        "received->payload_size",
        "result == 0 || result == (int)size",
        "mqtt_receive_length_enabled = false",
    ):
        require(token in bg95_binary_codec,
                f"shared BG95 binary guard missing: {token}")
    require("mqtt_receive_length_enabled" in bg95_header,
            "BG95 connection does not expose verified receive length mode")
    for token in (
        "ZS_BG95_COMMAND_TRANSPORT_WAIT_SUBSCRIBE_RESULT",
        "ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_PROMPT",
        "ZS_BG95_COMMAND_TRANSPORT_WAIT_ACK_RESULT",
        "zs_bg95_command_transport_subscribe",
        "zs_bg95_command_transport_on_frame",
        "zs_bg95_command_transport_on_prompt",
        "authenticated_server_only_nonretained_down_route",
        "does not expose MQTT retain",
    ):
        require(token in bg95_binding_header,
                f"BG95 command binding API missing: {token}")
    for token in (
        '"AT+QMTSUB=%u,%u,\\\""',
        '"AT+QMTPUB=%u,%u,1,0,\\\""',
        "binding->modem->mqtt_receive_length_enabled",
        "zs_bg95_mqtt_parse_receive_frame",
        "zs_mqtt_command_transport_handle",
        "binding->ack_publication.payload_size",
        "Retain is not present in +QMTRECV",
        "ZS_BG95_COMMAND_TRANSPORT_OUTCOME_ACK_BROKER_ACK",
    ):
        require(token in bg95_binding_codec,
                f"BG95 command binding invariant missing: {token}")
    require(bg95_binding_codec.index("zs_mqtt_command_transport_handle") <
            bg95_binding_codec.index("send_ack_command(binding)"),
            "BG95 ACK can be sent before durable command handling")
    for token in (
        "test_binary_down_to_fixed_length_durable_ack",
        "test_receive_routing_and_framing_guards",
        "test_policy_setup_and_ack_uart_failures",
        "Server retry after reconnect obtains durable ACK without re-execution",
        "ZS_COMMAND_STATUS_DUPLICATE",
        "memchr(zs_command_vector_payload, 0",
    ):
        require(token in bg95_binding_test,
                f"BG95 command binding QG-2 case missing: {token}")
    for token in (
        "src/zs_bg95_mqtt_binary.c",
        "src/zs_bg95_command_transport.c",
        "zs_bg95_command_transport_tests",
        "bg95_command_transport",
    ):
        require(token in cmake, f"BG95 command binding is absent from CMake: {token}")
    for token in (
        "ZS_BG95_MQTT_SESSION_RX_BYTES 2304u",
        "ZS_BG95_MQTT_OWNER_COMMAND_SUBSCRIBE",
        "ZS_BG95_MQTT_OWNER_RECEIPT_SUBSCRIBE",
        "ZS_BG95_MQTT_OWNER_EVENT_UPLINK",
        "ZS_BG95_MQTT_OWNER_COMMAND_ACK",
        "ZS_BG95_MQTT_INPUT_COMMAND_RETRY_REQUIRED",
        "zs_bg95_mqtt_session_feed_uart",
        "sole caller of the three child BG95 MQTT bindings",
        "Target USART/DMA/ISR ownership",
    ):
        require(token in bg95_session_header,
                f"BG95 MQTT session interface missing: {token}")
    for token in (
        "qmt_frame_length",
        "payload_size > ZS_BG95_MQTT_SESSION_RX_BYTES",
        "session->pending_command",
        "session->owner == ZS_BG95_MQTT_OWNER_NONE",
        "zs_bg95_command_transport_on_prompt",
        "zs_bg95_event_uplink_on_prompt",
        "zs_bg95_mqtt_invalidate",
    ):
        require(token in bg95_session_codec,
                f"BG95 MQTT session guard missing: {token}")
    for token in (
        "test_serialized_fragmented_end_to_end_lifecycle",
        "test_binary_payload_and_protocol_guards",
        "test_disconnect_discards_ram_queue_and_resubscribes",
        "ZS_BG95_MQTT_INPUT_COMMAND_QUEUED",
        "ZS_BG95_MQTT_INPUT_COMMAND_RETRY_REQUIRED",
        "binary_payload",
    ):
        require(token in bg95_session_test,
                f"BG95 MQTT session QG-2 case missing: {token}")
    for token in (
        "src/zs_bg95_mqtt_session.c",
        "zs_bg95_mqtt_session_tests",
        "bg95_mqtt_session",
    ):
        require(token in cmake, f"BG95 MQTT session is absent from CMake: {token}")
    require(
        "command_binary_mqtt_transport: PORTABLE_EXACT_TOPIC_PAYLOAD_LENGTH_QG1_QG2_PASS_BG95_SESSION_ROUTED_TARGET_PENDING"
        in target_status,
        "target status omits the portable BG95 command binding",
    )
    require(
        "mqtt_uart_session: PORTABLE_BOUNDED_RAW_UART_FRAMER_SINGLE_TX_OWNER_QG1_QG2_PASS_TARGET_USART_DMA_ISR_CACHE_AND_MODEM_PENDING"
        in target_status and
        "command_bg95_binding: PORTABLE_LENGTH_ENABLED_BINARY_QMTRECV_FIXED_LENGTH_ACK_SESSION_SERIALIZED_QG1_QG2_PASS_TARGET_USART_DMA_RETAIN_POLICY_AND_HARDWARE_PENDING"
        in target_status and
        "command_mqtt_binding: PORTABLE_BG95_SESSION_FRAMED_SERIALIZED_QG1_QG2_PASS_TARGET_USART_DMA_RETAIN_POLICY_AND_HARDWARE_BLOCKER"
        in target_status and
        "command_mqtt_subscription_ack_binding: PORTABLE_BG95_SESSION_FRAMED_SERIALIZED_QG1_QG2_PASS_TARGET_USART_DMA_RETAIN_POLICY_AND_HARDWARE_BLOCKER"
        in target_status,
        "target BG95 command blockers are not bounded",
    )
    require(
        "command_result_journal: PORTABLE_ATOMIC_QG1_QG2_PASS_NOR_ERASE_ISOLATED_SHARED_NONOVERLAP_BOUND_TARGET_SLOT_COUNT_ENDURANCE_PENDING"
        in target_status and
        "command_journal_nor_adapter: PORTABLE_ERASE_ISOLATED_SHARED_ARCHIVE_COMMAND_OUTBOX_NONOVERLAP_QG1_QG2_PASS_TARGET_SLOT_COUNT_ENDURANCE_PENDING"
        in target_status and
        "command_journal_flash_binding: PORTABLE_NOR_ERASE_ISOLATED_SHARED_NONOVERLAP_QG1_QG2_PASS_TARGET_SLOT_COUNT_OCTOSPI_ENDURANCE_BLOCKER"
        in target_status,
        "target command journal storage blocker is not bounded",
    )
    require("command_journal_slot_count: MISSING_BLOCKER" in target_status,
            "target command journal slot-count blocker is not explicit")
    require(
        "nor_boot_probe: PORTABLE_W25Q512JV_EXACT_JEDEC_SFDP_CAPACITY_QE_RESTORE_QG1_QG2_PASS_TARGET_OCTOSPI_AND_SAMPLE_PENDING"
        in target_status and
        "nor_octospi_binding: PORTABLE_W25Q512JV_PROBE_QG1_QG2_PASS_TARGET_OCTOSPI_AND_SAMPLE_BLOCKER"
        in target_status,
        "target exact NOR boot-probe blocker is not bounded",
    )

    require("PORTABLE_BG95_SESSION_FRAMED_SERIALIZED_QG_PASS; TARGET_CRYPTO_USART_DMA_RETAIN_POLICY_AND_HARDWARE_PENDING" in icd,
            "ICD does not report the bounded implementation status")
    require("The BG95 command binding" in firmware_contract and
            "target USART/DMA/ISR integration" in firmware_contract,
            "firmware target gap is not explicit")
    for token in ("tamper", "retry", "ownership", "duplicate"):
        require(token in tests, f"negative/robustness test missing: {token}")
    require("validate_mqtt_command_transport.py" in ci,
            "QG-1 is not bound to CI")
    require("audit_mqtt_command_transport_technical.py" in ci,
            "QG-2 is not bound to CI")
    require("generate_mqtt_command_vector.py --check" in ci,
            "server/firmware vector freshness is not bound to CI")
    require("zs_command_transport_tests" in cmake,
            "firmware command codec test is not bound to CTest")
    require("zs_command_journal_tests" in cmake,
            "firmware durable command journal test is not bound to CTest")
    require("zs_command_trust_tests" in cmake,
            "firmware command trust-store test is not bound to CTest")
    require("zs_command_channel_tests" in cmake,
            "portable command channel test is not bound to CTest")
    require("zs_mqtt_command_binding_tests" in cmake,
            "portable binary MQTT boundary test is not bound to CTest")

    print("MQTT signed command transport QG-1: PASS")
    print("scope: server + durable firmware/NOR adapter + exact W25Q512JV boot probe + shared archive/command/outbox non-overlap + BG95 bounded raw-UART session/ACK host path; target crypto/slot count/OCTOSPI/sample/USART-DMA/retain policy/hardware remain pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
