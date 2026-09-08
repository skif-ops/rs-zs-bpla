# EVT-PRE-20 Rev.A native KiCad capture specification

Status: `CAPTURE_INPUT / BLOCKING`

This specification is the bridge between the approved EVT-PRE-20 system architecture and native KiCad schematic capture. It is not a substitute for manufacturer datasheets or reference designs.

## 1. PCB-MAIN functional blocks

### U1 - MCU
- MPN: STM32U585VIT6Q.
- Package: LQFP100 14x14 mm.
- Required peripherals: 4-channel PDM/MDF or equivalent capture, UART for BG95, UART/I2C for GNSS, SPI for LoRa, UART for BLE coprocessor, OCTOSPI/QSPI NOR, SDMMC preferred for microSD, I2C sensors/power monitoring, USB FS, SWD, timer/input capture for GNSS PPS.
- Mandatory support: all VDD/VSS/VDDA/VSSA/VREF/VCAP/SMPS-related pins according to selected supply mode; local decoupling at every supply group; NRST; BOOT configuration; SWDIO/SWCLK.
- Pin assignment remains blocked until verified in STM32CubeMX for the exact LQFP100 device.

### Audio/PDM interface
- Four external PCB-MIC leaves; one T5838 per leaf.
- Common PDM clock net: `PDM_CLK`.
- Independent data nets: `PDM_DATA1..4`.
- Microphone supply: `1V8_MIC` with common reference `GND`.
- Four board connectors `J_MIC1..J_MIC4` use identical logical pin numbering.
- Series termination footprints shall be provided at the clock source and/or per branch as determined by SI test; populate value after bench validation.
- No level translation scheme may introduce unequal or uncontrolled channel delay without characterization.

### Cellular
- Candidate modem: Quectel BG95-M3, fitted as U8 after regional band/operator confirmation.
- Power rail: `3V8_MODEM`; dimension copper/decoupling for modem current bursts.
- MCU interface: UART TX/RX plus PWRKEY, RESET_N, STATUS, DTR and RI where used.
- Logic levels shall match BG95 requirements; do not directly drive a 1.8 V-only input from 3.3 V GPIO.
- Cellular RF uses dedicated 50-ohm path to external connector with optional matching/ESD footprints per reference design.

### Dual nano-SIM
- Two physical nano-SIM connectors, `J_SIM1` and `J_SIM2`.
- One modem USIM interface through an approved 2:1 mux.
- Mux candidate from current BOM: TS3A27518E family; final exact suffix/footprint must be verified before release.
- Nets from modem: `USIM_VDD`, `USIM_RST`, `USIM_CLK`, `USIM_DATA`, `USIM_GND`.
- Per-slot nets: `SIM1_*`, `SIM2_*` plus `SIM1_DET`, `SIM2_DET`.
- Control: `SIM_MUX_SEL`, `SIM_MUX_EN` with safe default state.
- Switching while BG95 is powered is prohibited by hardware/software design rule.
- Low-capacitance ESD must be located adjacent to each external SIM connector.

### GNSS/PPS
- Candidate: u-blox MAX-M10S class.
- Main role: continuous timing/position independent of cellular operation.
- Interfaces: UART or I2C for control/data plus `GNSS_PPS`/TIMEPULSE to a timer input-capture capable MCU pin.
- RF: dedicated GNSS connector/path with antenna bias/ESD as required by selected antenna.
- Backup supply and reset/control shall follow u-blox reference recommendations.

### LoRa RU868
- Candidate module: Ebyte E22-900M22S/SX1262 class.
- Digital: SPI SCK/MISO/MOSI plus NSS, DIO1, BUSY, RESET_N.
- Power: 3.3 V domain with separately measurable/controllable consumption where practical.
- RF: dedicated 868 MHz path/connector with matching footprint and ESD strategy.
- Default boot state shall not transmit until a valid RU868 profile is loaded.

### BLE commissioning/OTA
- Candidate: ESP32-C3-MINI-1-N4.
- MCU-to-BLE service link: UART TX/RX plus enable/reset.
- Provide ESP32-C3 boot/programming access for manufacturing recovery.
- Keep boot straps isolated from external connector transients.
- BLE module shall be disabled or low-power outside commissioning/OTA windows according to firmware policy.

