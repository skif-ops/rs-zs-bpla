"""Muhoed twin: the server side of the station digital twin (firmware/twin/station_twin.c).

Speaks the twin link on stdin/stdout, one line per message: ``PUB <topic> <hex-payload>`` for MQTT and
``LORA <hex-frame>`` for the LoRa gateway (LORA_BACKUP_ICD_v0_1 addendum A; an ACK frame goes back the same way). Uplink
publishes from the station are decoded with the real server codecs (station.cbor_codec) and stored in memory;
every accepted detection is answered with the real receipt encoding (station.event_receipt_codec) on the
station's receipt topic, exactly as mqtt_bridge would.  Remote commands (ICD addendum D): ``ZS_TWIN_COMMANDS`` lists a
queue (``set_params``, ``reboot``, ``reboot_again`` = the same reboot UUID redelivered); the first command goes out
when the station subscribes to its down topic (``SUB <topic> <wall_us>``, as the broker delivers its QoS 1 queue),
every further one in reply to the previous ACK.  Commands are signed with the repository test key
(tools/generate_command_set_vector.py), valid from one second before the station's wall clock for ten minutes.  Every line gets exactly one reply (a message or ``OK``) so the twin's simulated time stays deterministic
regardless of wall-clock scheduling.  A final ``REPORT`` line summarises what arrived.
Run by the twin: ``python3 -m twin.twin_server`` from the server/ directory.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid

from station import cbor_codec
from station import lora_codec
from station.command_codec import CommandSigner, decode_command_ack, encode_signed_command
from station.event_receipt_codec import EventReceipt, encode_event_receipt
from station.schemas import StationCommand
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# The twin station's engineer key (the registry would hold it per station); the LoRa key derives from it.
TWIN_ENGINEER_KEY = bytes(range(0xA0, 0xA0 + 32))


# Repository test key of the command vectors (public data, never a production key).
TWIN_COMMAND_SEED = bytes(range(1, 33))
TWIN_SET_PARAMS = {"reset": False, "params": {"heartbeat_period_s": 900, "mic_channel": 1, "listen_dwell_s": 5}}


def command_queue(spec: str) -> list[tuple[str, str, dict]]:
    """(command_id, command, payload) in delivery order; ``reboot_again`` reuses the reboot UUID."""
    queue: list[tuple[str, str, dict]] = []
    reboot_id = None
    for item in [x.strip() for x in spec.split(",") if x.strip()]:
        if item == "set_params":
            queue.append((str(uuid.uuid4()), "CMD_SET_PARAMS", TWIN_SET_PARAMS))
        elif item == "reboot":
            reboot_id = str(uuid.uuid4())
            queue.append((reboot_id, "CMD_REBOOT", {"delay_s": 10}))
        elif item == "reboot_again" and reboot_id:
            queue.append((reboot_id, "CMD_REBOOT", {"delay_s": 10}))
        else:
            raise SystemExit(f"twin server: unknown command {item!r}")
    return queue


def main() -> int:
    detections: list[dict] = []
    heartbeats: list[dict] = []
    seen_event_ids: set[int] = set()
    duplicates = 0
    decode_errors = 0
    lora_frames = 0
    lora_detections = 0
    lora_key = lora_codec.derive_key(TWIN_ENGINEER_KEY)
    signer = CommandSigner(Ed25519PrivateKey.from_private_bytes(TWIN_COMMAND_SEED))
    queue = command_queue(os.environ.get("ZS_TWIN_COMMANDS", ""))
    signed: dict[str, bytes] = {}          # a redelivered command is the identical envelope, as a broker would resend it
    commands_sent: list[dict] = []
    acks: list[dict] = []
    wall_us = 0
    down_topic = ""
    out = sys.stdout

    def next_command() -> str:
        if not queue or not down_topic:
            return "OK"
        command_id, name, payload = queue.pop(0)
        if command_id not in signed:
            signed[command_id] = encode_signed_command(StationCommand(
                command_id=command_id, station_id=int(down_topic.split("/")[3]), command=name, payload=payload,
                created_time_us=wall_us - 1_000_000, expires_time_us=wall_us + 600_000_000), signer)
        commands_sent.append({"command_id": command_id, "command": name})
        return f"PUB {down_topic} {signed[command_id].hex()}"

    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line:
            continue
        parts = line.split(" ", 2)
        if parts[0] == "LORA" and len(parts) == 2:
            # gateway: authenticate, dedup by event_id like the MQTT path, ACK only after the event is stored
            lora_frames += 1
            try:
                e = lora_codec.decode_event(bytes.fromhex(parts[1]), lora_key)
            except ValueError as exc:
                decode_errors += 1
                sys.stderr.write(f"twin gateway: {exc}\n")
                out.write("OK\n"); out.flush()
                continue
            dup = e.event_id in seen_event_ids
            if dup:
                duplicates += 1
            else:
                lora_detections += 1
            seen_event_ids.add(e.event_id)
            detections.append({"event_id": e.event_id, "seq_no": e.seq_no, "boot_id": e.boot_id, "time_us": e.event_time_us,
                               "class_id": e.class_id, "confidence": e.confidence_u8, "duplicate": dup, "via": "lora",
                               "retry": bool(e.flags & lora_codec.FLAG_RETRY)})
            out.write(f"LORA {lora_codec.encode_ack(e.station_id, e.boot_id, e.seq_no, lora_key).hex()}\n"); out.flush()
            continue
        if parts[0] == "SUB" and len(parts) == 3:
            # the station subscribed: deliver the queued command (the broker's QoS 1 queue)
            if parts[1].endswith("/down"):
                down_topic, wall_us = parts[1], int(parts[2])
                out.write(next_command() + "\n")
            else:
                out.write("OK\n")
            out.flush()
            continue
        if parts[0] == "REPORT":
            report = {
                "commands_sent": commands_sent, "acks": acks,
                "detections": len(detections), "unique_event_ids": len(seen_event_ids), "duplicates": duplicates,
                "heartbeats": len(heartbeats), "decode_errors": decode_errors,
                "lora_frames": lora_frames, "lora_detections": lora_detections,
                "last_heartbeat": heartbeats[-1] if heartbeats else None,
                "events": detections[:20],
            }
            out.write("REPORT " + json.dumps(report) + "\n"); out.flush()
            continue
        if parts[0] != "PUB" or len(parts) != 3:
            out.write("OK\n"); out.flush()
            continue
        topic, payload = parts[1], bytes.fromhex(parts[2])
        segs = topic.split("/")
        if len(segs) != 5:
            out.write("OK\n"); out.flush()
            continue
        prefix, tenant, station, kind = "/".join(segs[:2]), segs[2], segs[3], segs[4]
        try:
            if kind == "up":
                d = cbor_codec.decode_detection_cbor(payload)
                dup = d.event_id in seen_event_ids
                if dup:
                    duplicates += 1
                seen_event_ids.add(d.event_id)
                detections.append({"event_id": d.event_id, "seq_no": d.seq_no, "boot_id": d.boot_id, "time_us": d.event_time_us,
                                   "class_id": d.classification.class_id, "confidence": d.classification.confidence_u8, "duplicate": dup, "via": "gsm"})
                receipt = EventReceipt(station_id=d.station_id, boot_id=d.boot_id, seq_no=d.seq_no, event_id=d.event_id,
                                       payload_sha256=hashlib.sha256(payload).digest())
                out.write(f"PUB {prefix}/{tenant}/{station}/receipt {encode_event_receipt(receipt).hex()}\n"); out.flush()
            elif kind == "ack":
                a = decode_command_ack(payload)
                acks.append({"command_id": a.command_id, "result": a.result_code, "detail": a.detail_code,
                             "completed_time_us": a.completed_time_us})
                out.write(next_command() + "\n"); out.flush()
            elif kind == "status":
                h = cbor_codec.decode_heartbeat_cbor(payload)
                heartbeats.append({"time_us": h.time_us, "battery_pct": h.power.battery_pct, "battery_mv": h.power.battery_mv,
                                   "detector": (h.detector.model_dump() if getattr(h, "detector", None) else None)})
                out.write("OK\n"); out.flush()
            else:
                out.write("OK\n"); out.flush()
        except Exception as exc:  # noqa: BLE001 - the twin reports, it does not crash on a bad frame
            decode_errors += 1
            sys.stderr.write(f"twin server: {kind}: {exc}\n")
            out.write("OK\n"); out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
