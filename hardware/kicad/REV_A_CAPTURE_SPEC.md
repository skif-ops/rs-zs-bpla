# EVT-PRE-20 Rev.A native KiCad capture specification

Status: `CAPTURE_INPUT / BLOCKING / NOT FOR MANUFACTURE`

This document is the authoritative bridge from the locked EVT-PRE-20 system baseline to native KiCad capture. Native `.kicad_sch/.kicad_pcb` files, ERC/DRC and Review A/B remain mandatory before any Gerber may be released.

Authoritative inputs:
- `config/EVT_PRE_20_BASELINE.yaml`;
- `hardware/EVT_PRE_20_PIN_MAP_REV_A.csv`;
- `hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv`;
- `hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv` and its independent review record;
- `hardware/PCB_MAIN_STORAGE_SENSOR_PIN_AUTHORITY_REV_A.csv` and its independent review record;
- `hardware/PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv` and its independent review record;
- `hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv` and its independent review record;
- `hardware/PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv` and its independent review record;
- `hardware/PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv` and its independent review record;
- `hardware/PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv` and its independent review record;
- `hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv` and its independent review record;
- `hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv` and its independent review record;
- `hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv` and its independent review record;
- `hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv`;
- `hardware/MAIN_COMPONENT_FREEZE_REV_A.csv`;
- `hardware/POWER_COMPONENT_FREEZE_REV_A.csv`;
- `hardware/CONNECTOR_FREEZE_REV_A.csv`;
- `hardware/CLOCKING_REV_A.md` / `DEC-016`;
- `protocols/POSITION_TIME_TRUST_REV_A.md` / `DEC-018`;
- `hardware/PCB_DOUBLE_REVIEW_GATE.md`.

Capture-control status is recorded in
`hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json` and independently checked by
`tools/audit_pcb_main_capture_authority_rev_a.py`. A PASS from that audit means
only that the current input set and open-authority register are controlled. It
does not mean that native capture, Review A, Review B or the production BOM has
passed.

## 1. PCB-MAIN Rev.A

### 1.1 MCU

- `U1`: ST `STM32U585VIT6Q`.
- Exact device/pin database: `STM32U585VITxQ`.
- Package: LQFP100 14x14 mm, SMPS-capable package.
- The complete 100-position package disposition is frozen in `hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv`; it closes only `MAIN-AUTH-001`.
- Exact selected orderable part is treated as a `-40..+85 °C` item until an alternative exact MPN is formally selected; environmental release therefore remains blocked by IN-006.
- `PB12`, `PE1`, `PC4`, `PC5` are absent from the exact Q-package and forbidden.
- All VDD/VSS/VDDA/VSSA/VREF/VDDUSB/VDD11/SMPS pins, NRST, BOOT0 and SWD are captured exactly per the selected supply mode and ST reference documentation.

### 1.2 Clocking

- Locked policy `DEC-016`: internal MSI/HSI + PLL for high-speed clocks.
- No HSE crystal, HSE oscillator, HSE load capacitors or DNP HSE footprint in Rev.A.
- `X1`: `SiT1552AI-JE-DCC-32.768D`, 32.768 kHz low-frequency reference.
- SiT1552 drives PC14/OSC32_IN in external-clock mode. PC15/OSC32_OUT is reserved by RCC but externally NC; there is no crystal wiring.
- Target validation must prove USB FS, PDM sample-rate accuracy, PPS capture, low-power wake and clock-transition recovery.

### 1.3 Frozen STM32 peripheral map

- PDM/MDF: PE9 `MDF1_CCK0`; PB1 `MDF1_SDI0`; PD6 `MDF1_SDI1`; PE7 `MDF1_SDI2`; PE4 `MDF1_SDI3`.
- AAD aggregate wake: PA8, physical LQFP100 pin 67, GPIO/EXTI wake input `MIC_WAKE`.
- OCTOSPI1 NOR: PE10 CLK; PE11 NCS; PE12..PE15 IO0..IO3.
- SDMMC1: PC8..PC11 D0..D3; PC12 CK; PD2 CMD; PC13 DET.
- GNSS: PA2/PA3 USART2 TX/RX; PA0 TIM2_CH1 PPS.
- LoRa: PA4..PA7 SPI1 NSS/SCK/MISO/MOSI; PC2 DIO1/EXTI2; PB15 TXEN; PD8 RXEN; PD9 BUSY; PD10 RESET_N.
- `MIC_WAKE` remains PA8/EXTI8. `LORA_DIO1` was moved from PD8/EXTI8 to
  PC2/EXTI2 by DEC-022 because STM32U5 permits only one GPIO port source per
  EXTI line. This pin-map change invalidates prior PCB-MAIN Review A/B evidence.
