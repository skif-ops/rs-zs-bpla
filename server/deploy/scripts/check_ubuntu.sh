#!/usr/bin/env bash
set -euo pipefail
docker version
docker compose version
docker compose -f "$(dirname "$0")/../compose.ubuntu.yml" config
curl -fsS http://127.0.0.1:8000/api/v1/health
