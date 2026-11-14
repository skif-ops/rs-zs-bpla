#!/usr/bin/env bash
# Restore of the Muhoed server data and output from an archive of backup_ubuntu.sh (docs/SERVER_RETENTION_2026-10-03.md).
# Stops the services, runs station/backup.py --restore inside the server image (it refuses an archive that is not a
# server backup or whose databases fail their integrity check, replaces the contents of data and output and keeps
# what it replaced in output/backups/before_restore_<stamp>.tar.gz), then starts the services again whatever happened.
set -euo pipefail
archive="${1:?usage: restore_ubuntu.sh <backup.tar.gz | backup.zip>}"
[ -f "$archive" ] || { echo "archive not found: $archive" >&2; exit 1; }
archive="$(cd "$(dirname "$archive")" && pwd)/$(basename "$archive")"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
deploy_dir="$(cd "$script_dir/.." && pwd)"
server_dir="$(cd "$deploy_dir/.." && pwd)"
stamp="$(date -u +%Y%m%d_%H%M%S)"
case "$archive" in *.zip) ext=".zip" ;; *) ext=".tar.gz" ;; esac
inside="restore_${stamp}${ext}"
cd "$deploy_dir"
compose=(docker compose --env-file .env -f compose.ubuntu.yml)
mkdir -p "$server_dir/output/backups"
cp "$archive" "$server_dir/output/backups/$inside"
cleanup() {
  rm -f "$server_dir/output/backups/$inside"
  "${compose[@]}" up -d
}
trap cleanup EXIT
"${compose[@]}" stop
"${compose[@]}" run --rm --no-deps -T server python -m station.backup --restore "/app/output/backups/$inside"
printf 'Restored: %s\n' "$archive"