- `hardware/kicad/components.csv` and `hardware/kicad/nets.csv` are superseded
  placeholders and must not be used as component, pin or capture authorities.
  They remain only as historical drift fixtures. Regenerate the native PCB-MAIN
  component/net input from the active freeze registers,
  `hardware/EVT_PRE_20_PIN_MAP_REV_A.csv` and the reviewed addenda.
- BG95 UART: PB6/PB7 USART1 TX/RX; PD11..PD15 control/status.
- BLE: PB10/PB11 USART3 TX/RX; PE6 BLE_EN; PB2 BLE_DFU_REQ.
- I2C2: PB13/PB14.
- PCB-PWR: PD0 PWR_GOOD; PD1 PWR_FAULT; PD4 EN_MODEM; PD5 EN_AUX.
- Production LPUART: PC0 RX; PC1 TX.
- USB FS: PA9 VBUS; PA11 DM; PA12 DP.
- SWD: PA13 SWDIO; PA14 SWCLK.
- revision straps PB8/PB9; BOOT0 PH3.
- PC14 is `LSE_IN`; PC15 is reserved by RCC and externally NC.

The 100-position MCU pin-authority CSV is the machine-checkable package authority if this prose and the CSV ever differ. The functional pin map and AAD addendum remain its upstream functional sources.

### 1.4 T5838 PDM and Acoustic Activity Detect

Each station has four identical external `PCB-MIC` leaves with one TDK/InvenSense `T5838` each.

PDM:
- common `PDM_CLK`;
- independent `PDM_DATA1..4`;
- `1V8_MIC` supply;
- `U7` `SN74AXC8T245PWR` provides explicit 3.3 V / 1.8 V translation;
- U7 VCCA pin 1 is `1V8_MIC`; VCCB pins 23 and 24 are `3V3_DIGITAL`; GND pins 12 and 13 are grounded;
- U7 DIR1 pin 2 is tied high to `1V8_MIC`, so A1..A4 pins 3..6 receive `PDM_DATA1_1V8`..`PDM_DATA4_1V8` and B1..B4 pins 21..18 drive the corresponding 3.3 V MCU nets;
- U7 DIR2 pin 11 is tied low to GND, so B5 pin 17 receives `PDM_CLK` and A5 pin 7 drives `PDM_CLK_1V8`; B6 pin 16 receives `AAD_CFG` and A6 pin 8 drives `AAD_CFG_1V8`;
- U7 unused B7/B8 inputs on pins 15/14 are tied directly to GND; unused A7/A8 outputs on pins 9/10 are NC;
- U7 active-low OE pin 22 is tied directly to GND. The translator remains enabled whenever both rails are valid; MCU `PDM_CLK` and `AAD_CFG` are held low in S0;
- U7 VCC isolation and Ioff cover fully unpowered-domain backfeed. Its maximum static current is included in the measured S0 budget;
- no external pull-up or pull-down is allowed on `PDM_DATA1_1V8`..`PDM_DATA4_1V8`; final-harness PDM SI and source termination remain Review A measurements.

