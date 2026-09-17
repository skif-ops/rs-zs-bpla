# Дионея EVT-PRE-20 Rev.A - расчётная база PCB-PWR

Status: `CAPTURE BASELINE - NOT FOR MANUFACTURE`
Configuration: `EVT-PRE-20 Rev.A`
Ambient requirement: `-40...+70 C`
Component temperature capability target: at least `-40...+85 C`, with junction margin verified at +70 C.

## 1. Входная шина

Источник: 4S LiFePO4, номинально 12.8 V.

EVT-кандидат аккумулятора зафиксирован как RELiON `RB40`, 12.8 V / 40 Ah /
512 Wh. Для расчёта DC/DC до завершения sample/EVT проверки сохраняется
консервативное рабочее окно 10.0...14.6 V. Паспортные и измеренные BMS
cutoff/recovery voltages RB40 должны заменить это provisional окно перед выпуском.

EVT-кандидат солнечного тракта: SLD Tech `SLP080S-12M` и Victron SmartSolar
75/10 `SCC075010060R` с датчиком Smart Battery Sense `SBS050150200` (`0.45 m`
провода, wireless range до `10 m`, M10 eyelets, рабочий диапазон `-10..60 C`).
Для M10 eyelets на M8 терминалах RB40 нужен утверждённый washer/retention stack.
Выбор точных MPN не заменяет измерение переходного процесса и конфигурационный audit.

Входной transient envelope пока НЕ заморожен. До выпуска платы требуется измерить/утвердить:

- MPPT disconnect/reconnect transient;
- подключение аккумулятора;
- длинный внешний жгут;
- reverse polarity event;
- fuse clearing energy;
- допустимый импульс TVS.

Поэтому `SMBJ18A` и PCB-fuse остаются кандидатами, а не release values.

### 1.1 Fuse desk review and bounded value ECO

Ранее подписанная native-схема содержала `0451005.MRL` 5 A. Значение `5 A` в
этом проекте является консервативной qualification/protection envelope, а не
расчётным нормальным непрерывным потреблением станции. Даже одновременная
теоретическая отдача двух buck на полном номинале составляет
`3.8 V * 4 A + 3.3 V * 4 A = 28.4 W`: это примерно `2.47 A` от 12.8 V при
90% КПД или `3.34 A` от 10.0 V при 85% КПД. Реальный envelope должен быть
заморожен по измерениям нагрузки, пусковым процессам и fault coordination.

Кандидат 5 A всё равно отклонён для принятой 5 A qualification envelope:
Littelfuse требует стандартный derating 25% для continuous operation
дополнительно к температурной кривой. Поэтому 5 A nominal даёт только `3.75 A`
до температурного derating и не покрывает контрольную envelope.

Для EVT-квалификации выбран точный кандидат Littelfuse `0451008.MRL` в том же
Nano2 451 land pattern:

- nominal rating `8 A`;
- nominal cold resistance `7.7 mOhm`;
- nominal melting I²t `20.23 A²s`;
- после только стандартного 25% derating остаётся `6.0 A`;
- при 5 A nominal cold loss составляет `0.1925 W`.

`7 A` не выбран: после стандартного derating он оставляет лишь `5.25 A` ещё
до обязательного +70 C temperature rerating. `8 A` также остаётся ниже
опубликованного Molex предела `8.5 A/contact` для J1 `43045-0213` и terminal
`43030-0038`, но разница `0.5 A` не считается release margin. Нужны
assembled thermal tests J1/harness/F1 при +70 C и подтверждённом 18 AWG проводе.
Окончательный номинал должен также пройти I²t coordination с защищаемыми
дорожками, жгутом 18 AWG / 0.75 mm2 и внешним первичным предохранителем батареи.

