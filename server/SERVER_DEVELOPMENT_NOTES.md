# РС ЗС-БПЛА server branch

This branch preserves the original Мухоед single-file and file-based localization workflows and adds live station ingestion.

## Added
- `/api/v1/stations/{id}/heartbeat`
- `/api/v1/stations/{id}/detection` and `.cbor`
- `/api/v1/stations/{id}/security`
- `/api/v1/stations`, `/api/v1/events`, `/api/v1/events/{id}`
- audio request/command polling and audio upload
- `/api/v1/stream` WebSocket
- SQLite WAL persistence with 365-day retention hook
- DOA intersection and 4+ station arrival-time TDOA solver on WGS84/ENU
- 3D constant-velocity Kalman tracking
- optional MQTT/TLS bridge

## Backward compatibility
Original `/api/analyze-single`, `/api/localize`, dataset UI and tests are retained.

## v0.8 family layer

- Added `ml/acoustic_family.py` and `ml/family_classifier.py`.
- Family identity is evaluated before UAV type identity using the unchanged 43-feature contract.
- `Лютый` and weak `FP-1` contribute to `PROP_PISTON`, with source quality x label-confidence weighting.
- Unsupported `TURBINE_JET` is explicit and is not fabricated from absent training data.
- Specific type identity remains governed by v0.7 readiness gates and may remain `UNKNOWN`.