AAD wake:
- T5838 `WAKE` is preserved on every leaf; it is not tied off;
- physical MIC connector is 6 contacts;
- J_MIC1..J_MIC4 physical order: 1=`1V8_MIC`, 2=`GND`, 3=`PDM_CLK`, 4=`PDM_DATAn`, 5=`MIC_WAKEn`, 6=`AAD_CFG`;
- connector family: Molex Pico-Lock 1.50 mm; board header `5040500691`, cable housing `5040510601`, terminal `5040520098`;
- `MIC_WAKE1..4` remain separate through the four harnesses;
- each `MIC_WAKEn` has a 100 kOhm pull-down to GND and an individual Review A test point before aggregation;
- `U17` `SN74LVC32APWR` is powered from `1V8_MIC`; gate 1 forms `MIC_WAKE1 OR MIC_WAKE2`, gate 2 forms `MIC_WAKE3 OR MIC_WAKE4`, and gate 3 forms the final `MIC_WAKE_OR_1V8`;
- U17 unused gate inputs pins 12 and 13 are tied directly to GND; unused output pin 11 is NC;
- `U18` `SN74AXC1T45DRLR` has VCCA=`1V8_MIC`, VCCB=`3V3_DIGITAL`, and DIR tied to `1V8_MIC`; it translates `MIC_WAKE_OR_1V8` from A pin 3 to B pin 4;
- U18 output is `MIC_WAKE` to STM32 PA8/pin 67;
- `MIC_WAKE` has a 100 kOhm pull-down to GND at the MCU side so PA8 remains inactive when U18 is high impedance;
- the wake path remains powered while AAD monitoring is armed;
- exact physical pins and required networks are authoritative in `hardware/PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv`.

T5838 leaf-local control:
- `SELECT` is tied directly to GND on every leaf, fixing identical right-channel timing; each leaf has an independent data line and no runtime cable is allocated to SELECT;
- `THSEL` is routed as `AAD_CFG` on J1 pin 6 and is driven through U7 from STM32 PA15;
- all four identical leaves receive the shared `AAD_CFG` write; firmware must use one common validated AAD threshold profile;
- local VDD decoupling is placed immediately at T5838;
- bottom acoustic port, solder mask, adhesive, membrane and enclosure stack preserve the acoustic opening.

Required AAD tests before release:
- entry/configuration sequence;
- missed-wake and false-wake tests;
- wake edge level and latency at PA8;
- Stop-mode wake;
- PDM restart after AAD wake;
- all four individual WAKE paths;
- measured S0 current with four microphones, OR gate, translator, LDO, MCU and timing source strategy.

### 1.5 Cellular and dual SIM