Это двухступенчатое изменение. BOM и qualification contract перешли на
`0451008.MRL`; bounded value-only ECO уже применён к native schematic/PCB и
генераторам без изменения footprint, placement, topology, nets или pad map.
Старые ERC/PDF/подпись относятся только к исторической value `0451005.MRL`.
Повторные KiCad 9 ERC/PDF evidence для активного ECO прошли и привязаны к commit
и SHA-256. До независимого hierarchy review и закрытия
`PCB_PWR_INPUT_PROTECTION_TEST_MATRIX_REV_A.csv` запрещены PCBA procurement и
manufacturing release. Топология и footprint не меняются.

`SMBJ18A` сохраняется как точный EVT-кандидат: 18 V standoff,
20.0...22.1 V breakdown, 29.2 V maximum clamp at 20.6 A и 600 W at
10/1000 us. Его 29.2 V tabulated clamp даёт только 6.8 V до 36 V absolute
maximum buck input, поэтому qualification требует измеренный максимум не более
`32.0 V` на protected node и немедленный reject при любом измерении
`>=36.0 V`. TVS не предназначен для длительного MPPT overvoltage.

INA226 scaling остаётся `200 uA/bit` для нормального operating envelope до
5 A. Его signed current register покрывает около `6.5534 A`; overload и
fault-energy испытания выше этого тока обязаны использовать внешний
калиброванный current probe и осциллограф. INA226 не является прибором
fuse-clearing qualification.

## 2. Reverse polarity / reverse current

Baseline:

- U: Texas Instruments `LM74700QDBVRQ1`;
- Q: Texas Instruments `CSD18540Q5B`, 60 V N-MOSFET;
- topology: ideal diode on protected battery input ahead of both buck converters.

Конденсатор `C1` между VCAP и ANODE равен `100 nF`. Это соответствует
рекомендованным `0.1 uF` и условиям электрических характеристик LM74700-Q1
Rev.G; замена на 1 uF не требуется.

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

TI Table 8-3 отдельно требует для каждого преобразователя `CIN_HF = 0.1 uF`
непосредственно у VIN/PGND и `CIN = 4.7 uF` рядом с устройством, оба с rating
не ниже 50 V. Поэтому Rev.A содержит `C20` у U3 и `C21` у U4, оба
`100 nF / 50 V X7R`, дополнительно к `C11/C12 = 4.7 uF / 50 V X7R`.
`C13 = 100 uF` остаётся общей демпфирующей ёмкостью VBAT_SYS, а не заменой
локальных HF-петель. Effective capacitance C11/C12 при 10.0...14.6 V пока не
считается подтверждённой: требуется кривая DC bias либо измерение/модель TDK.

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

Точный orderable `LMR604403SRAKR` по SNAS877 прямо обозначен как
`3.3 V fixed / adjustable`. Режим определяется соединением FB: сопротивление
FB-VOUT менее 1 Ohm выбирает fixed 3.3 V, а параллельное сопротивление делителя
более 3 kOhm выбирает adjustable mode. Для U3
`100 kOhm || 35.7 kOhm = 26.3 kOhm`, поэтому это допустимый adjustable 3.8 V
режим. У U4 FB соединён непосредственно с 3V3_DIGITAL, поэтому это fixed 3.3 V
режим. Дополнительная замена MPN по этому вопросу не требуется.

### 3.3 Modem local bulk

Quectel requires approximately 100 uF low-ESR bypass near VBAT and reserves separate RF/baseband decoupling networks. Rev.A shall therefore reserve:

- converter effective COUT >=54 uF after DC-bias derating;
- local low-ESR 100 uF class bulk at BG95 VBAT_BB path;
- local low-ESR 100 uF class bulk at BG95 VBAT_RF path;
- Quectel-recommended HF MLCC arrays adjacent to the appropriate modem pins;
- star split from the common 3.8 V source into VBAT_BB and VBAT_RF.

