"""MQTT audio upload on the server (ICD addendum B): chunk authorisation against the request, parts that survive a
bridge restart, assembly into a WAV, re-selection after a lost session, auto-request per detection episode, ACL and
the operator endpoints."""
import hashlib
import math
import time
import uuid
import wave
from pathlib import Path
from types import SimpleNamespace

import cbor2
import pytest
from fastapi.testclient import TestClient

from pki.mosquitto import render_acl, station_topics
from station import audio_ingest
from station.audio_chunk_codec import (
    AUDIO_CHUNK_DATA_MAX,
    CODEC_IMA_ADPCM_1S,
    AudioChunk,
    chunk_count,
    encode_chunk,
    ima_encode_block,
)
from station.audio_ingest import ingest_audio_chunk
from station.cbor_codec import decode_cbor, decode_detection_obj
from station.mqtt_bridge import handle_message, request_event_audio
from station.service import StationFusionService
from station.store import EventStore

RATE = 8000
T0 = 1_800_000_000_000_000


def segment_bytes(seconds: int, salt: int) -> bytes:
    """Independent 1 s IMA-ADPCM blocks, as the station's prehistory records are."""
    out = b""
    for s in range(seconds):
        pcm = [int(8000 * math.sin(2 * math.pi * (200 + 50 * salt) * (i / RATE)) + 100 * s) for i in range(RATE)]
        out += ima_encode_block(pcm)
    return out


def chunks(data: bytes, *, command_id: str, station_id: int = 17, event_id: int = 42, segment: int = 0,
           start_us: int = T0, digest: bytes | None = None) -> list[bytes]:
    count = chunk_count(len(data))
    sha = digest or hashlib.sha256(data).digest()
    return [encode_chunk(AudioChunk(station_id, uuid.UUID(command_id).bytes, event_id, segment, i, count, CODEC_IMA_ADPCM_1S,
                                    RATE, start_us, sha, data[i * AUDIO_CHUNK_DATA_MAX:(i + 1) * AUDIO_CHUNK_DATA_MAX]))
            for i in range(count)]


class Client:
    def __init__(self):
        self.acks, self.published = [], []

    def ack(self, mid, qos):
        self.acks.append(mid)

    def publish(self, topic, payload, qos, retain):
        self.published.append(topic)
        return SimpleNamespace(rc=0)


def msg(payload: bytes, mid: int, topic: str = "zs/v1/evt/17/audio"):
    return SimpleNamespace(topic=topic, payload=payload, mid=mid, qos=1, retain=False)


def test_both_segments_assemble_across_a_bridge_restart(tmp_path: Path):
    db = tmp_path / "events.sqlite3"
    store = EventStore(db)
    cmd = store.create_command(17, "CMD_REQUEST_AUDIO", {"event_id": 42, "segment": "both"})
    pre, post = segment_bytes(3, 1), segment_bytes(2, 2)
    pre_chunks = chunks(pre, command_id=cmd.command_id, segment=0, start_us=T0 - 3_000_000)
    post_chunks = chunks(post, command_id=cmd.command_id, segment=1, start_us=T0)
    client = Client()
    # half of pre, out of order, with a QoS 1 duplicate
    order = [2, 0, 1, 0]
    for mid, i in enumerate(order):
        assert handle_message(client, msg(pre_chunks[i], mid), "evt", True, event_store=store)
    assert store.audio_upload_progress(17, cmd.command_id) == {0: (3, len(pre_chunks))}
    # the bridge restarts: a new store object on the same database still has the parts
    store = EventStore(db)
    for mid, c in enumerate(pre_chunks[3:] + post_chunks, start=10):
        assert handle_message(client, msg(c, mid), "evt", True, event_store=store)
    assert client.acks == list(range(4)) + list(range(10, 10 + len(pre_chunks) - 3 + len(post_chunks)))
    rows = {r["segment"]: r for r in store.list_audio(17, 42)}
    assert set(rows) == {"pre", "post"} and store.audio_upload_progress(17, cmd.command_id) == {}
    assert rows["pre"]["start_time_us"] == T0 - 3_000_000 and rows["pre"]["duration_ms"] == 3000 and rows["post"]["duration_ms"] == 2000
    with wave.open(rows["pre"]["path"]) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (RATE, 1, 2, 3 * RATE)
    assert Path(rows["pre"]["path"]).parent == store.audio_root / "17" / "42"
    # a late duplicate after completion changes nothing
    assert ingest_audio_chunk(post_chunks[0], 17, event_store=store) == "already"