- `U8`: Quectel `BG95-M3` in the 102-pad 23.6 x 19.9 mm LGA; exact ordered firmware/region identity and operator validation remain release blockers.
- The complete U8 pad disposition is frozen in `hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv`; it closes only `MAIN-AUTH-004` together with U16 and Q1/Q2.
- U8 pins 32/33 `VBAT_BB` use `3V8_MODEM_BB`; pins 52/53 `VBAT_RF` use `3V8_MODEM_RF`; both branches originate from the single `3V8_MODEM` star point.
- The BB branch requires 100 uF low-ESR plus 220 nF, 47 nF, 150 pF, 100 pF, 68 pF, 33 pF, and 10 pF with a ferrite bead adjacent to U8. BB copper is at least 0.6 mm equivalent width.
- The RF branch requires 100 uF low-ESR plus 100 nF, 33 pF, and 10 pF with a 0 Ohm link adjacent to U8. RF copper is at least 2.7 mm equivalent width with no neck-down.
- Both branches must remain at or above 3.3 V at all four U8 VBAT pads during representative LTE and EGPRS bursts.
- U8 pin 29 `VDD_EXT` powers U16 VCCA and the local 1.8 V pull-ups. U16 VCCB uses `3V3_DIGITAL`; U16 GND and control LOW straps use `GND_MODEM`.
- U16 DIR1 is high: `MAIN_TXD`, `STATUS`, and `MAIN_RI` translate from the U8 A side to MCU-side `CELL_RX`, `CELL_STATUS`, and `CELL_RI`.
- U16 DIR2 is low: MCU-side `CELL_TX` and `CELL_DTR` translate from B to U8 `MAIN_RXD` and `MAIN_DTR`.
- U16 OE is tied low. A4, B7, and B8 are tied to `GND_MODEM`; B4, A7, and A8 are NC.
- BG95 UART/status domain is 1.8 V; direct STM32 3.3 V connection is forbidden. U16 VCC isolation and Ioff protect the unpowered modem domain.
- Q1 and Q2 are `MMBT3904,215` SOT23 open-collector drivers. Each uses 4.7 kOhm base series and 47 kOhm base-emitter pull-down. Q1 drives U8 PWRKEY; Q2 drives U8 RESET_N.
- PWRKEY and RESET_N are not routed through U16 and are never driven push-pull. PWRKEY has 10 nF to `GND_MODEM`; RESET_N has no large capacitance.
- Power-on selects a slot with U13 High-Z, waits at least 30 ms after stable `3V8_MODEM`, enables the selected slot through Q3, and then uses a selected 700 ms PWRKEY pulse. Normal power-off uses `AT+QPOWD`, waits for `CELL_STATUS=LOW`, disables U13, and only then removes `EN_MODEM`.
- The fallback PWRKEY shutdown pulse is 650-1500 ms. The emergency RESET_N pulse is 2-3.8 s. PWRKEY and RESET_N commands never overlap.
- Firmware masks RI and ignores UART until `CELL_STATUS=HIGH`. `CELL_DTR` defaults LOW to keep the modem awake until deliberate sleep entry.
- Review A must prove less than 75 mV peak `GND_MODEM` to `GND_DIGITAL` offset plus noise at U16 under the worst 2G burst.
- The complete 55-row U13/U14/U15/J6/J7/Q3 electrical map is frozen in `hardware/PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv`; it closes only `MAIN-AUTH-005`.
- Two physical nano-SIM/4FF slots operate in Single Standby only. J6 and J7 are exact TE `2336582-1` push-push connectors with independent active-HIGH card-present inputs.
- U13 is exact `TS3A27518EPWR`, powered from `3V3_DIGITAL`. Channels 1, 4, and 6 are paralleled for selected-card VDD; channels 2, 3, and 5 switch RST, CLK, and DATA.
- U13 IN1 and IN2 are tied to `SIM_MUX_SEL`: LOW selects the SIM1 NC paths and HIGH selects the SIM2 NO paths.
- Q3 `MMBT3904,215` preserves active-HIGH MCU `SIM_MUX_EN`: reset/default LOW leaves Q3 off and the 47 kOhm U13 EN pull-up holds all paths High-Z.
- U14/U15 are exact `ESDALC6V1-5P6` arrays at J6/J7. Pin 2 is `GND_MODEM`; the other pins protect VDD, RST, CLK, DATA, and DET.
- Each slot has 100 nF local VDD bypass, populated 0 Ohm series tuning positions on RST/CLK/DATA, and DNP 33 pF shunt tuning positions. Exact passive RefDes/MPNs and the DNP shunt population are frozen by `MAIN-AUTH-010`.
- U8 `USIM_DET` remains NC. J6/J7 DET switches go independently to MCU PE3/PE5 with 10 kOhm pull-ups, 10 nF filters, and at least 20 ms debounce.
- J6/J7 card and shell grounds connect directly to `GND_MODEM`; SIM ground is never switched through U13.
- Selected card VDD must measure at least 1.62 V. The unselected slot must remain isolated through reset, brownout, and every slot transition.
- TE procurement risk is explicit because `2336582-1` is active but not currently available; a validated common second source is required before lot release.
- No SIM selection change is allowed unless U13 is High-Z and `CELL_STATUS=LOW`.

### 1.6 GNSS / trusted fixed position

