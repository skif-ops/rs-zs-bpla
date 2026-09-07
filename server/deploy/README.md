# Deployment v1.2 EVT-MB

## Development smoke environment

```bash
cd deploy
docker compose -f docker-compose.dev.yml up --build
curl http://127.0.0.1:8000/api/v1/health
```

The development broker listens only on localhost and allows anonymous clients for bench testing. It is not a production configuration.

## Production requirements

- Private APN/VPN where available.
- MQTT over TLS 1.2+ on port 8883.
- Per-station credentials or client certificates.
- Server-side `station_id` authorization, rate limiting and replay protection.
- Persistent database volume and backup policy.
- Reverse proxy for the REST/WebSocket UI with HTTPS.
- Telegram/mobile notification credentials injected as secrets, not committed.

The station wire message remains compact CBOR. `station/cbor_codec.py` is the reference decoder for firmware protocol 1.4.
