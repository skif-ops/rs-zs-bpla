# PCB-MAIN BLE authority - EVT-PRE-20 Rev.A

Status: `BLE_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE`

This record closes only `MAIN-AUTH-008`. It freezes all 61 physical U11 pads, the four-contact independent nRF SWD fixture interface, the 3.3 V normal-voltage supply mode, UART endpoints, deterministic reset and DFU-entry topology, the internal low-frequency RC choice, and the Raytac PCB-antenna keepout rule. It does not release exact support-component MPNs or RefDes, native capture, final placement coordinates, housing RF performance, signed nRF firmware, PCB Review A, PCB Review B, or the production BOM.

Machine authority: `hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv`.

Authority CSV SHA-256: `9dc9bc2f57d722bd4cb6ae9f6de251cffe22c883c68dc9f25ee55a2eb577dbe3`.

## Primary evidence

- Raytac exact `MDBT50Q-P1MV2` product page: `https://www.raytac.com/product/ins.php?index_id=47`.
- Raytac `MDBT50Q-1MV2 & MDBT50Q-P1MV2 Specification`, Version L, 24 May 2023: `https://www.raytac.com/download/index.php?index_id=43`. Retrieved SHA-256: `61fec8c0c9f8c33175be2237a8ebba73c6cfc0a3572fe3835fd341079c103d03`.
- Raytac `MDBT50Q & MDBT50Q-P & MDBT50Q-U Footprint & Design Guide`, 6 June 2023: `https://www.raytac.com/document/act.php?act=1&index_id=30`. Retrieved archive SHA-256: `7ff6f11d0185a9db73c7140a4fe7e70b31615539916e60d5c27af8178f9f9fc2`.
- Nordic exact nRF52840 product page: `https://www.nordicsemi.com/Products/nRF52840`.

Raytac Version L identifies the selected PCB-antenna module as the 10.5 x 15.5 x 2.0 mm, 61-pad, nRF52840 Revision 2 module. The chip-antenna `MDBT50Q-1MV2`, APProtect `MDBT50Q-P1MEN`, and u.FL `MDBT50Q-U1MV2` variants are different orderable configurations and are forbidden as silent substitutes. The U1MV2 external-antenna variant remains only a formal RF fallback after enclosure testing and change review.

## Supply and clock contract

Rev.A supplies both U11 pad 28 `VDD` and pad 30 `VDDH` from `3V3_DIGITAL`. This is the Raytac normal-voltage configuration for a highest input below 3.6 V. Pad 31 `DCCH` remains NC because Reg0 DC/DC is disabled. U11 pad 28 has local 100 nF plus 10 uF ceramic decoupling. Exact capacitor MPNs and RefDes are frozen by `MAIN-AUTH-010`; Review A and EVT must verify rail ramp, RF-current transient, reset current and sleep current over temperature.

U11 is not connected to USB in Rev.A. Pad 32 `VBUS`, pad 34 `D-` and pad 35 `D+` are explicit NC. The PCB-MAIN USB-C service interface is owned by the STM32 endpoint under `MAIN-AUTH-009`, so connecting it to U11 is forbidden without reopening both authorities.

The nRF firmware uses its calibrated internal low-frequency RC source. Pads 17 `P0.00/XL1` and 18 `P0.01/XL2` are NC; no 32.768 kHz crystal or load capacitors are fitted. Firmware must enable the SDK/RTOS LFRC calibration policy and the EVT campaign must measure connection stability, timekeeping tolerance and sleep current before release.

## UART, reset and DFU contract

| Function | U11 pad | nRF endpoint | STM32 endpoint | Safe state |
|---|---:|---|---|---|
| nRF transmit | 22 | `P0.06` UARTE TX | PB11 / package pin 45 `BLE_RX` | input at STM32; no external pull |
| nRF receive | 24 | `P0.08` UARTE RX | PB10 / package pin 44 `BLE_TX` | no external pull |
| DFU request | 39 | `P0.15` GPIO input | PB2 / package pin 34 `BLE_DFU_REQ` open-drain | HIGH through 10 kOhm; request is LOW |
| module reset/run | 40 | `P0.18/nRESET` | PE6 / package pin 5 `BLE_EN` through reset buffer | reset asserted while `BLE_EN` is LOW or high-impedance |

