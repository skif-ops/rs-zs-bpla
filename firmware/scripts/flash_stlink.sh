#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 1 ]; then
  printf 'Usage: %s firmware.hex\n' "$0" >&2
  exit 2
fi
image_path="$1"
test -f "$image_path"
STM32_Programmer_CLI -c port=SWD mode=UR reset=HWrst -e all -w "$image_path" -v -rst
printf 'Flash and verification PASS\n'
