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
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

OpenAPI: `http://localhost:8000/docs`

## Test

```bash
pytest -q
```

Current working branch: 94 tests PASS.

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
python -m station.mqtt_bridge --host mqtt.example --port 8883 --tenant pilot
```

Full IMSI/ICCID is stored in the restricted station record. Do not expose the
SQLite database or raw status payloads through logs, backups, diagnostics or the
general API. The JSON/HTTP heartbeat route deliberately rejects cellular identity.

## Data provenance note

The source archive contains `features.csv` with 840 windows / 8 labels and a trained model, but the raw FP-1 MP3 referenced by `uploads/981a53c2-.../______.mp3` is not present. Russian `dataset/raw` folder names in the ZIP had CP437/UTF-8 mojibake; the working copy has been repaired.

Do not retrain the full current model and claim reproducibility until the missing FP-1 source is restored or the dataset is rebuilt from traceable raw recordings.

## v0.2 integration changes

- Compact numeric-key CBOR from the MCU is decoded by `station/cbor_codec.py` without requiring a Python CBOR package at runtime for the supported subset.
- `/api/v1/health` added for deployment checks.
- Development Docker Compose includes a local Mosquitto broker and separate MQTT bridge.
- Regression suite now includes actual compact-CBOR ingress tests.
- `tools/golden/` contains 100 x 1-second/32-kHz PCM16 golden vectors generated from the non-empty source audio recovered from the supplied archive.
