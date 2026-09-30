"""ICD addendum F, firmware update over MQTT: manifest, .fw_info and release signature; CMD_UPDATE_FIRMWARE in the
command codec and the shared firmware vector; fwreq/fw messages; the release repository and fw-sign; the bridge's
answer to a request (store and repository rules, QoS 0 on the fw topic); the operator route (heartbeat keys 18..20: server/tools/test_firmware_packet.py)."""
import hashlib
import importlib.util
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import cbor2
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from station import firmware_codec as fw
from station.command_codec import CommandSigner, decode_signed_command, encode_signed_command, validate_command_payload
from station.mqtt_bridge import answer_firmware_request, handle_message, station_id_from_topic
from station.schemas import StationCommand
from station.store import EventStore

ROOT = Path(__file__).resolve().parents[2]
RELEASE = fw.ReleaseSigner(Ed25519PrivateKey.from_private_bytes(bytes(range(65, 97))))
COMMANDS = CommandSigner(Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33))))


def _gen():
    spec = importlib.util.spec_from_file_location("gen_fw_update", ROOT / "tools" / "generate_fw_update_vector.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _image(version=5, size=5000, target=fw.TARGET_STM32_APP):
    return _gen().test_image(version=version, size=size, target=target)


def test_firmware_vector_is_current():
    assert (ROOT / "firmware" / "generated" / "zs_fw_update_vector.h").read_text() == _gen().render()


def test_fw_info_and_manifest():
    image = _image()
    assert fw.parse_fw_info(image) == fw.FirmwareInfo(target=1, version=5)
    assert image[0x400:0x404] == b"DIOF"
    with pytest.raises(ValueError, match=".fw_info"):
        fw.parse_fw_info(image[:0x410])
    with pytest.raises(ValueError, match="no valid"):
        fw.parse_fw_info(bytes(4096))
    m = fw.manifest_for_image(image)
    assert m == fw.Manifest(target=1, version=5, size=5000, sha256=hashlib.sha256(image).digest())
    raw = m.encode()
    assert cbor2.loads(raw) == {0: 1, 1: 1, 2: 5, 3: 5000, 4: m.sha256} and fw.decode_manifest(raw) == m
    for bad in (cbor2.dumps({0: 1, 1: 1, 2: 5, 3: 5000}), cbor2.dumps({0: 2, 1: 1, 2: 5, 3: 5000, 4: m.sha256}, canonical=True),
                cbor2.dumps({0: 1, 1: 1, 2: 0, 3: 5000, 4: m.sha256}, canonical=True), raw + b"\x00", b""):
        with pytest.raises(ValueError):
            fw.decode_manifest(bad)
    noncanonical = b"\xa5\x00\x01\x01\x01\x02\x18\x05" + raw[4:]       # version 5 in the one-byte form
    with pytest.raises(ValueError, match="canonical"):
        fw.decode_manifest(noncanonical)


def test_release_signature():
    raw = fw.manifest_for_image(_image()).encode()
    sig = RELEASE.sign(raw)
    assert fw.verify_release(raw, RELEASE.key_id, sig, [RELEASE.public_raw]).version == 5
    other = fw.ReleaseSigner(Ed25519PrivateKey.from_private_bytes(bytes(32)))
    with pytest.raises(ValueError, match="unknown release key"):
        fw.verify_release(raw, RELEASE.key_id, sig, [other.public_raw])
    with pytest.raises(ValueError, match="invalid release signature"):
        fw.verify_release(raw, RELEASE.key_id, bytes(64), [RELEASE.public_raw])
    Ed25519PrivateKey.from_private_bytes(bytes(range(65, 97))).public_key().verify(sig, b"DIO-FW-V1" + raw)   # the domain


def _command(payload, command_id="2b0f1c3a-0000-4000-8000-0000000000f5"):
    return StationCommand(command_id=command_id, station_id=17, command="CMD_UPDATE_FIRMWARE", payload=payload,
                          created_time_us=1_000_000, expires_time_us=2_000_000)


def test_command_codec_round_trip():
    raw = fw.manifest_for_image(_image()).encode()
    payload = fw.command_payload(raw, RELEASE.key_id, RELEASE.sign(raw))
    wire = encode_signed_command(_command(payload), COMMANDS)
    obj = cbor2.loads(wire)
    assert obj[6] == 5 and obj[7] == {0: raw, 1: RELEASE.key_id, 2: bytes.fromhex(payload["signature"])}
    back = decode_signed_command(wire, {COMMANDS.key_id: COMMANDS.public_key}, now_us=1_500_000)
    assert back.command == "CMD_UPDATE_FIRMWARE" and back.payload == payload
    assert len(wire) < 300                                             # far below the 2048-byte envelope


@pytest.mark.parametrize("mutate,match", [
    (lambda p: {**p, "extra": "00"}, "exactly"),
    (lambda p: {k: v for k, v in p.items() if k != "signature"}, "exactly"),
    (lambda p: {**p, "signature": "zz"}, "hex"),
    (lambda p: {**p, "signature": "00" * 63}, "64"),
    (lambda p: {**p, "release_key_id": "00" * 7}, "8 bytes"),
    (lambda p: {**p, "manifest": "a0"}, "five-key"),
])
def test_command_payload_rejections(mutate, match):
    raw = fw.manifest_for_image(_image()).encode()
    payload = mutate(fw.command_payload(raw, RELEASE.key_id, RELEASE.sign(raw)))
    with pytest.raises(ValueError, match=match):
        validate_command_payload("CMD_UPDATE_FIRMWARE", payload)


def test_request_and_chunk_messages():
    cid = uuid.uuid4().bytes
    req = fw.FirmwareRequest(17, cid, 2048, 1024)
    raw = fw.encode_request(req)
    assert cbor2.loads(raw) == {0: 1, 1: 8, 2: 17, 3: cid, 4: 2048, 5: 1024} and fw.decode_request(raw) == req
    for bad in (fw.FirmwareRequest(17, cid, 0, 1025), fw.FirmwareRequest(0, cid, 0, 1), fw.FirmwareRequest(17, bytes(16), 0, 1)):
        with pytest.raises(ValueError):
            fw.encode_request(bad)
    chunk = fw.encode_chunk(17, cid, 2048, b"\x01" * 1024)
    assert fw.decode_chunk(chunk) == (17, cid, 2048, b"\x01" * 1024) and len(chunk) <= fw.CHUNK_BYTES + 48
    with pytest.raises(ValueError, match="type"):
        fw.decode_chunk(raw)
    with pytest.raises(ValueError, match="type"):
        fw.decode_request(fw.encode_chunk(17, cid, 0, b"\x01"))           # a short chunk is no request
    with pytest.raises(ValueError, match="1..1024"):
        fw.decode_request(cbor2.dumps({0: 1, 1: 8, 2: 17, 3: cid, 4: 0, 5: 1025}, canonical=True))
    with pytest.raises(ValueError):
        fw.encode_chunk(17, cid, 0, b"")


def test_repository_and_fw_sign(tmp_path):
    from pki.cli import main as pki_main

    key = tmp_path / "release.pem"
    assert pki_main(["fw-release-key", "--out", str(key)]) == 0
    assert (key.stat().st_mode & 0o777) == 0o600
    assert pki_main(["fw-release-key", "--out", str(key)]) == 2         # never overwritten
    image_path = tmp_path / "app.bin"
    image_path.write_bytes(_image(version=9, size=3000))
    repo_dir = tmp_path / "repo"
    assert pki_main(["fw-sign", "--key", str(key), "--image", str(image_path), "--out", str(repo_dir)]) == 0
    assert pki_main(["fw-sign", "--key", str(key), "--image", str(image_path), "--out", str(repo_dir)]) == 2
    (tmp_path / "bad.bin").write_bytes(bytes(3000))
    assert pki_main(["fw-sign", "--key", str(key), "--image", str(tmp_path / "bad.bin"), "--out", str(repo_dir)]) == 2
    repo = fw.ReleaseRepository(repo_dir)
    assert repo.versions() == [9]
    release = repo.get(9)
    signer = fw.ReleaseSigner.from_pem_file(key)
    assert fw.verify_release(release.manifest_bytes, release.key_id, release.signature, [signer.public_raw]) == release.manifest
    assert repo.get(8) is None and repo.get(0) is None
    (repo_dir / "9.bin").write_bytes(_image(version=9, size=3001))
    with pytest.raises(ValueError, match="inconsistent"):
        repo.get(9)


class Client:
    def __init__(self):
        self.published, self.acked = [], []

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, payload, qos, retain))
        return SimpleNamespace(rc=0)

    def ack(self, mid, qos):
        self.acked.append(mid)


