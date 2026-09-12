# PCB-MAIN passive and support authority - EVT-PRE-20 Rev.A

Status: `PASSIVE_SUPPORT_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE`

This record closes `MAIN-AUTH-010`. It freezes every PCB-MAIN passive, support device, protection device, pull, strap, termination, filter and decoupling RefDes/MPN/population decision required by the closed electrical authorities. It also gives the complete physical-pin set for every listed component. It does not release native capture, placement, Review A, Review B, external RF assemblies, physical validation or the production BOM.

Machine authority: `hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv`.

Authority CSV SHA-256: `0b2abb5e967526590b02f069992579a2606d05d485f8ce3917472a3dbfbcd2b6`.

The registry contains 211 unique physical components: 80 capacitors, 103 resistors, two inductors, one ferrite bead, one SAW filter, two support ICs, one complementary MOSFET, seven four-channel ESD arrays, two USB ESD arrays, six single-line ESD diodes, two supply TVS devices, three RF ESD devices and the already-selected X1 TCXO. There are 196 fitted and 15 DNP positions. Every row has an exact manufacturer, orderable MPN, package, value/function, population state, temperature range, logical net, full physical-pin map, electrical path and disposition.

## Primary evidence

- ST `STM32U585xx` data sheet DS13086 Rev 10 and hardware-development note AN5373 Rev 7: `https://www.st.com/resource/en/datasheet/stm32u585ai.pdf` and `https://www.st.com/resource/en/application_note/an5373-getting-started-with-stm32u5-mcu-hardware-development-stmicroelectronics.pdf`.
- SiTime `SiT1552` data sheet Rev 1.43: `https://www.sitime.com/datasheet/SiT1552`.
- Quectel `BG95 Series Hardware Design` v1.6 and all previously frozen PCB-MAIN device authorities.
- u-blox `MAX-M10S Integration manual` UBX-20053088 R05 Figure 38: `https://content.u-blox.com/sites/default/files/MAX-M10S_IntegrationManual_UBX-20053088.pdf`.
- Analog Devices `LT6000/LT6001/LT6002` data sheet: `https://www.analog.com/media/en/technical-documentation/data-sheets/600012fa.pdf`.
- Vishay `Si1016X` data sheet Rev E: `https://www.vishay.com/docs/71168/si1016x.pdf`.
- Abracon `ABSES5AF-L100KM` data sheet revised 16 September 2025: `https://abracon.com/datasheets/ABSES5AF-L100KM.pdf`.
- TI `SN74LVC1G07`, `TPDxE05U06`, and `TPD2EUSB30` product data: `https://www.ti.com/product/SN74LVC1G07`, `https://www.ti.com/lit/ds/symlink/tpd1e05u06.pdf`, and `https://www.ti.com/product/TPD2EUSB30`.
- Nexperia `PESD5V0S1UL` and `PESD5V0C1BSF` product data: `https://assets.nexperia.com/documents/data-sheet/PESD5V0S1UL.pdf` and `https://assets.nexperia.com/documents/data-sheet/PESD5V0C1BSF.pdf`.

The named document identities in the CSV are traceability labels. The exact MPN and physical-pin values are the capture contract. Supplier inventory, lot traceability and counterfeit screening remain procurement controls and are not inferred from this authority.

The seven fitted `TPD4E05U06DQAR` devices `U19..U24/U27` use the project-local
`TI_DQA0010A_USON10` footprint from the DQA0010A board/stencil layout in the
official `TPD4E05U06` data sheet. It fixes 0.565 x 0.20 mm signal lands,
0.565 x 0.40 mm GND lands 3/8, 0.50 mm pitch, 0.835 mm row-center spacing,
0.07 mm preferred NSMD expansion and 0.565 x 0.36 mm GND stencil apertures.
Source: `https://www.ti.com/lit/ds/symlink/tpd4e05u06.pdf`, SHA-256
`c167cf1e72a5473a4d2c59b6a3c0251498701da05b7785919b9ceaae3b3e02c6`.
The `TPD2EUSB30DRTR` devices `U25/U26` remain on the reviewed KiCad DRT-3
pattern pending independent IPC/assembly control because TI `MPDS340` publishes
only the package outline and no PCB land or stencil recommendation.
The seven `TPD1E05U06DYAR` devices `D4/D6..D11` use project-local
`TI_DYA0002A_SOD523` geometry from drawing 4224978/B in the same Rev.O data
sheet: two 0.67 x 0.40 mm R0.05 lands at 1.48 mm center spacing, equal-size
stencil apertures and 0.05 mm preferred NSMD expansion.
The two `PESD5V0S1UL` supply TVS devices `D1/D2` use project-local
`Nexperia_PESD5V0S1UL_SOD882` geometry from data-sheet v5 Figure 11: 0.40 x
0.70 mm R0.05 copper, 0.50 x 0.80 mm solder-resist openings and separate
0.30 x 0.60 mm R0.05 paste apertures at 0.70 mm center spacing. Source
SHA-256: `8ddea76afa74f87de5d3662e4d9149bf7397761fa99dc29b44bfbe42872d447e`.
The `Si1016X-T1-GE3` antenna-switch MOSFET `Q4` uses project-local
`Vishay_Si1016X_SC-89` copper from Application Note 826: six rectangular
0.300 x 0.478 mm minimum pads at 0.500 mm pitch and a 0.798 mm inner gap.
Rotated into the established board orientation, the lands are 0.478 x
0.300 mm at 1.276 mm row-center spacing. Mask and stencil remain
assembly-process controls because the Vishay guideline does not define them.
The official Rev E data sheet embedding the application note is SHA-256
`5e561d2786874eb79c8c6e36e4eb4d9b0de774384005e72c4998ab3dcc2cf518`.

