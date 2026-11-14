# Station digital twin — phase 2: channel model, degraded-GSM policy, LoRa fallback (2026-09-24)

## Channel model (twin)
`--publish-loss P` (the BG95 reports a lost publish only after its own retries, +QMTPUB result 2 after 15 s),
`--receipt-latency MS` (default 60 ms; real links 0.5-5 s), `--receipt-loss P`, `--mqtt-refuse FROM TO` (the
network registers, the broker does not open), `--gsm-outage FROM TO`.  With 50 % loss and 3 s receipts the receipt
hold of phase 1 keeps every event at exactly one server detection.

## Degraded-GSM policy (twin and tasks.c)
Three consecutive S3 sessions ended by the watchdog (`APP_COMMS_DEGRADED_AFTER`) mark the link degraded: the S3
watchdog drops 180 s -> 60 s (`APP_COMMS_MAX_DEGRADED_MS`), the route hint switches to LoRa (`app_route_hint_lora`),
and a capped S3 probes GSM every 30 min (`APP_GSM_PROBE_MS`); a completed session restores the defaults.  Modem
cost of a dead network: ~9 min searching at the start of an outage, then ~1 min per probe.

## LoRa fallback
`LORA_BACKUP_ICD_v0_1_ADDENDUM_A_COMPACT_UPLINK.md`: 38-byte event frame, 21-byte ACK, HMAC-SHA256/8 tag with a
key derived from the engineer key, regional profile id; codecs `zs_lora_frame` (C) and `station/lora_codec.py`
with a shared vector; airtime per AN1200.13 (SF9/125 kHz: 268 + 186 ms -> ~75 events/hour in the 1 % duty cycle).
`zs_lora_uplink` (host-tested): drains the outbox one event at a time while the route hint is LoRa, ACK window 3 s,
per-event backoff 30 s -> 10 min, duty-cycle token bucket, late/duplicate ACKs accepted, delivered only on a valid
ACK (same outbox semantics as MQTT).  The gateway (twin server) authenticates, dedups by event_id, stores, ACKs.

Not yet on the target: `tasks.c` exposes the route hint only; wiring `zs_lora_uplink` to `zs_sx1262` waits for the
regional profile gate of the ICD (tx_enabled) and the RF bring-up — the module and the frames are ready.

## Scenarios (server/tools/test_station_twin_e2e.py, CI protocol-e2e job)
1. Drone over GSM with 2 s receipts: one detection, one heartbeat, COMMS_DONE, no duplicates.
2. 12 events during a 20-minute outage with 30 % LoRa loss both ways: degraded after 2 failed sessions, 16 LoRa
   frames, 12 delivered exactly once (late ACK duplicates deduped by the gateway), exponential backoff on the
   unlucky event (30/60/120/240 s), GSM probe after the network returns -> "link healthy again".
