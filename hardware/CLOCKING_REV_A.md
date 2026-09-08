# EVT-PRE-20 Rev.A clocking policy

Status: `LOCKED_INPUT / TARGET_VALIDATION_REQUIRED`
Decision: `DEC-016`

## 1. High-speed clock policy

The STM32U585VIT6Q on EVT-PRE-20 Rev.A shall not use an external HSE crystal or HSE oscillator.

Approved high-speed sources are the MCU internal MSI/HSI oscillators and PLL. The exact runtime clock tree, PLL multipliers/dividers and voltage-scaling operating points are generated in CubeMX for the exact `STM32U585VITxQ/LQFP100` target and then measured on hardware.

No HSE crystal, HSE oscillator, load capacitors or HSE tuning network shall be populated on PCB-MAIN Rev.A. HSE-capable pins remain available for their approved Rev.A functions only if the exact package pin map assigns them; no hidden HSE dependency is allowed in firmware.

## 2. Low-frequency reference

The separate 32.768 kHz reference remains `SiT1552AI-JE-DCC-32.768D` as listed in the EVT-PRE-20 BOM. Its role is low-frequency/timebase support only; it is not the high-speed system clock.

The exact STM32 LSE bypass/external-clock configuration and PC14/PC15 treatment must be generated and reviewed in CubeMX for `STM32U585VITxQ`. Do not assume crystal-mode wiring for the SiT1552 oscillator output.

## 3. Required runtime profiles

Firmware shall define at least these measured profiles before release:

- `S0_SLEEP`: lowest practical station standby clock/power state compatible with wake sources.
- `S1_LISTEN`: microphone acquisition / detector listening state.
- `S2_DSP`: full 32 kHz four-channel acquisition and feature extraction.
- `S3_COMMS`: cellular/LoRa/BLE service state with required CPU clock margin.
- `S4_SERVICE`: USB/SWD/commissioning/recovery state.

The final frequencies are not released by this document; they must come from the reviewed CubeMX target and measured timing/energy evidence.

## 4. Mandatory validation

Before `FOR_MANUFACTURE` / firmware release, verify on target hardware:

1. clock startup and recovery from reset/brownout;
2. every required MSI/HSI/PLL transition with no deadlock;
3. 32 kHz four-channel PDM sample-rate accuracy and long-run drift;
4. USB FS enumeration and sustained transfer under the selected internal-clock configuration;
5. GNSS PPS timestamp capture accuracy and jitter;
6. low-power entry/wake and clock restoration;
7. cellular burst plus DSP operation without clock/power instability;
8. temperature sweep of timing-critical functions over the EVT environmental range once that range is frozen.

## 5. Release gate

Any later introduction of an HSE component or dependency is a configuration change and invalidates the affected schematic review, PCB Review A, firmware target review and clock-validation evidence.