- `U9`: exact u-blox `MAX-M10S-00B`, LCC-18 9.7 x 10.1 mm. The complete module-pad and J9 contact authority is `hardware/PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv`; it closes only `MAIN-AUTH-006`.
- VCC and V_IO use `3V3_DIGITAL`; VIO_SEL is NC/open. V_BCKP, RESET_N, EXTINT and SAFEBOOT_N are NC. U9 VCC has local 100 nF plus 10 uF, no more than 0.2 Ohm total feed resistance, and capacity for 100 mA startup inrush.
- U9 TXD drives `GNSS_RX` at PA3/USART2_RX; U9 RXD receives `GNSS_TX` from PA2/USART2_TX. TIMEPULSE drives `GNSS_PPS` at PA0/TIM2_CH1. Each line has a populated 22 Ohm series position.
- TIMEPULSE has only a high-impedance test point and no external pull or startup-low load. SAFEBOOT_N has no trace or test pad because the module couples it internally to TIMEPULSE through 1 kOhm.
- The active antenna uses the u-blox Figure 38 three-pin supervisor: PIO7/LNA_EN controls power, PIO2/SDA reports open, and PIO3/SCL reports short. I2C is disabled before PIO2/PIO3 reassignment. Voltage control, open/short detection, power-down on fault and automatic recovery are enabled.
- `J9` is exact Hirose `U.FL-R-SMT-1(60)`. The populated RF path is `J9 -> ultra-low-C ESD -> biased node -> 47 pF C0G DC block -> wideband GNSS L1 SAW -> U9 RF_IN`; it is a 50 Ohm dedicated route.
- The VCC_RF supervisor network includes the Figure 38 switch/comparator topology, 10 Ohm 5% 0.25 W sensing, 27 nH 5% bias injection with more than 500 Ohm impedance at GNSS L1 and more than 300 mA rating, and 10 nF 10% 16 V X7R sensing filter. `MAIN-AUTH-010` freezes the exact U5/Q4/R59-R62/L2/C63-C65/FL1/D4 MPNs and physical pins.
- The external active antenna and cable are separate unreleased system BOM lines and must be qualified with the supervisor, SAW loss and cellular/RU868 coexistence.
- configured installation coordinates are authoritative after commissioning; GNSS position is an integrity/diagnostic channel and must not silently move network/TDOA geometry.
- receiver jam/spoof flags are read by firmware.
- position-trust and time-trust are independent; loss of GNSS position trust does not alter configured coordinates, while PPS/time suspicion affects TDOA validity/holdover separately.

### 1.7 LoRa RU868

- `U10`: exact Ebyte `E22-900M22S`, 20 x 14 mm, 22 pads, SX1262, 850 to 930 MHz and 22 dBm. The complete U10/J10 electrical authority is `hardware/PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv`; it closes only `MAIN-AUTH-007`.
- VCC is `3V3_DIGITAL` with local 100 nF plus 10 uF. The branch supports at least 182 mA, derived from the current Ebyte 140 mA upper TX-current value plus 30 percent margin.
- PA4..PA7 provide SPI1 NSS/SCK/MISO/MOSI; NSS has 10 kOhm pull-up. PB15/pin54 drives active-HIGH `LORA_TXEN`, and PD8/pin55 drives active-HIGH `LORA_RXEN`; both have 100 kOhm pull-downs and initialize LOW. PC2/EXTI2 receives DIO1, PD9 receives BUSY, and PD10 drives active-LOW NRST with 10 kOhm pull-up plus 100 nF.
- TXEN/RXEN truth table is TX=1/0, RX=0/1 and CLOSE=0/0. State 1/1 is forbidden. U10 DIO2 is NC and must not be shorted to TXEN in Rev.A.
- The exact 20 x 14 mm module uses its internal TCXO; firmware configures DIO3 for 2.2 V before RF operation.
- Rev.A procures the castellated-ANT form with no module-side IPEX fitted. Because Ebyte publishes the same model name for IPEX-1 and castellated forms, supplier configuration evidence remains a production-release blocker.
- The RF path is U10 pin21 to a pi network with populated 0 Ohm series baseline and two DNP shunts, then connector-side ultra-low-C ESD and exact J10 `U.FL-R-SMT-1(60)`. It is a dedicated 50 Ohm no-stub route over uninterrupted RF ground; J10 is also the conducted-test port.
- All 20 EVT-PRE-20 units use RU868 profile; no transmit before a valid signed region profile is loaded. External cable/antenna, exact support-component MPNs, RF layout and regulatory evidence remain blocked.

### 1.8 BLE commissioning / diagnostics / OTA

