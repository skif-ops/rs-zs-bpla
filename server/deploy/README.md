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
- Build identity: package the server with `git archive` (`git archive
  --format=tar.gz --prefix=muhoed/ -o muhoed-server.tar.gz <commit> server
  tools/generate_command_signing_key.py`). It writes the commit and its date into
  `server/BUILD_ID` (`.gitattributes`, `export-subst`), and the server shows the
  release version with that build in the footer of every page and in
  `/api/v1/health` (`version`, `build`), so an operator and monitoring see which
  build runs without reading the host. A working copy keeps the placeholder and
  asks git; `ZS_BUILD="<commit> <YYYY-MM-DD>"` overrides both on a bench
  (utils/build_info.py).
- MQTT over TLS 1.2+ on port 8883. The server certificate carries the compose
  service name `mqtt` besides the public name and address (`python -m pki.cli
  server-cert --dns <public> --dns mqtt --ip <ip>`): the bridges and `mqtt_alerts`
  connect to the broker as `mqtt` and verify that name. Mosquitto reads
  `tls/server.key.pem` after dropping privileges to uid 1883 (chown 1883, mode
  0400, the `tls` directory 0755). The CRL `tls/crl.pem` is valid 30 days and
  an expired one makes the broker refuse every client: rewrite it with
  `python -m pki.cli crl` and restart `mqtt` at least monthly (a weekly cron).
- Per-station credentials or client certificates.
- Server-side `station_id` authorization, rate limiting and replay protection.
- Broker ACL permits the bridge to publish event application receipts and each
  station credential to read only its own `receipt` topic.
- The output API `dioneya.alert/1` over MQTT (`mqtt_alerts` service, the bridge
  certificate): topic `dioneya/alert/v1/{tenant}`, QoS 1. A consumer gets its own
  client certificate and its tenants from the PKI (`python -m pki.cli consumer-cert
  <name> --tenants ...`), the regenerated ACL gives it read access to those topics
  only; revoke with `consumer-revoke` (CRL + ACL again). The broker keeps up to
  10 000 queued messages and the session for 7 days for a consumer that is away
  (`max_queued_messages`, `persistent_client_expiration`); older backlog is caught
  up over `/api/v1/alerts?after_seq=`.
- Persistent database volume, retention and backups (docs/SERVER_RETENTION_2026-10-03.md):
  the server removes events, bearings, tracks, commands and ingress records older
  than `ZS_RETENTION_DAYS` (90), the `dioneya.alert/1` outbox older than
  `ZS_ALERT_OUTBOX_DAYS` (30) and the audio of events, WAV files included, older
  than `ZS_AUDIO_RETENTION_DAYS` (30), at startup and then once a day
  (`ZS_RETENTION_INTERVAL_S`, 86400). `/api/v1/health` reports the database and
  audio sizes, the free disk space and the last cleanup, so monitoring sees a
  filling disk. Back up with `deploy/scripts/backup_ubuntu.sh [archive]`
  (Windows: `backup_windows.ps1 [-Destination]`): the databases are copied with
  the SQLite backup API inside the server container, so the archive is consistent
  while the server runs; never archive the live `*.sqlite3` with its `-wal`.
  Restore with `deploy/scripts/restore_ubuntu.sh <archive>` (Windows:
  `restore_windows.ps1 -Archive <archive>`): the services are stopped, the
  archive is checked (a server backup, databases pass `integrity_check`), what
  it replaces is kept in `output/backups/before_restore_<stamp>.tar.gz`, and the
  services are started again.
- Reverse proxy for the REST/WebSocket UI with HTTPS. The proxy must pass the
  original `Host` header (`proxy_set_header Host $host;` and the WebSocket
  `Upgrade`/`Connection` headers): changing requests made with the session cookie
  are accepted only when `Origin`/`Referer` matches `Host`.
