# Мухоед / РС ЗС-БПЛА server development branch

Рабочая ветка создана непосредственно из `drone_acoustic_intelligence-2026-06-30.zip` и сохраняет исходные workflow анализа файлов, dataset UI и file-based localization.

## Что добавлено

- live station protocol under `/api/v1`;
- JSON and CBOR detection ingestion;
- station heartbeat and security events;
- compact cellular heartbeat with full IMSI/ICCID accepted only over mutual-TLS
  MQTT status transport; general station listing returns masked identifiers;
- persistent SQLite WAL event store;
- AIR_WARNING for one station and AIR_ALERT only for two or more stations;
- WGS84/ECEF/ENU geodesy;
- DOA intersection for 2+ stations;
- 4+ station arrival-time TDOA nonlinear solver;
- real 3D constant-velocity Kalman filter;
- WebSocket realtime event stream;
- station command queue and audio request/upload;
- optional MQTT/TLS bridge process;
- signed MQTT command downstream with canonical CBOR, Ed25519, TTL/retry and
  station-bound application ACK; omitted signing key disables downstream;
- portable firmware command codec with canonical fixed-memory parsing, strict
  station/time/TTL checks, required signature and durable-dedup callbacks, ACK
  encoding and a deterministic server-to-firmware Ed25519 test vector;
- portable power-loss-safe command journal that persists accepted/completed
  states and permits ACK encoding only from a durable completed record;
- bounded firmware public-key rotation adapter with SHA-256-derived key IDs and
  a mandatory target-provided Ed25519 verification backend;
- portable command application channel that emits an ACK only after verified,
  idempotent execution and durable completed-result read-back;
- portable binary MQTT command boundary with exact topic/payload lengths,
  canonical station ownership, QoS 1 and non-retained delivery guards;
- portable atomic event outbox with schema-4 encoding, metadata CRC32, payload
  SHA-256, priority/FIFO ordering and at-least-once torn-write recovery;
- fail-closed station HTTP transport, enabled only on an isolated bench with
  exact opt-in `ZS_STATION_HTTP_INSECURE_BENCH=1`;
- hierarchical family/type updates use only the latest 4-8 unique feature
  windows; fewer than four windows remain `warming_up`;
- portable station firmware uses the same 4-8-window and 5/8 consensus rule
  before filling the compact hierarchy fields;
- known UAV families retain an explicit unknown-type branch:
  `UNKNOWN_PROP_PISTON_UAV`, `UNKNOWN_TURBINE_JET_UAV` or
  `UNKNOWN_ROTOR_ELECTRIC_UAV`;
- 365-day retention cleanup hook.

## Run

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\\Scripts\\activate
pip install --require-hashes -r requirements.lock.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

OpenAPI: `http://localhost:8000/docs`

## Test

```bash
pytest -q
```

Current working branch: 131 full tests PASS.

Dependency constraints, hashed locks and the reproducible CycloneDX SBOM are
described in `DEPENDENCY_LOCK.md`.

## v0.8.1 field-recording corrections

- narrow suppression of stationary 50/60 Hz mains harmonics before propulsion-comb fitting;
- adaptive RMS gate for feature windows when a short transient distorts peak normalization;
- acoustic-family confidence now includes absolute model fit and is explicitly conditional on an independently confirmed AIR target;
- unvalidated expert FP-1/GR2 hints remain research metadata and cannot become an operational type;
- `httpx2` is pinned in runtime requirements so the complete API regression suite is reproducible.

The four September 2026 field recordings are intentionally not added to the training set because their aircraft type and flight metadata have not yet been confirmed. Detection is usable; a family may remain visible after 4-8 agreeing windows, but the exact type stays `UNKNOWN` until labeled source material passes the dataset readiness gate.

Live feature updates may set `air_target_confirmed=true` only when the event has
already passed the independent AIR target gate. This flag restricts family
competition to UAV propulsion families; it does not permit a hard type lock.

## MQTT bridge

Run separately after configuring TLS credentials:

```bash
python -m station.mqtt_bridge --host mqtt.example --port 8883 --tenant pilot \
  --ca /run/tls/ca.crt --cert /run/tls/bridge.crt \
  --key /run/tls/bridge.key \
  --command-signing-key /run/tls/command-signing.key
```

The command signing key is an owner-only (`0600`) Ed25519 PKCS#8 PEM. Without
it the bridge remains telemetry-only and will not downgrade to unsigned
commands. To rotate it without a site visit (MQTT ICD addendum E), start the
bridge with `--command-next-signing-key <new pem>` as well, queue
`POST /api/v1/stations/{id}/command-key-rotation` with the new public key it
prints, and switch `--command-signing-key` to the new key once every station
reports it as current (`detector.command_key_id` in `/api/v1/stations`).

