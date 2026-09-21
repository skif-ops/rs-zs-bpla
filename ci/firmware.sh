#!/usr/bin/env bash
# Host test suite + STM32U585 target build. Run by .github/workflows/ci-dispatch.yml (ubuntu).
set -euo pipefail
sudo apt-get update -qq && sudo apt-get install -y -qq gcc-arm-none-eabi cmake >/dev/null
cmake -S firmware -B build-host -DCMAKE_BUILD_TYPE=Release
cmake --build build-host --parallel
ctest --test-dir build-host --output-on-failure
if [ -d firmware/targets/evt_pre_20/app ]; then
  cmake -S firmware/targets/evt_pre_20/app -B build-target \
    -DCMAKE_TOOLCHAIN_FILE="$PWD/firmware/targets/evt_pre_20/app/cmake/arm-none-eabi.cmake" -DCMAKE_BUILD_TYPE=Release
  cmake --build build-target --parallel
fi
