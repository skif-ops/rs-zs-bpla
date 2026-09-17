# PCB-MAIN connector and fixture authority - EVT-PRE-20 Rev.A

Status: `CONNECTOR_FIXTURE_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE`

This record closes only `MAIN-AUTH-009`. It freezes the exact electrical contacts and endpoint separation for the industrial microSD card and socket, STM32 USB-C service port, all three U.FL receptacles, enclosure tamper loop, STM32 SWD, production EOL access, and BG95 USB/debug recovery. It does not release exact support-component RefDes or MPNs, connector placement or orientation, native capture, Review A, Review B, physical test results, or the production BOM.

Machine authority: `hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv`.

Authority CSV SHA-256: `b94cd4723efeffbdea7f1c6ba82f977da9c83c556967316630461af6048eaf12`.

## Primary evidence

- GCT `USB4105`, active USB 2.0 Type-C 16-contact receptacle family and exact `USB4105-GF-A-120` orderable option: `https://gct.co/connector/usb4105`.
- USB-IF `USB Type-C Cable and Connector Specification`, Release 2.5: `https://www.usb.org/document-library/usb-type-cr-cable-and-connector-specification-release-25`.
- GCT `MEM2052`, active push-push microSD connector `MEM2052-00-195-00-A`, eight contacts plus normally-open card detect, 1.95 mm profile: `https://gct.co/connector/mem2052`.
- Kingston Industrial microSD `SDCIT2`, including the 32 GB orderable capacity, pSLC mode, power-failure protection and -40 to +85 C operating range: `https://www.kingston.com/en/memory-cards/industrial-grade-microsd-uhs-i-u3`.
- SD Association simplified specifications and standard eight-contact microSD convention: `https://www.sdcard.org/downloads/pls/`.
- Molex Pico-Lock header `504050-0291`, mating housing `504051-0201`, and crimp terminal `504052-0098`: `https://www.molex.com/en-us/products/part-detail/5040500291`, `https://www.molex.com/en-us/products/part-detail/5040510201`, and `https://www.molex.com/en-us/products/part-detail/5040520098`.
- Hirose U.FL series and selected receptacle `U.FL-R-SMT-1(60)`: `https://www.hirose.com/product/series/U.FL`.
- ST `STM32U585xx` datasheet and AN2606 system-memory boot-mode application note: `https://www.st.com/resource/en/datasheet/stm32u585ai.pdf` and `https://www.st.com/resource/en/application_note/an2606-stm32-microcontroller-system-memory-boot-mode-stmicroelectronics.pdf`.
- Quectel `BG95 Series Hardware Design`, version 1.6, SHA-256 `6ff03aa31577971d02dc15eac11adee4d52b80077ae3fa3503978c1b12496e81`; product page: `https://www.quectel.com/product/lpwa-bg95-cat-m1-cat-nb2-egprs-series/`.

## Frozen electrical decisions

### Industrial microSD

`U12` is the 32 GB Kingston `SDCIT2/32GB` industrial microSD card. `J12` is GCT `MEM2052-00-195-00-A`. Contacts 1 through 8 follow the standard microSD `DAT2`, `CD/DAT3`, `CMD`, `VDD`, `CLK`, `VSS`, `DAT0`, `DAT1` order and terminate at the already frozen four-bit STM32 SDMMC1 endpoints. SPI fallback is not part of Rev.A.

The normally-open J12 detect contact closes `SD_DET` to ground only when a card is fully inserted. PC13 therefore uses a pull-up and reports an open or absent card as inactive. Exact pull, debounce, source damping, ESD and decoupling RefDes/MPNs are frozen by `MAIN-AUTH-010`; southward access and insertion direction are frozen by `MAIN-AUTH-011`, while retention remains a physical test.

### USB-C service port

`J11` is exact GCT `USB4105-GF-A-120`. It is a USB 2.0 device-only service and STM32 system-memory recovery port. A6/B6 join locally as `USB_DP` to PA12, A7/B7 join locally as `USB_DM` to PA11, and all VBUS contacts join only to `USB_VBUS_CONN`, from which PA9 receives protected high-impedance sense. The station neither sources nor consumes operating power through J11. CC1 and CC2 are separate device-mode Rd endpoints; SBU1 and SBU2 are NC.