- Operator login (`station/operator_auth.py`): every page, `/api/v1` route and the
  `/api/v1/stream` WebSocket need an operator; only `/static`, `/login`,
  `/api/v1/health` and the (disabled) station bench routes are open. Without
  a login the server refuses everything (fail-closed). Create accounts on the
  server, outside Git (`data/operators.json` and `data/operator_state.sqlite3`,
  both mode 0600):

  ```bash
  OA="docker compose -f compose.ubuntu.yml exec server python -m station.operator_auth"
  docker compose -f compose.ubuntu.yml exec server python -m station.operator_auth add-user duty --role viewer
  $OA add-user anna --role operator
  $OA add-user ivan --roles operator,engineer
  $OA totp-enroll ivan                       # secret shown once: add it to an authenticator app
  $OA add-user sec --role admin
  $OA totp-enroll sec
  $OA set-scope anna --tenants north --stations 17,18   # what she sees (empty: all)
  $OA issue-token anna --label reports --scopes read --expires-days 90
  ```

  Roles (an account may have several): `viewer` reads events, stations and the
  map; `operator` also listens to event audio (it can contain speech), requests
  audio and runs analyses; `engineer` also edits the dataset and commands
  stations (network configuration, firmware and model updates); `admin` (security
  administrator) manages accounts and their visibility, rotates the command
  signing key and reads the audit log, but does not command stations; `service`
  is for integrations (read only). Engineers and admins log in with a TOTP code
  of an authenticator app (`totp-enroll`; `totp-reset` when a phone is lost).
  An account file from before roles keeps working: `"role": "operator"` becomes
  the operator role, and engineer rights are given with `set-roles`.

  `set-scope` limits an account to tenants and stations: it then sees only
  those stations and what they took part in, in every API, stream and the
  `dioneya.alert/1` output. The security admin and engineers set it from the
  web too (`PUT /api/v1/access/accounts/<name>/scope`); a station's tenant is
  the tenant of the MQTT bridge its messages come through. A file analysis
  (`/single`, `/localization`) belongs to the account that ran it: its plots,
  reports and separated audio are seen by that account, by accounts without
  limits and by accounts whose tenants cover the maker's
  (docs/SERVER_ACCESS_CONTROL_2026-10-02.md, §10).

  The superuser `skif_root` (role `superuser`, every permission, every station,
  the switch of the audit log of actions) is created by the server itself with
  the default password `12345678`. Log in as `skif_root` right after the first
  start, before the server is reachable from the network: the first login asks
  for a new password (12+ characters) and then shows the second-factor secret
  once and takes a code; only then a session opens. `skif_root` cannot be
  removed, disabled, limited or given other roles; `$OA passwd skif_root` and
  `$OA totp-reset skif_root` recover it on the server.

  The `/admin` page does the same from the browser for the security admin and
  `skif_root` (accounts, roles, resets, tokens, sessions, the audit log) and for
  engineers (station visibility); every change there repeats the current
  second-factor code. An account made or reset there sets its own password at
  its next login, and an engineer or admin enrols its second factor there too.

  Scripts send `Authorization: Bearer <token>`; a token may use only its scopes
  (default `read`), never more than its account. The session cookie is `Secure`:
  serve the UI over HTTPS (an SSH tunnel to `localhost` also works). Sessions
  are kept on the server: logout ends one, 30 min without a request or 12 h end
  it, `passwd`, `disable`, `remove-user` and `logout-all` end all of an
  account's at once (`sessions` lists them). Failed logins lock one name from
  one address after 5 tries and a whole address after 20 (15 min); behind the
  proxy set `ZS_OPERATOR_TRUSTED_PROXY=1` and have the proxy append
  `X-Forwarded-For`, otherwise all logins share the proxy address.

  The audit log records logins and failed logins, logouts, every changing
  request (who, from where, what, the answer) and every account change; each
  record carries the hash of the one before. `$OA audit --limit 100` shows it,
  `$OA audit-verify` checks that no record was changed or removed; back up
  `operator_state.sqlite3` with the database. `skif_root` may switch the log of
  actions off and on (`PUT /api/v1/admin/audit-logging`, or `$OA audit-logging
  off|on`); the switching, failed logins and refusals are recorded even then.
  Never set `ZS_OPERATOR_AUTH_INSECURE_BENCH`, `ZS_OPERATOR_COOKIE_SECURE=0` or
  `ZS_OPERATOR_TOTP=0` in production.
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
