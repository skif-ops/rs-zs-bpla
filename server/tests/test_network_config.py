"""ICD addendum G, remote network configuration: CMD_SET_NETWORK_CONFIG in the command codec (payload -> the station's
config_write patch, canonical CBOR), every refusal the station would give, the shared vector, heartbeat keys 21..23
and the operator route (version from the station's report; heartbeat encoding: server/tools/test_firmware_packet.py)."""
import importlib.util
import time
from pathlib import Path

import cbor2
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from station import network_config as nc
from station.command_codec import CommandSigner, decode_signed_command, encode_signed_command, validate_command_payload
from station.schemas import DetectorHealth, HeartbeatMessage, StationCommand, StationPosition
from station.store import EventStore

ROOT = Path(__file__).resolve().parents[2]
SIGNER = CommandSigner(Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33))))


def _gen():
    spec = importlib.util.spec_from_file_location("gen_net", ROOT / "tools" / "generate_network_config_vector.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cmd(payload):
    return StationCommand(command_id="2b0f1c3a-0000-4000-8000-0000000000aa", station_id=17, command=nc.NETWORK_COMMAND,
                          payload=payload, created_time_us=1_000_000, expires_time_us=2_000_000)


def test_vector_is_current():
    assert (ROOT / "firmware" / "generated" / "zs_network_config_vector.h").read_text() == _gen().render()


def test_round_trip_and_wire_form():
    payload = {"version": 2, "server_host": "muhoed2.twin", "mqtt_port": 443, "server_fingerprint": "ab" * 32,
               "tenant": "pilot2", "topic_prefix": "zs/v1", "preferred_sim": 2, "apn1": "iot.pilot", "apn2": "internet",
               "https_port": 0}
    wire = encode_signed_command(_cmd(payload), SIGNER)
    top = cbor2.loads(wire)
    assert top[6] == 6 and set(top[7]) == {0}
    patch = top[7][0]
    assert patch == cbor2.dumps(cbor2.loads(patch), canonical=True)                  # canonical, as the station demands
    assert list(cbor2.loads(patch)) == [1, 2, 3, 4, 6, 7, 8, 9, 10, 11]              # ascending keys, no 5 / 12 / 13
    assert cbor2.loads(patch)[6] == bytes.fromhex("ab" * 32)
    back = decode_signed_command(wire, {SIGNER.key_id: SIGNER.public_key}, now_us=1_500_000)
    assert back.command == nc.NETWORK_COMMAND and back.payload == payload


def test_vector_patch_is_the_codec_output():
    v = _gen().vector()
    assert nc.payload_to_wire(_gen().PAYLOAD)[0] == v["patch"]
    back = decode_signed_command(v["command"], {SIGNER.key_id: SIGNER.public_key}, now_us=1_800_000_000_001_000)
    assert back.payload == _gen().PAYLOAD


@pytest.mark.parametrize("payload, message", [
    ({"server_host": "x.twin"}, "version"),
    ({"version": 3}, "no network field"),
    ({"version": 3, "ca_reference": "other-ca"}, "service-mode"),
    ({"version": 3, "region": 2}, "service-mode"),
    ({"version": 3, "station_id": 18}, "service-mode"),
    ({"version": 0, "server_host": "x.twin"}, "version"),
    ({"version": 3, "server_host": "bad host"}, "server_host"),
    ({"version": 3, "server_host": "mqtts://x.twin"}, "server_host"),
    ({"version": 3, "server_host": "1.2.3"}, "server_host"),
    ({"version": 3, "server_host": "10.0.0.01"}, "server_host"),
    ({"version": 3, "server_host": "a" * 65}, "server_host"),
    ({"version": 3, "mqtt_port": 0}, "mqtt_port"),
    ({"version": 3, "mqtt_port": 70000}, "mqtt_port"),
    ({"version": 3, "mqtt_port": "8883"}, "mqtt_port"),
    ({"version": 3, "mqtt_port": 8884}, "mqtt_port"),
    ({"version": 3, "mqtt_port": 8883, "https_port": 8883}, "https_port"),
    ({"version": 3, "https_port": 70000}, "https_port"),
    ({"version": 3, "server_fingerprint": "ab" * 31}, "server_fingerprint"),
    ({"version": 3, "server_fingerprint": "zz" * 32}, "server_fingerprint"),
    ({"version": 3, "tenant": ""}, "tenant"),
    ({"version": 3, "tenant": "pilot/1"}, "tenant"),
    ({"version": 3, "tenant": "t" * 17}, "tenant"),
    ({"version": 3, "topic_prefix": "/zs/v1"}, "topic_prefix"),
    ({"version": 3, "topic_prefix": "zs/v1/"}, "topic_prefix"),
    ({"version": 3, "preferred_sim": 3}, "preferred_sim"),
    ({"version": 3, "apn1": "bad apn"}, "apn1"),
    ({"version": 3, "apn1": "", "apn2": "internet"}, "apn2"),
])
def test_refusals(payload, message):
    with pytest.raises(ValueError, match=message):
        validate_command_payload(nc.NETWORK_COMMAND, payload)


def test_hosts_accepted_like_the_station():
    for host in ("muhoed.example.ru", "10.0.0.1", "0.0.0.0", "fd00::1", "::", "2001:db8:0:0:0:0:0:1", "a-b.c1"):
        assert nc.host_valid(host), host
    for host in ("-a.b", "a-.b", "a..b", "1.2.3.4.5", "256.1.1.1", "fd00:::1", "a_b.c", "", "12345:1::"):
        assert not nc.host_valid(host), host


def test_wire_decoding_refuses_non_canonical_and_foreign_keys():
    good = nc.payload_to_wire({"version": 2, "server_host": "x.twin"})
    assert nc.payload_from_wire(good) == {"version": 2, "server_host": "x.twin"}
    with pytest.raises(ValueError):
        nc.payload_from_wire({0: cbor2.dumps({2: "x.twin", 1: 2})})                  # keys out of order
    with pytest.raises(ValueError):
        nc.payload_from_wire({0: cbor2.dumps({1: 2, 5: "other-ca"}, canonical=True)})
    with pytest.raises(ValueError):
        nc.payload_from_wire({0: b"\xff"})
    with pytest.raises(ValueError):
        nc.payload_from_wire({1: good[0]})


def test_heartbeat_defaults_for_older_firmware():
    d = DetectorHealth()                         # keys 21..23 absent: version unknown, stable, nothing failed
    assert (d.net_config_version, d.net_state, d.net_failed_version) == (0, "STABLE", 0)


def test_next_version():
    with pytest.raises(ValueError):
        nc.next_version(None)
    hb = HeartbeatMessage(station_id=17, time_us=1, station=StationPosition(lat_e7=0, lon_e7=0, alt_dm=0), detector=DetectorHealth())
    with pytest.raises(ValueError):
        nc.next_version(hb)
    hb.detector.net_config_version = 4
    assert nc.next_version(hb) == 5


def test_operator_route(tmp_path, monkeypatch):
    from app import app
    import station.router as router

    store = EventStore(tmp_path / "events.sqlite3")
    monkeypatch.setattr(router, "store", store)
    client = TestClient(app)
    # without a report the station's version is unknown: an explicit one is needed
    assert client.post("/api/v1/stations/17/network-config", json={"server_host": "muhoed2.twin"}).status_code == 409
    store.upsert_station(HeartbeatMessage(station_id=17, time_us=1, station=StationPosition(lat_e7=0, lon_e7=0, alt_dm=0),
                                          detector=DetectorHealth(net_config_version=3)))
    ok = client.post("/api/v1/stations/17/network-config", json={"server_host": "muhoed2.twin", "mqtt_port": 443})
    assert ok.status_code == 200 and ok.json()["command"] == nc.NETWORK_COMMAND
    assert ok.json()["payload"] == {"server_host": "muhoed2.twin", "mqtt_port": 443, "version": 4}
    explicit = client.post("/api/v1/stations/17/network-config", json={"version": 9, "apn1": "iot.pilot"})
    assert explicit.status_code == 200 and explicit.json()["payload"]["version"] == 9
    assert client.post("/api/v1/stations/17/network-config", json={"server_host": "bad host"}).status_code == 400
    assert client.post("/api/v1/stations/17/network-config", json={}).status_code == 400
    assert client.post("/api/v1/stations/17/network-config", json={"ca_reference": "x"}).status_code == 400
    assert client.post("/api/v1/stations/17/network-config", json={"mqtt_port": "8883"}).status_code == 422
    due = store.due_commands(int(time.time() * 1e6) + 1, 5)
    assert [c.command for c in due] == [nc.NETWORK_COMMAND, nc.NETWORK_COMMAND]