The UART is 3.3 V point-to-point with no RTS/CTS. A populated 22 Ohm source-series tuning position is located at the driver end of each line. The exact resistor RefDes/MPN are frozen by `MAIN-AUTH-010`; measured edge-integrity acceptance remains Review A evidence.

`BLE_EN` is an active-HIGH run request, not a switched U11 power rail. It drives the input of a 3.3 V non-inverting open-drain reset buffer. A 100 kOhm pull-down holds the buffer input LOW while the STM32 is reset or high-impedance; the buffer then holds `NRF_RESET_N` LOW. When PE6 drives HIGH, the buffer releases its output and a 10 kOhm pull-up releases U11 pad 40. The exact buffer MPN and passive RefDes are frozen by `MAIN-AUTH-010`; inversion, default state and active levels are frozen here.

The production image must configure nRF UICR `PSELRESET[0]` and `PSELRESET[1]` for `P0.18`, then read back the setting before the unit leaves programming. Until that configuration and the reset test pass, `BLE_EN` cannot be credited as a recovery path.

`BLE_DFU_REQ` is application-defined rather than a fixed nRF hardware boot pin. PB2 must operate only as open-drain: normal state is high-impedance and the 10 kOhm U11-side pull-up supplies HIGH. The signed nRF bootloader samples P0.15 LOW during a controlled reset release to enter recovery; it boots the verified application otherwise. The STM32 must never drive this net HIGH. SWD remains the independent recovery path even if UART or the bootloader is unusable.

## Independent nRF SWD fixture

U11 pad 51 `SWDIO` and pad 53 `SWDCLK` route only to the dedicated four-contact `TP_BLE_SWD` pogo group:

1. `VTREF` senses `3V3_DIGITAL` and must not source station power.
2. `NRF_SWDIO` connects to U11 pad 51.
3. `NRF_SWCLK` connects to U11 pad 53.
4. `GND` is the adjacent debug reference.

The nRF contacts must not share nets, pads or fixture switching paths with STM32 `J_SWD`. Exact pad coordinates and the fixture envelope are now frozen by `MAIN-AUTH-011`; all four contacts must remain accessible after assembly. EOL must still prove identify, erase/recover, program, verify, UICR readback and reset operation using this interface.

## PCB-antenna keepout

The PCB-antenna end of U11 is placed at the PCB edge. The Raytac Version L minimum illustrated antenna no-ground depth is 3.8 mm across the full 10.5 mm module width, and Raytac requires this no-ground region to be made wider wherever the board outline permits. The corresponding antenna region contains no copper pours, ground pads, planes, traces or vias on any layer.

No component, test pad, screw, standoff, shield wall, battery, conductive label, cable or cable bundle may occupy or cross the antenna volume. No digital or switching trace is routed beneath the module antenna end. The precise east-edge coordinates, board outline and mechanical exclusion volume are now frozen by `MAIN-AUTH-011`; any smaller or obstructed keepout reopens `MAIN-AUTH-008` and `MAIN-AUTH-011`.

Pads marked by Raytac as standard-drive, low-frequency-only near the radio are left NC in Rev.A. UART, reset, DFU and SWD use only the explicitly frozen pads in the machine authority. No unused U11 GPIO is exposed as an informal test point.

## Review A and EVT evidence still required

- Verify all 65 authority rows against the final symbol, the exact 61-pad Raytac land pattern and the four independent fixture contacts.
- Confirm VDD/VDDH shorting, DCCH/USB/LF crystal NC markers, local decoupling and the absence of implicit power pins.
- Measure power ramp, fail-closed reset, UICR reset configuration, DFU request timing, UART integrity, SWD recovery and sleep/RF current at temperature.
- Inspect every copper layer and the assembled mechanical stack for the 10.5 mm by 3.8 mm minimum no-ground region and the wider practical clearance required by Raytac.
- Measure BLE 2M, 1M and coded-PHY range, packet error rate, antenna detuning and coexistence in the final housing with battery, shields and installed cable bundles.
- Complete signed nRF boot/application/rollback evidence, exact support-component MPNs, native ERC, layout Review B, BOM-from-schematic provenance and both independent PCB reviews before manufacturing release.
