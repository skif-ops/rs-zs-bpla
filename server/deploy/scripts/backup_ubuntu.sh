#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
server_dir="$(cd "$script_dir/../.." && pwd)"
stamp="$(date -u +%Y%m%d_%H%M%S)"
archive="${1:-$server_dir/backup_${stamp}.tar.gz}"
tar -C "$server_dir" -czf "$archive" data output
printf 'Backup saved: %s\n' "$archive"