Межплатный путь использует одну пару контактов Micro-Fit: pin 1
`3V8_MODEM` и pin 2 `GND_MODEM`, оба 18 AWG / 0.75 mm2. На PCB-MAIN
`C36` и `C44` по `100 uF` каждый обязательны у ветвей VBAT_BB/VBAT_RF.
При LTE/EGPRS burst требуется не менее `3.3 V` на всех четырёх VBAT pads U8,
а end-to-end сопротивление RF power path при 25 C должно быть не более
`100 mOhm`; окончательное подтверждение выполняется на реальном жгуте при
номинальной и +70 C температуре.

Exact PCB-PWR capacitor candidates are controlled in
`PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv` so schematic capture and the engineering BOM use
one identity. They are not released for manufacture until cold-temperature ESR,
DC-bias derating, transient/load-step and layout review are closed.

## 4. 3.3 V digital rail

Converter: second `LMR604403SRAKR`.

For Rev.A the 3.3 V rail uses the fixed-3.3 configuration of the selected
`LMR604403SRAKR`. TI SNAS877 explicitly identifies this orderable as
`3.3 V fixed / adjustable`; direct FB-to-output connection selects fixed mode.

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

Firmware scaling baseline for the conservative 5 A qualification envelope:

- minimum Current_LSB = 5 / 32768 = 152.6 uA;
- choose Current_LSB = `200 uA/bit`;
- CAL = 0.00512 / (0.0002 * 0.010) = `2560`;
- Power_LSB = 25 * Current_LSB = `5 mW/bit`.

These values remain the normal-operation telemetry baseline. They must be updated
if the released operating-current envelope, rather than only the protective fuse
rating, exceeds 5 A. Overload/fault qualification uses external instrumentation.

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

### PWR-07 - conducted EMI and input-filter decision

Measure battery/MPPT harness common-mode and differential conducted emissions
with LISN/current probe in worst buck, LTE and LoRa/GNSS coexistence modes.
Near-field probe the two hot loops and check GNSS/LoRa/LTE desense. Rev.A does
not add a ferrite or common-mode choke blindly: TI warns that an undamped input
filter can destabilize the converter. Before routing, either freeze a simulated
and measured stable filter plus damping network or explicitly reserve and approve
the no-filter EVT configuration; any populated filter requires repeat load-step,
startup and EMI tests.

### PWR-08 - 3V8 diagnostic coverage

`PG_3V8` remains diagnostic-only at `TP5`; `R15` is DNP and no dedicated
PG_3V8 signal crosses J2. Firmware therefore infers modem-rail health from modem
state and INA226 telemetry, while bench EVT probes TP5. A direct firmware PG_3V8
input requires a separate interboard ECO; `PWR_GOOD` remains the 3V3 AON status
because the modem rail may be intentionally disabled.

## 8. Freeze state

Can proceed into native schematic capture now:

- LM74700-Q1 controller;
- CSD18540Q5B concept;
- LMR60440 x2;
- verified dual fixed/adjustable use of exact `LMR604403SRAKR`;
- local `C20/C21 = 100 nF / 50 V` CIN_HF plus `C11/C12 = 4.7 uF / 50 V`;
- 3.8 V feedback 100k / 35.7k;
- 400 kHz baseline, RT 86.6k;
- Coilcraft XAL7030-472MEC 4.7 uH inductors with controlled land pattern;
- TPS7A2018;
- INA226 with Vishay WSK2512R0100FEA 10 mOhm four-terminal shunt and controlled land pattern.

Still open before `FOR_MANUFACTURE`:

- in-application inductor thermal/load-step/EMI evidence;
- release of the controlled MLCC/bulk capacitor candidates after DC-bias,
  cold-ESR, transient, load-step and package/assembly review;
- TVS;
- PCB fuse;
- shunt Kelvin layout, temperature rise and reference-meter calibration;
- measured RB40 BMS cutoff/recovery voltage limits and cold-system behavior;
- measured `SCC075010060R` disconnect/reconnect transient envelope and exported
  charge profile;
- proof that `SBS050150200` remains in the VE.Smart network and disables charge
  below the project `0 C` threshold;
- thermal and load-step test evidence;
- EMC/EMI evidence.

No item in this document overrides the two independent Review A / Review B release gates.