@pytest.mark.parametrize("case", ["unknown", "other_station", "other_event", "not_requested", "topic", "other_command"])
def test_chunks_that_do_not_answer_our_request_are_discarded(tmp_path: Path, case: str):
    store = EventStore(tmp_path / "events.sqlite3")
    cmd = store.create_command(17, "CMD_REQUEST_AUDIO", {"event_id": 42, "segment": "pre"})
    data = segment_bytes(1, 1)
    kwargs = {"command_id": cmd.command_id}
    topic_station = 17
    if case == "unknown":
        kwargs["command_id"] = str(uuid.uuid4())
    elif case == "other_station":
        other = store.create_command(18, "CMD_REQUEST_AUDIO", {"event_id": 42, "segment": "pre"})
        kwargs["command_id"] = other.command_id
    elif case == "other_event":
        kwargs["event_id"] = 43
    elif case == "not_requested":
        kwargs["segment"] = 1
    elif case == "topic":
        topic_station = 18
    elif case == "other_command":
        kwargs["command_id"] = store.create_command(17, "CMD_REBOOT", {"delay_s": 10}).command_id
    client = Client()
    payload = chunks(data, **kwargs)[0]
    assert not handle_message(client, msg(payload, 1, f"zs/v1/evt/{topic_station}/audio"), "evt", True, event_store=store)
    assert client.acks == [1]                                  # invalid input is dropped, never retried
    assert store.list_audio(17, 42) == [] and store.audio_upload_progress(17, kwargs["command_id"]) == {}


