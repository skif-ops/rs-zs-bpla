"""ICD addendum I, model package: the "DIOM" package of the station classifier (encode/parse with every refusal of the
station's zs_model_load), the shared vector, the manifest of target 3 and the model repository, model-sign and the
exporter's --package, the bridge serving model chunks from its own repository, and the operator routes."""
import hashlib
import importlib.util
import struct
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from station import firmware_codec as fw
from station import model_codec as mc
from station.command_codec import validate_command_payload
from station.mqtt_bridge import answer_firmware_request, handle_message
from station.store import EventStore

ROOT = Path(__file__).resolve().parents[2]
RELEASE = fw.ReleaseSigner(Ed25519PrivateKey.from_private_bytes(bytes(range(65, 97))))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _gen():
    return _load("gen_model_update", ROOT / "tools" / "generate_model_update_vector.py")


def _builtin():
    return _gen().builtin_model()


def _package(version=5):
    return mc.encode_model(_builtin(), version)


def test_model_vector_is_current():
    assert (ROOT / "firmware" / "generated" / "zs_model_update_vector.h").read_text() == _gen().render()


def test_package_round_trip_and_layout():
    model = _builtin()
    raw = _package(5)
    n = len(model["class_id"])
    assert len(raw) == mc.package_bytes(n) and raw[:4] == b"DIOM" and mc.MIN_BYTES == 556
    assert struct.unpack_from("<IHHHHII", raw) == (mc.MAGIC, 1, 43, n, 0, 5, 1) and raw[20:32] == bytes(12)
    p = mc.parse_model(raw)
    assert p.version == 5 and p.class_count == n and p.describe() == "m5"
    assert np.array_equal(p.class_id, model["class_id"].astype(np.uint8))
    assert np.array_equal(p.centroids, model["centroids"].astype(np.float32))
    assert mc.encode_model(p.as_model(), 5) == raw                                  # float32 survives the round trip
    # the station's prediction mirror gives the same answers on the package as on the float64 table (away from ties)
    esm = _load("export_station_model", ROOT / "server" / "tools" / "export_station_model.py")
    X = model["mean"] + model["centroids"][::5] * model["std"]
    assert np.array_equal(esm.predict(p.as_model(), X)[0], esm.predict(model, X)[0])


def _mutate(raw, offset, data):
    b = bytearray(raw)
    b[offset:offset + len(data)] = data
    return bytes(b)


@pytest.mark.parametrize("case, match", [
    ("magic", "format 1"), ("format", "format 1"), ("features", "format 1"), ("reserved", "format 1"),
    ("version0", "format 1"), ("feature_set", "feature set 2"), ("short", "size"), ("classes", "size"),
    ("nan", "non-finite"), ("std", "negative"), ("radius", "non-positive"), ("class", "unknown class"),
    ("padding", "unknown class"), ("tiny", "too short"),
])
def test_parse_refuses_what_the_station_refuses(case, match):
    raw = _package()
    n = struct.unpack_from("<H", raw, 8)[0]
    ids = 32 + 8 * 43
    radius = ids + ((n + 3) & ~3)
    bad = {
        "magic": _mutate(raw, 0, b"X"), "format": _mutate(raw, 4, b"\x02"), "features": _mutate(raw, 6, b"\x2a"),
        "reserved": _mutate(raw, 25, b"\x01"), "version0": _mutate(raw, 12, bytes(4)), "feature_set": _mutate(raw, 16, b"\x02"),
        "short": raw[:-1], "classes": _mutate(raw, 8, bytes([n - 1])), "nan": _mutate(raw, 36, struct.pack("<f", float("nan"))),
        "std": _mutate(raw, 32 + 4 * 43, struct.pack("<f", -1.0)), "radius": _mutate(raw, radius, struct.pack("<f", 0.0)),
        "class": _mutate(raw, ids, b"\x04"), "padding": _mutate(raw, ids + n, b"\x01") if radius > ids + n else _mutate(raw, ids, b"\x00"),
        "tiny": raw[:20],
    }[case]
    with pytest.raises(ValueError, match=match):
        mc.parse_model(bad)


def test_encode_refuses_bad_models():
    model = _builtin()
    with pytest.raises(ValueError, match="version"):
        mc.encode_model(model, 0)
    with pytest.raises(ValueError, match="unknown class"):
        mc.encode_model({**model, "class_id": np.array([0] * len(model["class_id"]))}, 1)
    with pytest.raises(ValueError, match="radius"):
        mc.encode_model({**model, "radius": np.zeros(len(model["radius"]))}, 1)
    with pytest.raises(ValueError, match="class count"):
        mc.encode_model({**model, "class_id": np.array([1] * 97), "radius": np.ones(97), "centroids": np.zeros((97, 43))}, 1)
    with pytest.raises(ValueError, match="mean"):
        mc.encode_model({**model, "mean": model["mean"][:42]}, 1)


