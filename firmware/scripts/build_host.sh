#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd "$script_dir/.." && pwd)"
build_dir="$root_dir/build-host-v1.2"
mkdir -p "$build_dir"
gcc -std=c11 -Wall -Wextra -Werror -pedantic \
  -I"$root_dir/include" -I"$root_dir/generated" \
  "$root_dir"/src/*.c "$root_dir/tests/test_core.c" -lm \
  -o "$build_dir/zs_core_tests"
"$build_dir/zs_core_tests"
gcc -std=c11 -Wall -Wextra -Werror -pedantic \
  -I"$root_dir/include" -I"$root_dir/generated" \
  "$root_dir"/src/*.c "$root_dir/tools/emit_detection.c" -lm \
  -o "$build_dir/zs_emit_detection"
"$build_dir/zs_emit_detection" "$build_dir/detection_v14.cbor"
printf 'Host verification PASS\n'
