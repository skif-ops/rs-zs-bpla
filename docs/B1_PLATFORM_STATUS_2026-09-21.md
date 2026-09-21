# Milestone B1 (platform bring-up) - status 2026-09-21

Branch `feature/b1-platform` on top of `feature/station-config-pki`.

## Delivered

Portable modules (host tests 36/36 with -Wall -Wextra -Wpedantic -Werror):
- `zs_power_modes`: S0..S4 + SHUTDOWN scheduler, events, dwell/watchdog timers, wake-storm hysteresis, transition journal, clock profile and rail map per mode.
- `zs_pdm_capture`: MDF DMA double buffers -> int16 frames into `zs_audio_ring`, DC blocker, sample counter, overrun/sequence accounting, cross-correlation channel-lag self-test.
- `zs_pps_sync`: TIM2 capture <-> sample counter interpolation, UTC label pairing, timer wrap, drop accounting, sample-rate error in ppm; feeds `zs_time`.
- `zs_selftest`: registry with required/optional tests, CBOR report.

Target application `firmware/targets/evt_pre_20/app` (STM32U585, builds with arm-none-eabi-gcc 13.2, 53 KB flash / 399 KB RAM):
- FreeRTOS V11.1.0 (ADR-001), STM32CubeU5 v1.9.0 HAL fetched at the commits pinned in `vendor/stm32cubeu5.lock.json`.
- Clock tree per `REV_A_INTERNAL_HSI_MSI_PLL_NO_HSE`: MSIS 4 MHz in PLL-mode locked to the SiT1552 LSE, PLL1R 160 MHz SYSCLK, PLL1P 3.2 MHz MDF kernel; PDM clock 3.2 MHz, SINC5 decimation 100 -> 32 kHz.
- MDF1 filters 0..3 on SITF0..3 (PB1/PD6/PE7/PE4), CCK0 on PE9, one GPDMA1 linked-list circular channel each, synchronous start with one software TRGO, half/complete callbacks into `zs_pdm_capture`, block marks into `zs_pps_sync`.
- TIM2 CH1 (PA0) 32-bit input capture at 16 MHz for PPS; USART1 (BG95), USART2 (GNSS RMC -> UTC label), LPUART1 console with bench commands `st lag pps audio svc modes heap`.
- Rail enables EN_MODEM (PD4) and EN_AUX (PD5), PWR_GOOD/PWR_FAULT inputs, MIC_WAKE EXTI8 -> supervisor event, TAMPER_IN (PC7) polled as service trigger (5 s hold), AAD_CFG (PA15) idle.

## Validated on host only

Everything above compiles and links; nothing has run on silicon yet. First hardware steps
(NUCLEO-U575ZI-Q + PCB-MIC + GNSS module): clock tree comes up and console prints; `audio`
shows growing block count with zero overruns; `lag` reports 0 for all channels on a common
source; `pps` shows bound count increasing with a GNSS fix; measure MDF timing margin and
audio task CPU share.

## Open items found during B1

1. The locked Rev.A pin map has no service-button pin. Decision 2026-09-21 (no board change): TAMPER_IN (PC7, enclosure switch) doubles as the service trigger - held active for 5 s = service mode request, shorter activations are tamper events; the console `svc` command remains for the bench. To be recorded as a DEC entry and reflected in the BLE ICD.
2. The 3 s four-channel prehistory (768 KB int16) does not fit SRAM together with heap and DMA buffers; B1 keeps 1 s (256 KB). Decision 2026-09-21: the full prehistory moves to NOR through `zs_prehistory`/`zs_nor_archive` in B3.
3. `zs_dsp.c`/`zs_fft.c` are excluded from the target library (double precision, ~430 KB static): the CMSIS-DSP rewrite is the next B1 item.
4. `zs_dual_sim.c` line 28 triggers `-Wtype-limits` on the Cortex-M33 build (comparison always true); harmless, to be cleaned when that module is touched.
5. Tickless idle / STOP2 / clock profile switching are stubbed (`apply_power` keeps 160 MHz).
6. GPDMA port allocation and `TransferEventMode` for the MDF channels follow ST's MDF examples; confirm on hardware that half-transfer events are delivered in linked-list circular mode with a single node (otherwise split each buffer into two nodes).

## Building

```
cmake -S firmware/targets/evt_pre_20/app -B build-target \
  -DCMAKE_TOOLCHAIN_FILE=firmware/targets/evt_pre_20/app/cmake/arm-none-eabi.cmake -DCMAKE_BUILD_TYPE=Release
cmake --build build-target      # dioneya_evt_pre_20.elf/.bin/.hex + .map
```
Vendor sources are fetched from GitHub at pinned commits; `FETCHCONTENT_SOURCE_DIR_*` overrides allow an offline build.
The CI workflow `firmware-target.yml` (docs/ci/firmware-target.yml until the workflow permission is available) runs the same build on ubuntu with `gcc-arm-none-eabi`.
