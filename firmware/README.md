# ЗС-БПЛА firmware development baseline

This is the platform-neutral production core for the station firmware. It freezes event types, CBOR encoding, LoRa power-state behavior, PPS-to-audio time mapping, feature ordering and the first-level centroid classifier exported from the current server model.

The hardware-specific STM32Cube project must bind the frozen APIs to STM32U585ZI HAL/LL/CMSIS-DSP. Production FFT/YIN/MFCC must pass the golden-vector acceptance test.

Build host verification:
```sh
cmake -S . -B build && cmake --build build && ctest --test-dir build --output-on-failure
```
