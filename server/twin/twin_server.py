"""Muhoed twin: the server side of the station digital twin (firmware/twin/station_twin.c).

Speaks the twin link on stdin/stdout, one line per message: ``PUB <topic> <hex-payload>`` for MQTT and
``LORA <hex-frame>`` for the LoRa gateway (LORA_BACKUP_ICD_v0_1 addendum A; an ACK frame goes back the same way). Uplink
publishes from the station are decoded with the real server codecs (station.cbor_codec) and stored in memory;
every accepted detection is answered with the real receipt encoding (station.event_receipt_codec) on the
station's receipt topic, exactly as mqtt_bridge would.  Remote commands (ICD addendum D): ``ZS_TWIN_COMMANDS`` lists a
queue (``set_params``, ``reboot``, ``reboot_again`` = the same reboot UUID redelivered); the first command goes out
when the station subscribes to its down topic (``SUB <topic> <wall_us>``, as the broker delivers its QoS 1 queue),
every further one in reply to the previous ACK.  Commands are signed with the repository test key
(tools/generate_command_set_vector.py), valid from one second before the station's wall clock for ten minutes.
Key rotation (addendum E): ``rotate_key`` installs the next test key (tools/generate_command_rotate_vector.py); every
command is signed by the bridge's ``CommandKeyring`` against a real ``EventStore`` (heartbeats and the rotation's ACK),
so after the OK the next command goes out under the next key; ``reboot_by_old_key`` is a CMD_REBOOT signed with the
old key on purpose (the station must refuse it once the next key is promoted).  Every line gets exactly one reply (a message or ``OK``) so the twin's simulated time stays deterministic
regardless of wall-clock scheduling.  Audio (addendum B): with ``ZS_TWIN_AUDIO=<pre|post|both>`` the first detection
over GSM is answered with its receipt and, on a second line, a signed ``CMD_REQUEST_AUDIO`` for that event (the
auto-request policy of mqtt_bridge.request_event_audio); the request is a command of a real ``EventStore`` and the
chunks on the audio topic go through the bridge's ``ingest_audio_chunk`` (authorisation against the request, parts in
SQLite, SHA-256, WAV on disk; ``ZS_TWIN_WAV_DIR`` keeps the store and the WAV files, a temporary directory otherwise;
``ZS_TWIN_AUDIO_REDELIVER=1`` answers the first chunk with the same request envelope again, as a QoS 1 redelivery
would).  Firmware update (addendum F): ``update_firmware`` queues CMD_UPDATE_FIRMWARE for a release of the repository
test image (tools/generate_fw_update_vector.py, version ``ZS_TWIN_FW_VERSION``, default 2) signed by the test release
key into a real ``ReleaseRepository``; every ``fwreq`` is answered by the bridge's ``serve_request`` against the
store (``ZS_TWIN_FW_DROP=n`` drops the n-th request, as a lost chunk would; ``ZS_TWIN_FW_REDELIVER=1`` sends the command
envelope again after the second chunk, as a QoS 1 redelivery during the download would).  Network configuration (addendum G): ``set_network`` queues CMD_SET_NETWORK_CONFIG moving the station to
``muhoed2.twin:443`` (the same twin behind a second name, which the twin modem reaches), ``set_network_bad`` one to a
host no DNS knows (the station must roll back).  Bearing stream (addendum H): batches on the bearing topic are
decoded with the server codec and listed in the report.  A final ``REPORT`` line summarises what arrived.
Run by the twin: ``python3 -m twin.twin_server`` from the server/ directory.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import importlib.util

from station import cbor_codec
from station import firmware_codec
from station import lora_codec
from station.bearing_codec import decode_bearing_batch
from station.command_codec import CommandKeyring, CommandSigner, decode_command_ack, encode_signed_command
from station.event_receipt_codec import EventReceipt, encode_event_receipt
from station.audio_ingest import ingest_audio_chunk
from station.mqtt_bridge import request_event_audio
from station.network_config import NETWORK_COMMAND
from station.schemas import StationCommand
from station.store import EventStore
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# The twin station's engineer key (the registry would hold it per station); the LoRa key derives from it.
TWIN_ENGINEER_KEY = bytes(range(0xA0, 0xA0 + 32))


# Repository test key of the command vectors (public data, never a production key).
TWIN_COMMAND_SEED = bytes(range(1, 33))
TWIN_NEXT_COMMAND_SEED = bytes(range(33, 65))    # the next key of tools/generate_command_rotate_vector.py
TWIN_SET_PARAMS = {"reset": False, "params": {"heartbeat_period_s": 900, "mic_channel": 1, "listen_dwell_s": 5}}
TWIN_RELEASE_SEED = bytes(range(65, 97))          # the test release key of tools/generate_fw_update_vector.py
TWIN_FW_IMAGE_BYTES = 40_000                      # 40 chunks; the twin's simulated bank holds 120 KiB
TWIN_NETWORK = {"version": 2, "server_host": "muhoed2.twin", "mqtt_port": 443}   # the second endpoint the twin modem reaches


def twin_release(repository: firmware_codec.ReleaseRepository, version: int) -> firmware_codec.Release:
    spec = importlib.util.spec_from_file_location("gen_fw_update", Path(__file__).resolve().parents[2] / "tools" / "generate_fw_update_vector.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    signer = firmware_codec.ReleaseSigner(Ed25519PrivateKey.from_private_bytes(TWIN_RELEASE_SEED))
    return repository.add(gen.test_image(version=version, size=TWIN_FW_IMAGE_BYTES), signer)


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
        elif item == "rotate_key":
            nxt = CommandSigner(Ed25519PrivateKey.from_private_bytes(TWIN_NEXT_COMMAND_SEED))
            queue.append((str(uuid.uuid4()), "CMD_ROTATE_COMMAND_KEY", {"public_key": nxt.public_key_hex}))
        elif item == "reboot_by_old_key":
            queue.append((str(uuid.uuid4()), "CMD_REBOOT@old", {"delay_s": 10}))
        elif item == "update_firmware":
            queue.append((str(uuid.uuid4()), "CMD_UPDATE_FIRMWARE", {}))      # the payload comes from the release
        elif item == "set_network":                   # addendum G: the twin broker under its second name and port
            queue.append((str(uuid.uuid4()), NETWORK_COMMAND, dict(TWIN_NETWORK)))
        elif item == "set_network_bad":               # a host no DNS knows: the station must roll back
            queue.append((str(uuid.uuid4()), NETWORK_COMMAND, {"version": 2, "server_host": "dead.twin"}))
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
    keyring = CommandKeyring(signer, CommandSigner(Ed25519PrivateKey.from_private_bytes(TWIN_NEXT_COMMAND_SEED)))
    queue = command_queue(os.environ.get("ZS_TWIN_COMMANDS", ""))
    signed: dict[str, bytes] = {}          # a redelivered command is the identical envelope, as a broker would resend it
    key_ids: dict[str, str] = {}
    commands_sent: list[dict] = []
    acks: list[dict] = []
    wall_us = 0
    down_topic = ""
    out = sys.stdout
    audio_segment = os.environ.get("ZS_TWIN_AUDIO", "")
    wav_dir = os.environ.get("ZS_TWIN_WAV_DIR", "")
    store_dir = Path(wav_dir) if wav_dir else Path(tempfile.mkdtemp(prefix="zs_twin_"))
    event_store = EventStore(store_dir / "twin.sqlite3") if audio_segment else None
    key_store = EventStore(store_dir / "twin_keys.sqlite3")        # heartbeats and commands for the keyring
    audio_chunks = 0
    audio_duplicates = 0
    audio_segments: list[dict] = []
    audio_requested: list[dict] = []
    audio_envelopes: dict[str, bytes] = {}
    redeliver = os.environ.get("ZS_TWIN_AUDIO_REDELIVER", "") == "1"
    repository = firmware_codec.ReleaseRepository(store_dir / "firmware")
    release = twin_release(repository, int(os.environ.get("ZS_TWIN_FW_VERSION", "2"))) if any(c[1] == "CMD_UPDATE_FIRMWARE" for c in queue) else None
    fw_drop = int(os.environ.get("ZS_TWIN_FW_DROP", "0") or 0)
    fw_redeliver = os.environ.get("ZS_TWIN_FW_REDELIVER", "") == "1"
    fw_command: list[str] = []
    fw_requests = 0
    fw_served = 0
    fw_dropped = 0
    bearing_batches: list[dict] = []

    def request_audio(detection) -> str:
        """A signed CMD_REQUEST_AUDIO for the event, sent right after its receipt (second reply line)."""
        cmd = request_event_audio(detection, segment=audio_segment, min_gap_us=120_000_000, now_us=wall_us, event_store=event_store)
        if cmd is None:
            return ""
        command_id, event_id = cmd.command_id, detection.event_id
        envelope = encode_signed_command(cmd.model_copy(update={
            "created_time_us": wall_us - 1_000_000, "expires_time_us": wall_us + 600_000_000}), signer)
        commands_sent.append({"command_id": command_id, "command": "CMD_REQUEST_AUDIO"})
        audio_requested.append({"command_id": command_id, "event_id": event_id, "segment": audio_segment})
        audio_envelopes[command_id] = envelope
        return f"PUB {down_topic} {envelope.hex()}"

    def next_command() -> str:
        if not queue or not down_topic:
            return "OK"
        command_id, name, payload = queue.pop(0)
        station_id = int(down_topic.split("/")[3])
        by_old_key = name.endswith("@old")
        name = name.removesuffix("@old")
        if command_id not in signed:
            if name == "CMD_UPDATE_FIRMWARE":           # the bridge serves the chunks against this store record
                payload = release.command_payload()
                fw_command.append("")
            if name in ("CMD_ROTATE_COMMAND_KEY", "CMD_UPDATE_FIRMWARE"):   # the keyring / fw server read the store
                command_id = key_store.create_command(station_id, name, payload).command_id
            chosen = keyring.primary if by_old_key else keyring.signer_for(station_id, key_store)
            signed[command_id] = encode_signed_command(StationCommand(
                command_id=command_id, station_id=station_id, command=name, payload=payload,
                created_time_us=wall_us - 1_000_000, expires_time_us=wall_us + 600_000_000), chosen)
            key_ids[command_id] = chosen.key_id.hex()
            if fw_command and fw_command[-1] == "":
                fw_command[-1] = command_id
        commands_sent.append({"command_id": command_id, "command": name, "key_id": key_ids[command_id]})
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
            audio_store = None
            if event_store is not None and audio_requested:
                req = audio_requested[0]
                record = event_store.command_record(req["command_id"])
                audio_store = {"acked": record["acked"], "ack_result": record["ack_result"], "ack_detail": record["ack_detail"],
                               "pending_parts": sum(n for n, _ in event_store.audio_upload_progress(int(down_topic.split("/")[3]), req["command_id"]).values())}
            report = {
                "audio_store": audio_store,
                "commands_sent": commands_sent, "acks": acks,
                "detections": len(detections), "unique_event_ids": len(seen_event_ids), "duplicates": duplicates,
                "heartbeats": len(heartbeats), "decode_errors": decode_errors,
                "lora_frames": lora_frames, "lora_detections": lora_detections,
                "audio_requested": audio_requested, "audio_chunks": audio_chunks, "audio_duplicates": audio_duplicates,
                "audio_segments": audio_segments,
                "last_heartbeat": heartbeats[-1] if heartbeats else None,
                "heartbeat_self_test_ok": [h["self_test_ok"] for h in heartbeats],
                "key_ids": {"current": keyring.primary.key_id.hex(), "next": keyring.next.key_id.hex()},
                "firmware": {"release_version": release.manifest.version if release else None, "requests": fw_requests,
                             "served": fw_served, "dropped": fw_dropped,
                             "chunks": (release.manifest.size + firmware_codec.CHUNK_BYTES - 1) // firmware_codec.CHUNK_BYTES if release else 0},
                "events": detections[:20],
                "bearing_batches": len(bearing_batches),
                "bearings": [dict(s, track_event_id=b["track_event_id"]) for b in bearing_batches for s in b["samples"]],
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
                                   "class_id": d.classification.class_id, "confidence": d.classification.confidence_u8, "duplicate": dup, "via": "gsm",
                                   "doa": {"valid": d.doa.valid, "azimuth_deg": d.doa.azimuth_deg, "elevation_deg": d.doa.elevation_deg,
                                           "sigma_deg": d.doa.sigma_deg} if d.doa.valid else None,
                                   "tdoa_valid": d.spatial.tdoa_valid})
                receipt = EventReceipt(station_id=d.station_id, boot_id=d.boot_id, seq_no=d.seq_no, event_id=d.event_id,
                                       payload_sha256=hashlib.sha256(payload).digest())
                reply = f"PUB {prefix}/{tenant}/{station}/receipt {encode_event_receipt(receipt).hex()}\n"
                if audio_segment and down_topic and not audio_requested and not dup:
                    request = request_audio(d)
                    if request:
                        reply += request + "\n"
                out.write(reply); out.flush()
            elif kind == "ack":
                a = decode_command_ack(payload)
                acks.append({"command_id": a.command_id, "result": a.result_code, "detail": a.detail_code,
                             "completed_time_us": a.completed_time_us})
                if event_store is not None and event_store.command_record(a.command_id) is not None:
                    event_store.ack_command(a.station_id, a.command_id, a.result_code, a.detail_code, a.completed_time_us)
                if key_store.command_record(a.command_id) is not None:
                    key_store.ack_command(a.station_id, a.command_id, a.result_code, a.detail_code, a.completed_time_us)
                out.write(next_command() + "\n"); out.flush()
            elif kind == "audio":
                audio_chunks += 1
                status = ingest_audio_chunk(payload, int(station), event_store=event_store, now_us=wall_us)
                audio_duplicates += status in ("duplicate", "already")
                if status == "complete":
                    event_id = audio_requested[0]["event_id"]
                    done = {r["segment"] for r in audio_segments}
                    for row in event_store.list_audio(int(station), event_id):
                        if row["segment"] not in done:
                            audio_segments.append({"event_id": event_id, "segment": row["segment"], "sample_rate": row["sample_rate"],
                                                   "start_time_us": row["start_time_us"], "seconds": row["duration_ms"] / 1000,
                                                   "path": row["path"], "command_id": row["command_id"]})
                if redeliver and audio_chunks == 1 and audio_requested:
                    command_id = audio_requested[0]["command_id"]
                    commands_sent.append({"command_id": command_id, "command": "CMD_REQUEST_AUDIO"})
                    out.write(f"PUB {down_topic} {audio_envelopes[command_id].hex()}\n"); out.flush()
                else:
                    out.write("OK\n"); out.flush()
            elif kind == "fwreq":
                fw_requests += 1
                answer = firmware_codec.serve_request(payload, int(station), event_store=key_store, repository=repository,
                                                      now_us=int(time.time() * 1_000_000))
                if answer is None or fw_requests == fw_drop:
                    fw_dropped += answer is not None
                    out.write("OK\n"); out.flush()
                else:
                    fw_served += 1
                    reply = f"PUB {prefix}/{tenant}/{station}/fw {answer[1].hex()}\n"
                    if fw_redeliver and fw_served == 2 and fw_command:          # the broker delivers the command again
                        commands_sent.append({"command_id": fw_command[0], "command": "CMD_UPDATE_FIRMWARE", "key_id": key_ids[fw_command[0]]})
                        reply += f"PUB {down_topic} {signed[fw_command[0]].hex()}\n"
                    out.write(reply); out.flush()
            elif kind == "bearing":
                batch = decode_bearing_batch(payload)
                if batch.station_id != int(station):
                    raise ValueError("station_id mismatch between topic and bearing batch")
                bearing_batches.append({"track_event_id": batch.track_event_id, "time_trust": batch.time_trust,
                                        "samples": [{"time_us": x.time_us, "azimuth_deg": x.azimuth_deg,
                                                     "elevation_deg": x.elevation_deg, "sigma_deg": x.sigma_deg} for x in batch.samples]})
                out.write("OK\n"); out.flush()
            elif kind == "status":
                h = cbor_codec.decode_heartbeat_cbor(payload)
                key_store.upsert_station(h)
                heartbeats.append({"time_us": h.time_us, "battery_pct": h.power.battery_pct, "battery_mv": h.power.battery_mv, "self_test_ok": h.self_test_ok,
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