def test_digest_mismatch_drops_the_parts(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    cmd = store.create_command(17, "CMD_REQUEST_AUDIO", {"event_id": 42, "segment": "pre"})
    bad = chunks(segment_bytes(2, 1), command_id=cmd.command_id, digest=b"\x01" * 32)
    for c in bad[:-1]:
        assert ingest_audio_chunk(c, 17, event_store=store) == "stored"
    with pytest.raises(ValueError, match="digest"):
        ingest_audio_chunk(bad[-1], 17, event_store=store)
    assert store.audio_upload_progress(17, cmd.command_id) == {} and store.list_audio(17, 42) == []


def test_reselected_segment_replaces_the_old_parts(tmp_path: Path):
    """The session broke mid-upload; after the redelivery the station selected a different run (the ring moved on)."""
    store = EventStore(tmp_path / "events.sqlite3")
    cmd = store.create_command(17, "CMD_REQUEST_AUDIO", {"event_id": 42, "segment": "post"})
    first = chunks(segment_bytes(2, 1), command_id=cmd.command_id, segment=1)
    second = chunks(segment_bytes(3, 2), command_id=cmd.command_id, segment=1, start_us=T0 + 500_000)
    assert ingest_audio_chunk(first[0], 17, event_store=store) == "stored"
    statuses = [ingest_audio_chunk(c, 17, event_store=store) for c in second]
    assert statuses[-1] == "complete" and statuses[:-1] == ["stored"] * (len(second) - 1)
    (row,) = store.list_audio(17, 42)
    assert row["start_time_us"] == T0 + 500_000 and row["duration_ms"] == 3000


def test_pending_parts_are_bounded_per_station(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(audio_ingest, "MAX_PENDING_PARTS_PER_STATION", 3)
    store = EventStore(tmp_path / "events.sqlite3")
    cmd = store.create_command(17, "CMD_REQUEST_AUDIO", {"event_id": 42, "segment": "pre"})
    parts = chunks(segment_bytes(3, 1), command_id=cmd.command_id)
    for c in parts[:3]:
        ingest_audio_chunk(c, 17, event_store=store)
    with pytest.raises(ValueError, match="pending"):
        ingest_audio_chunk(parts[3], 17, event_store=store)


def detection(event_id: int, time_trust: int = 1) -> bytes:
    return cbor2.dumps({0: 4, 1: 2, 2: 17, 3: event_id, 4: 9, 5: event_id, 6: 1_700_000, 7: 0,
                        8: {14: time_trust}, 10: {}, 12: {}, 13: {}, 14: {}}, canonical=True)


def test_auto_request_once_per_episode_and_only_for_new_trusted_detections(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    fusion = StationFusionService(store)
    requested = []

    def on_new(det):
        cmd = request_event_audio(det, segment="both", min_gap_us=120_000_000, now_us=int(time.time() * 1e6), event_store=store)
        requested.append(cmd.payload if cmd else None)

    client = Client()
    up = "zs/v1/evt/17/up"
    first = detection(100)
    assert handle_message(client, msg(first, 1, up), "evt", True, event_store=store, fusion_service=fusion, on_new_detection=on_new)
    assert requested == [{"event_id": 100, "segment": "both", "event_time_us": 1_700_000}]   # the time goes along
    # the same detection redelivered: stored already, no second request
    assert handle_message(client, msg(first, 2, up), "evt", True, event_store=store, fusion_service=fusion, on_new_detection=on_new)
    assert len(requested) == 1
    # an update of the same episode within the gap: no request
    assert handle_message(client, msg(detection(101), 3, up), "evt", True, event_store=store, fusion_service=fusion, on_new_detection=on_new)
    assert requested[-1] is None
    # after the gap the next episode is asked for again
    later = request_event_audio(decode_detection_obj(decode_cbor(detection(104))), segment="both", min_gap_us=120_000_000,
                                now_us=int(time.time() * 1e6) + 121_000_000, event_store=store)
    assert later is not None and later.payload == {"event_id": 104, "segment": "both", "event_time_us": 1_700_000}
    assert client.published.count("zs/v1/evt/17/receipt") == 3            # every delivery still gets its receipt
    # the station said its time was not synchronised: it would refuse (REJECTED 3)
    unsynced = decode_detection_obj(decode_cbor(detection(102, time_trust=4)))
    assert request_event_audio(unsynced, segment="both", min_gap_us=0, now_us=0, event_store=store) is None
    assert request_event_audio(decode_detection_obj(decode_cbor(detection(103))), segment="off", min_gap_us=0, now_us=0, event_store=store) is None


def test_follow_up_failure_does_not_block_the_ack(tmp_path: Path):
    store = EventStore(tmp_path / "events.sqlite3")
    client = Client()

    def broken(det):
        raise RuntimeError("boom")

    assert handle_message(client, msg(detection(200), 7, "zs/v1/evt/17/up"), "evt", True, event_store=store,
                          fusion_service=StationFusionService(store), on_new_detection=broken)
    assert client.acks == [7]


def test_acl_lets_the_station_write_and_the_bridge_read_the_audio_topic():
    row = SimpleNamespace(serial="DIO-1", station_id=3, tenant="pilot1")
    assert ("write", "zs/v1/pilot1/3/audio") in station_topics(row)
    acl = render_acl(SimpleNamespace(active=lambda: [row]))
    bridge, station = acl.split("user DIO-1")
    assert "topic read zs/v1/pilot1/+/audio" in bridge and "topic write zs/v1/pilot1/3/audio" in station


def test_operator_endpoints_list_and_serve_the_wav(tmp_path: Path, monkeypatch):
    from app import app
    import station.router as router

    store = EventStore(tmp_path / "events.sqlite3")
    monkeypatch.setattr(router, "store", store)
    cmd = store.create_command(17, "CMD_REQUEST_AUDIO", {"event_id": 42, "segment": "pre"})
    for c in chunks(segment_bytes(1, 1), command_id=cmd.command_id):
        ingest_audio_chunk(c, 17, event_store=store)
    client = TestClient(app)
    listing = client.get("/api/v1/stations/17/events/42/audio").json()
    assert [(x["segment"], x["duration_ms"]) for x in listing] == [("pre", 1000)]
    wav = client.get(listing[0]["url"])
    assert wav.status_code == 200 and wav.headers["content-type"] == "audio/wav" and wav.content[:4] == b"RIFF"
    assert client.get("/api/v1/stations/17/events/42/audio/post.wav").status_code == 404
    assert client.get("/api/v1/stations/17/events/42/audio/..%2Fx.wav").status_code == 404


def test_operator_audio_request_carries_the_stored_event_time(tmp_path: Path, monkeypatch):
    """A station that rebooted no longer knows its earlier events: the request carries the detection's time."""
    from app import app
    import station.router as router

    store = EventStore(tmp_path / "events.sqlite3")
    monkeypatch.setattr(router, "store", store)
    store.save_detection(decode_detection_obj(decode_cbor(detection(300))))
    client = TestClient(app)
    known = client.post("/api/v1/stations/17/audio-request", json={"event_id": 300, "segment": "post"}).json()
    assert known["payload"] == {"event_id": 300, "segment": "post", "start_offset_ms": None, "duration_ms": None, "event_time_us": 1_700_000}
    unknown = client.post("/api/v1/stations/17/audio-request", json={"event_id": 301}).json()
    assert "event_time_us" not in unknown["payload"]                     # nothing to add: the station decides
    explicit = client.post("/api/v1/stations/17/audio-request", json={"event_id": 301, "event_time_us": 5}).json()
    assert explicit["payload"]["event_time_us"] == 5
