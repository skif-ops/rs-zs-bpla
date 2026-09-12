# Дионея EVT-PRE-20 Rev.A - расчётная база PCB-PWR

Status: `CAPTURE BASELINE - NOT FOR MANUFACTURE`
Configuration: `EVT-PRE-20 Rev.A`
Ambient requirement: `-40...+70 C`
Component temperature capability target: at least `-40...+85 C`, with junction margin verified at +70 C.

## 1. Входная шина

Источник: 4S LiFePO4, номинально 12.8 V.

Для расчёта DC/DC до фиксации конкретного аккумулятора используется рабочее окно 10.0...14.6 V. Реальные BMS cutoff/recovery voltages должны быть заменены паспортными значениями выбранного аккумуляторного SKU.

Входной transient envelope пока НЕ заморожен. До выпуска платы требуется измерить/утвердить:

- MPPT disconnect/reconnect transient;
- подключение аккумулятора;
- длинный внешний жгут;
- reverse polarity event;
- fuse clearing energy;
- допустимый импульс TVS.

Поэтому `SMBJ18A` и PCB-fuse остаются кандидатами, а не release values.

## 2. Reverse polarity / reverse current

Baseline:

- U: Texas Instruments `LM74700QDBVRQ1`;
- Q: Texas Instruments `CSD18540Q5B`, 60 V N-MOSFET;
- topology: ideal diode on protected battery input ahead of both buck converters.

LM74700-Q1 работает при 3.2...65 V, предназначен для внешнего N-MOSFET и обеспечивает reverse polarity / reverse current blocking. Это соответствует 12.8 V battery architecture с большим запасом по DC input voltage.

Release blockers:

1. окончательная TVS/fuse coordination;
2. MOSFET SOA при ошибочном подключении и переходных процессах;
3. gate resistor / gate transient review;
4. reverse test на реальном аккумуляторе/лабораторном эквиваленте.

## 3. 3.8 V modem rail

Converter: `LMR604403SRAKR`, 4 A synchronous buck.

Назначение: отдельная шина `V_CELL_3V8` для BG95-M3.

BG95-M3 nominal VBAT: 3.8 V, допустимый диапазон 3.3...4.3 V. В совместимом design guide Quectel указаны peak currents до 0.6 A по VBAT_BB и до 2.7 A по VBAT_RF; поэтому rail проектируется как 4 A rail с локальным low-ESR bulk storage около модема.

### 3.1 Switching frequency baseline

Для первого capture принимается `400 kHz`.

Причины:

- выше efficiency margin, чем у 1...2 MHz;
- меньшие switching losses важны для автономности;
- размеры L/C допустимы для EVT-PRE-20;
- окончательное решение проверяется EMI и load-step тестами.

TI reference values для 3.8 V / 4 A / 400 kHz:

- L = `4.7 uH`;
- effective COUT target = `54 uF`;
- CIN = `4.7 uF` minimum reference value;
- CBOOT = `100 nF`, >=10 V;
- RT = `86.6 kOhm`.

Release inductor requirement:

- shielded;
- 4.7 uH;
- Isat >= 6 A target;
- Irms >= 4.5 A target;
- low DCR;
- -40...+125 C preferred.

Selected for both rails: Coilcraft `XAL7030-472MEC`, 4.7 uH +/-20%,
AEC-Q200, DCR 26.1 mOhm typical / 30.0 mOhm maximum, Isat 10.1 A and
Irms 6.9 A for 20 C rise. The controlled footprint follows Coilcraft document
863-2: two `1.58 x 6.50 mm` lands separated by a `2.94 mm` inner gap. Pad 1 is
the marked start/short lead and must face the SW/high-dV/dt node.

At the provisional maximum input of 14.6 V and 400 kHz:

- 3.8 V rail ripple is about 1.50 A p-p, so the 4 A full-load peak is about
  4.75 A and calculated RMS is about 4.02 A;
- 3.3 V rail ripple is about 1.36 A p-p, so the 4 A full-load peak is about
  4.68 A and calculated RMS is about 4.02 A;
- maximum winding loss from the 30.0 mOhm DCR limit is 0.48 W at 4 A.

The exact MPN and land pattern are therefore frozen. In-application +70 C
temperature rise, load-step behaviour and EMI remain release gates.

### 3.2 Feedback divider for 3.8 V

LMR60440 typical VFB = 1.0 V. TI recommends 100 kOhm as a typical top feedback resistor.

Using:

`VOUT = VFB * (1 + RFBT/RFBB)`

for:

- RFBT = 100.0 kOhm, 0.1%;
- VOUT = 3.8 V;

we obtain:

`RFBB = 100k / (3.8 - 1.0) = 35.714 kOhm`.

Capture value: `35.7 kOhm, 0.1%, low-TCR`.

Nominal calculated VOUT with 100k / 35.7k is approximately 3.801 V before IC/reference tolerance.

### 3.3 Modem local bulk

Quectel requires approximately 100 uF low-ESR bypass near VBAT and reserves separate RF/baseband decoupling networks. Rev.A shall therefore reserve:

- converter effective COUT >=54 uF after DC-bias derating;
- local low-ESR 100 uF class bulk at BG95 VBAT_BB path;
- local low-ESR 100 uF class bulk at BG95 VBAT_RF path;
- Quectel-recommended HF MLCC arrays adjacent to the appropriate modem pins;
- star split from the common 3.8 V source into VBAT_BB and VBAT_RF.