- `U11`: exact Raytac `MDBT50Q-P1MV2`, nRF52840 Revision 2, 10.5 x 15.5 mm, 61 physical pads and integrated PCB antenna. The complete module-pad and four-contact recovery interface is `hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv`; it closes only `MAIN-AUTH-008`.
- ESP32-C3 is superseded and forbidden in active Rev.A schematic/BOM.
- U11 pad 22 `P0.06` UARTE TX drives `BLE_RX` at STM32 PB11; STM32 PB10 `BLE_TX` drives U11 pad 24 `P0.08` UARTE RX. Each line has a populated 22 Ohm source-series tuning position at its driver; RTS/CTS are not used.
- PE6 `BLE_EN` is an active-HIGH run request into a non-inverting open-drain reset buffer. A 100 kOhm input pull-down asserts reset by default; the buffer drives U11 pad 40 `P0.18/nRESET`, which has a 10 kOhm pull-up. nRF UICR `PSELRESET[0]` and `PSELRESET[1]` must be programmed and read back.
- PB2 `BLE_DFU_REQ` is open-drain active-LOW to U11 pad 39 `P0.15`, with a 10 kOhm U11-side pull-up. The signed bootloader samples it only during controlled reset release; STM32 never drives the net HIGH.
- separate `TP_BLE_SWD` contacts are fixed as VREF/`NRF_SWDIO`/`NRF_SWCLK`/GND from U11 pads 51/53; they never share STM32 SWD nets or fixture switching paths and do not consume STM32 GPIOs.
- U11 pads 28 `VDD` and 30 `VDDH` tie to `3V3_DIGITAL` for normal-voltage mode, with local 100 nF plus 10 uF. Pad 31 `DCCH`, pad 32 `VBUS`, pads 34/35 USB data, and every unused GPIO are explicit NC.
- nRF firmware uses the calibrated internal LFRC; U11 pads 17/18 are NC and no 32.768 kHz crystal is fitted.
- integrated antenna is placed at the PCB edge with the Raytac all-layer no-ground/copper region at least 10.5 mm wide by 3.8 mm deep and extended wider where possible; no component, battery, shield, conductive label, standoff or cable bundle occupies the antenna volume.
- Exact reset-buffer/passive RefDes and MPNs are frozen by `MAIN-AUTH-010`; exact placement coordinates and mechanical exclusion remain `MAIN-AUTH-011`.
- final housing RF validation is mandatory; same-family external-antenna module may be adopted only by formal change if margin is insufficient.

### 1.9 Storage, sensors, USB and DFT

- NOR `W25Q512JVFIQ` on OCTOSPI1.
- U2 uses the exact 16-pin SOIC package-F map: IO3/IO1/IO2/IO0 on pins 1/8/9/15, `/CS` on pin 7 with 10 kOhm pull-up, dedicated `/RESET` pin 3 tied high, and all seven N/C-DNU pins left unconnected.
- U2 VCC has local 100 nF plus 1 uF decoupling; firmware uses 4-byte addressing for the full 512-Mbit array.
- `U12` is Kingston industrial microSD `SDCIT2/32GB` in exact `J12` GCT `MEM2052-00-195-00-A`; contacts 1..8 are `DAT2/CD-DAT3/CMD/VDD/CLK/VSS/DAT0/DAT1`, and the normally-open detect switch grounds `SD_DET` only with a fully inserted card. The complete electrical map is `hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv`. Four-bit SDMMC1 is mandatory; SPI fallback is not part of Rev.A without revision approval.
- LIS2DW12 is hard-strapped to I2C mode and address `0x18`; INT1 routes to PC6 `ACCEL_INT`, INT2 is NC, VDD has 100 nF plus 10 uF, and VDD_IO has 100 nF.
- `U4` is the exact orderable `STTS22HTR` in `UDFN-6L 2.0 x 2.0 mm`; the earlier `WLCSP-4` description is superseded.
- STTS22HTR is strapped to address `0x3F`; ALERT/INT is NC and VDD has 100 nF. Its unnumbered exposed pad has no electrical net and follows the ST land pattern.
- I2C2 addresses are fixed as U3 `0x18`, U4 `0x3F`, and PCB-PWR INA226 `0x40`. The only populated pull-ups are 2.2 kOhm 1% on PCB-MAIN; initial speed is 100 kHz and final-harness rise time is a Review-A measurement.
- INA226-class monitoring on I2C2 with shunt/range frozen by power calculation.
- `J13` is the two-contact Molex `504050-0291` normally-closed tamper loop: pin 1 is PC7/EXTI7 `TAMPER_IN`, pin 2 is GND, and an open loop is an alarm or cable fault.
- `J11` is GCT `USB4105-GF-A-120`, USB2 device-only for STM32 service/recovery: A6/B6 join to PA12 `USB_DP`, A7/B7 join to PA11 `USB_DM`, VBUS is protected sense-only to PA9, CC1/CC2 have independent device Rd endpoints, SBU is NC, and `USB_SHIELD` has a controlled bond. J11 never connects to U11 or U8 USB.
- `J8/J9/J10` are exact Hirose `U.FL-R-SMT-1(60)` receptacles. Their center/shell endpoints are controlled by `PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv` and cross-checked against the GNSS/LoRa authorities.
- `TP_MCU_SWD` is an independent five-contact STM32 SWD group; `TP_EOL` is an exact 13-contact production group; `TP_CELL_USB` and `TP_CELL_DBG` are isolated BG95 recovery groups. `TP_BLE_SWD` remains independently controlled by `MAIN-AUTH-008` and shares no SWD contacts.
- Connector/card identities and all contact endpoints close `MAIN-AUTH-009`. Exact support/protection/passive RefDes and MPNs are frozen by `MAIN-AUTH-010`; connector orientation and fixture-pad coordinates remain `MAIN-AUTH-011`.

