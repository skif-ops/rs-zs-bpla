# Station digital twin — phase 1 (2026-09-24)

`firmware/twin/station_twin.c` runs the portable station stack on the host with simulated time:

    scene (twin/scene.c) -> 4-ch audio ring -> zs_station_pipeline (zs_dsp_mcu, AIR gate, level 1)
      -> zs_event_outbox (RAM) -> zs_power_modes with the tasks.c event wiring -> app_comms (the real STM32
      comms task via tests/host_sim) -> scripted BG95 -> twin link -> server/twin/twin_server.py

The server side speaks the link on a pipe (`PUB <topic> <hex>` per MQTT message), decodes uplinks with the
real server codecs, answers every accepted detection with the real receipt encoding and prints a report.

    cd server && ../build-host/zs_station_twin --scene drone --seconds 200 --server "python3 -m twin.twin_server"
    ... --gsm-outage 15 480      # the network disappears between 15 s and 480 s of station time
    ... --dump-pcm scene.pcm     # the mono scene for tools/presence_eval

Scenes: `drone` (fly-by 20-60 s, f0 185 Hz, harmonics, Doppler-like drift, rotor wobble; a second fly-by
after 100 s in long runs), `ground` (32 Hz rumble + broadband), `quiet`. The synthetic background is level
NONE on the host pipeline; the drone yields CONFIRMED windows and a detection event.  Real recordings (FP-1)
remain the reference for the detector itself - the twin exercises the system around it.

## What the first runs found (all fixed here)

1. **Every event was published twice.** The outbox drain re-offered an event as soon as the broker acknowledged
   the publish, until the server receipt arrived (`zs_event_outbox_peek` has no notion of "in flight"). With
   real receipt latency this is 2..10 publishes per event; on LoRa it would be fatal. Fix: a receipt hold in
   `zs_mqtt_event_transport` (`ZS_MQTT_EVENT_RECEIPT_WAIT_MS` 30 s, RAM table, `zs_event_outbox_peek_filtered`):
   a broker-acknowledged event is not offered again before the receipt or the hold expiry.
2. **An event emitted during a GSM outage was never retried.** After the S3 watchdog (180 s) the station went
   back to listening and nobody raised OUTBOX_PENDING again; the event waited for the next detection or reboot.
   Fix: outbox retry in the supervisor (twin and tasks.c): 5 min after a failed S3, doubling to 1 h, reset by
   COMMS_DONE (`APP_OUTBOX_RETRY_MS`, `APP_OUTBOX_RETRY_MAX_MS`).
3. **OUTBOX_PENDING in S1 did nothing** (it only set `comms_requested`, honoured on GATE_NEGATIVE, which no task
   raises yet): the boot-time outbox flush of PR #55 and the retry above could never reach S3 from S1. Fix in
   `zs_power_modes`: S0 and S1 enter S3 on OUTBOX_PENDING; S2 still finishes the detection first.

Verified end to end: drone -> event -> S3 -> publish -> receipt -> outbox empty -> COMMS_DONE -> S1 -> S0;
with a 465 s outage: S3 times out, S0, retry at +300 s -> delivered, one server detection, no duplicates.

## Not in phase 1

Dual SIM in the twin (own host test exists), commands from the server, LoRa (no station-side event transport
yet - phase 2 designs it here), multi-station / TDOA (phase 3), battery model, real recordings as scenes.
CTest runs a smoke (`station_twin_smoke`: a drone fly-by must yield an event); the closed loop with the Python
server twin runs from the server CI job.
