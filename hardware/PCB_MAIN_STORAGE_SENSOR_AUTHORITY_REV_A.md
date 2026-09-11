# PCB-MAIN storage and sensor authority - EVT-PRE-20 Rev.A

Status: `DEVICE_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE`

This record closes only `MAIN-AUTH-002`. It freezes U2, U3, and U4 device-pad maps, power and decoupling contracts, interface straps, and I2C addresses. It does not release the native PCB-MAIN schematic, PCB Review A, PCB Review B, or the production BOM.

## Primary evidence

- Winbond `W25Q512JV` SpiFlash Memory datasheet, Revision B, 25 June 2019. Retrieved document SHA-256: `a898962af314ca90719eadba732e7f5fd42a1c48c4bfd283062c403d1c27bfd0`.
- Winbond official W25Q512JV product catalog: `https://www.winbond.com/hq/product/code-storage-flash-memory/serial-nor-flash/?__locale=en&partNo=W25Q512JV`.
- ST `LIS2DW12` datasheet DS11811 Rev 9, September 2024: `https://www.st.com/resource/en/datasheet/lis2dw12.pdf`. Retrieved document SHA-256: `5208623aa91c63a33be0e930518c20f5210c4eb76932350f35369687ae1d0dd5`.
- ST technical note `TN0018`, Rev 8, March 2025: `https://www.st.com/resource/en/technical_note/tn0018-surface-mounting-guidelines-for-mems-sensors-in-an-lga-package-stmicroelectronics.pdf`. Retrieved document SHA-256: `4dc419fabe93f7f0b1ee5730967ed74573aa0dc91188cf88749ce10d5ab4a34e`.
- ST `STTS22H` datasheet DS12606 Rev 8, March 2026: `https://www.st.com/resource/en/datasheet/stts22h.pdf`. Retrieved document SHA-256: `3f6937595517c4f738021037942e7d19d5b7c84cfe4e9b7e8635fcc06ff783fe`.
- Project functional map: `hardware/EVT_PRE_20_PIN_MAP_REV_A.csv`.

## U2 W25Q512JVFIQ contract

- Exact package is Winbond package code F: 16-pin SOIC, 300 mil.
- Pin 1 is `NOR_IO3`, pin 8 is `NOR_IO1`, pin 9 is `NOR_IO2`, and pin 15 is `NOR_IO0`. The exact `IQ` ordering option ships with the factory default `QE=1`; firmware must verify or restore QE before Quad operation.
- Pin 7 `/CS` is `NOR_NCS` with a required 10 kOhm pull-up to `3V3_DIGITAL`, so the device remains deselected while the MCU pins are high impedance during power transitions.
- Dedicated pin 3 `/RESET` is tied directly to `3V3_DIGITAL`. Reset recovery is performed with the Winbond software-reset sequence when required.
- Pins 4, 5, 6, 11, 12, 13, and 14 are manufacturer `N/C / DNU` and must have no electrical connection.
- VCC pin 2 uses local 100 nF plus 1 uF decoupling to GND pin 10.
- Firmware must validate JEDEC/SFDP identity and use 4-byte addressing mode or the dedicated 4-byte instructions before accessing addresses above the 128-Mbit boundary.

## U3 LIS2DW12TR contract

- I2C mode is selected by tying CS pin 2 directly to `3V3_DIGITAL`.
- SDO/SA0 pin 3 is tied directly to GND, fixing the 7-bit address at `0x18`.
- SCL pin 1 and SDA pin 4 connect to `I2C2_SCL` and `I2C2_SDA`.
- INT1 pin 12 drives `ACCEL_INT` at STM32 PC6. INT2 pin 11 is unused and externally NC.
- Reserved pin 7 is tied directly to GND. Pin 5 is internally unconnected and remains externally NC. Pins 6 and 8 connect to GND.
- VDD pin 9 uses 100 nF plus 10 uF local decoupling. VDD_IO pin 10 uses separate local 100 nF decoupling. Both rails connect to `3V3_DIGITAL` and are present together.
- PCB assembly documentation must preserve the manufacturer pin-1 marker and X/Y/Z orientation. Final self-test and orientation verification remain required.
- The local LGA-12L footprint uses the DS11811 package-pad geometry and TN0018 rules: 0.375 x 0.350 mm PCB lands, 0.05 mm solder-mask expansion, and an 81% stencil aperture area.

## U4 STTS22HTR contract

- SCL pin 1 and SDA pin 6 connect to `I2C2_SCL` and `I2C2_SDA`.
- Addr pin 4 is tied directly to GND, fixing the 7-bit address at `0x3F`.
- ALERT/INT pin 2 is unused and externally NC; temperature is polled in Rev.A.
- VDD pin 3 connects to `3V3_DIGITAL` with local 100 nF decoupling. Pin 5 connects to GND.
- The unnumbered exposed pad is soldered using the ST land pattern but has no electrical net. It must not be shorted to signal or supply nets. Place U4 away from regulators, RF power stages, and other local heat sources so its reading remains representative.

## Shared I2C2 contract

| Device | Rev.A 7-bit address | Address strap |
|---|---:|---|
| U3 LIS2DW12TR | `0x18` | SA0 to GND |
| U4 STTS22HTR | `0x3F` | Addr to GND |
| PCB-PWR INA226AIDGSR | `0x40` | A1 and A0 to GND |

- The authoritative PCB-MAIN pull-ups are 2.2 kOhm, 1%, from both `I2C2_SCL` and `I2C2_SDA` to `3V3_DIGITAL`. PCB-PWR pull-up footprints remain DNP.
- At the 400 pF standard-mode bus limit, the estimated 30%-to-70% rise time is `0.8473 x 2.2 kOhm x 400 pF = 0.746 us`, below the 1.0 us limit. At `VOL=0.4 V`, each asserted line draws about 1.32 mA, below the 3 mA sink condition of the local sensors.
- Initial bus speed is 100 kHz. Reserve 22 Ohm series-damping positions adjacent to the STM32 master on SCL and SDA; baseline population is fitted and may change only from measured rise-time and ringing evidence.
- Review A must include measured SCL/SDA rise time at the final harness length, enumeration of all three addresses, and a switching-noise test while the 3V8 modem rail is under burst load.

Exact passive MPNs, passive RefDes, OCTOSPI series-damping decisions, and placement are controlled by `MAIN-AUTH-010`. This record cannot by itself authorize manufacturing.
