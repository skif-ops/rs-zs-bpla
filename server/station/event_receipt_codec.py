"""Canonical application receipt for durably processed station events."""

from __future__ import annotations

from dataclasses import dataclass

import cbor2


EVENT_RECEIPT_SCHEMA = 1
EVENT_RECEIPT_MESSAGE_TYPE = 6
MAX_EVENT_RECEIPT_BYTES = 128


@dataclass(frozen=True)
class EventReceipt:
    station_id: int
    boot_id: int
    seq_no: int
    event_id: int
    payload_sha256: bytes


def _validate(receipt: EventReceipt) -> None:
    if type(receipt.station_id) is not int or not 0 < receipt.station_id <= 0xFFFFFFFF:
        raise ValueError("event receipt station_id is outside uint32 range")
    if type(receipt.boot_id) is not int or not 0 <= receipt.boot_id <= 0xFFFFFFFF:
        raise ValueError("event receipt boot_id is outside uint32 range")
    if type(receipt.seq_no) is not int or not 0 <= receipt.seq_no <= 0xFFFFFFFF:
        raise ValueError("event receipt seq_no is outside uint32 range")
    if type(receipt.event_id) is not int or not 0 < receipt.event_id <= 0xFFFFFFFFFFFFFFFF:
        raise ValueError("event receipt event_id is outside uint64 range")
    if not isinstance(receipt.payload_sha256, bytes) or len(receipt.payload_sha256) != 32:
        raise ValueError("event receipt payload SHA-256 must contain 32 bytes")


def encode_event_receipt(receipt: EventReceipt) -> bytes:
    _validate(receipt)
    payload = cbor2.dumps(
        {
            0: EVENT_RECEIPT_SCHEMA,
            1: EVENT_RECEIPT_MESSAGE_TYPE,
            2: receipt.station_id,
            3: receipt.boot_id,
            4: receipt.seq_no,
            5: receipt.event_id,
            6: receipt.payload_sha256,
        },
        canonical=True,
    )
    if len(payload) > MAX_EVENT_RECEIPT_BYTES:
        raise ValueError("event receipt exceeds size limit")
    return payload


def decode_event_receipt(payload: bytes) -> EventReceipt:
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_EVENT_RECEIPT_BYTES:
        raise ValueError("event receipt exceeds size limit")
    try:
        obj = cbor2.loads(payload)
    except Exception:
        raise ValueError("invalid event receipt CBOR") from None
    if (
        not isinstance(obj, dict)
        or len(obj) != 7
        or any(type(key) is not int for key in obj)
        or set(obj) != set(range(7))
    ):
        raise ValueError("invalid event receipt keys")
    if cbor2.dumps(obj, canonical=True) != payload:
        raise ValueError("event receipt is not canonical CBOR")
    if obj[0] != EVENT_RECEIPT_SCHEMA or obj[1] != EVENT_RECEIPT_MESSAGE_TYPE:
        raise ValueError("unsupported event receipt version or type")
    receipt = EventReceipt(
        station_id=obj[2],
        boot_id=obj[3],
        seq_no=obj[4],
        event_id=obj[5],
        payload_sha256=obj[6],
    )
    _validate(receipt)
    return receipt