def _setup(tmp_path, version=5, size=5000):
    store = EventStore(tmp_path / "events.sqlite3")
    repo = fw.ReleaseRepository(tmp_path / "firmware")
    release = repo.add(_image(version=version, size=size), RELEASE)
    command = store.create_command(17, "CMD_UPDATE_FIRMWARE", release.command_payload())
    return store, repo, release, uuid.UUID(command.command_id).bytes


def _req(cid, offset, length, station=17):
    return fw.encode_request(fw.FirmwareRequest(station, cid, offset, length))


def test_bridge_serves_chunks(tmp_path):
    store, repo, release, cid = _setup(tmp_path)
    now = int(time.time() * 1e6)
    assert station_id_from_topic("zs/v1/evt/17/fwreq", "evt") == (17, "fwreq")
    client = Client()
    assert answer_firmware_request(client, "zs/v1/evt/17/fwreq", _req(cid, 4096, 904), "evt", event_store=store,
                                   firmware_repository=repo, now_us=now) == "fw_served"
    (topic, payload, qos, retain), = client.published
    assert topic == "zs/v1/evt/17/fw" and qos == 0 and retain is False
    assert fw.decode_chunk(payload) == (17, cid, 4096, release.image[4096:5000])
    # through handle_message: the QoS 1 fwreq is acknowledged after the answer
    client = Client()
    msg = SimpleNamespace(topic="zs/v1/evt/17/fwreq", payload=_req(cid, 0, 1024), mid=7, qos=1, retain=False)
    assert handle_message(client, msg, "evt", True, event_store=store, firmware_repository=repo)
    assert client.acked == [7] and fw.decode_chunk(client.published[0][1])[3] == release.image[:1024]
    # malformed or foreign: discarded and acknowledged, nothing published
    client = Client()
    bad = SimpleNamespace(topic="zs/v1/evt/18/fwreq", payload=_req(cid, 0, 1024), mid=8, qos=1, retain=False)
    assert not handle_message(client, bad, "evt", True, event_store=store, firmware_repository=repo)
    assert client.acked == [8] and client.published == []