J11 is never connected to U11 nRF USB or U8 BG95 USB. `USB_SHIELD` is distinct from signal ground at the connector and requires the controlled bond network selected under `MAIN-AUTH-010`. South-edge geometry, 1.20 mm stake selection and plug-service allocation are frozen by `MAIN-AUTH-011`; sealed-cover fit remains a mechanical validation.

### RF receptacles

`J8`, `J9` and `J10` are exact Hirose `U.FL-R-SMT-1(60)` receptacles with center contact 1 and grounded shell group. J8 center is `CELL_RF_ANT` and reaches U8 pad 60 `CELL_RF` only through its no-stub 50 Ohm matching/protection path. J9 and J10 rows intentionally restate the already closed GNSS and LoRa receptacle identities and nets; the verifier cross-checks them against `MAIN-AUTH-006` and `MAIN-AUTH-007` so this authority cannot silently diverge.

Exact RF protection and matching RefDes/MPNs are frozen by `MAIN-AUTH-010`. Zones, receptacle coordinates, tool clearance and enclosure exclusions are frozen by `MAIN-AUTH-011`. Stackup-derived trace geometry, via fences, cable fit, conducted validation and final antenna-system acceptance remain Review-B and physical EVT evidence.

### Tamper

`J13` is Molex Pico-Lock `504050-0291`, mated by `504051-0201` with `504052-0098` terminals. A normally-closed external loop connects PC7/EXTI7 `TAMPER_IN` to ground while the enclosure is secure. Cover opening, cable break or unmated connector opens the circuit and is treated as an alarm. Exact pull-up, filter, debounce and ESD parts are frozen by `MAIN-AUTH-010`.

### Production and recovery fixtures

The fixture contact groups are electrically separate:

| Group | Contacts | Fixed purpose |
|---|---:|---|
| `TP_MCU_SWD` | 5 | `VTREF`, STM32 `SWDIO`, `SWCLK`, `NRST`, `GND` |
| `TP_BLE_SWD` | 4 | Independently controlled by `MAIN-AUTH-008`; it is not duplicated here |
| `TP_EOL` | 13 | rail sensing, DUT LPUART, power states, controlled `BOOT0`, revision straps and guarded I2C2 access |
| `TP_CELL_USB` | 4 | BG95-only USB VBUS, D+, D- and modem ground |
| `TP_CELL_DBG` | 5 | BG95 1.8 V reference sense, debug TX/RX, controlled USB_BOOT and modem ground |

VTREF and rail-sense contacts never source station power. Fixture outputs remain high impedance until their referenced DUT domain is valid. The two USB interfaces do not share data, VBUS or test contacts. STM32 and nRF SWD contacts do not share debug nets. BG95 debug is 1.8 V only; `USB_BOOT` is normally LOW and may be driven HIGH only by the current-limited recovery fixture during the documented recovery power-on sequence.

The EOL fixture uses the production LPUART with directions named at the DUT: PC1 is `TEST_UART_TX`, PC0 is `TEST_UART_RX`. I2C2 test access is open-drain and enables direct INA226 calibration/readback without adding an uncontrolled pull-up. `BOOT0` may be driven only while reset is asserted. Exact passive/protection parts are frozen by `MAIN-AUTH-010`; bottom-side pogo geometry and coordinates are frozen by `MAIN-AUTH-011`.

## Checkpoint boundary and current gates

- At the `MAIN-AUTH-009` checkpoint, `MAIN-AUTH-010` and `MAIN-AUTH-011` were still open. They are now separately closed by their own machine authorities and independent checks.
- Native PCB-MAIN schematic is present, KiCad 9 ERC passes with zero violations
  and Review A is signed. The native board remains an unrouted placement
  candidate; Review B is blocked by routing, DRC, DFM and physical evidence.
- Connector samples, card endurance/power-loss behavior, USB enumeration/recovery, tamper fault coverage, fixture MSA/programming, RF/VNA tests and environmental verification are `NOT RUN`.
- The production BOM and any `FOR_MANUFACTURE` release remain blocked.