The exact capacitor technology/MPN is frozen only after cold-temperature ESR, load-step and layout review.

## 4. 3.3 V digital rail

Converter: second `LMR604403SRAKR`.

For Rev.A the 3.3 V rail uses the fixed-3.3 configuration of the selected device variant, provided the final captured part-number option is verified against TI ordering data before BOM release.

Initial switching baseline: `400 kHz`.

Initial TI reference values at 3.3 V / 4 A / 400 kHz:

- L = `4.7 uH`;
- effective COUT target = `54 uF`;
- CIN = `4.7 uF` minimum reference value;
- CBOOT = `100 nF`, >=10 V;
- RT = `86.6 kOhm`.

This rail supplies STM32, GNSS, LoRa, nRF52840 module and digital/peripheral loads subject to explicit load gating.

A separate 3V3_AON regulator is not added in Rev.A unless measured S0 current proves the merged rail cannot meet autonomy requirements.

## 5. 1.8 V microphone rail

LDO: `TPS7A2018PDBVR`.

Input: 3.3 V.
Output: fixed 1.8 V.
Rating: 300 mA.

Initial capture:

- CIN = 2.2 uF X7R, voltage rating >=6.3 V;
- COUT = 2.2 uF X7R, voltage rating >=6.3 V;
- both values must remain >=1 uF effective at bias and temperature;
- local 100 nF remains on each MIC leaf at T5838 VDD.

TPS7A20 has low-noise/high-PSRR characteristics and low Iq, suitable for the microphone/AAD rail. Final noise acceptance is by PDM/AAD measurement, not only by datasheet calculation.

## 6. Input current monitor

Monitor: `INA226AIDGSR`.

Capture shunt selection:

- RSHUNT = `10 mOhm`;
- 4-terminal/Kelvin construction required;
- >=1 W rating target;
- <=1% tolerance, 0.5% or 0.1% preferred;
- low TCR, <=50 ppm/C target.

Selected: Vishay Dale `WSK2512R0100FEA`, true four-terminal construction,
10 mOhm +/-1%, 1 W at 70 C and +/-35 ppm/C TCR. Its controlled footprint uses
the current Vishay document 30108 land-pattern values for the 0.005...0.2 Ohm
range: `a=2.29`, `b=3.30`, `c=0.76`, `d=0.51`, `e=1.70`, `l=3.68 mm`.
Pads 1/2 are source/load current lands; pads 3/4 are the corresponding
source/load Kelvin sense lands.

Reasoning:

At 5 A input current:

- VSHUNT = 50 mV;
- P = 0.25 W;

which remains inside INA226 shunt measurement range while providing useful resolution.
The 1 W rating is exactly four times the 0.25 W nominal dissipation at 5 A.
Final Kelvin routing, thermal evidence and reference-meter calibration remain blocking.

Firmware scaling baseline for max expected 5 A:

- minimum Current_LSB = 5 / 32768 = 152.6 uA;
- choose Current_LSB = `200 uA/bit`;
- CAL = 0.00512 / (0.0002 * 0.010) = `2560`;
- Power_LSB = 25 * Current_LSB = `5 mW/bit`.

These values are capture/firmware defaults and must be updated if final fuse/current envelope changes.

## 7. Required bench validation before release

### PWR-01 - 3.8 V load step

Test 0.05 A -> 2.0 A -> 3.3 A and representative pulsed BG95 profiles. Verify:

- no drop below BG95 minimum rail limit;
- converter does not enter unintended current limit;
- recovery without oscillation;
- local VBAT ripple/undershoot;
- hot/cold bulk capacitor behaviour.

### PWR-02 - 3.3 V load step

Exercise sleep/active transitions of MCU, LoRa, GNSS, BLE and storage.

### PWR-03 - thermal

At +70 C ambient run worst realistic concurrent load. Record regulator, inductor, MOSFET and PCB copper temperatures.

### PWR-04 - cold start

At -40 C verify startup, capacitor ESR effects, rail sequencing and modem attach bursts.

### PWR-05 - reverse polarity / input transient

Execute only with current-limited protected fixture. Verify LM74700-Q1, MOSFET, TVS and fuse coordination.

### PWR-06 - standby

Measure complete S0 current including both buck converters, TPS7A20, monitors and leakage paths. If merged 3V3 architecture misses the autonomy budget, raise an ECO rather than hiding the measured current.

## 8. Freeze state

Can proceed into native schematic capture now:

- LM74700-Q1 controller;
- CSD18540Q5B concept;
- LMR60440 x2;
- 3.8 V feedback 100k / 35.7k;
- 400 kHz baseline, RT 86.6k;
- Coilcraft XAL7030-472MEC 4.7 uH inductors with controlled land pattern;
- TPS7A2018;
- INA226 with Vishay WSK2512R0100FEA 10 mOhm four-terminal shunt and controlled land pattern.

Still open before `FOR_MANUFACTURE`:

- in-application inductor thermal/load-step/EMI evidence;
- exact MLCC/bulk capacitor MPNs after derating;
- TVS;
- PCB fuse;
- shunt Kelvin layout, temperature rise and reference-meter calibration;
- selected battery/BMS voltage limits;
- selected MPPT transient envelope;
- thermal and load-step test evidence;
- EMC/EMI evidence.

No item in this document overrides the two independent Review A / Review B release gates.
