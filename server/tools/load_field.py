#!/usr/bin/env python3
"""Load, reconnect and duplicate-delivery check of the Muhoed ingest with a pilot-size field on one host
(server/EVT_PRE_20_RELEASE_AUDIT.md item 5, the "20-station soak" of the release gate;
docs/SERVER_LOAD_FIELD_2026-10-03.md).

41 synthetic stations (two groups of 20 along two roads, tenants pilot1 and pilot2, and the bench sample 41) publish
what real stations publish: compact CBOR heartbeats every minute, a detection at the rising edge of every tracking
window and an update every 5 s while the target is heard, bearing batches (schema 2, two samples a second) of the
window, and the audio of the event (two 30 s IMA-ADPCM segments in 3072-byte chunks) after the bridge's audio request.
Targets fly straight passes over the field at 25..45 m/s; a station hears a target within 1800 m, so most passes are
heard by two or three neighbours and the fusion gets real work (system events of two stations, fused tracks of the
bearings, dioneya.alert/1 messages).

Everything goes through the bridge code path (station.mqtt_bridge.handle_message with a recording MQTT client: decode,
dedup, fusion, application receipts, audio requests) into ONE shared SQLite database, one worker process per tenant
like the bridge containers of the deployment, while a reader process asks the store what the web UI asks (events,
tracks, stations, alerts, storage).  Delivery is as fast as the host allows: the simulated day is not waited for.

Faults of a real link (all on by default, see --help): QoS 1 redeliveries of single messages, the redelivery of the
last unacknowledged messages of a station after its reconnect, a station outage after which its backlog arrives in
one burst (store-and-forward over 2G), and bridge restarts (the fusion state of the process is lost, the database
stays).  Expected outcome, checked with --check: every unique detection, bearing sample and audio segment is stored
exactly once, every redelivery is answered as a duplicate with the same receipt, no message stays unacknowledged
(a "processing error" leaves a QoS 1 message in flight, and twenty of them stall a Mosquitto client), the readers
never hit a locked database, and the throughput leaves a margin over real time.

Usage:  python tools/load_field.py --hours 2 --out /tmp/load --check        (about a minute)
        python tools/load_field.py --hours 24 --episodes 5 --out /tmp/soak   (the soak of a pilot day)
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import io
import json
import math
import multiprocessing as mp
import random
import re
import statistics
import struct
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import cbor2

SERVER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_ROOT))

LAT0, LON0, ALT0 = 55.0, 37.0, 150.0
M_PER_DEG = 111320.0
WALL0_US = 1_800_000_000_000_000                     # the stations' wall clock at scene time 0
HEAR_RANGE_M = 1800.0                               # a station hears the target within this slant range
UPDATE_S = 5.0                                      # detection updates while the window is open
BEARING_S = 1.0                                     # one batch a second, two samples
HEARTBEAT_S = 60.0
AUDIO_RATE = 8000
AUDIO_SEGMENT_S = 30
AUDIO_CHUNK_DATA = 3072
AUDIO_AFTER_S = 15.0                                # the station starts the upload this long after the request
AUDIO_CHUNK_GAP_S = 0.75                            # 3072 bytes at the modem's ~4 kB/s
STATION_SPACING_M = 1200.0


@dataclass(frozen=True)
class Station:
    station_id: int
    tenant: str
    enu: tuple[float, float, float]

    @property
    def geodetic(self) -> tuple[float, float, float]:
        e, n, u = self.enu
        return LAT0 + n / M_PER_DEG, LON0 + e / (M_PER_DEG * math.cos(math.radians(LAT0))), ALT0 + u


@dataclass(frozen=True)
class Pass:
    index: int
    start_us: int
    origin: tuple[float, float, float]           # position at start (m, field frame)
    velocity: tuple[float, float, float]         # m/s
    seconds: float
    f0_hz: float
    class_id: int                                # 1 piston, 3 electric

    def at(self, t_s: float) -> tuple[float, float, float]:
        return tuple(self.origin[k] + self.velocity[k] * t_s for k in range(3))


def make_field() -> list[Station]:
    """Two roads 6 km apart, twenty poles each at 1200 m with a 250 m zigzag off the road (so that neighbours are not
    collinear), tenants pilot1 and pilot2; the bench sample 41 between the roads."""
    stations = []
    for i in range(20):
        stations.append(Station(i + 1, "pilot1", (i * STATION_SPACING_M, 250.0 if i % 2 else -250.0, 0.0)))
    for i in range(20):
        stations.append(Station(i + 21, "pilot2", (i * STATION_SPACING_M + 600.0, 6000.0 + (250.0 if i % 2 else -250.0), 0.0)))
    stations.append(Station(41, "bench", (11400.0, 3000.0, 0.0)))
    return stations


def scenario_stations(count: int, tenant: str = "", station_id_base: int = 1000) -> list[Station]:
    """Keep the field geometry while giving an isolated bench its own tenant and virtual IDs."""
    if not 1 <= count <= 41:
        raise ValueError("station count must be between 1 and 41")
    stations = make_field()[:count]
    if not tenant:
        return stations
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}", tenant) is None:
        raise ValueError("invalid tenant")
    if station_id_base < 0 or station_id_base + count > 0xFFFFFFFF:
        raise ValueError("virtual station IDs outside uint32 range")
    return [Station(station_id_base + i + 1, tenant, s.enu) for i, s in enumerate(stations)]


def plan_passes(rng: random.Random, stations: list[Station], hours: float, episodes_per_station_day: float) -> list[Pass]:
    """Straight passes crossing within 500 m of a random station; a pass is heard by about 2.5 stations, so this many
    passes give every station the asked number of episodes a day."""
    count = max(1, round(len(stations) * episodes_per_station_day / 2.5 * hours / 24.0))
    passes = []
    for i in range(count):
        anchor = rng.choice(stations)
        cx = anchor.enu[0] + rng.uniform(-500, 500)
        cy = anchor.enu[1] + rng.uniform(-500, 500)
        heading = rng.uniform(0, 2 * math.pi)
        speed = rng.uniform(25, 45)
        altitude = rng.uniform(150, 300)
        vx, vy = speed * math.sin(heading), speed * math.cos(heading)
        reach = 2600.0                                   # from 2.6 km before the crossing to 2.6 km after
        origin = (cx - vx / speed * reach, cy - vy / speed * reach, altitude)
        start_us = WALL0_US + int(rng.uniform(0, hours * 3600) * 1e6)
        passes.append(Pass(i, start_us, origin, (vx, vy, 0.0), 2 * reach / speed, rng.uniform(150, 260),
                           1 if rng.random() < 0.3 else 3))
    passes.sort(key=lambda p: p.start_us)
    return passes


def hearing_window(station: Station, p: Pass) -> tuple[float, float] | None:
    """(t_in, t_out) in pass seconds while the slant range is within HEAR_RANGE_M, sampled every second."""
    inside = [t for t in range(int(p.seconds) + 1) if math.dist(station.enu, p.at(t)) <= HEAR_RANGE_M]
    return (float(inside[0]), float(inside[-1])) if len(inside) >= 2 else None


def look(station: Station, p: Pass, t_s: float) -> tuple[float, float]:
    """Azimuth (clockwise from north) and elevation, degrees, from the station to the target."""
    x, y, z = p.at(t_s)
    de, dn, du = x - station.enu[0], y - station.enu[1], z - station.enu[2]
    az = math.degrees(math.atan2(de, dn)) % 360.0
    el = math.degrees(math.atan2(du, math.hypot(de, dn)))
    return az, el


# ---- what a station publishes --------------------------------------------------------------------------------------
def heartbeat_payload(st: Station, time_us: int, boot_id: int, uptime_s: int) -> bytes:
    lat, lon, alt = st.geodetic
    obj = {0: 2, 1: 3, 2: st.station_id, 3: time_us,
           4: {0: round(lat * 1e7), 1: round(lon * 1e7), 2: round(alt * 10), 3: 5, 4: 1, 5: 1},
           5: {0: 3, 1: 12, 2: 90, 3: True, 4: 50, 5: False, 6: False, 7: 0, 8: False, 9: False, 10: False, 11: False, 12: 1, 13: 1},
           6: {0: 82, 1: 12900, 2: 17000, 3: 200, 4: 12900, 5: -120, 6: 1500, 7: 0},
           7: {0: 2, 1: 0, 2: -85, 3: 120, 4: 0},
           8: "1.2.0", 9: "c46", 10: "revA", 11: True,
           12: {0: f"2500112345{st.station_id:05d}", 1: f"897010123456789{st.station_id:05d}", 2: "25001", 3: "25001",
                4: "internet", 5: f"10.10.{st.station_id // 256}.{st.station_id % 256}", 6: "10.10.0.1", 7: "1.1.1.1",
                8: "8.8.8.8", 9: 7, 10: 2, 11: True},
           13: {0: boot_id, 1: uptime_s, 2: 0}}
    return cbor2.dumps(obj, canonical=True)


def detection_payload(st: Station, p: Pass, t_s: float, *, seq_no: int, boot_id: int, event_id: int, rng: random.Random) -> bytes:
    lat, lon, alt = st.geodetic
    az, el = look(st, p, t_s)
    az = (az + rng.gauss(0, 2.0)) % 360.0
    feats = struct.pack("<" + "e" * 43, *[rng.uniform(-1, 1) for _ in range(43)])
    family = 1 if p.class_id == 1 else 2
    obj = {0: 4, 1: 2, 2: st.station_id, 3: seq_no, 4: boot_id, 5: event_id, 6: p.start_us + int(t_s * 1e6), 7: 0x04,
           8: {0: round(lat * 1e7), 1: round(lon * 1e7), 2: round(alt * 10), 3: True, 4: p.class_id, 5: 220, 6: 3, 7: 12,
               8: 90, 9: 50, 10: 1 if p.class_id == 1 else 0, 11: 32000, 12: 0, 13: 1, 14: 1, 15: 5},
           9: feats,
           10: {0: 82, 1: 12900, 2: 17000, 3: 200, 4: 2, 5: 0, 6: -85, 7: 120, 8: 0},
           11: {0: round(az * 100), 1: round(max(0.0, el) * 100), 2: 300, 3: True},
           12: {0: family, 1: 220, 2: 0, 3: 0, 4: 3, 5: 0},
           13: {0: round(p.origin[2] * 10), 1: 500, 2: round(math.hypot(*p.velocity[:2]) * 10), 3: 50, 4: 200, 5: 3, 6: 2},
           14: {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 2}}
    return cbor2.dumps(obj, canonical=True)


def bearing_payload(st: Station, p: Pass, t_s: float, *, boot_id: int, track_event_id: int, rng: random.Random) -> bytes:
    base_us = p.start_us + int(t_s * 1e6)
    rows = []
    for dt_ms in (0, 500):
        az, el = look(st, p, t_s + dt_ms / 1000.0)
        az = (az + rng.gauss(0, 2.0)) % 360.0
        rows.append([dt_ms, round(az * 100) % 36000, round(max(-90.0, min(90.0, el)) * 100), 300, 200, 8,
                     round(p.f0_hz * 10)])
    obj = {0: 2, 1: 7, 2: st.station_id, 3: boot_id, 4: track_event_id, 5: base_us, 6: 1, 7: 1, 8: rows}
    return cbor2.dumps(obj, canonical=True)


def audio_segment(rng: random.Random) -> bytes:
    """30 s of IMA-ADPCM blocks of one second (the station's codec): a hum with noise, encoded block by block."""
    from station.audio_chunk_codec import ima_encode_block

    out = bytearray()
    phase = 0.0
    for _ in range(AUDIO_SEGMENT_S):
        pcm = []
        for _ in range(AUDIO_RATE):
            phase += 2 * math.pi * 185.0 / AUDIO_RATE
            pcm.append(max(-32768, min(32767, int(6000 * math.sin(phase) + 2000 * math.sin(2 * phase) + rng.gauss(0, 800)))))
        out += ima_encode_block(pcm)
    return bytes(out)


def audio_chunks(st: Station, command_id: str, event_id: int, segment: int, start_us: int, data: bytes) -> list[bytes]:
    from station.audio_chunk_codec import AudioChunk, CODEC_IMA_ADPCM_1S, encode_chunk

    digest = hashlib.sha256(data).digest()
    count = -(-len(data) // AUDIO_CHUNK_DATA)
    out = []
    for i in range(count):
        chunk = AudioChunk(station_id=st.station_id, command_id=uuid.UUID(command_id).bytes, event_id=event_id,
                           segment=segment, chunk_index=i, chunk_count=count, codec=CODEC_IMA_ADPCM_1S,
                           sample_rate=AUDIO_RATE, segment_start_time_us=start_us, segment_sha256=digest,
                           data=data[i * AUDIO_CHUNK_DATA:(i + 1) * AUDIO_CHUNK_DATA])
        out.append(encode_chunk(chunk))
    return out


# ---- the stream of one tenant ----------------------------------------------------------------------------------------
@dataclass
class Faults:
    dup_p: float = 0.03                 # a message delivered twice (QoS 1 redelivery), seconds later
    reconnect_s: float = 900.0          # every station reconnects this often and redelivers its last messages
    inflight: int = 8                   # how many of its last messages a reconnect redelivers
    outage_p_per_h: float = 0.1         # a station loses the link this often (per station-hour) ...
    outage_s: tuple[float, float] = (300.0, 900.0)   # ... for this long, then its backlog comes in one burst
    restart_s: float = 3600.0           # the bridge process restarts this often (fusion memory lost)


@dataclass
class Expected:
    detections: int = 0
    bearing_samples: int = 0
    audio_segments: int = 0
    heartbeats: int = 0
    windows: int = 0
    multi_station_passes: int = 0


class RecordingClient:
    """What handle_message needs of paho: publish (the receipts), ack."""

    def __init__(self):
        self.receipts: list[tuple[str, bytes]] = []
        self.acked = 0

    def publish(self, topic, payload, qos, retain):
        self.receipts.append((topic, payload))
        return _PublishInfo()

    def ack(self, mid, qos):
        self.acked += 1


class _PublishInfo:
    rc = 0


@dataclass
class Message:
    topic: str
    payload: bytes
    mid: int
    qos: int = 1
    retain: bool = False


def _percentiles(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    s = sorted(values)
    return {"n": len(s), "mean_ms": statistics.fmean(s) * 1e3, "p50_ms": s[len(s) // 2] * 1e3,
            "p99_ms": s[min(len(s) - 1, int(len(s) * 0.99))] * 1e3, "max_ms": s[-1] * 1e3}


def worker(tenant: str, stations: list[Station], passes: list[Pass], db: Path, hours: float,
           faults: Faults | None, seed: int, result_queue) -> None:
    """One bridge process: the stations of its tenant, their messages in delivery order through handle_message."""
    from station.mqtt_bridge import handle_message, request_event_audio
    from station.service import StationFusionService
    from station.store import EventStore

    rng = random.Random(seed)
    store = EventStore(db)

    def fresh_service():
        s = StationFusionService(store)
        s.alerts.tenant = tenant
        s.alerts.clock = lambda: clock["now_us"] / 1e6
        return s

    clock = {"now_us": WALL0_US}
    service = fresh_service()
    client = RecordingClient()
    stderr = io.StringIO()
    expected = Expected()
    heap: list[tuple[int, int, int, str, bytes, bool]] = []     # (deliver_us, seq, station_id, kind, payload, redelivery)
    seq = [0]

    def push(deliver_us: int, station_id: int, kind: str, payload: bytes, redelivery: bool = False) -> None:
        seq[0] += 1
        heapq.heappush(heap, (deliver_us, seq[0], station_id, kind, payload, redelivery))

    # outages: per station, intervals [off, on) during which its messages are held and then burst
    outages: dict[int, list[tuple[int, int]]] = {}
    if faults and faults.outage_p_per_h > 0:
        for st in stations:
            t = 0.0
            spans = []
            while t < hours * 3600:
                t += rng.expovariate(faults.outage_p_per_h / 3600.0)
                if t >= hours * 3600:
                    break
                length = rng.uniform(*faults.outage_s)
                spans.append((WALL0_US + int(t * 1e6), WALL0_US + int((t + length) * 1e6)))
                t += length
            outages[st.station_id] = spans

    def delivery_time(station_id: int, publish_us: int) -> int:
        for off, on in outages.get(station_id, ()):
            if off <= publish_us < on:
                return on + (publish_us - off) // 20            # the backlog drains 20 times faster than it came
        return publish_us

    boot = {st.station_id: 3 for st in stations}
    seq_no = {st.station_id: 0 for st in stations}
    end_us = WALL0_US + int(hours * 3600 * 1e6)
    for st in stations:
        t = 0.0
        while t < hours * 3600:
            push(delivery_time(st.station_id, WALL0_US + int(t * 1e6)), st.station_id, "status",
                 heartbeat_payload(st, WALL0_US + int(t * 1e6), boot[st.station_id], int(t)))
            expected.heartbeats += 1
            t += HEARTBEAT_S
    rising: dict[tuple[int, int], tuple[Pass, float]] = {}          # (station, event_id) -> (pass, t_in)
    audio_data = audio_segment(rng)
    for p in passes:
        heard = 0
        for st in stations:
            window = hearing_window(st, p)
            if window is None:
                continue
            heard += 1
            t_in, t_out = window
            expected.windows += 1
            seq_no[st.station_id] += 1
            track_event = (boot[st.station_id] << 32) | seq_no[st.station_id]
            rising[(st.station_id, track_event)] = (p, t_in)
            t = t_in
            while t <= t_out:
                seq_no[st.station_id] += 1 if t > t_in else 0
                event_id = (boot[st.station_id] << 32) | seq_no[st.station_id]
                at = p.start_us + int(t * 1e6)
                if at >= end_us:
                    break
                push(delivery_time(st.station_id, at), st.station_id, "up",
                     detection_payload(st, p, t, seq_no=seq_no[st.station_id], boot_id=boot[st.station_id], event_id=event_id, rng=rng))
                expected.detections += 1
                t += UPDATE_S
            t = t_in
            while t <= t_out:
                at = p.start_us + int(t * 1e6)
                if at >= end_us:
                    break
                push(delivery_time(st.station_id, at) + 300_000, st.station_id, "bearing",
                     bearing_payload(st, p, t, boot_id=boot[st.station_id], track_event_id=track_event, rng=rng))
                expected.bearing_samples += 2
                t += BEARING_S
        if heard >= 2:
            expected.multi_station_passes += 1
    # ---- delivery ----------------------------------------------------------------------------------------------------
    timings: dict[str, list[float]] = {"up": [], "bearing": [], "status": [], "audio": []}
    counts = {"delivered": 0, "redelivered": 0, "unacked": 0, "receipts": 0, "receipt_mismatch": 0,
              "audio_requests": 0, "restarts": 0, "reconnect_redeliveries": 0, "refused": 0}
    receipts: dict[bytes, bytes] = {}
    last_sent: dict[int, list[tuple[str, bytes]]] = {st.station_id: [] for st in stations}
    next_reconnect = {st.station_id: WALL0_US + int(rng.uniform(0, faults.reconnect_s) * 1e6) for st in stations} if faults and faults.reconnect_s > 0 else {}
    next_restart = WALL0_US + int(faults.restart_s * 1e6) if faults and faults.restart_s > 0 else None
    next_sweep = WALL0_US
    audio_requested: set[tuple[int, int]] = set()
    mid = 0
    started = time.perf_counter()
    old_stderr = sys.stderr
    sys.stderr = stderr
    try:
        while heap:
            deliver_us, _, station_id, kind, payload, redelivery = heapq.heappop(heap)
            clock["now_us"] = max(clock["now_us"], deliver_us)
            now_us = clock["now_us"]
            if next_restart is not None and now_us >= next_restart:
                service = fresh_service()
                counts["restarts"] += 1
                next_restart += int(faults.restart_s * 1e6)
            if now_us >= next_sweep:
                service.alerts.sweep(now_us)
                next_sweep = now_us + 5_000_000
            if next_reconnect and now_us >= next_reconnect[station_id]:
                for k, pl in last_sent[station_id][-faults.inflight:]:
                    push(now_us + 1000, station_id, k, pl, True)
                    counts["reconnect_redeliveries"] += 1
                next_reconnect[station_id] = now_us + int(faults.reconnect_s * 1e6)
            mid = (mid % 65535) + 1
            topic = f"zs/v1/{tenant}/{station_id}/{kind}"
            message = Message(topic, payload, mid)
            st = next(s for s in stations if s.station_id == station_id)

            def on_new_detection(detection, st=st, now_us=now_us):
                key = (detection.station_id, detection.event_id)
                if key not in rising or key in audio_requested:
                    return
                audio_requested.add(key)
                command = request_event_audio(detection, segment="both", min_gap_us=0, now_us=now_us, event_store=store)
                if command is None:
                    return
                counts["audio_requests"] += 1
                p, t_in = rising[key]
                when = now_us + int(AUDIO_AFTER_S * 1e6)
                for segment in (0, 1):
                    start = p.start_us + int((t_in - AUDIO_SEGMENT_S if segment == 0 else t_in) * 1e6)
                    for i, chunk in enumerate(audio_chunks(st, command.command_id, detection.event_id, segment, start, audio_data)):
                        push(delivery_time(station_id, when + int(i * AUDIO_CHUNK_GAP_S * 1e6)), station_id, "audio", chunk)
                    when += int(40 * AUDIO_CHUNK_GAP_S * 1e6)
                expected.audio_segments += 2

            before = len(client.receipts)
            t0 = time.perf_counter()
            ok = handle_message(client, message, tenant, True, event_store=store, fusion_service=service,
                                on_new_detection=on_new_detection)
            timings[kind].append(time.perf_counter() - t0)
            counts["delivered"] += 1
            counts["redelivered"] += redelivery
            counts["refused"] += not ok
            if kind == "up" and len(client.receipts) > before:
                counts["receipts"] += 1
                receipt = client.receipts[-1][1]
                key = hashlib.sha256(payload).digest()
                if key in receipts and receipts[key] != receipt:
                    counts["receipt_mismatch"] += 1
                receipts[key] = receipt
            if not redelivery:
                last_sent[station_id].append((kind, payload))
                del last_sent[station_id][:-faults.inflight if faults else -1]
                if faults and faults.dup_p > 0 and rng.random() < faults.dup_p:
                    push(now_us + int(rng.uniform(2, 30) * 1e6), station_id, kind, payload, True)
    finally:
        sys.stderr = old_stderr
    elapsed = time.perf_counter() - started
    counts["unacked"] = counts["delivered"] - client.acked          # a message handle_message did not acknowledge
    log = stderr.getvalue()
    counts["decode_errors"] = log.count("MQTT decode error")
    counts["processing_errors"] = log.count("MQTT processing error")
    counts["follow_up_errors"] = log.count("MQTT follow-up error")
    result_queue.put({"tenant": tenant, "stations": [s.station_id for s in stations], "elapsed_s": elapsed,
                      "counts": counts, "timings": {k: _percentiles(v) for k, v in timings.items()},
                      "expected": expected.__dict__, "receipts": len(client.receipts), "acked": client.acked,
                      "log_tail": log[-4000:], "outages": sum(len(v) for v in outages.values())})


def reader(db: Path, stop, result_queue, period_s: float = 0.5) -> None:
    """The web UI's questions to the store while the bridges write: never a locked database."""
    from station.store import EventStore

    store = EventStore(db)
    timings: list[float] = []
    errors: list[str] = []
    rounds = 0
    seq = 0
    while not stop.is_set():
        t0 = time.perf_counter()
        try:
            store.list_events(50)
            store.list_tracks(limit=50)
            store.list_stations()
            store.storage_usage(0.0)
            for row in store.list_alerts(seq, limit=200):
                seq = max(seq, row["seq"])
            store.list_bearings(limit=500)
        except Exception as exc:  # noqa: BLE001 - what the reader saw is the result
            errors.append(f"{type(exc).__name__}: {exc}")
        timings.append(time.perf_counter() - t0)
        rounds += 1
        time.sleep(period_s)
    result_queue.put({"reader": True, "rounds": rounds, "timings": _percentiles(timings), "errors": errors[:20],
                      "error_count": len(errors)})


def database_facts(db: Path) -> dict:
    import sqlite3

    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    q = lambda sql: c.execute(sql).fetchone()[0]  # noqa: E731
    facts = {
        "detections": q("SELECT COUNT(*) FROM detections"),
        "ingress": q("SELECT COUNT(*) FROM mqtt_detection_ingress"),
        "ingress_unprocessed": q("SELECT COUNT(*) FROM mqtt_detection_ingress WHERE processed=0"),
        "bearings": q("SELECT COUNT(*) FROM bearings"),
        "stations": q("SELECT COUNT(*) FROM stations"),
        "system_events": q("SELECT COUNT(*) FROM system_events"),
        "air_alerts": q("SELECT COUNT(*) FROM system_events WHERE event_type='AIR_ALERT'"),
        "fused_tracks": q("SELECT COUNT(*) FROM fused_tracks"),
        "track_points": q("SELECT COUNT(*) FROM track_points"),
        "tracks_5_points": q("SELECT COUNT(*) FROM fused_tracks WHERE points>=5"),
        "commands": q("SELECT COUNT(*) FROM commands"),
        "audio_rows": q("SELECT COUNT(*) FROM audio"),
        "audio_parts_pending": q("SELECT COUNT(*) FROM audio_parts"),
        "alert_outbox": q("SELECT COUNT(*) FROM alert_outbox"),
        "database_bytes": sum(p.stat().st_size for p in db.parent.glob(db.name + "*")),
    }
    c.close()
    return facts


def run(args) -> dict:
    out = Path(args.out)
    if out.resolve().is_relative_to((SERVER_ROOT / "data").resolve()):
        raise ValueError("load-test output must be outside the server data directory")
    out.mkdir(parents=True, exist_ok=True)
    db = out / "zs_bpla.sqlite3"
    for f in out.glob("zs_bpla.sqlite3*"):
        f.unlink()
    audio_root = out / "audio"                       # EventStore keeps the assembled segments beside its database
    stations = scenario_stations(args.stations, args.tenant, args.station_id_base)
    rng = random.Random(args.seed)
    passes = plan_passes(rng, stations, args.hours, args.episodes)
    faults = None if args.no_faults else Faults(dup_p=args.dup, reconnect_s=args.reconnect, restart_s=args.restart,
                                                 outage_p_per_h=args.outage)
    tenants = sorted({s.tenant for s in stations})
    ctx = mp.get_context("spawn")
    results = ctx.Queue()
    stop = ctx.Event()
    procs = []
    for i, tenant in enumerate(tenants):
        mine = [s for s in stations if s.tenant == tenant]
        procs.append(ctx.Process(target=worker, args=(tenant, mine, passes, db, args.hours, faults, args.seed + i, results), name=tenant))
    readers = [ctx.Process(target=reader, args=(db, stop, results), name="reader")] if args.readers else []
    started = time.perf_counter()
    for p in procs + readers:
        p.start()
    reports = []
    for _ in procs:
        reports.append(results.get())
    for p in procs:
        p.join()
    stop.set()
    for p in readers:
        reports.append(results.get())
        p.join()
    elapsed = time.perf_counter() - started
    workers = [r for r in reports if "tenant" in r]
    readers_r = [r for r in reports if r.get("reader")]
    facts = database_facts(db)
    expected = {k: sum(r["expected"][k] for r in workers) for k in workers[0]["expected"]}
    delivered = sum(r["counts"]["delivered"] for r in workers)
    audio_files = sum(1 for _ in audio_root.rglob("*.wav")) if audio_root.exists() else 0
    report = {
        "stations": len(stations), "hours": args.hours, "passes": len(passes), "episodes_per_station_day": args.episodes,
        "faults": faults.__dict__ if faults else None, "elapsed_s": elapsed, "messages": delivered,
        "messages_per_s": delivered / elapsed if elapsed else None,
        "real_time_factor": args.hours * 3600 / elapsed if elapsed else None,
        "expected": expected, "database": facts, "audio_files": audio_files,
        "workers": workers, "readers": readers_r,
    }
    checks = {
        "detections stored once": facts["detections"] == expected["detections"] and facts["ingress"] == expected["detections"],
        "ingress all processed": facts["ingress_unprocessed"] == 0,
        "bearing samples stored once": facts["bearings"] == expected["bearing_samples"],
        "audio segments complete once": facts["audio_rows"] == expected["audio_segments"] == audio_files and facts["audio_parts_pending"] == 0,
        "every station known": facts["stations"] == len(stations),
        "no unacknowledged message": all(r["counts"]["unacked"] == 0 for r in workers),
        "no processing error": all(r["counts"]["processing_errors"] == 0 and r["counts"]["follow_up_errors"] == 0 for r in workers),
        "no decode error": all(r["counts"]["decode_errors"] == 0 for r in workers),
        "redeliveries answered with the same receipt": all(r["counts"]["receipt_mismatch"] == 0 for r in workers),
        "one receipt per detection delivery": all(r["counts"]["receipts"] == r["timings"]["up"]["n"] for r in workers),
        "readers never failed": all(r["error_count"] == 0 for r in readers_r),
        # a pass along the road gives nearly parallel bearings (no crossing), so not every multi-station pass fuses:
        # 49..68 % measured without faults; the faults cost about one track in twenty (the document, §3)
        "fused tracks for multi-station passes": facts["tracks_5_points"] >= 0.4 * expected["multi_station_passes"],
        "alerts of two stations": facts["air_alerts"] > 0,
        "throughput margin over real time": (report["real_time_factor"] or 0) >= args.min_real_time_factor,
    }
    report["checks"] = checks
    report["ok"] = all(checks.values())
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return report


def summary(report: dict) -> str:
    lines = [f"load field: {report['stations']} stations, {report['hours']} h simulated, {report['passes']} passes, "
             f"{report['messages']} messages in {report['elapsed_s']:.1f} s "
             f"({report['messages_per_s']:.0f} msg/s, {report['real_time_factor']:.0f}x real time)"]
    for w in report["workers"]:
        c = w["counts"]
        lines.append(f"  {w['tenant']}: {len(w['stations'])} stations, {c['delivered']} delivered ({c['redelivered']} redelivered, "
                     f"{c['reconnect_redeliveries']} after reconnects, {w['outages']} outages, {c['restarts']} restarts), "
                     f"unacked {c['unacked']}, processing errors {c['processing_errors']}, decode errors {c['decode_errors']}, "
                     f"audio requests {c['audio_requests']}")
        for kind, t in w["timings"].items():
            if t["n"]:
                lines.append(f"    {kind:8s} n={t['n']:6d} mean {t['mean_ms']:.2f} ms p50 {t['p50_ms']:.2f} p99 {t['p99_ms']:.1f} max {t['max_ms']:.0f}")
    for r in report["readers"]:
        t = r["timings"]
        lines.append(f"  reader: {r['rounds']} rounds, errors {r['error_count']}, p50 {t.get('p50_ms', 0):.1f} ms p99 {t.get('p99_ms', 0):.1f} ms")
    d, e = report["database"], report["expected"]
    lines.append(f"  database: detections {d['detections']}/{e['detections']}, bearings {d['bearings']}/{e['bearing_samples']}, "
                 f"audio {d['audio_rows']}/{e['audio_segments']} ({report['audio_files']} files), system events {d['system_events']} "
                 f"(AIR_ALERT {d['air_alerts']}), tracks {d['fused_tracks']} ({d['tracks_5_points']} with 5+ points) for "
                 f"{e['multi_station_passes']} multi-station passes, outbox {d['alert_outbox']}, {d['database_bytes'] / 1e6:.1f} MB")
    for name, ok in report["checks"].items():
        lines.append(f"  [{'ok' if ok else 'FAIL'}] {name}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True, help="directory for the database, the audio and report.json")
    ap.add_argument("--hours", type=float, default=2.0, help="simulated duration")
    ap.add_argument("--episodes", type=float, default=5.0, help="episodes per station and day")
    ap.add_argument("--stations", type=int, default=41)
    ap.add_argument("--tenant", default="", help="place every virtual station in one tenant, e.g. bench")
    ap.add_argument("--station-id-base", type=int, default=1000,
                    help="first ID is base + 1 when --tenant is set; keep clear of physical station IDs")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--dup", type=float, default=Faults.dup_p, help="probability of a QoS 1 redelivery per message")
    ap.add_argument("--reconnect", type=float, default=Faults.reconnect_s, help="seconds between reconnects of a station (0: none)")
    ap.add_argument("--restart", type=float, default=Faults.restart_s, help="seconds between bridge restarts (0: none)")
    ap.add_argument("--outage", type=float, default=Faults.outage_p_per_h, help="station outages per station-hour (0: none)")
    ap.add_argument("--no-faults", action="store_true")
    ap.add_argument("--no-readers", dest="readers", action="store_false")
    ap.add_argument("--min-real-time-factor", type=float, default=10.0)
    ap.add_argument("--check", action="store_true", help="exit 1 when a check fails")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    report = run(args)
    print(summary(report))
    return 0 if report["ok"] or not args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
