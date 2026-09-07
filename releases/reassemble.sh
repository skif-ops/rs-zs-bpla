#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 PARTS_DIRECTORY OUTPUT_ZIP" >&2
  exit 2
fi

find "$1" -maxdepth 1 -type f -name 'part-*' -print0 | sort -z | xargs -0 cat -- > "$2"
sha256sum "$2"

