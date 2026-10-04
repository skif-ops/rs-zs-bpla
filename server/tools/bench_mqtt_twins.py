#!/usr/bin/env python3
"""Send a bounded heartbeat from 3, 20 or 40 bench identities over MQTT TLS.

Each virtual station uses its own certificate and publishes only to its own
zs/v1/bench/<id>/status topic. There is no pilot tenant option. This checks the
real broker, bridge and station storage after the offline field simulation.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from threading import Event

import paho.mqtt.client as mqtt
from cryptography import x509
from cryptography.x509.oid import NameOID

from load_field import heartbeat_payload, scenario_stations


def identities(count: int, credentials: Path) -> list[tuple[int, str, Path, Path]]:
    if count not in (3, 20, 40):
        raise ValueError("bench network stage must be 3, 20 or 40 stations")
    out = []
    for i in range(1, count + 1):
        serial = f"DIO-TWIN-{i:03d}"
        folder = credentials / serial
        cert, key = folder / f"{serial}.crt.pem", folder / f"{serial}.key.pem"
        if not cert.is_file() or not key.is_file():
            raise FileNotFoundError(f"missing bench certificate/key for {serial}")
        subject = x509.load_pem_x509_certificate(cert.read_bytes()).subject
        cn = subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if len(cn) != 1 or cn[0].value != serial:
            raise ValueError(f"certificate CN does not match {serial}")
        out.append((1000 + i, serial, cert, key))
    return out


def send_one(host: str, port: int, ca: Path, cert: Path, key: Path,
             station_id: int, payload: bytes, timeout_s: float) -> None:
    connected = Event()
    rejected = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"dioneya-twin-{station_id}-{os.getpid()}")
    client.tls_set(ca_certs=str(ca), certfile=str(cert), keyfile=str(key))
    client.tls_insecure_set(False)

    def on_connect(_client, _userdata, _flags, reason_code, _properties):
        if reason_code == 0:
            connected.set()
        else:
            rejected.append(str(reason_code))
            connected.set()

    client.on_connect = on_connect
    client.connect(host, port, keepalive=30)
    client.loop_start()
    try:
        if not connected.wait(timeout_s) or rejected:
            raise ConnectionError(f"MQTT connection failed for station {station_id}: {rejected or 'timeout'}")
        topic = f"zs/v1/bench/{station_id}/status"
        receipt = client.publish(topic, payload, qos=1, retain=False)
        if receipt.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT publish refused for station {station_id}: {receipt.rc}")
        receipt.wait_for_publish(timeout=timeout_s)
        if not receipt.is_published():
            raise TimeoutError(f"no PUBACK for station {station_id}")
    finally:
        client.disconnect()
        client.loop_stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stations", type=int, choices=(3, 20, 40), required=True)
    parser.add_argument("--credentials", type=Path, required=True, help="directory with DIO-TWIN-001/... certificates")
    parser.add_argument("--ca", type=Path, required=True)
    parser.add_argument("--host", default="dioneya.ru")
    parser.add_argument("--port", type=int, default=8883)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--gap", type=float, default=1.0, help="minimum seconds between stations")
    parser.add_argument("--out", type=Path, help="write a result JSON without credentials or payloads")
    parser.add_argument("--execute", action="store_true", help="send real traffic; omitted means validation only")
    args = parser.parse_args(argv)
    if not args.ca.is_file() or not 1 <= args.port <= 65535 or args.timeout <= 0 or args.gap < 1:
        parser.error("CA, port, timeout and gap (at least 1 s) must be valid")
    identities_list = identities(args.stations, args.credentials)
    stations = scenario_stations(args.stations, "bench", 1000)
    outcome = {"stage": args.stations, "tenant": "bench", "planned": len(identities_list),
               "published": 0, "status": "validated" if not args.execute else "running", "station_ids": []}
    if args.execute:
        try:
            for index, ((sid, _serial, cert, key), station) in enumerate(zip(identities_list, stations)):
                if station.station_id != sid or station.tenant != "bench":
                    raise ValueError("virtual station plan changed unexpectedly")
                if index:
                    time.sleep(args.gap)
                payload = heartbeat_payload(station, int(time.time() * 1e6), 1, 60)
                send_one(args.host, args.port, args.ca, cert, key, sid, payload, args.timeout)
                outcome["published"] += 1
                outcome["station_ids"].append(sid)
            outcome["status"] = "published"
        except Exception as exc:
            outcome["status"] = "failed"
            outcome["error"] = f"{type(exc).__name__}: {exc}"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(outcome, ensure_ascii=False))
    return 0 if outcome["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
