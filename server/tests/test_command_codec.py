from pathlib import Path

import cbor2
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from station.command_codec import (
    CommandAck,
    CommandSigner,
    decode_command_ack,
    decode_signed_command,
    encode_command_ack,
    encode_signed_command,
)
from station.schemas import StationCommand


def signer() -> CommandSigner:
    return CommandSigner(Ed25519PrivateKey.generate())


def command(**overrides) -> StationCommand:
    values = {
        "command_id": "12345678-1234-5678-1234-567812345678",
        "station_id": 17,
        "command": "CMD_REQUEST_AUDIO",
        "payload": {"event_id": 42, "segment": "both"},
        "created_time_us": 1_000_000,
        "expires_time_us": 2_000_000,
    }
    values.update(overrides)
    return StationCommand(**values)


def test_signed_command_round_trip_and_key_id_binding():
    key = signer()
    encoded = encode_signed_command(command(), key)
    decoded = decode_signed_command(
        encoded,
        {key.key_id: key.public_key},
        now_us=1_500_000,
    )
    assert decoded.station_id == 17
    assert decoded.command_id == "12345678-1234-5678-1234-567812345678"
    assert decoded.command == "CMD_REQUEST_AUDIO"
    assert decoded.payload["event_id"] == 42


def test_signed_command_rejects_tamper_unknown_key_and_expiry():
    key = signer()
    encoded = encode_signed_command(command(), key)
    obj = cbor2.loads(encoded)
    obj[7][0] = 43
    tampered = cbor2.dumps(obj, canonical=True)
    with pytest.raises(ValueError, match="signature"):
        decode_signed_command(tampered, {key.key_id: key.public_key}, now_us=1_500_000)
    with pytest.raises(ValueError, match="unknown command signing key"):
        decode_signed_command(encoded, {}, now_us=1_500_000)
    with pytest.raises(ValueError, match="expired"):
        decode_signed_command(encoded, {key.key_id: key.public_key}, now_us=2_000_000)
    with pytest.raises(ValueError, match="not yet valid"):
        decode_signed_command(encoded, {key.key_id: key.public_key}, now_us=999_999)


def test_signed_command_rejects_noncanonical_and_unsupported_command():
    key = signer()
    canonical = encode_signed_command(command(), key)
    obj = cbor2.loads(canonical)
    noncanonical = cbor2.dumps(obj, canonical=False)
    if noncanonical == canonical:
        noncanonical = bytes([0xBA, 0, 0, 0, 10]) + canonical[1:]
    with pytest.raises(ValueError, match="canonical"):
        decode_signed_command(noncanonical, {key.key_id: key.public_key}, now_us=1_500_000)
    with pytest.raises(ValueError, match="unsupported command"):
        encode_signed_command(command(command="CMD_UNKNOWN"), key)
    with pytest.raises(ValueError, match="nil UUID"):
        encode_signed_command(
            command(command_id="00000000-0000-0000-0000-000000000000"), key
        )


def test_command_ack_round_trip_and_strict_fields():
    ack = CommandAck(
        station_id=17,
        command_id="12345678-1234-5678-1234-567812345678",
        result_code=2,
        completed_time_us=1_750_000,
        detail_code=12,
    )
    encoded = encode_command_ack(ack)
    assert decode_command_ack(encoded) == ack
    obj = cbor2.loads(encoded)
    obj[7] = 1
    with pytest.raises(ValueError, match="keys"):
        decode_command_ack(cbor2.dumps(obj, canonical=True))
    obj.pop(7)
    obj[2] = True
    with pytest.raises(ValueError, match="station_id"):
        decode_command_ack(cbor2.dumps(obj, canonical=True))


def test_command_and_ack_reject_boolean_integer_confusion_and_long_ttl():
    key = signer()
    with pytest.raises(ValueError, match="valid integer"):
        command(station_id=True)
    with pytest.raises(ValueError, match="validity interval"):
        encode_signed_command(command(expires_time_us=1_000_000 + 900_000_001), key)
    with pytest.raises(ValueError, match="result code"):
        encode_command_ack(
            CommandAck(
                station_id=17,
                command_id="12345678-1234-5678-1234-567812345678",
                result_code=True,
                completed_time_us=1,
            )
        )


def test_audio_payload_is_compact_numeric_and_range_is_unambiguous():
    key = signer()
    encoded = encode_signed_command(command(), key)
    wire = cbor2.loads(encoded)
    assert wire[7] == {0: 42, 1: 2, 2: None, 3: None}
    ranged = command(
        payload={
            "event_id": 42,
            "segment": "range",
            "start_offset_ms": -5000,
            "duration_ms": 10000,
        }
    )
    decoded = decode_signed_command(
        encode_signed_command(ranged, key),
        {key.key_id: key.public_key},
        now_us=1_500_000,
    )
    assert decoded.payload == ranged.payload
    with pytest.raises(ValueError, match="requires offset"):
        encode_signed_command(
            command(payload={"event_id": 42, "segment": "range"}),
            key,
        )
    # optional key 4: the event time for a station that no longer knows the event (addendum B)
    timed = command(payload={"event_id": 42, "segment": "both", "event_time_us": 1_800_000_000_123_456})
    encoded = encode_signed_command(timed, key)
    assert cbor2.loads(encoded)[7] == {0: 42, 1: 2, 2: None, 3: None, 4: 1_800_000_000_123_456}
    decoded = decode_signed_command(encoded, {key.key_id: key.public_key}, now_us=1_500_000)
    assert decoded.payload["event_time_us"] == 1_800_000_000_123_456
    for bad in (0, -1, 2 ** 63, True):
        with pytest.raises(ValueError, match="event_time_us"):
            encode_signed_command(command(payload={"event_id": 42, "segment": "both", "event_time_us": bad}), key)


def test_signer_loads_only_ed25519_pem(tmp_path: Path):
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    key_path = tmp_path / "command.key"
    key_path.write_bytes(pem)
    key_path.chmod(0o600)
    loaded = CommandSigner.from_pem_file(key_path)
    assert loaded.key_id == CommandSigner(private).key_id
    invalid = tmp_path / "invalid.key"
    invalid.write_text("not a key", encoding="utf-8")
    invalid.chmod(0o600)
    with pytest.raises(ValueError, match="invalid unencrypted"):
        CommandSigner.from_pem_file(invalid)
