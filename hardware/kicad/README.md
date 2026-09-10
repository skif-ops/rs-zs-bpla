# ZS-BPLA EVT-PRE-20 KiCad package

Status: `CAPTURE_INPUT / NOT FOR MANUFACTURE`
Configuration: `EVT-PRE-20 Rev.A`
Authoritative branch: `evt-pre-20`

This directory is the authoritative electrical-CAD input package for the EVT-PRE-20 custom-PCB build. It is intentionally blocked from manufacturing until native KiCad schematic/PCB capture, ERC/DRC, CAM and independent review are complete.

## Frozen baseline used for capture

- MCU: `STM32U585VIT6Q`, LQFP100 14x14 mm. The earlier `STM32U585CIU6`/48-pin and `STM32U585ZIT6Q` references are superseded for EVT-PRE-20.
- Microphones: 4 x TDK/InvenSense `T5838`, identical MPN; same lot preferred.
- Acoustic geometry: 3+1, equilateral base 120 mm, upper microphone +150 mm over center.
- Cellular: Quectel `BG95-M3` candidate, two physical nano-SIM slots through external 2:1 SIM mux, Dual-SIM Single-Standby only.
- GNSS/PPS: independent u-blox `MAX-M10S` class receiver.
- LoRa: Ebyte `E22-900M22S` / SX1262 class, RU868 pilot profile on all 20 units.
- BLE commissioning/diagnostics/OTA coprocessor: Raytac `MDBT50Q-P1MV2` based on Nordic `nRF52840`, integrated PCB antenna. `ESP32-C3-MINI-1-N4` is superseded and forbidden in active Rev.A BOM/capture.
- BLE requirements: BLE 2M/1M/Coded Long Range, authenticated commissioning, signed OTA, local diagnostics; Wi-Fi is not required.
- Local storage: W25Q512-class 64 MB NOR plus industrial microSD.
- Power source: 12.8 V LiFePO4 40-60 Ah, external 10 A LiFePO4 MPPT, 60-80 W solar panel.
- MPPT function is external. Do not reintroduce the older BQ24650/CN3791 charger topology into EVT-PRE-20 PCB-MAIN or PCB-PWR.

## PCB set

1. `PCB-MAIN`: MCU, BG95, dual SIM, MAX-M10S, LoRa module, nRF52840 BLE module, NOR, microSD, sensors, USB service, SWD and test points.
2. `PCB-MIC`: one T5838 microphone leaf; four identical boards per station.
3. `PCB-PWR`: protected battery interface and DC/DC rails for 3.8 V modem, 3.3 V digital/AON and 1.8 V microphone domains. External MPPT remains a separate assembly.

## Logical sheet plan

1. `01_POWER` - protected input and regulated rails; no integrated solar MPPT.
2. `02_MCU` - STM32U585VIT6Q, clocks, reset, SWD, decoupling, boot straps.
3. `03_AUDIO` - four PDM channels, common clock fanout/interface, microphone connectors.
4. `04_GNSS` - MAX-M10S, TIMEPULSE/PPS, RF connector/bias, backup supply.
5. `05_CELLULAR` - BG95-M3, 3.8 V transient decoupling, 1.8 V logic translation, dual nano-SIM mux and ESD.
6. `06_LORA` - E22-900M22S/SX1262 interface, RF connector/matching/ESD.
7. `07_BLE` - Raytac MDBT50Q-P1MV2 / nRF52840 service, commissioning and OTA coprocessor with SWD/UART recovery access and antenna keepout.
8. `08_STORAGE_SENSORS` - W25Q512, industrial microSD, LIS2DW12, temperature and current/voltage monitoring.
9. `09_CONNECTORS_TEST` - PCB-PWR, MIC1..MIC4, USB-C service, SWD, production test fixture and revision straps.

## Required CAD gates before Gerber release

- Freeze CubeMX pin/peripheral assignment for STM32U585VIT6Q; no unresolved AF conflicts.
- Complete native `.kicad_sch` and `.kicad_pcb` for MAIN, MIC and PWR.
- Datasheet/reference-design review for STM32U585, T5838, BG95, MAX-M10S, E22/SX1262, nRF52840/Raytac module and all power ICs.
- ERC: zero unexplained errors.
- DRC: zero blocker/critical violations.
- Review modem burst current, brownout and decoupling at 3.8 V.
- Review PDM 1.8 V level compatibility, clock fanout and channel-to-channel skew.
- Review dual-SIM powered-off isolation, signal integrity and low-capacitance ESD.
- RF review for cellular/GNSS/LoRa 50-ohm paths, BLE 2.4 GHz antenna keepout, grounding and coexistence.
- Validate BLE range/RSSI/OTA throughput in the final vacuum-cast housing and the full-lot 3D fallback housing.
- USB differential pair and ESD review.
- Power-current/thermal review for PCB-PWR including fault cases.
- DFT review: SWD, reset, rails, production UART and fixture-accessible test points.
- Generate and inspect Gerber, Excellon, IPC-356, pick-and-place, BOM/AVL, assembly drawings, fabrication notes and STEP.
- Independent Review A: schematic/net/pin/BOM check against source requirements.
- Independent Review B: PCB/CAM/assembly/DFM check against released source.

## Manufacturing prohibition

Do not manufacture or assemble EVT-PRE-20 PCB from the CSV sheets, component lists, current placeholder `.kicad_pro`, or any Gerber generated before both independent reviews pass. The release flag may change to `FOR_MANUFACTURE` only when the production gate and SHA-256 manifest are complete.
