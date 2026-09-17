#!/usr/bin/env python3
"""QG-1 traceability check for the portable event store-and-forward outbox."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    header = read("firmware/include/zs_event_outbox.h")
    source = read("firmware/src/zs_event_outbox.c")
    test = read("firmware/tests/test_event_outbox.c")
    nor_header = read("firmware/include/zs_nor_event_outbox.h")
    nor_source = read("firmware/src/zs_nor_event_outbox.c")
    nor_test = read("firmware/tests/test_nor_event_outbox.c")
    core_nor_header = read("firmware/include/zs_nor.h")
    core_nor_source = read("firmware/src/zs_nor.c")
    core_nor_test = read("firmware/tests/test_nor.c")
    layout_header = read("firmware/include/zs_nor_storage_layout.h")
    layout_source = read("firmware/src/zs_nor_storage_layout.c")
    layout_test = read("firmware/tests/test_nor_storage_layout.c")
    cmake = read("firmware/CMakeLists.txt")
    ci = read(".github/workflows/ci.yml")
    icd = read("protocols/MQTT_TLS_ICD_v0_1.md")
    requirements = read("docs/REQUIREMENTS_TRACEABILITY.csv")
    target = read("firmware/targets/evt_pre_20/target_status.yaml")

    for token in (
        "ZS_EVENT_OUTBOX_PAYLOAD_MAX_BYTES 512u",
        "ZS_EVENT_OUTBOX_SLOT_BYTES 616u",
        "ZS_EVENT_OUTBOX_MAX_RETRIES 128u",
        "zs_event_outbox_event_t",
        "payload_sha256[ZS_SHA256_DIGEST_BYTES]",
        "zs_event_outbox_enqueue_detection",
        "zs_event_outbox_lookup",
        "zs_event_outbox_note_attempt",
        "zs_event_outbox_mark_application_acked",
    ):
        require(token in header, f"event outbox API missing: {token}")

    for token in (
        "OUTBOX_COMMIT_OFFSET",
        "OUTBOX_RETRY_BITMAP_OFFSET",
        "OUTBOX_DELIVERED_OFFSET",
        "zs_sha256_digest",
        "crc32(raw, OUTBOX_METADATA_CRC_OFFSET)",
        "ZS_EVENT_OUTBOX_ALREADY_PENDING",
        "ZS_EVENT_OUTBOX_CONFLICT",
        "decoded.item.priority > item->priority",
        "zs_protocol_encode_detection",
    ):
        require(token in source, f"event outbox invariant missing: {token}")
    require(
        source.index("OUTBOX_PAYLOAD_OFFSET + event->payload_size")
        < source.index("OUTBOX_COMMIT_OFFSET, raw, 4u"),
        "event outbox commit marker is not written last",
    )
    require(
        "get_u32(&raw[OUTBOX_DELIVERED_OFFSET]) == OUTBOX_DELIVERED" in source,
        "event delivery state is not read from a separate atomic marker",
    )

    for token in (
        "test_priority_fifo_attempt_and_reclaim",
        "test_duplicate_conflict_and_full",
        "test_power_loss_is_at_least_once",
        "test_corruption_io_retry_limit_and_stale_token",
        "test_real_detection_payload_and_argument_guards",
        "torn application-ACK marker",
        "ZS_EVENT_OUTBOX_RETRY_EXHAUSTED",
    ):
        require(token in test, f"event outbox QG-2 case missing: {token}")

    require("zs_event_outbox_tests" in cmake,
            "event outbox test is not bound to CMake/CTest")
    require("src/zs_event_outbox.c" in cmake,
            "event outbox source is not bound to the firmware core")
    for token in (
        "zs_nor_event_outbox_adapter_t",
        "zs_nor_event_outbox_io_init",
        "one complete physical erase block",
    ):
        require(token in nor_header, f"NOR outbox adapter API missing: {token}")
    for token in (
        "slot * adapter->nor->geometry.erase_bytes",
        "erase_bytes < ZS_EVENT_OUTBOX_SLOT_BYTES",
        "base_address % nor->geometry.erase_bytes != 0u",
        "partition_end > nor->geometry.capacity_bytes",
        "zs_nor_erase",
        "zs_nor_program",
    ):
        require(token in nor_source, f"NOR outbox adapter guard missing: {token}")
    for token in (
        "test_sector_isolation_reclaim_and_roundtrip",
        "test_partition_and_callback_guards",
        "ZS_EVENT_OUTBOX_FULL",
        "memcmp(preserved",
    ):
        require(token in nor_test, f"NOR outbox QG-2 case missing: {token}")
    require("src/zs_nor_event_outbox.c" in cmake and
            "zs_nor_event_outbox_tests" in cmake,
            "NOR outbox adapter is not bound to CMake/CTest")
    for token in (
        "ZS_NOR_W25Q512JV_JEDEC_MANUFACTURER 0xefu",
        "ZS_NOR_W25Q512JV_JEDEC_MEMORY_TYPE 0x40u",
        "ZS_NOR_W25Q512JV_JEDEC_CAPACITY 0x20u",
        "zs_nor_probe_result_t",
        "zs_nor_probe_w25q512jv",
        "quad_enable_restored",
    ):
        require(token in core_nor_header,
                f"exact NOR boot-probe API missing: {token}")
    for token in (
        "ZS_NOR_OP_READ_SFDP 0x5au",
        "ZS_NOR_OP_READ_STATUS_2 0x35u",
        "ZS_NOR_OP_WRITE_STATUS_2 0x31u",
        "memcmp(sfdp, \"SFDP\", 4u)",
        "sfdp_density_bytes",
        "capacity_bytes != nor->geometry.capacity_bytes",
        "restore_quad_enable",
        "ZS_NOR_PROBE_QUAD_ENABLE_FAILED",
    ):
        require(token in core_nor_source,
                f"exact NOR boot-probe guard missing: {token}")
    for token in (
        "test_w25q512_probe_and_quad_restore",
        "test_w25q512_probe_fail_closed",
        "ZS_NOR_PROBE_JEDEC_MISMATCH",
        "ZS_NOR_PROBE_SFDP_MISMATCH",
        "ZS_NOR_PROBE_CAPACITY_MISMATCH",
        "ZS_NOR_PROBE_QUAD_ENABLE_FAILED",
    ):
        require(token in core_nor_test,
                f"exact NOR boot-probe QG-2 case missing: {token}")
    require("zs_nor_tests" in cmake,
            "exact NOR boot-probe test is not bound to CMake/CTest")
    for token in (
        "zs_nor_storage_layout_t",
        "command_slot_count",
        "command_base_address",
        "command_partition_bytes",
        "outbox_slot_count",
        "outbox_base_address",
        "outbox_partition_bytes",
        "zs_archive_layout_t archive",
        "zs_nor_storage_layout_make",
        "zs_nor_storage_bindings_t",
        "zs_nor_probe_info_t nor_probe",
        "zs_nor_command_journal_adapter_t command_adapter",
        "zs_nor_storage_bind",
    ):
        require(token in layout_header, f"NOR layout API missing: {token}")
    for token in (
        "command_slot_count < 2u",
        "erase_block_bytes < ZS_COMMAND_JOURNAL_SLOT_BYTES",
        "erase_block_bytes < ZS_EVENT_OUTBOX_SLOT_BYTES",
        "capacity_bytes % erase_block_bytes != 0u",
        "(uint64_t)command_slot_count * (uint64_t)erase_block_bytes",
        "(uint64_t)outbox_slot_count * (uint64_t)erase_block_bytes",
        "reserved_bytes = command_bytes + outbox_bytes",
        "zs_nor_probe_w25q512jv(nor, &bindings->nor_probe)",
        "zs_archive_make_default_layout",
        "out->command_base_address = archive_bytes",
        "out->outbox_base_address = archive_bytes + (uint32_t)command_bytes",
        "(uint64_t)archive_bytes + command_bytes + outbox_bytes !=",
        "zs_nor_archive_storage_init",
        "zs_nor_command_journal_io_init",
        "zs_nor_event_outbox_io_init",
        "out_archive_storage->size_bytes = bindings->layout.command_base_address",
    ):
        require(token in layout_source, f"NOR layout invariant missing: {token}")
    for token in (
        "test_default_64m_three_consumer_layout",
        "test_slot_counts_remain_target_inputs",
        "test_capacity_and_geometry_guards",
        "test_shared_binding_caps_archive_and_separates_tail",
        "test_shared_binding_failure_is_atomic",
        "bindings.nor_probe.quad_enabled",
        "layout.command_partition_bytes == 64u * 1024u",
        "layout.outbox_base_address == 63u * 1024u * 1024u",
        "archive_end(&layout.archive) == layout.command_base_address",
        "layout.command_partition_bytes ==",
        "layout.outbox_base_address",
    ):
        require(token in layout_test, f"NOR layout QG-2 case missing: {token}")
    require("src/zs_nor_storage_layout.c" in cmake and
            "zs_nor_storage_layout_tests" in cmake,
            "NOR layout planner is not bound to CMake/CTest")
    require("validate_event_outbox_contract.py" in ci,
            "event outbox QG-1 is not bound to CI")
    for token in (
        "MQTT PUBACK не является application ACK",
        "commit marker",
        "SHA-256",
        "at-least-once",
    ):
        require(token in icd, f"store-and-forward ICD detail missing: {token}")
    require("REQ-CELL-003" in requirements and
            "PARTIAL_PASS_HOST_OUTBOX_RECEIPT" in requirements,
            "REQ-CELL-003 does not report bounded host evidence")
    require(
        "event_store_forward_outbox: PORTABLE_ATOMIC_SHA256_PRIORITY_QG1_QG2_PASS_TARGET_STORAGE_BINDING_PENDING"
        in target,
        "target status overclaims or omits portable outbox evidence",
    )
    require(
        "event_outbox_nor_adapter: PORTABLE_ERASE_ISOLATED_QG1_QG2_PASS_PARTITION_AND_OCTOSPI_BINDING_PENDING"
        in target,
        "target status overclaims or omits NOR outbox evidence",
    )
    require(
        "event_nor_partition_planner: PORTABLE_ARCHIVE_COMMAND_OUTBOX_NONOVERLAP_QG1_QG2_PASS_SLOT_COUNTS_AND_OCTOSPI_BINDING_PENDING"
        in target,
        "target status overclaims or omits portable NOR layout evidence",
    )
    require(
        "event_nor_shared_binding: PORTABLE_FAIL_CLOSED_ARCHIVE_COMMAND_OUTBOX_QG1_QG2_PASS_TARGET_BINDING_PENDING"
        in target,
        "target status overclaims or omits shared NOR binding evidence",
    )
    require(
        "event_outbox_storage_binding: PORTABLE_SHARED_THREE_CONSUMER_BINDING_PASS_EXACT_SLOT_COUNTS_OCTOSPI_ENDURANCE_BLOCKER"
        in target,
        "target outbox storage binding status is not bounded",
    )
    require(
        "event_outbox_nor_partition: PORTABLE_ARCHIVE_COMMAND_OUTBOX_NONOVERLAP_QG1_QG2_PASS_EXACT_SLOT_COUNTS_AND_TARGET_BINDING_BLOCKER"
        in target,
        "target outbox NOR partition blocker is not explicit",
    )
    require("event_outbox_slot_count: MISSING_BLOCKER" in target,
            "target outbox slot-count blocker is not explicit")
    require("command_journal_slot_count: MISSING_BLOCKER" in target,
            "target command-journal slot-count blocker is not explicit")
    require(
        "nor_boot_probe: PORTABLE_W25Q512JV_EXACT_JEDEC_SFDP_CAPACITY_QE_RESTORE_QG1_QG2_PASS_TARGET_OCTOSPI_AND_SAMPLE_PENDING"
        in target,
        "target status overclaims or omits exact NOR boot probe",
    )
    require(
        "nor_octospi_binding: PORTABLE_W25Q512JV_PROBE_QG1_QG2_PASS_TARGET_OCTOSPI_AND_SAMPLE_BLOCKER"
        in target,
        "target NOR OCTOSPI/sample blocker is not explicit",
    )

    print("Event store-and-forward outbox QG-1: PASS")
    print("scope: exact W25Q512JV JEDEC/SFDP/QE boot gate + portable atomic queue + erase-isolated NOR adapter + shared archive/command/outbox non-overlap binding; exact slot counts/OCTOSPI and hardware remain pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
