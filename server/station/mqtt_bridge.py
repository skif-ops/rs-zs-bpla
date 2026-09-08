"""MQTT/TLS bridge with topic-to-payload station binding."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import paho.mqtt.client as mqtt

from station.cbor_codec import decode_cbor, decode_detection_obj
from station.router import service
from station.schemas import HeartbeatMessage


def station_id_from_topic(topic: str, tenant: str) -> tuple[int, str]:
    parts = topic.split("/")
    if (
        len(parts) != 5
        or parts[0] != "zs"
        or parts[1] != "v1"
        or parts[2] != tenant
        or parts[4] not in {"up", "status"}
    ):
        raise ValueError(f"unexpected topic: {topic}")
    return int(parts[3]), parts[4]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("ZS_MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("ZS_MQTT_PORT", "8883")))
    parser.add_argument("--tenant", default=os.getenv("ZS_TENANT", "default"))
    parser.add_argument("--ca", default=os.getenv("ZS_MQTT_CA"))
    parser.add_argument("--cert", default=os.getenv("ZS_MQTT_CERT"))
    parser.add_argument("--key", default=os.getenv("ZS_MQTT_KEY"))
    parser.add_argument(
        "--insecure-bench",
        action="store_true",
        default=os.getenv("ZS_MQTT_INSECURE_BENCH", "0") == "1",
        help="Explicitly allow plaintext MQTT for an isolated development bench.",
    )
    return parser


def validate_transport(args: argparse.Namespace) -> bool:
    """Return True for TLS or fail closed on incomplete production settings."""

    tls_values = {"ca": args.ca, "cert": args.cert, "key": args.key}
    configured = [name for name, value in tls_values.items() if value]

    if args.insecure_bench:
        if configured:
            raise ValueError("--insecure-bench cannot be combined with TLS arguments")
        return False

    if len(configured) != len(tls_values):
        missing = ", ".join(name for name, value in tls_values.items() if not value)
        raise ValueError(
            "MQTT bridge requires CA, client certificate and private key; "
            f"missing: {missing}. Use --insecure-bench only on an isolated bench."
        )

    missing_files = [name for name, value in tls_values.items() if not Path(value).is_file()]
    if missing_files:
        raise ValueError(f"MQTT TLS files do not exist: {', '.join(missing_files)}")
    return True


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    tls_enabled = validate_transport(args)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if tls_enabled:
        client.tls_set(ca_certs=args.ca, certfile=args.cert, keyfile=args.key)
        client.tls_insecure_set(False)

    def on_connect(client_obj, userdata, flags, reason_code, properties=None):
        del userdata, flags, properties
        if reason_code != 0:
            raise ConnectionError(f"MQTT connection rejected: {reason_code}")
        client_obj.subscribe(f"zs/v1/{args.tenant}/+/up", qos=1)
        client_obj.subscribe(f"zs/v1/{args.tenant}/+/status", qos=1)

    def on_message(client_obj, userdata, message):
        del client_obj, userdata
        try:
            topic_station_id, kind = station_id_from_topic(message.topic, args.tenant)
            obj = decode_cbor(message.payload)
            if kind == "status":
                heartbeat = HeartbeatMessage.model_validate(obj)
                if heartbeat.station_id != topic_station_id:
                    raise ValueError("station_id mismatch between topic and heartbeat")
                from station.router import store

                store.upsert_station(heartbeat)
            else:
                detection = decode_detection_obj(obj)
                if detection.station_id != topic_station_id:
                    raise ValueError("station_id mismatch between topic and detection")
                service.ingest(detection)
        except Exception as exc:
            print(f"MQTT decode error: {exc}", file=sys.stderr)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, 60)
    client.loop_forever()


if __name__ == "__main__":
    main()