### NOR and microSD
- NOR: W25Q512JVFIQ-class 64 MB device on OCTOSPI/QSPI; include local decoupling and damping footprints.
- microSD: industrial card socket with detect; SDMMC 4-bit preferred if CubeMX pin budget permits, SPI fallback only by explicit revision decision.
- Both storage paths require power-loss recovery testing.

### Sensors/power monitor
- LIS2DW12 accelerometer.
- Temperature sensor candidate STTS22H or package-compatible approved alternative.
- INA226-class current/voltage monitors as applicable.
- Shared I2C bus only after address and power-domain compatibility check.

### USB-C service and SWD
- USB-C USB2 device/service port: VBUS, D+, D-, CC1, CC2, GND, shield; correct Rd configuration and ESD required.
- SWD production/recovery access: SWDIO, SWCLK, NRST, VTREF, GND.
- Test points must remain accessible to fixture independent of USB condition.

## 2. PCB-MIC Rev.A

Per board:
- `MK1` T5838 bottom-port PDM MEMS microphone.
- `J1` 4-position keyed locking connector.
- Logical pinout: 1=`1V8_MIC`, 2=`GND`, 3=`PDM_CLK`, 4=`PDM_DATA`.
- Local decoupling adjacent to microphone supply pins.
- Acoustic port keepout through PCB and enclosure stack.
- No copper, solder mask contamination, adhesive or conformal coat may block the acoustic port.
- All four leaves use identical PCB and BOM revision.

## 3. PCB-PWR Rev.A

Input: protected battery bus from LiFePO4/BMS/external MPPT assembly.

Required functions:
- input fuse coordination / service disconnect interface;
- reverse-polarity protection;
- transient/TVS protection;
- input voltage/current monitoring;
- controlled load switching where required;
- `3V8_MODEM` regulator sized for modem burst current;
- `3V3_DIGITAL` regulator;
- `3V3_AON` if separated from main digital rail;
- `1V8_MIC` low-noise regulator;
- `PWR_GOOD` and `FAULT` outputs to PCB-MAIN;
- enable inputs `EN_MODEM`, `EN_RF`, `EN_MIC` as defined by the final power-state machine.

No solar MPPT charger is implemented on this PCB.

## 4. Logical connector contracts

The exact connector manufacturer/MPN may be frozen after mechanical review, but the electrical pin order below is the baseline contract and must not be changed without an ICD revision.

- `J_MIC1..4`: 4 pins: 1V8_MIC, GND, PDM_CLK, PDM_DATAn.
- `J_PWR` MAIN side: 10 pins: 3V8_MODEM, GND_MODEM, 3V3_DIGITAL, GND_DIGITAL, 1V8_MIC, GND_MIC, PWR_GOOD, FAULT, EN_MODEM, EN_AUX (or split EN_RF/EN_MIC via expanded connector if needed). Final contact count may expand but existing net order remains documented.
- `J_SWD`: 5 pins: VTREF, SWDIO, SWCLK, NRST, GND.
- `J_USB`: standard USB-C device mapping according to USB2 requirements.

## 5. Layout constraints to capture as PCB rules/notes

- Keep cellular, GNSS and LoRa RF zones physically separated with uninterrupted reference ground.
- No high-current switching node under/adjacent to GNSS RF input or microphone signal fanout.
- Keep BG95 supply path short/wide; place bulk/high-frequency decoupling according to modem reference design.
- Keep SIM traces short and away from RF/high-current switch nodes.
- USB D+/D- differential routing must maintain a continuous return path.
- Preserve manufacturer antenna/RF keepouts for module candidates.
- Provide ground stitching around RF transitions/connectors and enclosure boundaries where appropriate.
- Route PDM clock/data away from modem DC/DC and RF feed lines; preserve comparable harness electrical length for MIC1..4.
- Provide explicit test points for all regulated rails, reset, SWD, production UART, PPS and power-state signals.

## 6. Capture completion criteria

Capture is complete only when:
1. three native schematic projects exist (MAIN/MIC/PWR);
2. exact symbols/footprints are assigned and datasheet-checked;
3. CubeMX pin map is committed and cross-checked;
4. connector net order matches `HARNESS_LOGICAL_PINOUT_REV_A.csv`;
5. ERC passes with no unexplained error;
6. Review A from `PCB_DOUBLE_REVIEW_GATE.md` is completed.

Only then may PCB placement/routing be treated as a release candidate.
