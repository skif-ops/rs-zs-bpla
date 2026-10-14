#!/usr/bin/env python3
"""Publish bounded UAV flight scenarios to the isolated bench MQTT tenant.

The controlled sequence uses a different station group for every scenario:
9001..9003 for one UAV, 9004..9006 for two UAVs and 9007..9009 for three
UAVs.  The tool is hard-bound to the ``bench`` tenant and QoS 1.  Omitting
``--execute`` validates the PKI and prints the plan without sending traffic.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from pathlib import Path
from threading import Event

import paho.mqtt.client as mqtt

from bench_mqtt_twins import identities
from load_field import Pass, Station, bearing_payload, detection_payload, heartbeat_payload

TENANT = "bench"
STATION_POSITIONS = (
    (0.0, 0.0, 0.0),
    (1200.0, 0.0, 0.0),
    (600.0, 1000.0, 0.0),
)
TARGETS = (
    ((-900.0, 800.0, 220.0), (50.0, 0.0, 0.0), 185.0),
    ((2100.0, -100.0, 180.0), (-50.0, 0.0, 0.0), 120.0),
    ((100.0, 1900.0, 260.0), (0.0, -50.0, 0.0), 290.0),
)
HEAR_RANGE_M = 2200.0


class StationClient:
    def __init__(self, station_id: int, host: str, port: int, ca: Path, cert: Path, key: Path, timeout: float):
        self.station_id = station_id
        self.timeout = timeout
        self.connected = Event()
        self.error: str | None = None
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"dioneya-flight-{station_id}-{os.getpid()}",
        )
        self.client.tls_set(ca_certs=str(ca), certfile=str(cert), keyfile=str(key))
        self.client.tls_insecure_set(False)

        def on_connect(_client, _userdata, _flags, reason_code, _properties):
            if reason_code == 0:
                self.connected.set()
            else:
                self.error = str(reason_code)
                self.connected.set()

        self.client.on_connect = on_connect
        self.client.connect(host, port, keepalive=30)
        self.client.loop_start()
        if not self.connected.wait(timeout) or self.error:
            self.close()
            raise ConnectionError(f"MQTT connection failed for station {station_id}: {self.error or 'timeout'}")

    def publish(self, kind: str, payload: bytes) -> None:
        info = self.client.publish(f"zs/v1/{TENANT}/{self.station_id}/{kind}", payload, qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT publish refused for station {self.station_id}: {info.rc}")
        info.wait_for_publish(timeout=self.timeout)
        if not info.is_published():
            raise TimeoutError(f"no PUBACK for station {self.station_id}/{kind}")

    def close(self) -> None:
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()


def make_passes(count: int, start_us: int, duration_s: int) -> list[Pass]:
    out = []
    for index, (origin, velocity, f0_hz) in enumerate(TARGETS[:count], 1):
        out.append(Pass(index, start_us, origin, velocity, float(duration_s), f0_hz, 3))
    return out


def heard(station: Station, flight: Pass, t_s: float) -> bool:
    return math.dist(station.enu, flight.at(t_s)) <= HEAR_RANGE_M


def stations_for_scenario(scenario: int) -> tuple[Station, ...]:
    first_id = 9001 + (scenario - 1) * 3
    return tuple(
        Station(first_id + index, TENANT, position)
        for index, position in enumerate(STATION_POSITIONS)
    )


def plan(scenarios: list[tuple[int, tuple[Station, ...]]], duration_s: int, gap_s: int) -> dict:
    return {
        "tenant": TENANT,
        "gap_s": gap_s,
        "scenarios": [
            {
                "uavs": uavs,
                "duration_s": duration_s,
                "station_ids": [station.station_id for station in stations],
                "targets": [
                    {"origin_enu_m": list(origin), "velocity_m_s": list(velocity), "f0_hz": f0}
                    for origin, velocity, f0 in TARGETS[:uavs]
                ],
            }
            for uavs, stations in scenarios
        ],
    }


def run_scenario(count: int, stations: tuple[Station, ...], duration_s: int,
                 clients: dict[int, StationClient], boot_id: int, seed: int) -> dict:
    started_us = time.time_ns() // 1000
    flights = make_passes(count, started_us, duration_s)
    rng = random.Random(seed + count)
    seq_no = {station.station_id: count * 1000 for station in stations}
    track_event: dict[tuple[int, int], int] = {}
    detection_started: set[tuple[int, int]] = set()
    counters = {"status": 0, "up": 0, "bearing": 0, "puback": 0}

    for station in stations:
        clients[station.station_id].publish(
            "status", heartbeat_payload(station, started_us, boot_id, max(1, count)),
        )
        counters["status"] += 1
        counters["puback"] += 1

    monotonic_start = time.monotonic()
    for second in range(duration_s + 1):
        for flight in flights:
            for station in stations:
                if not heard(station, flight, float(second)):
                    continue
                key = (station.station_id, flight.index)
                if key not in track_event:
                    seq_no[station.station_id] += 1
                    track_event[key] = (boot_id << 32) | seq_no[station.station_id]
                if second % 5 == 0:
                    if key not in detection_started:
                        event_id = track_event[key]
                        detection_started.add(key)
                    else:
                        seq_no[station.station_id] += 1
                        event_id = (boot_id << 32) | seq_no[station.station_id]
                    clients[station.station_id].publish(
                        "up",
                        detection_payload(
                            station, flight, float(second), seq_no=seq_no[station.station_id],
                            boot_id=boot_id, event_id=event_id, rng=rng,
                        ),
                    )
                    counters["up"] += 1
                    counters["puback"] += 1
                clients[station.station_id].publish(
                    "bearing",
                    bearing_payload(
                        station, flight, float(second), boot_id=boot_id,
                        track_event_id=track_event[key], rng=rng,
                    ),
                )
                counters["bearing"] += 1
                counters["puback"] += 1
        deadline = monotonic_start + second + 1
        time.sleep(max(0.0, deadline - time.monotonic()))

    return {
        "uavs": count,
        "started_us": started_us,
        "finished_us": time.time_ns() // 1000,
        "duration_s": duration_s,
        "station_ids": [station.station_id for station in stations],
        "counts": counters,
        "status": "published",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--ca", type=Path, required=True)
    parser.add_argument("--host", default="mqtt")
    parser.add_argument("--port", type=int, default=8883)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--uavs", type=int, choices=(1, 2, 3),
                      help="validate or run one scenario using its assigned station group")
    mode.add_argument("--sequence", action="store_true",
                      help="run 1, 2 and 3 UAV scenarios in order with different station groups")
    parser.add_argument("--duration", type=int, default=45)
    parser.add_argument("--gap", type=int, default=10, help="pause between scenarios in sequence, seconds")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.ca.is_file() or not 10 <= args.duration <= 180 or not 0 <= args.gap <= 120:
        parser.error("CA must exist; duration 10..180 s; gap 0..120 s")
    scenarios = (
        [(count, stations_for_scenario(count)) for count in (1, 2, 3)]
        if args.sequence else [(args.uavs, stations_for_scenario(args.uavs))]
    )
    expected_ids = [station.station_id for _, group in scenarios for station in group]
    identity_rows = [row for row in identities(20, args.credentials) if row[0] in expected_ids]
    if [row[0] for row in identity_rows] != expected_ids:
        raise RuntimeError("bench identity map differs from the controlled scenario plan")

    outcome = {"schema": "dioneya.bench-uav-flights/1", "plan": plan(scenarios, args.duration, args.gap),
               "executed": bool(args.execute), "runs": [], "status": "validated"}
    clients: dict[int, StationClient] = {}
    try:
        if args.execute:
            for station_id, _serial, cert, key in identity_rows:
                clients[station_id] = StationClient(
                    station_id, args.host, args.port, args.ca, cert, key, args.timeout,
                )
            boot_id = int(time.time()) & 0xFFFFFFFF
            for index, (uavs, stations) in enumerate(scenarios):
                outcome["runs"].append(run_scenario(uavs, stations, args.duration, clients, boot_id, args.seed))
                if index + 1 < len(scenarios) and args.gap:
                    time.sleep(args.gap)
            outcome["status"] = "published"
    except Exception as exc:
        outcome["status"] = "failed"
        outcome["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for client in clients.values():
            client.close()
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(outcome, ensure_ascii=False))
    return 0 if outcome["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
