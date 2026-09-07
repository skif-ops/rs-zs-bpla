#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
deploy_dir="$(cd "$script_dir/.." && pwd)"
cd "$deploy_dir"
mkdir -p ../data ../output
test -f .env
test -f tls/ca.crt
docker compose --env-file .env -f compose.ubuntu.yml build --pull
docker compose --env-file .env -f compose.ubuntu.yml up -d
docker compose --env-file .env -f compose.ubuntu.yml ps
curl --fail --retry 12 --retry-delay 2 http://127.0.0.1:8000/api/v1/health >/dev/null
printf 'Muhoed health check PASS. Use an SSH tunnel to 127.0.0.1:8000.\n'
