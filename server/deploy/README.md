# Deployment 1.2.0 source baseline for EVT-PRE-20

## Development smoke environment

```bash
cd deploy
docker compose -f docker-compose.dev.yml up --build
curl http://127.0.0.1:8000/api/v1/health
```

The development broker and server listen only on localhost and allow explicit
insecure station transports for bench testing. `docker-compose.dev.yml` and the
plaintext `compose.windows.yml` set `ZS_STATION_HTTP_INSECURE_BENCH=1` and
`ZS_OPERATOR_AUTH_INSECURE_BENCH=1` (no operator login); both are
isolated-bench configurations and must not be used for production.

## Production requirements

- Public APN/CGNAT is the EVT-PRE-20 baseline; the station opens outbound connections only.
- MQTT over TLS 1.2+ on port 8883.
- Per-station credentials or client certificates.
- Server-side `station_id` authorization, rate limiting and replay protection.
- Broker ACL permits the bridge to publish event application receipts and each
  station credential to read only its own `receipt` topic.
- Persistent database volume and backup policy.
- Reverse proxy for the REST/WebSocket UI with HTTPS. The proxy must pass the
  original `Host` header (`proxy_set_header Host $host;` and the WebSocket
  `Upgrade`/`Connection` headers): changing requests made with the session cookie
  are accepted only when `Origin`/`Referer` matches `Host`.
- Operator login (`station/operator_auth.py`): every page, `/api/v1` route and the
  `/api/v1/stream` WebSocket need an operator; only `/static`, `/login`,
  `/api/v1/health` and the (disabled) station bench routes are open. Without
  accounts the server refuses everything (fail-closed). Create accounts on the
  server, outside Git (`data/operators.json`, mode 0600):

  ```bash
  docker compose -f compose.ubuntu.yml exec server python -m station.operator_auth add-user anna --role operator
  docker compose -f compose.ubuntu.yml exec server python -m station.operator_auth add-user duty --role viewer
  docker compose -f compose.ubuntu.yml exec server python -m station.operator_auth issue-token anna --label reports
  ```

  `viewer` reads events and stations; `operator` also requests audio, manages the
  dataset and runs analyses, and is the only role that may fetch event audio (it
  can contain speech). Scripts send `Authorization: Bearer <token>`. The session
  cookie is `Secure`: serve the UI over HTTPS (an SSH tunnel to `localhost` also
  works). Failed logins lock one name from one address after 5 tries and a whole
  address after 20 (15 min); behind the proxy set `ZS_OPERATOR_TRUSTED_PROXY=1`
  and have the proxy append `X-Forwarded-For`, otherwise all logins share the
  proxy address. Never set `ZS_OPERATOR_AUTH_INSECURE_BENCH` or
  `ZS_OPERATOR_COOKIE_SECURE=0` in production.
- Station HTTP ingress disabled by default; production telemetry enters through
  the mutual-TLS MQTT bridge. Do not set `ZS_STATION_HTTP_INSECURE_BENCH`.
- Telegram/mobile notification credentials injected as secrets, not committed.
- Python packages installed from `requirements.lock.txt` with `--require-hashes`;
  `sbom/server.cdx.json` checked against that exact lock in CI.
- MQTT command publication requires `/run/tls/command-signing.key`, an
  unencrypted PKCS#8 Ed25519 private key readable only by its owner. Generate an
  initial keypair outside Git, from the repository root:

  ```bash
  python tools/generate_command_signing_key.py \
    --private server/deploy/tls/command-signing.key \
    --public server/deploy/tls/command-signing.pub
  ```

  Provision the exact 32-byte `.pub` file through the controlled station process.
  Never copy the private file to a station or commit either generated file.
  Ubuntu startup requires mode `0600`; on Windows restrict the source file with
  NTFS ACLs to the deployment account and Docker service before using the TLS
  compose file. Platform permission evidence remains part of the clean-deploy gate.

The station wire messages remain compact CBOR. `station/cbor_codec.py` is the
reference decoder for interface release 1.5, including detection schema 4 and
protected cellular heartbeat schema 1.
