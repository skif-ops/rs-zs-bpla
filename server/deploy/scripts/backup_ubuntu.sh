#!/usr/bin/env bash
# Backup of the Muhoed server data and output (docs/SERVER_RETENTION_2026-10-03.md).  station/backup.py runs inside
# the server container: it copies every SQLite database with the SQLite backup API (a consistent snapshot while the
# server and the bridges write; an archive of the live file with its WAL is not) and packs data (audio included)
# and output into one tar.gz.  With the server down the image is run once for the same job.
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
deploy_dir="$(cd "$script_dir/.." && pwd)"
server_dir="$(cd "$deploy_dir/.." && pwd)"
stamp="$(date -u +%Y%m%d_%H%M%S)"
archive="${1:-$server_dir/backup_${stamp}.tar.gz}"
cd "$deploy_dir"
compose=(docker compose --env-file .env -f compose.ubuntu.yml)
inside="/app/output/backups/backup_${stamp}.tar.gz"
mkdir -p "$server_dir/output/backups"
if [ -n "$("${compose[@]}" ps -q server 2>/dev/null)" ]; then
  "${compose[@]}" exec -T server python -m station.backup --out "$inside"
else
  "${compose[@]}" run --rm --no-deps -T server python -m station.backup --out "$inside"
fi
mv "$server_dir/output/backups/backup_${stamp}.tar.gz" "$archive"
printf 'Backup saved: %s\n' "$archive"
