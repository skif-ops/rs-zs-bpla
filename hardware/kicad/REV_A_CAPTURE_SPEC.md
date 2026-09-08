# EVT-PRE-20 Rev.A native KiCad capture specification

Status: `CAPTURE_INPUT / BLOCKING`

This specification is the bridge between the approved EVT-PRE-20 system architecture and native KiCad schematic capture. It is not a substitute for manufacturer datasheets or reference designs.

Authoritative MCU/net assignment: `hardware/EVT_PRE_20_PIN_MAP_REV_A.csv`.

## 1. PCB-MAIN functional blocks

### U1 - MCU
- MPN: `STM32U585VIT6Q`.
- Exact ST pin-database identity: `STM32U585VITxQ`.
- Package: LQFP100 14x14 mm with SMPS pins.
- Required peripherals: 4-channel PDM/MDF capture, UART for BG95, UART for GNSS, SPI for LoRa, UART for BLE coprocessor, OCTOSPI/QSPI NOR, SDMMC1 4-bit for microSD, I2C2 sensors/power monitoring, USB FS, SWD, timer input capture for GNSS PPS.
- Mandatory support: all VDD/VSS/VDDA/VSSA/VREF/VDDUSB/VDD11/SMPS-related pins according to selected supply mode; local decoupling at every supply group; NRST; BOOT0; SWDIO/SWCLK.
- Exact-package guard: `PB12`, `PE1`, `PC4`, and `PC5` are absent from `STM32U585VITxQ/LQFP100` and are forbidden in Rev.A even though generic STM32U585 package tables may show them for other variants.
- The Rev.A CSV map is checked by CI for duplicate use and required peripheral mapping. Final alternate-function initialization remains blocked until a CubeMX `.ioc` for this exact package is generated and reviewed.

### Frozen Rev.A peripheral map
- MDF/PDM: PE9=`MDF1_CCK0`; PB1=`MDF1_SDI0`; PD6=`MDF1_SDI1`; PE7=`MDF1_SDI2`; PE4=`MDF1_SDI3`.
- OCTOSPI1 NOR: PE10=`CLK`, PE11=`NCS`, PE12..PE15=`IO0..IO3`.
- SDMMC1: PC8..PC11=`D0..D3`, PC12=`CK`, PD2=`CMD`, PC13=`SD_DET` GPIO.
- GNSS: PA2/PA3=`USART2 TX/RX`, PA0=`TIM2_CH1` PPS input capture.
- LoRa: PA4..PA7=`SPI1 NSS/SCK/MISO/MOSI`, PD8=`DIO1`, PD9=`BUSY`, PD10=`RESET_N`.
- BG95 main UART: PB6/PB7=`USART1 TX/RX`; PD11..PD15 are cellular control/status GPIOs as defined in the pin-map CSV.
- BLE: PB10/PB11=`USART3 TX/RX`; PE6=`BLE_EN`; PB2=`BLE_BOOT` open-drain request.
- Sensor/power I2C: PB13/PB14=`I2C2 SCL/SDA`.
- Power interface: PD0=`PWR_GOOD`, PD1=`PWR_FAULT`, PD4=`EN_MODEM`, PD5=`EN_AUX`.
- Production LPUART: PC0=`RX`, PC1=`TX`.
- USB FS: PA9=`VBUS sense`, PA11=`DM`, PA12=`DP`.
- SWD: PA13=`SWDIO`, PA14=`SWCLK`.
- Hardware straps: PB8/PB9 revision straps, PH3 BOOT0.
- 32.768 kHz domain: PC14/PC15 reserved for the LSE/external-oscillator implementation.

### Audio/PDM interface
- Four external PCB-MIC leaves; one TDK/InvenSense `T5838` per leaf.
- Common PDM clock net: `PDM_CLK`.
- Independent data nets: `PDM_DATA1..4`.
- Microphone supply: `1V8_MIC`, nominal 1.8 V, with common reference `GND`.
- Four board connectors `J_MIC1..J_MIC4` use identical logical pin numbering.
- Rev.A level translation candidate: `SN74AXC8T245PWR`, TSSOP-24, with VCCA/VCCB arranged so one four-bit direction group carries the MCU-to-microphone clock and the other group carries the four microphone-to-MCU data channels. Unused bits in the clock-direction group are not routed to external connectors.
- Do not use an uncontrolled auto-direction translator for the PDM path.
- Provide direction/OE default states that keep microphones isolated during incomplete power sequencing. Translator isolation/partial-power-down behavior shall be verified in Review A.
- Series damping footprints shall be provided at the PDM clock source/fanout; population value is frozen after bench/SI validation.
- Channel-to-channel data-path skew shall be characterized; the design goal is ≤1 audio sample equivalent after calibration.