### 1.10 Complete passive and support capture

- `hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv` is the machine authority for `MAIN-AUTH-010` and contains 211 unique physical components: 196 fitted and 15 DNP.
- Every row freezes one PCB-MAIN RefDes with manufacturer, exact MPN, package, value/function, population, temperature range, full physical-pin set, endpoint-qualified net path and disposition.
- `C1..C80`, `R1..R103`, `L1/L2`, `FB1`, `FL1`, `U5/U6/U19..U27`, `Q4`, `D1..D11`, and `X1` are the complete Rev.A set governed by this authority. X1 is restated to close its complete four-pad map without creating a duplicate BOM item.
- Endpoint suffixes such as `_U1`, `_U9`, `_U10`, `_U11`, `_U16`, `_CARD`, `_CONN`, `_MUX` and `_TP` distinguish the two physical nets around a series component. The unsuffixed names in earlier device authorities remain logical interface names; the `MAIN-AUTH-010` endpoint map governs native capture around the series element.
- The GNSS supervisor is the exact u-blox Figure 38 topology with `LT6000IDCB#TRMPBF`, `Si1016X-T1-GE3`, `LQW15AN27NJ00D` and `ABSES5AF-L100KM`. The J9 RF protector is unidirectional because that RF node carries positive DC antenna bias.
- Rev.A hardware revision encoding is fixed as `HW_REV[1:0]=00`: R3/R5 fitted pull-downs and R4/R6 DNP alternate pull-ups.
- STM32/nRF SWD and guarded I2C fixture contacts remain direct by design. There is no board-side protection or series element on those controlled internal test contacts.
- The authority closes component selection only. DC-bias capacitance, SMPS stability, FB1 frequency response, modem burst droop, GNSS thresholds, USB/SIM signal integrity and RF tuning remain Review A/EVT evidence.
- `MAIN-AUTH-011`, native capture, Reviews A/B and physical tests remain open. This capture input is `NOT FOR MANUFACTURE` and cannot release a production BOM or fabrication data.

## 2. PCB-MIC Rev.A

One identical leaf is used four times.

Components/functions:
- `MK1`: T5838 bottom-port PDM MEMS microphone;
- `J1`: Molex `5040500691` 6-position Pico-Lock SMT board header;
- `C1`: local 0.1 uF X7R decoupling close to microphone VDD;
- `R1`: 0 ohm PDM DATA source-termination/tuning footprint, populated baseline;
- T5838 `SELECT` is tied to GND in the current native capture, which is the production default for independent data lines;
- `THSEL/AAD_CFG` is routed to J1 pin 6 for the shared runtime threshold configuration;
- WAKE routed to J1 pin 5;
- PDM DATA routed to J1 pin 4;
- CLK J1 pin 3, GND pin 2, 1V8 pin 1.

