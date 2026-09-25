"""LoRa uplink codec: the cross vector with firmware/tests/test_lora_frame.c, round trips, tampering, airtime."""
import pytest

from station import lora_codec as lc

ENGINEER_KEY = bytes(range(0xA0, 0xA0 + 32))
VECTOR_EVENT = "10010011000000050000002a0000007bd2496bc80103bc03b90090335002458f74816ba29b5f"
VECTOR_ACK = "9011000000050000002a0000001139d77b78a4d704"


def event() -> lc.LoraEvent:
    return lc.LoraEvent(1, 17, 5, 42, 1800000123, 456, 3, 188, 3, 185, 13200, 80, lc.FLAG_GSM_DEGRADED)


def test_vectors_match_firmware():
    key = lc.derive_key(ENGINEER_KEY)
    assert lc.encode_event(event(), key).hex() == VECTOR_EVENT
    assert lc.encode_ack(17, 5, 42, key).hex() == VECTOR_ACK
    e = lc.decode_event(bytes.fromhex(VECTOR_EVENT), key)
    assert e == event() and e.event_id == (5 << 32) | 42 and e.event_time_us == 1800000123456000
    assert lc.decode_ack(bytes.fromhex(VECTOR_ACK), key) == (17, 5, 42)


def test_tamper_and_wrong_key():
    key = lc.derive_key(ENGINEER_KEY)
    frame = bytearray(bytes.fromhex(VECTOR_EVENT))
    frame[22] ^= 1
    with pytest.raises(ValueError):
        lc.decode_event(bytes(frame), key)
    with pytest.raises(ValueError):
        lc.decode_event(bytes.fromhex(VECTOR_EVENT), lc.derive_key(bytes(32)))
    with pytest.raises(ValueError):
        lc.decode_ack(bytes.fromhex(VECTOR_EVENT), key)
    with pytest.raises(ValueError):
        lc.decode_ack(bytes.fromhex(VECTOR_ACK)[:-1], key)


def test_airtime_matches_firmware():
    assert round(lc.airtime_ms(38, 9, 125_000)) in range(263, 273)   # firmware: 268 ms
    assert round(lc.airtime_ms(21, 9, 125_000)) in range(181, 191)   # firmware: 186 ms
    assert lc.airtime_ms(38, 7, 125_000) < lc.airtime_ms(38, 9, 125_000) < lc.airtime_ms(38, 12, 125_000)
    # 1 % duty cycle: at SF9 one event + ack costs ~0.47 s of the 36 s/hour budget -> ~75 events/hour
    assert 36_000 / (lc.airtime_ms(38, 9, 125_000) + lc.airtime_ms(21, 9, 125_000)) > 70
