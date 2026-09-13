# Deployment 1.2.0 source baseline for EVT-PRE-20

## Development smoke environment

```bash
cd deploy
docker compose -f docker-compose.dev.yml up --build
curl http://127.0.0.1:8000/api/v1/health
```

The development broker and server listen only on localhost and allow explicit
insecure station transports for bench testing. `docker-compose.dev.yml` and the
plaintext `compose.windows.yml` set `ZS_STATION_HTTP_INSECURE_BENCH=1`; both are
isolated-bench configurations and must not be used for production.

## Production requirements

- Public APN/CGNAT is the EVT-PRE-20 baseline; the station opens outbound connections only.
- MQTT over TLS 1.2+ on port 8883.
- Per-station credentials or client certificates.
- Server-side `station_id` authorization, rate limiting and replay protection.
- Persistent database volume and backup policy.
- Reverse proxy for the REST/WebSocket UI with HTTPS.
- Station HTTP ingress disabled by default; production telemetry enters through
  the mutual-TLS MQTT bridge. Do not set `ZS_STATION_HTTP_INSECURE_BENCH`.
- Telegram/mobile notification credentials injected as secrets, not committed.

The station wire messages remain compact CBOR. `station/cbor_codec.py` is the
reference decoder for interface release 1.5, including detection schema 4 and
protected cellular heartbeat schema 1.