def test_manifest_and_repository(tmp_path):
    raw = _package(5)
    m = mc.manifest_for_model(raw)
    assert m == fw.Manifest(target=3, version=5, size=len(raw), sha256=hashlib.sha256(raw).digest())
    assert fw.TARGETS[3] == "model" and mc.MAX_BYTES <= mc.CAPACITY_BYTES
    repo = mc.ModelRepository(tmp_path / "models")
    release = repo.add(raw, RELEASE)
    assert repo.versions() == [5] and repo.get(5) == release and release.manifest == m
    assert fw.verify_release(release.manifest_bytes, release.key_id, release.signature, [RELEASE.public_raw]) == m
    payload = release.command_payload()
    validate_command_payload(fw.UPDATE_COMMAND, payload)
    # a firmware image is no model package and a model package no firmware image
    with pytest.raises(ValueError):
        repo.add(b"\x00" * 5000, RELEASE)
    with pytest.raises(ValueError, match=".fw_info"):
        fw.ReleaseRepository(tmp_path / "firmware").add(raw, RELEASE)
    # an image release dropped into the model directory is refused on load
    image = _load("gen_fw_update", ROOT / "tools" / "generate_fw_update_vector.py").test_image(version=6, size=5000)
    fw.ReleaseRepository(tmp_path / "models").add(image, RELEASE)
    with pytest.raises(ValueError, match="not a model manifest"):
        repo.get(6)


def test_model_sign_and_export_package(tmp_path):
    from pki.cli import main as pki_main

    key = tmp_path / "release.pem"
    assert pki_main(["fw-release-key", "--out", str(key)]) == 0
    pkg = tmp_path / "m7.diom"
    pkg.write_bytes(_package(7))
    repo_dir = tmp_path / "models"
    assert pki_main(["model-sign", "--key", str(key), "--model", str(pkg), "--out", str(repo_dir)]) == 0
    assert pki_main(["model-sign", "--key", str(key), "--model", str(pkg), "--out", str(repo_dir)]) == 2      # exists
    assert pki_main(["model-sign", "--key", str(key), "--model", str(pkg), "--out", str(repo_dir), "--force"]) == 0
    (tmp_path / "bad.diom").write_bytes(_package(8)[:-4])
    assert pki_main(["model-sign", "--key", str(key), "--model", str(tmp_path / "bad.diom"), "--out", str(repo_dir)]) == 2
    assert mc.ModelRepository(repo_dir).versions() == [7]


class Client:
    def __init__(self):
        self.published, self.acked = [], []

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, payload, qos, retain))
        return SimpleNamespace(rc=0)

    def ack(self, mid, qos):
        self.acked.append(mid)


def _req(cid, offset, length, station=17):
    return fw.encode_request(fw.FirmwareRequest(station, cid, offset, length))


def test_bridge_serves_model_chunks_from_the_model_repository(tmp_path):
    store = EventStore(tmp_path / "events.sqlite3")
    models = mc.ModelRepository(tmp_path / "models")
    firmware = fw.ReleaseRepository(tmp_path / "firmware")
    release = models.add(_package(5), RELEASE)
    cid = uuid.UUID(store.create_command(17, "CMD_UPDATE_FIRMWARE", release.command_payload()).command_id).bytes
    now = int(time.time() * 1e6)
    client = Client()
    assert answer_firmware_request(client, "zs/v1/evt/17/fwreq", _req(cid, 8192, 328), "evt", event_store=store,
                                   firmware_repository=firmware, model_repository=models, now_us=now) == "fw_served"
    (topic, payload, qos, _), = client.published
    assert topic == "zs/v1/evt/17/fw" and qos == 0 and fw.decode_chunk(payload) == (17, cid, 8192, release.image[8192:])
    # without a model repository (or only the firmware one) a model request is dropped
    for kwargs in ({"firmware_repository": firmware}, {}):
        client = Client()
        assert answer_firmware_request(client, "zs/v1/evt/17/fwreq", _req(cid, 0, 1024), "evt", event_store=store,
                                       now_us=now, **kwargs) == "fw_ignored"
    # past the end of the package
    assert answer_firmware_request(Client(), "zs/v1/evt/17/fwreq", _req(cid, 8192, 329), "evt", event_store=store,
                                   model_repository=models, now_us=now) == "fw_ignored"
    # through handle_message
    client = Client()
    msg = SimpleNamespace(topic="zs/v1/evt/17/fwreq", payload=_req(cid, 0, 1024), mid=9, qos=1, retain=False)
    assert handle_message(client, msg, "evt", True, event_store=store, model_repository=models)
    assert client.acked == [9] and fw.decode_chunk(client.published[0][1])[3] == release.image[:1024]


def test_operator_routes(tmp_path, monkeypatch):
    from app import app
    import station.router as router

    store = EventStore(tmp_path / "events.sqlite3")
    repo_dir = tmp_path / "models"
    release = mc.ModelRepository(repo_dir).add(_package(5), RELEASE)
    monkeypatch.setattr(router, "store", store)
    monkeypatch.setenv("ZS_MODEL_DIR", str(repo_dir))
    client = TestClient(app)
    listed = client.get("/api/v1/models/releases").json()
    assert listed == [{"version": 5, "target": 3, "size": release.manifest.size, "classes": len(_builtin()["class_id"]),
                       "sha256": release.manifest.sha256.hex(), "release_key_id": RELEASE.key_id.hex()}]
    ok = client.post("/api/v1/stations/17/model-update", json={"version": 5})
    assert ok.status_code == 200 and ok.json()["command"] == "CMD_UPDATE_FIRMWARE" and ok.json()["model"]["version"] == 5
    assert ok.json()["payload"] == release.command_payload()
    assert client.post("/api/v1/stations/17/model-update", json={"version": 6}).status_code == 404
    assert client.post("/api/v1/stations/17/model-update", json={"version": 0}).status_code == 422
    (repo_dir / "5.bin").write_bytes(b"x")
    assert client.post("/api/v1/stations/17/model-update", json={"version": 5}).status_code == 409
    assert client.get("/api/v1/models/releases").json() == [{"version": 5, "error": "inconsistent"}]