@pytest.mark.parametrize("case", ["past_end", "unknown_command", "acked", "other_station_command", "too_old", "no_release",
                                  "other_release", "no_repository", "not_update"])
def test_bridge_drops_what_it_does_not_cover(tmp_path, case):
    store, repo, release, cid = _setup(tmp_path)
    now = int(time.time() * 1e6)
    station, offset, length, repository = 17, 0, 1024, repo
    if case == "past_end":
        offset, length = 4096, 905
    elif case == "unknown_command":
        cid = uuid.uuid4().bytes
    elif case == "acked":
        store.ack_command(17, str(uuid.UUID(bytes=cid)), 0, 5, completed_us=now)
    elif case == "other_station_command":
        cid = uuid.UUID(store.create_command(18, "CMD_UPDATE_FIRMWARE", release.command_payload()).command_id).bytes
    elif case == "too_old":
        now += fw.SERVE_WINDOW_US + 1
    elif case == "no_release":
        (tmp_path / "firmware" / "5.bin").unlink()
    elif case == "other_release":
        (tmp_path / "firmware" / "5.bin").write_bytes(_image(version=5, size=5000, target=2))
        (tmp_path / "firmware" / "5.manifest.cbor").write_bytes(fw.manifest_for_image((tmp_path / "firmware" / "5.bin").read_bytes()).encode())
    elif case == "no_repository":
        repository = None
    elif case == "not_update":
        cid = uuid.UUID(store.create_command(17, "CMD_REBOOT", {"delay_s": 30}).command_id).bytes
    client = Client()
    assert answer_firmware_request(client, f"zs/v1/evt/{station}/fwreq", _req(cid, offset, length, station), "evt", event_store=store,
                                   firmware_repository=repository, now_us=now) == "fw_ignored"
    assert client.published == []


def test_operator_route_queues_the_release(tmp_path, monkeypatch):
    from app import app
    import station.router as router

    store = EventStore(tmp_path / "events.sqlite3")
    repo_dir = tmp_path / "firmware"
    release = fw.ReleaseRepository(repo_dir).add(_image(version=6), RELEASE)
    monkeypatch.setattr(router, "store", store)
    monkeypatch.setenv("ZS_FIRMWARE_DIR", str(repo_dir))
    client = TestClient(app)
    listed = client.get("/api/v1/firmware/releases").json()
    assert listed == [{"version": 6, "target": 1, "size": 5000, "sha256": release.manifest.sha256.hex(), "release_key_id": RELEASE.key_id.hex()}]
    ok = client.post("/api/v1/stations/17/firmware-update", json={"version": 6})
    assert ok.status_code == 200 and ok.json()["command"] == "CMD_UPDATE_FIRMWARE" and ok.json()["release"]["version"] == 6
    assert ok.json()["payload"] == release.command_payload()
    assert client.post("/api/v1/stations/17/firmware-update", json={"version": 7}).status_code == 404
    assert client.post("/api/v1/stations/17/firmware-update", json={"version": "6"}).status_code == 422
    assert [c.command for c in store.due_commands(int(time.time() * 1e6) + 1, 1)] == ["CMD_UPDATE_FIRMWARE"]
