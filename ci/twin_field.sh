#!/usr/bin/env bash
# Three station twins in one field, one target, through the real Muhoed path (server/tools/test_twin_field_e2e.py):
# station positions from the firmware, equal event ids of different stations, one fused track, acceptance metrics.
# Run by .github/workflows/ci-dispatch.yml (ubuntu).
set -euo pipefail
python3 -m pip install --require-hashes -r server/requirements.lock.txt
cmake -S firmware -B build-field -DCMAKE_BUILD_TYPE=Release
cmake --build build-field --parallel --target zs_station_twin
ZS_STATION_TWIN="$PWD/build-field/zs_station_twin" python3 server/tools/test_twin_field_e2e.py