Mechanical/acoustic:
- bottom-port PCB hole and keepout follow T5838 land pattern/reference guidance;
- no copper/mask/adhesive/coating blocks acoustic port;
- microphone port, membrane, drain/water strategy and enclosure pod stack are reviewed as one acoustic assembly;
- all four leaves share one PCB/BOM revision and preferably one microphone lot.

## 3. PCB-PWR Rev.A

Input: protected battery bus from LiFePO4/BMS/external MPPT. No MPPT charger is integrated on PCB-PWR.

Selected capture baseline:
- reverse/reverse-current controller `LM74700QDBVRQ1` plus `CSD18540Q5B` 60 V N-MOSFET;
- transient clamp `SMBJ18A` candidate pending measured transient envelope;
- PCB fuse `0451005.MRL` candidate pending fuse coordination;
- `3V8_MODEM`: `LMR604403SRAKR`, 4 A adjustable synchronous buck;
- `3V3_DIGITAL`: second `LMR604403SRAKR`, 4 A;
- no separate 3V3_AON regulator in Rev.A unless measured S0 requires a configuration change;
- `1V8_MIC`: `TPS7A2018PDBVR` 1.8 V LDO, kept active during AAD monitoring;
- INA226 monitor, final shunt and Kelvin routing pending current-range calculation.

MAIN/PWR 12-contact electrical contract:
1. 3V8_MODEM
2. GND_MODEM
3. 3V3_DIGITAL
4. GND_DIGITAL
5. 1V8_MIC
6. GND_MIC
7. PWR_GOOD
8. FAULT
9. EN_MODEM
10. EN_AUX
11. I2C2_SCL
12. I2C2_SDA

Molex Micro-Fit 3.0 board header `43045-1202`, mating housing `43025-1200`, power contact `43030-0038` and control/I2C contact `43030-0001` are selected electrically; exact board orientation remains a mechanical-freeze input.

## 4. PCB layout constraints

- separate cellular, GNSS, LoRa and BLE RF zones;
- uninterrupted reference ground under RF and digital high-speed return paths as appropriate;
- no DC/DC switching node beneath/adjacent to GNSS RF or microphone/PDM/wake fanout;
- short/wide BG95 power path and reference-design decoupling;
- short SIM traces; 1.8 V USIM integrity; ESD at connector;
- USB D+/D- controlled differential routing with continuous return;
- Raytac integrated antenna edge/keepout strictly preserved;
- PDM CLK/DATA routed away from DC/DC and RF; comparable harness lengths for MIC1..4;
- WAKE lines kept away from PDM clock and switching nodes; no floating OR-gate inputs;
- U7, U17, U18 1.8/3.3 V decoupling local;
- test points for regulated rails, reset, PPS, production UART, power state, STM32 SWD and nRF SWD;
- no HSE footprint/routing.

## 5. Native capture and manufacturing gate

Native directory contract:
- `hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_sch/.kicad_pcb/.kicad_pro`;
- `hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_sch/.kicad_pcb/.kicad_pro`;
- `hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_sch/.kicad_pcb/.kicad_pro`.

Capture is complete only when:
1. exact symbols and footprints are assigned and datasheet-reviewed;
2. exact STM32 pin map and CubeMX `.ioc` agree;
3. clock policy agrees with DEC-016;
4. all four 6-contact MIC harnesses, PA8 AAD wake and PA15 AAD_CFG paths agree with the harness/interconnect files;
5. all 1.8/3.3 V crossings are explicit;
6. power passives/feedback/shunt/fuse/TVS calculations are frozen;
7. ERC has no unexplained violations;
8. Review A passes.

PCB release candidate requires:
- DRC no blocker/critical violations;
- fabrication/stackup/impedance review;
- independent CAM review;
- Gerber + Excellon;
- IPC-356 where supported;
- PnP/centroid;
- production BOM/AVL;
- TOP/BOTTOM assembly drawings;
- STEP and fabrication notes;
- DFM response from PCB/PCBA manufacturer;
- Review B passes;
- SHA-256 release manifest.

`tools/kicad_native_gate.py --strict --run-cli` is the machine gate for native source, ERC/DRC and fabrication export. Passing that CLI gate does **not** waive Review A or Review B.

Until all conditions are met the state remains `NOT FOR MANUFACTURE`.
