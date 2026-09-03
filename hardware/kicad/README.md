# ZS-BPLA EVT KiCad input package v0.3

This directory is the authoritative CAD input package before native schematic capture.
The current execution environment does not contain KiCad/kicad-cli, so no unvalidated
`.kicad_sch`, PCB or Gerber is claimed as production-ready.

## Sheet plan
1. 01_POWER - solar input, BQ24650, battery, V_CELL, V3V3, V_MIC_1V8.
2. 02_MCU - STM32U585ZIT6Q, reset, SWD, decoupling, clocks.
3. 03_AUDIO - 4 x TDK T5838, common MDF1 clock, 4 data lines.
4. 04_GNSS - MAX-M10S, TIMEPULSE/PPS, antenna and backup.
5. 05_CELLULAR - BG95-M3, V_CELL, 1.8 V UART translation, SIM/eSIM.
6. 06_LORA - SX1262, RU868 matching and antenna.
7. 07_BLE - nRF52832-class service module, Android-only MVP.
8. 08_STORAGE_SENSORS - 512 Mbit NOR, TMP117, LIS2DW12, tamper.
9. 09_CONNECTORS_TEST - battery/solar/service/debug/test fixture.

## Required CAD gates
- Import/refine `components.csv`, `nets.csv`, and sheet CSV files.
- Verify every MCU alternate function against STM32U585 DS/CubeMX.
- Run ERC with no unexplained errors.
- Verify BG95 1.8 V IO and V_CELL transient design against Quectel reference design.
- Use manufacturer/reference matching for SX1262 RF and validate conducted output/S11.
- Verify solar-panel cold Voc stays below charger input limit.
- Run DRC, impedance review, assembly clearance and production test-point review.

## Verification gate
Native schematic/PCB must pass KiCad ERC/DRC before Gerber release. The current package is CAD input/pre-schematic data; do not manufacture from it before ERC/DRC.
