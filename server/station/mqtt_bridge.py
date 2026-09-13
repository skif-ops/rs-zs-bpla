"""MQTT/TLS bridge with topic-to-payload station binding."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
import time

import paho.mqtt.client as mqtt

from station.cbor_codec import decode_cbor, decode_detection_obj, decode_heartbeat_obj
from station.command_codec import CommandSigner, decode_command_ack, encode_signed_command
from station.event_receipt_codec import EventReceipt, encode_event_receipt
from station.router import service, store
from station.schemas import HeartbeatMessage


TENANT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")


def validate_tenant(tenant: str) -> str:
    if TENANT_PATTERN.fullmatch(tenant) is None:
        raise ValueError("MQTT tenant must contain 1..32 safe identifier characters")
    return tenant


def station_id_from_topic(topic: str, tenant: str) -> tuple[int, str]:
    validate_tenant(tenant)
    parts = topic.split("/")
    if (
        len(parts) != 5
        or parts[0] != "zs"
        or parts[1] != "v1"
        or parts[2] != tenant
        or parts[4] not in {"up", "status", "ack"}
    ):
        raise ValueError(f"unexpected topic: {topic}")
    try:
        station_id = int(parts[3])
    except ValueError:
        raise ValueError(f"unexpected topic: {topic}") from None
    if not 0 < station_id <= 0xFFFFFFFF or str(station_id) != parts[3]:
        raise ValueError(f"unexpected topic: {topic}")
    return station_id, parts[4]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("ZS_MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("ZS_MQTT_PORT", "8883")))
    parser.add_argument("--tenant", default=os.getenv("ZS_TENANT", "default"))
    parser.add_argument("--ca", default=os.getenv("ZS_MQTT_CA"))
    parser.add_argument("--cert", default=os.getenv("ZS_MQTT_CERT"))
    parser.add_argument("--key", default=os.getenv("ZS_MQTT_KEY"))
    parser.add_argument(
        "--command-signing-key",
        default=os.getenv("ZS_COMMAND_SIGNING_KEY"),
        help="Unencrypted PKCS#8 Ed25519 PEM; downstream is disabled when omitted.",
    )
    parser.add_argument(
        "--command-poll-seconds",
        type=float,
        default=float(os.getenv("ZS_COMMAND_POLL_SECONDS", "1")),
    )
    parser.add_argument(
        "--command-retry-seconds",
        type=float,
        default=float(os.getenv("ZS_COMMAND_RETRY_SECONDS", "30")),
    )
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


def decode_status_obj(obj, tls_enabled: bool) -> HeartbeatMessage:
    try:
        if isinstance(obj, dict) and obj.get(1) == 3:
            heartbeat = decode_heartbeat_obj(obj)
        else:
            heartbeat = HeartbeatMessage.model_validate(obj)
    except Exception:
        raise ValueError("invalid protected heartbeat") from None
    if heartbeat.cellular is not None and not tls_enabled:
        raise ValueError("cellular identity telemetry requires mutual TLS")
    return heartbeat


def process_message(
    topic: str,
    payload: bytes,
    tenant: str,
    tls_enabled: bool,
    *,
    event_store=store,
    fusion_service=service,
) -> str:
    topic_station_id, kind = station_id_from_topic(topic, tenant)
    if kind == "ack":
        ack = decode_command_ack(payload)
        if ack.station_id != topic_station_id:
            raise ValueError("station_id mismatch between topic and command ACK")
        status = event_store.ack_command(
            ack.station_id,
            ack.command_id,
            ack.result_code,
            ack.detail_code,
            ack.completed_time_us,
        )
        if status == "unknown":
            raise ValueError("command ACK references an unknown command")
        if status == "station_mismatch":
            raise ValueError("command ACK ownership mismatch")
        return status

    obj = decode_cbor(payload)
    if kind == "status":
        heartbeat = decode_status_obj(obj, tls_enabled)
        if heartbeat.station_id != topic_station_id:
            raise ValueError("station_id mismatch between topic and heartbeat")
        event_store.upsert_station(heartbeat)
        return "stored"

    detection = decode_detection_obj(obj)
    if detection.station_id != topic_station_id:
        raise ValueError("station_id mismatch between topic and detection")
    wire_sha256 = hashlib.sha256(payload).digest()
    ingress = event_store.begin_mqtt_detection(detection, wire_sha256)
    if ingress == "conflict":
        raise ValueError("conflicting reuse of detection event_id")
    if ingress != "duplicate":
        fusion_service.ingest(detection)
        if not event_store.complete_mqtt_detection(detection, wire_sha256):
            raise RuntimeError("detection ingress completion failed")
    return "duplicate" if ingress == "duplicate" else "stored"


def build_event_receipt(topic: str, payload: bytes, tenant: str) -> tuple[str, bytes]:
    topic_station_id, kind = station_id_from_topic(topic, tenant)
    if kind != "up":
        raise ValueError("event receipt is valid only for detection uplink")
    detection = decode_detection_obj(decode_cbor(payload))
    if detection.station_id != topic_station_id:
        raise ValueError("station_id mismatch between topic and detection")
    receipt = encode_event_receipt(
        EventReceipt(
            station_id=detection.station_id,
            boot_id=detection.boot_id,
            seq_no=detection.seq_no,
            event_id=detection.event_id,
            payload_sha256=hashlib.sha256(payload).digest(),
        )
    )
    return f"zs/v1/{tenant}/{topic_station_id}/receipt", receipt


def publish_due_commands(
    client,
    tenant: str,
    signer: CommandSigner | None,
    *,
    now_us: int,
    retry_after_us: int,
    limit: int = 50,
    event_store=store,
) -> tuple[int, int]:
    """Queue due commands at MQTT QoS 1, retaining them until application ACK."""

    if signer is None:
        return 0, 0
    validate_tenant(tenant)
    published = failed = 0
    for command in event_store.due_commands(now_us, retry_after_us, limit):
        try:
            payload = encode_signed_command(command, signer)
            info = client.publish(
                f"zs/v1/{tenant}/{command.station_id}/down",
                payload,
                qos=1,
                retain=False,
            )
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                failed += 1
                continue
            if event_store.mark_command_published(
                command.station_id,
                command.command_id,
                now_us,
            ):
                published += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    return published, failed


def handle_message(
    client,
    message,
    tenant: str,
    tls_enabled: bool,
    *,
    event_store=store,
    fusion_service=service,
) -> bool:
    """Process then MQTT-ACK; discard invalid input but retry transient failures."""

    try:
        if type(message.qos) is not int or message.qos != 1 or getattr(message, "retain", False):
            raise ValueError("station MQTT delivery must be QoS 1 and non-retained")
        process_message(
            message.topic,
            message.payload,
            tenant,
            tls_enabled,
            event_store=event_store,
            fusion_service=fusion_service,
        )
        _, kind = station_id_from_topic(message.topic, tenant)
        if kind == "up":
            receipt_topic, receipt_payload = build_event_receipt(
                message.topic, message.payload, tenant
            )
            info = client.publish(
                receipt_topic,
                receipt_payload,
                qos=1,
                retain=False,
            )
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError("event application receipt publish failed")
    except ValueError as exc:
        print(f"MQTT decode error: {exc}", file=sys.stderr)
        if message.qos:
            client.ack(message.mid, message.qos)
        return False
    except Exception as exc:
        print(f"MQTT processing error: {type(exc).__name__}", file=sys.stderr)
        return False
    if message.qos:
        client.ack(message.mid, message.qos)
    return True


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    tls_enabled = validate_transport(args)
    validate_tenant(args.tenant)
    if args.command_poll_seconds <= 0 or args.command_retry_seconds <= 0:
        raise ValueError("command poll and retry intervals must be positive")
    signer = (
        CommandSigner.from_pem_file(args.command_signing_key)
        if args.command_signing_key
        else None
    )
    if signer is None:
        print(
            "MQTT command downstream disabled: signing key not configured",
            file=sys.stderr,
        )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.manual_ack_set(True)
    if tls_enabled:
        client.tls_set(ca_certs=args.ca, certfile=args.cert, keyfile=args.key)
        client.tls_insecure_set(False)

    def on_connect(client_obj, userdata, flags, reason_code, properties=None):
        del userdata, flags, properties
        if reason_code != 0:
            raise ConnectionError(f"MQTT connection rejected: {reason_code}")
        client_obj.subscribe(f"zs/v1/{args.tenant}/+/up", qos=1)
        client_obj.subscribe(f"zs/v1/{args.tenant}/+/status", qos=1)
        client_obj.subscribe(f"zs/v1/{args.tenant}/+/ack", qos=1)

    def on_message(client_obj, userdata, message):
        del userdata
        handle_message(client_obj, message, args.tenant, tls_enabled)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, 60)
    client.loop_start()
    try:
        while True:
            if client.is_connected():
                published, failed = publish_due_commands(
                    client,
                    args.tenant,
                    signer,
                    now_us=int(time.time() * 1_000_000),
                    retry_after_us=int(args.command_retry_seconds * 1_000_000),
                )
                if failed:
                    print(
                        f"MQTT command publish batch: {published} queued, {failed} failed",
                        file=sys.stderr,
                    )
            time.sleep(args.command_poll_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