### Cellular
- Candidate modem: Quectel `BG95-M3`, LGA module, fitted as U8 after regional-band/operator confirmation.
- Power rail: `3V8_MODEM`; design for the BG95-M3 3.3–4.3 V supply range and burst-current voltage drop with local bulk/high-frequency decoupling.
- Main UART and related BG95 digital interfaces are a **1.8 V domain**. PB6/PB7 must not be wired directly as 3.3 V UART to the module.
- MCU interface: translated UART TX/RX plus PWRKEY, RESET_N, STATUS, DTR and RI control/status paths.
- PWRKEY/RESET controls use a reference-design-compatible open-drain/transistor or other approved 1.8 V-domain interface; direct 3.3 V drive is forbidden.
- Cellular RF uses a dedicated 50-ohm path to external connector with reference-design matching/ESD footprints.

### Dual nano-SIM
- Two physical nano-SIM connectors, `J_SIM1` and `J_SIM2`.
- BG95 supports a 1.8 V USIM/SIM interface; both slots and the mux/ESD network must preserve this domain.
- One modem USIM interface through an approved 2:1 mux.
- Current mux candidate: TI `TS3A27518E` family; exact suffix/footprint remains subject to final USIM signal-integrity review.
- Nets from modem: `USIM_VDD`, `USIM_RST`, `USIM_CLK`, `USIM_DATA`, `USIM_GND`.
- Per-slot nets: `SIM1_*`, `SIM2_*` plus `SIM1_DET`, `SIM2_DET`.
- MCU control: PE0=`SIM_MUX_SEL`, PE2=`SIM_MUX_EN`, PE3=`SIM1_DET`, PE5=`SIM2_DET`.
- Safe reset state: mux disabled or SIM1 selected according to the final mux truth table; no uncontrolled slot switching.
- Switching while the modem USIM interface is powered is prohibited by the hardware/software design rule.
- Low-capacitance ESD must be located adjacent to each external SIM connector.

### GNSS/PPS
- Candidate: u-blox `MAX-M10S` class.
- Main role: continuous timing/position independent of cellular operation.
- UART: PA2/PA3 USART2; `GNSS_PPS`/TIMEPULSE on PA0/TIM2_CH1 input capture.
- Use the module in a 3.3 V-compatible I/O configuration; verify VIO/VIO_SEL and backup-supply wiring against the exact ordered MAX-M10S revision.
- RF: dedicated GNSS connector/path with antenna bias/ESD as required by the selected active antenna.

### LoRa RU868
- Candidate module: Ebyte `E22-900M22S` / SX1262 class.
- SPI1: PA4 NSS, PA5 SCK, PA6 MISO, PA7 MOSI; PD8 DIO1, PD9 BUSY, PD10 RESET_N.
- Power: 3.3 V domain with separately measurable/controllable consumption where practical.
- RF: dedicated 868 MHz path/connector with matching footprint and ESD strategy.
- Default boot state shall not transmit until a valid RU868 profile is loaded.

### BLE commissioning/OTA
- Candidate: `ESP32-C3-MINI-1-N4`.
- MCU-to-BLE service link: PB10/PB11 USART3 TX/RX to ESP32-C3 UART0-class service pins.
- PE6 controls module EN/reset. PB2 requests download boot by pulling ESP GPIO9 low through an open-drain arrangement; default bias keeps normal SPI boot.
- Respect ESP32-C3 strapping timing; GPIO2/GPIO8/GPIO9 strap states and any external pull resistors must be reviewed before capture release.
- Provide independent manufacturing recovery pads for EN, boot strap, TX, RX, 3V3 and GND.
- BLE module shall be disabled or low-power outside commissioning/OTA windows according to firmware policy.

### NOR and microSD
- NOR: `W25Q512JVFIQ`-class 64 MB device on OCTOSPI1/QSPI using PE10..PE15; include local decoupling and damping footprints.
- microSD: industrial card socket with detect on SDMMC1 4-bit bus using PC8..PC12 + PD2, with PC13 card detect.
- SPI fallback for microSD is not part of Rev.A unless an explicit configuration revision is approved.
- Both storage paths require power-loss recovery testing.

### Sensors/power monitor
- LIS2DW12 accelerometer with interrupt on PC6.
- Temperature sensor candidate STTS22H or approved package-compatible alternative.
- INA226-class current/voltage monitors as applicable.
- PB13/PB14 I2C2 bus; verify every selected device address and power domain before schematic freeze.
- PC7 is reserved for enclosure tamper input.

