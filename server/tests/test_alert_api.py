"""Output API dioneya.alert/1 (decision 7 of docs/ZVOOK_COMPARISON_DECISIONS_2026-09-30.md,
protocols/DIONEYA_ALERT_API_v1.md): the messages the fusion produces, their order and schema, HTTP polling,
WebSocket, webhook delivery over mutual TLS, and the separation of two targets by class and fundamental frequency."""

import datetime as dt
import http.server
import ipaddress
import json
import math
import re
import ssl
import struct
import threading
import time
from pathlib import Path

import cbor2
import httpx
import numpy as np
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fastapi.testclient import TestClient

from integration import alert_producer
from integration.webhook import Consumer, WebhookDispatcher, load_config
from station.service import StationFusionService
from station.store import EventStore
from tests.test_bearing_fusion import ARRIVALS, C, FRAME, T0, feed, publish, truth

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "protocols" / "schemas" / "dioneya.alert.1.schema.json").read_text())


# ---- a JSON Schema subset validator (the keywords the schema uses) --------------------------------------------------
def _resolve(ref: str) -> dict:
    node = SCHEMA
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return node


def _errors(value, schema: dict, path: str = "$") -> list[str]:
    if "$ref" in schema:
        return _errors(value, _resolve(schema["$ref"]), path)
    out = []
    types = schema.get("type")
    if types is not None:
        names = types if isinstance(types, list) else [types]
        checks = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
                  "string": lambda v: isinstance(v, str), "null": lambda v: v is None,
                  "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
                  "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)}
        if not any(checks[n](value) for n in names):
            return [f"{path}: {value!r} is not {names}"]
    if "const" in schema and value != schema["const"]:
        out.append(f"{path}: {value!r} != {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{path}: {value} < {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            out.append(f"{path}: {value} > {schema['maximum']}")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{path}: {value!r} does not match {schema['pattern']}")
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1 << 30):
            out.append(f"{path}: length of {value!r}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            out.append(f"{path}: fewer than {schema['minItems']} items")
        for i, item in enumerate(value):
            out += _errors(item, schema.get("items", {}), f"{path}[{i}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                out.append(f"{path}: missing {key}")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                out += _errors(item, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                out.append(f"{path}: unexpected {key}")
    if "oneOf" in schema:
        matching = sum(1 for option in schema["oneOf"] if not _errors(value, option, path))
        if matching != 1:
            out.append(f"{path}: matches {matching} of oneOf")
    return out


def assert_valid(messages: list[dict]):
    for m in messages:
        errors = _errors(m, SCHEMA)
        assert not errors, (m["type"], errors)


# ---- scene --------------------------------------------------------------------------------------------------------
class Clock:
    def __init__(self):
        self.offset = 0.0

    def __call__(self):
        return time.time() + self.offset


@pytest.fixture
def bridge(tmp_path):
    store = EventStore(tmp_path / "a.sqlite3")
    service = StationFusionService(store)
    service.alerts.tenant = "pilot1"
    service.alerts.clock = Clock()
    return store, service


def types(messages):
    return [m["type"] for m in messages]


def test_alert_track_and_lines_through_the_bridge(bridge):
    store, service = bridge
    streams = feed(store, service, (1, 2))
    messages = store.list_alerts(0, limit=10000)
    assert_valid(messages)
    assert [m["seq"] for m in messages] == sorted(m["seq"] for m in messages)
    assert len({m["msg_id"] for m in messages}) == len(messages)
    assert messages[0]["type"] == "alert.start" and messages[0]["alert"]["level"] == "warning"
    alert_id = messages[0]["alert_id"]
    assert alert_id.startswith("ALR-pilot1-") and all(m["alert_id"] == alert_id and m["tenant"] == "pilot1" for m in messages)
    assert {s["station_id"] for s in messages[0]["alert"]["stations"]} == {1}
    assert messages[0]["alert"]["stations"][0]["lat"] == pytest.approx(55.0)

    # bearing lines while no fused track carries the stations, at most one a second per station
    updates = [m for m in messages if m["type"] == "track.update"]
    lines = [m for m in messages if m["type"] == "bearing"]
    assert lines and updates
    assert max(m["seq"] for m in lines) < updates[0]["seq"]
    for station in (1, 2):
        times = [dt.datetime.fromisoformat(m["time"][:-1]) for m in lines if m["bearing"]["station"]["station_id"] == station]
        assert all((b - a).total_seconds() >= 1.0 for a, b in zip(times, times[1:]))
    line = lines[0]["bearing"]
    assert line["range_max_m"] == 5000.0 and line["class"]["code"] == "uav_piston" and re.fullmatch("[0-9a-f]{16}", line["track_event_id"])

    # the alert escalates and lists the track; track points one a second, newest only, forward in time
    escalations = [m for m in messages if m["type"] == "alert.update"]
    assert escalations[-1]["alert"]["level"] == "alert" and escalations[-1]["alert"]["tracks"] == [updates[0]["track"]["track_id"]]
    track_times = [m["time"] for m in updates]
    assert track_times == sorted(set(track_times))
    last = updates[-1]["track"]
    assert last["stations"] == [1, 2] and last["class"]["code"] == "uav_piston" and last["ended"] is None
    t_us = int(dt.datetime.fromisoformat(updates[-1]["time"][:-1]).replace(tzinfo=dt.timezone.utc).timestamp() * 1e6)
    e, n, _ = FRAME.to_enu(last["position"]["lat"], last["position"]["lon"], last["position"]["alt_msl_m"])
    assert math.hypot(*(np.array([e, n]) - truth(t_us * 1e-6)[:2])) < 3 * max(last["error"]["horizontal_m"], 50.0)
    assert abs(last["velocity"]["speed_mps"] - math.hypot(45, 5)) < 12.0

    # a redelivered batch adds nothing
    before = store.last_alert_seq()
    assert publish(store, service, 1, streams[1][10]) == "duplicate"
    assert store.last_alert_seq() == before

    # the track ends when its fusion goes quiet, the alert after two minutes of silence; each once
    clock = service.alerts.clock
    clock.offset = alert_producer.TRACK_END_US / 1e6 + 1
    service.alerts.sweep(force=True)
    ended = store.list_alerts(before)
    assert types(ended) == ["track.end"] and ended[0]["track"]["end_reason"] == "lost" and ended[0]["track"]["ended"]
    clock.offset = alert_producer.ALERT_END_US / 1e6 + 5
    service.alerts.sweep(force=True)
    service.alerts.sweep(force=True)
    tail = store.list_alerts(before)
    assert types(tail) == ["track.end", "alert.end"]
    assert tail[-1]["alert"]["ended"] and tail[-1]["alert"]["tracks"] == [last["track_id"]]
    assert_valid(tail)

    # the next detection opens a new alert
    assert publish(store, service, 1, detection2(1, int((T0 + 500) * 1e6), 1, 110.0, boot=8), "up") == "stored"
    fresh = store.list_alerts(tail[-1]["seq"])
    assert types(fresh) == ["alert.start"] and fresh[0]["alert_id"] != alert_id


def test_untrusted_time_gives_no_lines(bridge):
    store, service = bridge
    from tests.test_bearing_fusion import batches, detection, observe
    publish(store, service, 1, detection(1, int(ARRIVALS[0] * 1e6)), "up")
    for b in batches(1, observe(1, ARRIVALS[:20]), trust=4):
        publish(store, service, 1, b)
    assert types(store.list_alerts(0)) == ["alert.start"]


def test_a_failing_producer_does_not_stop_ingestion(bridge, monkeypatch):
    store, service = bridge

    def broken(*args):
        raise RuntimeError("consumer side broken")
    monkeypatch.setattr(service.alerts, "on_bearings", broken)
    monkeypatch.setattr(service.alerts, "on_track", broken)
    feed(store, service, (1, 2))
    assert store.list_tracks() and store.list_bearings(station_id=1)


# ---- two targets at once: class and fundamental keep their rays apart ----------------------------------------------
STATIONS2 = {1: (0.0, 0.0, 0.0), 2: (900.0, 0.0, 0.0), 3: (2600.0, 300.0, 0.0), 4: (3500.0, 1200.0, 0.0)}


def target_b(te: float) -> np.ndarray:
    t = te - T0
    return np.array([2200.0 - 20.0 * t, 2600.0 + 15.0 * t, 180.0])


def observe2(station: int, target, sigma: float = 1.5) -> list[dict]:
    rng = np.random.default_rng(40 + station)
    p = np.array(STATIONS2[station])
    rows = []
    for ta in ARRIVALS:
        te = ta
        for _ in range(10):
            te = ta - float(np.linalg.norm(target(te) - p)) / C
        v = target(te) - p
        rows.append({"time_us": int(round(ta * 1e6)),
                     "azimuth_deg": (math.degrees(math.atan2(v[0], v[1])) + rng.normal(0, sigma)) % 360.0,
                     "elevation_deg": math.degrees(math.atan2(v[2], math.hypot(v[0], v[1]))) + rng.normal(0, 2.0),
                     "sigma_deg": sigma})
    return rows


def detection2(station: int, time_us: int, class_id: int, f0_hz: float, boot: int = 7) -> bytes:
    lat, lon, alt = FRAME.to_geodetic(*STATIONS2[station])
    eid = (boot << 32) | station
    features = struct.pack("<" + "e" * 43, f0_hz, *([0.0] * 42))
    return cbor2.dumps({0: 4, 1: 2, 2: station, 3: eid & 0xFFFFFFFF, 4: eid >> 32, 5: eid, 6: time_us, 7: 0,
                        8: {0: int(round(lat * 1e7)), 1: int(round(lon * 1e7)), 2: int(round(alt * 10)), 4: class_id, 5: 200},
                        9: features, 10: {}, 12: {}, 13: {}, 14: {}}, canonical=True)


def feed_station(store, service, station: int, target, class_id: int, f0_hz: float):
    from tests.test_bearing_fusion import batches
    assert publish(store, service, station, detection2(station, int(ARRIVALS[0] * 1e6), class_id, f0_hz), "up") == "stored"
    for b in batches(station, observe2(station, target)):
        assert publish(store, service, station, b) == "stored"


def members(store) -> list[set[int]]:
    return sorted(({m["station_id"] for m in store.get_track(t["track_id"])["members"]} for t in store.list_tracks()), key=min)


def test_two_targets_same_class_form_a_ghost_pair(bridge):
    """The control: stations 1 and 3 hear different targets whose rays still cross; without a difference in class
    or fundamental the first two station tracks pair into a ghost."""
    store, service = bridge
    feed_station(store, service, 1, truth, 1, 110.0)
    feed_station(store, service, 3, target_b, 1, 115.0)
    assert members(store) == [{1, 3}]


@pytest.mark.parametrize("class_b,f0_b", [(3, 115.0), (1, 240.0)])     # another class, or the same class another note
def test_two_targets_are_kept_apart_by_class_or_fundamental(bridge, class_b, f0_b):
    store, service = bridge
    feed_station(store, service, 1, truth, 1, 110.0)
    feed_station(store, service, 3, target_b, class_b, f0_b)
    assert store.list_tracks() == []                                  # no ghost from 1 x 3
    feed_station(store, service, 2, truth, 1, 104.0)                  # Doppler-shifted note of the same engine
    feed_station(store, service, 4, target_b, class_b, f0_b * 1.05)
    assert members(store) == [{1, 2}, {3, 4}]
    for summary in store.list_tracks():
        track = store.get_track(summary["track_id"])
        target = truth if {m["station_id"] for m in track["members"]} == {1, 2} else target_b
        errs = [np.linalg.norm(np.array(FRAME.to_enu(p["lat"], p["lon"], p["alt_msl_m"])[:2]) - target(p["time_us"] * 1e-6)[:2])
                for p in track["track_points"]]
        assert np.median(errs) < 120.0
    classes = {m["track"]["track_id"]: m["track"]["class"] for m in store.list_alerts(0, limit=10000) if m["type"] == "track.update"}
    assert sorted(c["code"] for c in classes.values()) == sorted(["uav_piston", "uav_electric" if class_b == 3 else "uav_piston"])
    assert sorted(round(c["f0_hz"]) for c in classes.values()) == sorted([round(np.median([110.0, 104.0])), round(np.median([f0_b, f0_b * 1.05]))])


# ---- consumers: HTTP polling and WebSocket -------------------------------------------------------------------------
@pytest.fixture
def client(bridge, monkeypatch):
    store, service = bridge
    import station.router as router
    from app import app
    monkeypatch.setattr(router, "store", store)
    return TestClient(app)


def test_http_polling_pages_through_the_outbox(bridge, client):
    store, service = bridge
    feed(store, service, (1, 2))
    everything = store.list_alerts(0, limit=10000)
    got, after = [], 0
    while True:
        page = client.get("/api/v1/alerts", params={"after_seq": after, "limit": 7}).json()
        assert page["schema"] == "dioneya.alert/1"
        got += page["messages"]
        if not page["messages"]:
            break
        after = page["next_after_seq"]
    assert [m["seq"] for m in got] == [m["seq"] for m in everything]
    assert client.get("/api/v1/alerts", params={"tenant": "pilot2"}).json() == {
        "schema": "dioneya.alert/1", "messages": [], "next_after_seq": everything[-1]["seq"]}


def test_websocket_backlog_live_and_heartbeat(bridge, client):
    store, service = bridge
    feed(store, service, (1, 2))
    backlog = store.list_alerts(0, limit=10000)
    with client.websocket_connect("/api/v1/alerts/stream?after_seq=0&heartbeat_s=1") as ws:
        received = [ws.receive_json() for _ in backlog]
        assert [m["seq"] for m in received] == [m["seq"] for m in backlog]
        service.alerts.clock.offset = alert_producer.ALERT_END_US / 1e6 + 5
        service.alerts.sweep(force=True)                              # new messages arrive live
        live = [ws.receive_json(), ws.receive_json()]
        assert types(live) == ["track.end", "alert.end"]
        beat = ws.receive_json()
        assert beat["type"] == "heartbeat" and beat["seq"] == live[-1]["seq"]
        assert_valid([beat])
    with client.websocket_connect("/api/v1/alerts/stream?heartbeat_s=1") as ws:
        beat = ws.receive_json()                                      # default: only new messages
        assert beat["type"] == "heartbeat" and beat["seq"] == store.last_alert_seq()


# ---- webhook over mutual TLS ----------------------------------------------------------------------------------------
def _cert(subject: str, key, issuer_name, issuer_key, *, ca: bool = False, server: bool = False, client: bool = False):
    now = dt.datetime.now(dt.timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
               .issuer_name(issuer_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=1))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if server:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        builder = builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    if client:
        builder = builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
    return builder.sign(issuer_key, hashes.SHA256())


def _write(path: Path, cert=None, key=None) -> str:
    data = b""
    if cert is not None:
        data += cert.public_bytes(serialization.Encoding.PEM)
    if key is not None:
        data += key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    path.write_bytes(data)
    return str(path)


@pytest.fixture
def pki(tmp_path):
    """Two CAs: the consumer's (its HTTPS server) and Dioneya's (the webhook client certificate)."""
    out = {}
    for name in ("consumer", "dioneya", "stranger"):
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{name} CA")])
        out[f"{name}_ca_key"], out[f"{name}_ca"] = key, _cert(f"{name} CA", key, subject, key, ca=True)
        out[f"{name}_ca_pem"] = _write(tmp_path / f"{name}-ca.pem", out[f"{name}_ca"])
    skey = ec.generate_private_key(ec.SECP256R1())
    scert = _cert("127.0.0.1", skey, out["consumer_ca"].subject, out["consumer_ca_key"], server=True)
    out["server_cert"], out["server_key"] = _write(tmp_path / "srv.crt", scert), _write(tmp_path / "srv.key", key=skey)
    ckey = ec.generate_private_key(ec.SECP256R1())
    ccert = _cert("alert-client", ckey, out["dioneya_ca"].subject, out["dioneya_ca_key"], client=True)
    out["client_cert"], out["client_key"] = _write(tmp_path / "cli.crt", ccert), _write(tmp_path / "cli.key", key=ckey)
    return out


class Receiver:
    """The consumer: an HTTPS server that requires a client certificate of Dioneya's CA."""

    def __init__(self, pki, fail_first: int = 0):
        self.received, self.fail_left = [], fail_first
        receiver = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if receiver.fail_left > 0:
                    receiver.fail_left -= 1
                    self.send_response(503)
                else:
                    receiver.received.append((dict(self.headers), body, self.request.getpeercert()))
                    self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(pki["server_cert"], pki["server_key"])
        context.load_verify_locations(pki["dioneya_ca_pem"])
        context.verify_mode = ssl.CERT_REQUIRED
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"https://127.0.0.1:{self.server.server_address[1]}/dioneya"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def consumer(pki, receiver, **kw) -> Consumer:
    base = dict(name="platform", url=receiver.url, ca=pki["consumer_ca_pem"], cert=pki["client_cert"], key=pki["client_key"],
                start="earliest", heartbeat_s=3600.0)
    return Consumer(**{**base, **kw})


def drain(dispatcher: WebhookDispatcher, limit: int = 100):
    for _ in range(limit):
        if dispatcher.step() == 0:
            return


def test_webhook_delivers_in_order_over_mutual_tls(bridge, pki, tmp_path):
    store, service = bridge
    feed(store, service, (1, 2))
    expected = store.list_alerts(0, limit=10000)
    receiver = Receiver(pki, fail_first=2)
    try:
        dispatcher = WebhookDispatcher(store, consumer(pki, receiver))
        assert dispatcher.step() == -1 and dispatcher.backoff() == 1.0          # 503: retried, nothing skipped
        assert dispatcher.step() == -1 and dispatcher.backoff() == 2.0
        drain(dispatcher)
        bodies = [b for _, b, _ in receiver.received]
        assert [b["seq"] for b in bodies] == [m["seq"] for m in expected]
        headers, first, peer = receiver.received[0]
        assert headers["Idempotency-Key"] == first["msg_id"] and headers["X-Dioneya-Seq"] == str(first["seq"])
        assert headers["X-Dioneya-Schema"] == "dioneya.alert/1"
        assert dict(x[0] for x in peer["subject"])["commonName"] == "alert-client"   # the server saw our certificate
        assert store.alert_cursor("webhook:platform") == expected[-1]["seq"]

        # a restart resumes after the cursor; only new messages follow
        service.alerts.clock.offset = alert_producer.ALERT_END_US / 1e6 + 5
        service.alerts.sweep(force=True)
        again = WebhookDispatcher(store, consumer(pki, receiver))
        drain(again)
        assert [b["type"] for _, b, _ in receiver.received[len(expected):]] == ["track.end", "alert.end"]

        # heartbeat on an idle channel, another tenant filtered out
        idle = WebhookDispatcher(store, consumer(pki, receiver, heartbeat_s=0.0))
        assert idle.step() == 0 and receiver.received[-1][1]["type"] == "heartbeat"
        other = WebhookDispatcher(store, consumer(pki, receiver, name="other", tenants=("pilot2",), heartbeat_s=3600.0))
        count = len(receiver.received)
        drain(other)
        assert len(receiver.received) == count and store.alert_cursor("webhook:other") == store.last_alert_seq()
        assert_valid([b for _, b, _ in receiver.received])
    finally:
        receiver.close()


def test_webhook_refuses_without_mutual_tls(bridge, pki):
    store, service = bridge
    feed(store, service, (1, 2))
    receiver = Receiver(pki)
    try:
        # the consumer's server is not trusted: nothing is sent
        wrong_ca = WebhookDispatcher(store, consumer(pki, receiver, ca=pki["stranger_ca_pem"]))
        assert wrong_ca.step() == -1 and receiver.received == []
        # without a client certificate the consumer refuses the connection
        bare = httpx.Client(verify=ssl.create_default_context(cafile=pki["consumer_ca_pem"]))
        with pytest.raises(httpx.HTTPError):
            bare.post(receiver.url, json={})
        assert receiver.received == []
    finally:
        receiver.close()
    with pytest.raises(ValueError, match="HTTPS"):
        consumer(pki, receiver, url="http://127.0.0.1/x")
    with pytest.raises(ValueError, match="cert is required"):
        consumer(pki, receiver, cert="")


def test_webhook_config_file(tmp_path, pki):
    path = tmp_path / "webhooks.json"
    path.write_text(json.dumps({"consumers": [{"name": "platform", "url": "https://example.org/a", "tenants": ["pilot1"],
                                                "ca": pki["consumer_ca_pem"], "cert": pki["client_cert"], "key": pki["client_key"]}]}))
    (c,) = load_config(path)
    assert c.tenants == ("pilot1",) and c.start == "latest" and c.cursor_name == "webhook:platform"
    path.write_text(json.dumps({"consumers": [{"name": "a", "url": "https://x/", "ca": "c", "cert": "c", "key": "k"}] * 2}))
    with pytest.raises(ValueError, match="unique"):
        load_config(path)