## Frozen cross-domain decisions

| Domain | Frozen result |
|---|---|
| U1 power/reset/straps | Five VDD bypass capacitors, package bulk, VBAT/VDDA/VREF/VDDUSB/SMPS/core networks, 2.2 uH L1, normal NRST RC, 100 kOhm BOOT0 pull-down and Rev.A `HW_REV[1:0]=00` fitted pull-down encoding |
| Storage and sensors | W25Q512 local bypass, 10 kOhm NCS pull-up, fitted 22 Ohm OCTOSPI positions, exact LIS2DW12/STTS22H bypass, one authoritative 2.2 kOhm I2C2 pull-up pair and fitted 22 Ohm MCU-side damping |
| Audio/AAD | Exact U7/U17/U18 bypass, four 100 kOhm WAKE pull-downs, aggregate pull-down, fitted 22 Ohm PDM clock and AAD configuration fanout damping, and one four-channel ESD array at each MIC connector |
| Cellular | Separate BB and RF star branches, complete Quectel broadband capacitor ladders, exact 100 uF polymer bulk parts, fitted FB1 and RF-branch link, low-leakage rail TVS, deterministic translator/control pulls, protected USB/debug fixtures and a 0 Ohm plus DNP-shunt cellular RF pi network |
| Dual SIM | U13 bypass and safe-state pulls, Q3 base network, per-slot supply bypass and DET debounce, fitted 0 Ohm RST/CLK/DATA links and DNP 33 pF shunts |
| GNSS | Exact Figure 38 values and physical connectivity using `LT6000IDCB#TRMPBF`, `Si1016X-T1-GE3`, 560 Ohm/100 kOhm/100 kOhm/10 Ohm network, 27 nH bias-T, 10 nF sense capacitor, 47 pF DC block and exact `ABSES5AF-L100KM` wideband SAW |
| LoRa | Fail-closed pulls, reset RC, fitted 22 Ohm SPI damping and fitted 0 Ohm plus DNP-shunt RF pi network |
| BLE | Exact U11 decoupling, UART damping, DFU pull-up and fail-closed non-inverting open-drain reset stage using `SN74LVC1G07DBVR` |
| Connectors/fixtures | Four-bit microSD support/protection, USB-C Rd/data/VBUS/shield networks, tamper pull/filter/ESD, controlled EOL series parts, direct SWD policy and an intentional `FAULT` to `PWR_FAULT` 0 Ohm bridge |

## GNSS Figure 38 implementation

Q4 channel 1 is the N-channel pull-down and channel 2 is the P-channel high-side switch. U9 pin 13 `GNSS_ANT_OFF_N` drives Q4 pin 2. Q4 pin 6 and pin 5 form `GNSS_ANT_GATE`; R61 pulls that node to U9 pin 14 `GNSS_ANT_BIAS_RAW`. Q4 pin 3 produces `GNSS_ANT_SWITCHED`. R62 creates the current-sense drop to `GNSS_ANT_SHORT_N`; L2 injects that bias into `GNSS_RF_ANT_BIASED`.

R59/R60 create `GNSS_ANT_DIV`. U5 compares this divider on pin 1 with `GNSS_ANT_SHORT_N` on pin 2 and directly drives `GNSS_ANT_DETECT` on pin 6. The optional open-drain level buffers in the u-blox drawing are intentionally omitted because the receiver I/O and supervisor operate in the same nominal 3.3 V domain. U5 pin 3 is tied HIGH so shutdown cannot float. C64 then blocks antenna DC before FL1; FL1 pins C/A are input/output and B/D/E are ground.

D4 is unidirectional `TPD1E05U06DYAR`, rather than the bidirectional RF part used on J8/J10, because J9 is a positive DC-biased RF node. This avoids applying a part that its manufacturer excludes from DC-supply-connected lines.

## Explicit no-population and direct-connection rules

- C16/C17 are DNP VCORE high-frequency options. They may be fitted only by signed power-integrity change.
- C54-C59 and C69/C70/C79/C80 are DNP SIM/RF tuning shunts. Their exact stocked MPNs are frozen even though the Rev.A population is zero.
- R4/R6 are DNP alternate revision pull-ups; R3/R5 are the fitted Rev.A `00` straps. R98 is the DNP hard USB-shield bond; R97 and C77 are fitted.
- X1 has no external bypass or load capacitors because the exact SiTime device has internal supply filtering and an internally driven LVCMOS output.
- STM32 SWD, nRF SWD and guarded I2C2 fixture contacts have no board-side ESD or extra series components. Protection and drive discipline belong to the controlled fixture; adding board parts would alter closed recovery authorities.
- U9 `V_BCKP`, `RESET_N`, `VIO_SEL`, `SAFEBOOT_N`, the nRF LF crystal pads, unused active-device pins and all manufacturer DNU/NC positions remain explicit NC as frozen by their device authorities.

## Review and release boundary

Closing `MAIN-AUTH-010` means the native schematic can be captured without selecting any missing PCB-MAIN passive or support MPN. It does not prove placement-dependent performance. Review A must still verify every row and pin map against the rendered native schematic and schematic-derived BOM, plus DC-bias capacitance, U1 SMPS stability, the FB1 700-960 MHz impedance requirement, modem burst droop, SIM voltage, GNSS supervisor thresholds, USB signal integrity and RF tuning evidence.

At the `MAIN-AUTH-010` checkpoint, `MAIN-AUTH-011` remained open for outline, connector orientation, RF zones, keepouts and exact production test-point placement; it is now separately closed by the mechanical placement authority. Native capture has advanced to `SCHEMATIC_REVIEW`; Reviews A/B are incomplete and all physical tests remain `NOT RUN`. Production Gerbers and the production BOM remain blocked.