### USB-C service, production UART and SWD
- USB-C USB2 device/service port: PA9 VBUS sense, PA11 D-, PA12 D+, CC1, CC2, GND and shield; correct device-mode Rd configuration and ESD required.
- PC0/PC1 LPUART1 is production/EOL diagnostic UART and shall not be exposed as a general field console without authentication policy.
- SWD production/recovery access: PA13 SWDIO, PA14 SWCLK, NRST, VTREF, GND.
- Test points must remain accessible to the fixture independent of USB condition.

## 2. PCB-MIC Rev.A

Per board:
- `MK1` T5838 bottom-port PDM MEMS microphone.
- `J1` 4-position keyed locking connector.
- Logical pinout: 1=`1V8_MIC`, 2=`GND`, 3=`PDM_CLK`, 4=`PDM_DATA`.
- Local decoupling adjacent to microphone supply pins.
- Acoustic port keepout through PCB and enclosure stack.
- No copper, solder mask contamination, adhesive or conformal coat may block the acoustic port.
- All four leaves use identical PCB and BOM revision and preferably the same microphone lot.

## 3. PCB-PWR Rev.A

Input: protected battery bus from LiFePO4/BMS/external MPPT assembly.

Required functions:
- input fuse coordination / service disconnect interface;
- reverse-polarity protection;
- transient/TVS protection;
- input voltage/current monitoring;
- controlled load switching where required;
- `3V8_MODEM` regulator sized for modem burst current and verified against a worst-case load transient;
- `3V3_DIGITAL` regulator;
- `3V3_AON` if separated from the main digital rail;
- `1V8_MIC` low-noise regulator;
- `PWR_GOOD` and `FAULT` outputs to PCB-MAIN;
- `EN_MODEM` and `EN_AUX` inputs from PCB-MAIN.

No solar MPPT charger is implemented on PCB-PWR; the LiFePO4 MPPT remains an external assembly.

## 4. Logical connector contracts

The exact connector manufacturer/MPN may be frozen after mechanical review, but electrical order below is the baseline contract and must not change without an ICD revision.

- `J_MIC1..4`: 4 pins: 1V8_MIC, GND, PDM_CLK, PDM_DATAn.
- `J_PWR` MAIN side: 10 pins: 3V8_MODEM, GND_MODEM, 3V3_DIGITAL, GND_DIGITAL, 1V8_MIC, GND_MIC, PWR_GOOD, FAULT, EN_MODEM, EN_AUX.
- `J_SWD`: 5 pins: VTREF, SWDIO, SWCLK, NRST, GND.
- `J_USB`: standard USB-C USB2 device mapping according to USB requirements.
- Full electrical order and preliminary wire-gauge rules are in `hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv`.

## 5. Layout constraints to capture as PCB rules/notes

- Keep cellular, GNSS and LoRa RF zones physically separated with uninterrupted reference ground.
- No high-current switching node under/adjacent to GNSS RF input or microphone signal fanout.
- Keep BG95 supply path short/wide; place bulk/high-frequency decoupling according to Quectel reference design.
- Keep SIM traces short and away from RF/high-current switching nodes; preserve the 1.8 V USIM domain.
- USB D+/D- differential routing must maintain a continuous return path.
- Preserve manufacturer antenna/RF keepouts for module candidates.
- Provide ground stitching around RF transitions/connectors and enclosure boundaries where appropriate.
- Route PDM clock/data away from modem DC/DC and RF feed lines; preserve comparable harness electrical length for MIC1..4.
- Keep the PDM translator close to the MCU/fanout origin and keep its 1.8 V and 3.3 V decoupling local.
- Provide explicit test points for all regulated rails, reset, SWD, production UART, PPS and power-state signals.

## 6. Capture completion criteria

Capture is complete only when:
1. three native schematic projects exist (MAIN/MIC/PWR);
2. exact symbols/footprints are assigned and datasheet-checked;
3. the exact-package pin map matches `hardware/EVT_PRE_20_PIN_MAP_REV_A.csv`;
4. a CubeMX `.ioc` for `STM32U585VITxQ/LQFP100` is committed and cross-checked against the CSV map;
5. connector net order matches `hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv`;
6. all BG95 1.8 V crossings and the T5838 1.8 V PDM crossing are explicit in the schematic;
7. ERC passes with no unexplained error;
8. Review A from `hardware/PCB_DOUBLE_REVIEW_GATE.md` is complete.

Only then may PCB placement/routing be treated as a release candidate.
