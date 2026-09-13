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
    require("event_outbox_storage_binding: MISSING_BLOCKER" in target,
            "target outbox storage binding blocker is not explicit")

    print("Event store-and-forward outbox QG-1: PASS")
    print("scope: portable atomic queue; target storage and hardware remain pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
