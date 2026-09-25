"""Muhoed twin: the server side of the station digital twin (firmware/twin/station_twin.c).

Speaks the twin link on stdin/stdout, one line per message: ``PUB <topic> <hex-payload>`` for MQTT and
``LORA <hex-frame>`` for the LoRa gateway (LORA_BACKUP_ICD_v0_1 addendum A; an ACK frame goes back the same way). Uplink
publishes from the station are decoded with the real server codecs (station.cbor_codec) and stored in memory;
every accepted detection is answered with the real receipt encoding (station.event_receipt_codec) on the
station's receipt topic, exactly as mqtt_bridge would.  A final ``REPORT`` line summarises what arrived.
Run by the twin: ``python3 -m twin.twin_server`` from the server/ directory.
"""
from __future__ import annotations

import hashlib
import json
import sys

from station import cbor_codec
from station import lora_codec
from station.event_receipt_codec import EventReceipt, encode_event_receipt

# The twin station's engineer key (the registry would hold it per station); the LoRa key derives from it.
TWIN_ENGINEER_KEY = bytes(range(0xA0, 0xA0 + 32))


def main() -> int:
    detections: list[dict] = []
    heartbeats: list[dict] = []
    seen_event_ids: set[int] = set()
    duplicates = 0
    decode_errors = 0
    lora_frames = 0
    lora_detections = 0
    lora_key = lora_codec.derive_key(TWIN_ENGINEER_KEY)
    out = sys.stdout
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
        if parts[0] == "REPORT":
            report = {
                "detections": len(detections), "unique_event_ids": len(seen_event_ids), "duplicates": duplicates,
                "heartbeats": len(heartbeats), "decode_errors": decode_errors,
                "lora_frames": lora_frames, "lora_detections": lora_detections,
                "last_heartbeat": heartbeats[-1] if heartbeats else None,
                "events": detections[:20],
            }
            out.write("REPORT " + json.dumps(report) + "\n"); out.flush()
            continue
        if parts[0] != "PUB" or len(parts) != 3:
            continue
        topic, payload = parts[1], bytes.fromhex(parts[2])
        segs = topic.split("/")
        if len(segs) != 5:
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
            elif kind == "status":
                h = cbor_codec.decode_heartbeat_cbor(payload)
                heartbeats.append({"time_us": h.time_us, "battery_pct": h.power.battery_pct, "battery_mv": h.power.battery_mv,
                                   "detector": (h.detector.model_dump() if getattr(h, "detector", None) else None)})
        except Exception as exc:  # noqa: BLE001 - the twin reports, it does not crash on a bad frame
            decode_errors += 1
            sys.stderr.write(f"twin server: {kind}: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
