#!/usr/bin/env python3
"""Keep the 40 isolated bench identities visible with low-rate synthetic heartbeats."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from bench_mqtt_twins import identities, send_one
from load_field import heartbeat_payload, scenario_stations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--ca", type=Path, required=True)
    parser.add_argument("--host", default="mqtt")
    parser.add_argument("--port", type=int, default=8883)
    parser.add_argument("--cycle-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.cycle_seconds < 300:
        parser.error("cycle must be at least five minutes")
    source = identities(40, args.credentials)
    stations = scenario_stations(40, "bench", 9000)
    if [item[0] for item in source] != [station.station_id for station in stations]:
        raise RuntimeError("bench registry and station plan differ")

    boot_id = int(time.time()) & 0xFFFFFFFF
    boot_monotonic = time.monotonic()
    while True:
        started = time.monotonic()
        published = 0
        for (station_id, _serial, cert, key), station in zip(source, stations):
            try:
                payload = heartbeat_payload(station, int(time.time() * 1e6), boot_id,
                                            max(1, int(time.monotonic() - boot_monotonic)))
                send_one(args.host, args.port, args.ca, cert, key, station_id, payload, 10.0)
                published += 1
            except Exception as exc:
                print(json.dumps({"station_id": station_id, "error": type(exc).__name__ + ": " + str(exc)}), flush=True)
            time.sleep(1.0)
        print(json.dumps({"tenant": "bench", "published": published, "planned": 40,
                          "cycle_seconds": args.cycle_seconds}), flush=True)
        time.sleep(max(1, args.cycle_seconds - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
