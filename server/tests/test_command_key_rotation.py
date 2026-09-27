"""ICD addendum E, command key rotation: CMD_ROTATE_COMMAND_KEY codec and shared firmware vector, the bridge's
keyring choosing the signer per station (heartbeat key ids, an acknowledged rotation), the operator route."""
import importlib.util
import time
from pathlib import Path
from types import SimpleNamespace

import cbor2
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from station.command_codec import (CommandKeyring, CommandSigner, decode_signed_command, encode_signed_command,
                                   key_id_hex, validate_command_payload)
from station.mqtt_bridge import publish_due_commands
from station.schemas import DetectorHealth, HeartbeatMessage, StationCommand, StationPosition
from station.store import EventStore

ROOT = Path(__file__).resolve().parents[2]
CURRENT = CommandSigner(Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33))))
NEXT = CommandSigner(Ed25519PrivateKey.from_private_bytes(bytes(range(33, 65))))


def _gen():
    spec = importlib.util.spec_from_file_location("gen_command_rotate", ROOT / "tools" / "generate_command_rotate_vector.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cmd(payload, command_id="2b0f1c3a-0000-4000-8000-00000000000b"):
    return StationCommand(command_id=command_id, station_id=17, command="CMD_ROTATE_COMMAND_KEY", payload=payload,
                          created_time_us=1_000_000, expires_time_us=2_000_000)


def _heartbeat(time_us, current=None, nxt=None):
    return HeartbeatMessage(station_id=17, time_us=time_us, station=StationPosition(lat_e7=0, lon_e7=0, alt_dm=0),
                            detector=DetectorHealth(command_key_id=current, command_next_key_id=nxt))


def test_firmware_vector_is_current():
    assert (ROOT / "firmware" / "generated" / "zs_command_rotate_vector.h").read_text() == _gen().render()


def test_round_trip_and_wire_form():
    wire = encode_signed_command(_cmd({"public_key": NEXT.public_key_hex}), CURRENT)
    assert cbor2.loads(wire)[6] == 4 and cbor2.loads(wire)[7] == {0: bytes.fromhex(NEXT.public_key_hex)}
    back = decode_signed_command(wire, {CURRENT.key_id: CURRENT.public_key}, now_us=1_500_000)
    assert back.command == "CMD_ROTATE_COMMAND_KEY" and back.payload == {"public_key": NEXT.public_key_hex}
    assert key_id_hex(NEXT.public_key_hex) == NEXT.key_id.hex()


@pytest.mark.parametrize("payload,match", [
    ({"public_key": "00" * 32}, "non-zero"),
    ({"public_key": "ab" * 31}, "32-byte"),
    ({"public_key": "zz" * 32}, "64 hex"),
    ({"public_key": 5}, "64 hex"),
    ({"public_key": "ab" * 32, "retire": True}, "exactly public_key"),
    ({}, "exactly public_key"),
])
def test_rejections(payload, match):
    with pytest.raises(ValueError, match=match):
        validate_command_payload("CMD_ROTATE_COMMAND_KEY", payload)
    with pytest.raises(ValueError, match=match):
        encode_signed_command(_cmd(payload), CURRENT)


def test_keyring_picks_the_key_the_station_trusts(tmp_path):
    store = EventStore(tmp_path / "events.sqlite3")
    ring = CommandKeyring(CURRENT, NEXT)
    assert CommandKeyring(CURRENT).signer_for(17, store) is CURRENT
    with pytest.raises(ValueError, match="differ"):
        CommandKeyring(CURRENT, CURRENT)
    # unknown station, or one that reports only the current key: the current key
    assert ring.signer_for(17, store) is CURRENT
    store.upsert_station(_heartbeat(1_000, current=CURRENT.key_id.hex()))
    assert ring.signer_for(17, store) is CURRENT
    # the rotation acknowledged OK after that heartbeat: the next key at once (the same session)
    rotate = store.create_command(17, "CMD_ROTATE_COMMAND_KEY", {"public_key": NEXT.public_key_hex})
    assert ring.signer_for(17, store) is CURRENT                           # queued, not acknowledged
    store.ack_command(17, rotate.command_id, 0, 0, completed_us=2_000)
    assert store.acked_key_rotation(17) == (NEXT.public_key_hex, 2_000)
    assert ring.signer_for(17, store) is NEXT
    # a later heartbeat decides: both keys listed -> next; next promoted to current -> next
    store.upsert_station(_heartbeat(3_000, current=CURRENT.key_id.hex(), nxt=NEXT.key_id.hex()))
    assert ring.signer_for(17, store) is NEXT
    store.upsert_station(_heartbeat(4_000, current=NEXT.key_id.hex()))
    assert ring.signer_for(17, store) is NEXT
    # the engineer reset the key over BLE after the rotation: the heartbeat no longer lists it -> current key
    store.upsert_station(_heartbeat(5_000, current=CURRENT.key_id.hex()))
    assert ring.signer_for(17, store) is CURRENT
    # a refused rotation never switches
    store2 = EventStore(tmp_path / "other.sqlite3")
    refused = store2.create_command(17, "CMD_ROTATE_COMMAND_KEY", {"public_key": NEXT.public_key_hex})
    store2.ack_command(17, refused.command_id, 1, 2, completed_us=2_000)
    assert store2.acked_key_rotation(17) is None and ring.signer_for(17, store2) is CURRENT


def test_bridge_signs_each_station_with_its_key(tmp_path):
    store = EventStore(tmp_path / "events.sqlite3")
    store.upsert_station(_heartbeat(1_000, current=NEXT.key_id.hex()))    # station 17 already rotated
    store.create_command(17, "CMD_REBOOT", {"delay_s": 30})
    store.create_command(18, "CMD_REBOOT", {"delay_s": 30})
    sent = {}

    class Client:
        def publish(self, topic, payload, qos, retain):
            sent[topic] = cbor2.loads(payload)[8]
            return SimpleNamespace(rc=0)

    published, failed = publish_due_commands(Client(), "evt", CommandKeyring(CURRENT, NEXT), now_us=int(time.time() * 1e6) + 1, retry_after_us=1,
                                             event_store=store)
    assert (published, failed) == (2, 0)
    assert sent == {"zs/v1/evt/17/down": NEXT.key_id, "zs/v1/evt/18/down": CURRENT.key_id}


def test_operator_route_queues_the_rotation(tmp_path, monkeypatch):
    from app import app
    import station.router as router

    store = EventStore(tmp_path / "events.sqlite3")
    monkeypatch.setattr(router, "store", store)
    client = TestClient(app)
    ok = client.post("/api/v1/stations/17/command-key-rotation", json={"public_key": NEXT.public_key_hex.upper()})
    assert ok.status_code == 200 and ok.json()["command"] == "CMD_ROTATE_COMMAND_KEY"
    assert ok.json()["payload"] == {"public_key": NEXT.public_key_hex}
    assert client.post("/api/v1/stations/17/command-key-rotation", json={"public_key": "00" * 32}).status_code == 400
    assert client.post("/api/v1/stations/17/command-key-rotation", json={"public_key": "ab"}).status_code == 422
    assert [c.command for c in store.due_commands(int(time.time() * 1e6) + 1, 1)] == ["CMD_ROTATE_COMMAND_KEY"]