Station firmware goes over MQTT as well (ICD addendum F). Offline, create the
release key once (`python -m pki.cli fw-release-key --out release.pem`, its
public key is built into the firmware with `-DZS_FW_RELEASE_PUBLIC_KEYS=`) and
sign every application image into the release repository
(`python -m pki.cli fw-sign --key release.pem --image dioneya_evt_pre_20.bin
--out data/firmware`; target and version come from the image's `.fw_info`).
The bridge serves the chunks from that directory (`--firmware-dir`,
`ZS_FIRMWARE_DIR`, default `data/firmware`); `GET /api/v1/firmware/releases`
lists it and `POST /api/v1/stations/{id}/firmware-update {"version": N}`
queues CMD_UPDATE_FIRMWARE. Progress is in the heartbeat
(`detector.fw_version / fw_state / fw_other_version`).

A retrained station model goes out the same way without a firmware release (MQTT ICD addendum I): export it as a
package (`python tools/export_station_model.py --package m7.diom --version 7`), sign it offline with the same release
key (`python -m pki.cli model-sign --key release.pem --model m7.diom --out data/models`), and queue it with
`POST /api/v1/stations/{id}/model-update {"version": 7}` (`GET /api/v1/models/releases` lists the packages; the bridge
serves them from `--model-dir` / `ZS_MODEL_DIR`, default `data/models`). The station loads it after the OK ACK without
a reset; the heartbeat model text changes from `c46` (built-in) to `m7`.

Acceptance metrics of a trial (decision 5, `docs/ACCEPTANCE_METRICS.md`): with the ground truth of what flew
(`dioneya.trial/1`: stations, passes with the target's GNSS log, quiet periods, exclusions, reference SPL),
`python tools/acceptance_metrics.py report --db data/zs_bpla.sqlite3 --trial trial.json --json r.json --md r.md`
gives Pd per class with its 95 % interval, detection ranges, classification, false alarms per station-hour, the
elevation sector, bearing and track point accuracy, received levels and the geometry of the layout. Blind zones of
the station geometry: `GET /api/v1/geometry/coverage?station_ids=…&range_m=…`, and the «Слепые зоны расстановки»
layer of the replay page.

The network part of a station's configuration (server host, MQTT/HTTPS port, certificate pin, tenant, topic prefix,
SIM, APNs; ICD addendum G) changes remotely as well: `POST /api/v1/stations/{id}/network-config` with the fields to
change queues CMD_SET_NETWORK_CONFIG (the version defaults to the one the station reports + 1). The station tries the
new record on its next bring-up and stores it only when a session comes online with it; otherwise it rolls back after
three failed bring-ups or 30 minutes. The outcome is in the heartbeat (`detector.net_config_version / net_state /
net_failed_version`); the CA reference stays a service-mode field. Command delivery uses QoS 1, retain false and durable retries until a
station-bound application ACK or the 15-minute TTL. The checked-in ACL contains
separate topic rights for station credentials 01 through 20.

The server and portable firmware event-receipt path is host-tested: after durable
detection processing the bridge publishes canonical CBOR on the station-specific
`receipt` topic, bound to the exact uplink payload SHA-256. Byte-identical retries
do not repeat fusion side effects. Production store-and-forward is not complete
until BG95 binary receipt handling and target storage/endurance are implemented
and verified on assembled stations. MQTT PUBACK alone must not authorize event
reclamation.

Full IMSI/ICCID is stored in the restricted station record. Do not expose the
SQLite database or raw status payloads through logs, backups, diagnostics or the
general API. The JSON/HTTP heartbeat route deliberately rejects cellular identity
even when the isolated bench transport is enabled.

## Data provenance note

The source archive contains `features.csv` with 840 windows / 8 labels and a trained model, but the raw FP-1 MP3 referenced by `uploads/981a53c2-.../______.mp3` is not present. Russian `dataset/raw` folder names in the ZIP had CP437/UTF-8 mojibake; the working copy has been repaired.

Do not retrain the full current model and claim reproducibility until the missing FP-1 source is restored or the dataset is rebuilt from traceable raw recordings.

## v0.2 integration changes

- Compact numeric-key CBOR from the MCU is decoded by `station/cbor_codec.py` without requiring a Python CBOR package at runtime for the supported subset.
- `/api/v1/health` added for deployment checks.
- Development Docker Compose includes a local Mosquitto broker and separate MQTT bridge.
- Regression suite now includes actual compact-CBOR ingress tests.
- `tools/golden/` contains 100 x 1-second/32-kHz PCM16 golden vectors generated from the non-empty source audio recovered from the supplied archive.
