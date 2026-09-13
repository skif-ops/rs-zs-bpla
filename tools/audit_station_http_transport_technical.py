#!/usr/bin/env python3
"""QG-2 independent runtime audit of the station HTTP fail-closed boundary."""

from __future__ import annotations

import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
ENV = "ZS_STATION_HTTP_INSECURE_BENCH"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    sys.path.insert(0, str(SERVER))
    os.environ.pop(ENV, None)

    from fastapi.routing import APIRoute
    from fastapi.testclient import TestClient
    from app import app
    from station.http_transport import require_insecure_station_http_bench
    from station.router import station_http_router

    expected = {
        ("POST", "/stations/{station_id}/heartbeat"),
        ("POST", "/stations/{station_id}/detection"),
        ("POST", "/stations/{station_id}/detection.cbor"),
        ("POST", "/stations/{station_id}/events/{event_id}/features"),
        ("POST", "/stations/{station_id}/security"),
        ("GET", "/stations/{station_id}/commands/poll"),
        ("POST", "/stations/{station_id}/commands/{command_id}/ack"),
        ("POST", "/stations/{station_id}/events/{event_id}/audio"),
    }
    guarded = set()
    for route in station_http_router.routes:
        if not isinstance(route, APIRoute):
            continue
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
        if require_insecure_station_http_bench in dependency_calls:
            guarded.update((method, route.path) for method in route.methods)
    require(guarded == expected, f"guarded station route set drift: {guarded ^ expected}")

    client = TestClient(app)
    heartbeat = {
        "station_id": 17,
        "time_us": 1,
        "station": {"lat_e7": 0, "lon_e7": 0, "alt_dm": 0},
    }
    denied = client.post("/api/v1/stations/17/heartbeat", json=heartbeat)
    require(denied.status_code == 403, f"default station HTTP status is {denied.status_code}")
    require("mutual-TLS MQTT" in denied.json().get("detail", ""),
            "default denial does not direct production traffic to MQTT mTLS")

    for ambiguous in ("true", "yes", "on", "0", ""):
        os.environ[ENV] = ambiguous
        denied = client.get("/api/v1/stations/17/commands/poll")
        require(denied.status_code == 403, f"ambiguous opt-in accepted: {ambiguous!r}")

    os.environ[ENV] = "1"
    allowed = client.post("/api/v1/stations/18/heartbeat", json=heartbeat)
    require(allowed.status_code == 400 and "station_id mismatch" in allowed.text,
            "exact bench opt-in did not reach route validation")

    heartbeat["station_id"] = 17
    heartbeat["cellular"] = {
        "imsi": "250011234567890",
        "iccid": "89701012345678901234",
        "apn": "network.apn",
        "local_address": "10.10.0.2",
        "gateway": "10.10.0.1",
        "primary_dns": "1.1.1.1",
        "apn_source": "NETWORK",
        "settings_valid": True,
    }
    identity = client.post("/api/v1/stations/17/heartbeat", json=heartbeat)
    require(identity.status_code == 400 and "mutual-TLS MQTT status" in identity.text,
            "bench HTTP accepted protected cellular identity")

    os.environ.pop(ENV, None)
    print("Station HTTP transport QG-2 independent runtime audit: PASS")
    print("exact bench opt-in works; default deny and MQTT-only IMSI/ICCID remain enforced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
