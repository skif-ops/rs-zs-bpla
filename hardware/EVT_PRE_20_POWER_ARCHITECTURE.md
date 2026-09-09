# EVT-PRE-20 - архитектура питания Rev.A

Статус: `DRAFT / COMPONENT FREEZE STARTED / NOT RUN`

## 1. Зафиксированные входные данные

- батарея: LiFePO4, 12.8 V, 40-60 Ah, встроенный или отдельный BMS;
- солнечная панель: 60-80 W;
- целевая автономность без солнца: 30 суток;
- внешний MPPT: не менее 10 A, профиль LiFePO4, дистанционный температурный датчик или запрет заряда при низкой температуре;
- собственная PCB-PWR: защита, измерение и DC/DC, без силового MPPT;
- T5838 Acoustic Activity Detect используется как основной низкопотребляющий акустический wake-path, поэтому `1V8_MIC` остаётся включённой в режиме AAD monitoring.

## 2. Проверка энергетического предела

| Батарея | Номинальная энергия | При 80% используемой энергии | Допустимая средняя мощность на 30 суток |
|---|---:|---:|---:|
| 12.8 V x 40 Ah | 512 Wh | 410 Wh | 0.57 W |
| 12.8 V x 60 Ah | 768 Wh | 614 Wh | 0.85 W |

30 суток без солнца подтверждаются только после измерения фактических режимов S0-S4. Расчёт по одной ёмкости батареи недостаточен.

## 3. Шины PCB-PWR

| Шина | Нагрузка | Rev.A |
|---|---|---|
| `VBAT_PROTECTED` | вход DC/DC | 10-15 V рабочий диапазон; `LM74700QDBVRQ1` + внешний 60 V MOSFET `CSD18540Q5B`; TVS и fuse окончательно после fault/surge profile |
| `3V8_MODEM` | BG95 | `LMR604403SRAKR`, 4 A; dedicated rail; LTE/2G burst load-step обязателен |
| `3V3_DIGITAL` | STM32, GNSS, LoRa, nRF52840, SD | `LMR604403SRAKR`, 4 A; low-Iq; отдельный `3V3_AON` в Rev.A не ставится |
| `1V8_MIC` | 4 x T5838 + low-voltage wake/PDM logic | `TPS7A2018PDBVR`, 300 mA low-noise LDO; остаётся активной при AAD monitoring |

Точные passives, inductors, feedback values, current shunt и TVS/fuse coordination остаются блокерами принципиальной схемы и рассчитываются до Review A.

## 4. Режимы мощности Rev.A

### S0 - AAD monitoring / deepest field listen

- STM32U585 в согласованном Stop mode с PA8 как wake-capable `MIC_WAKE` input;
- четыре T5838 остаются на `1V8_MIC` в AAD mode;
- PDM clock выключен после входа T5838 в AAD;
- U7 `SN74AXC8T245PWR` остаётся включённым при фиксированном `OE=LOW`; `PDM_CLK` и `AAD_CFG` удерживаются в LOW, поэтому микрофонный clock и THSEL transitions отсутствуют; его гарантированный worst-case static current входит в измеряемый S0 budget;
- `MIC_WAKE1..4` объединяются на 1.8 V через `SN74LVC32APWR`, затем `SN74AXC1T45DRLR` переводит aggregate wake на PA8/3.3 V;
- BG95, LoRa TX, SD high-power operations и BLE выключены/усыплены согласно state machine;
- MAX-M10S duty/continuous-time mode определяется timing requirement и измеренным holdover budget.

До выпуска измеряется полный ток S0 на реальной PCB, включая LDO Iq, T5838 AAD, wake logic, MCU Stop, GNSS timing strategy и leakage всех отключённых доменов.

### S1 - acoustic confirmation

AAD wake переводит STM32 в активное состояние, запускается PDM clock/MDF и короткий detector/feature pipeline. При неподтверждённом событии система возвращается в S0.

### S2 - classification/event build

Работают PDM capture, DSP/classifier, NOR/SD event buffer по необходимости.

### S3 - communications

Включается cellular или резервный LoRa/BLE service path; отдельно измеряются LTE/2G burst, attach, TLS и retransmission.

### S4 - service/OTA/test

Максимальный одновременный сервисный режим, не используемый для расчёта типового field average без соответствующего duty cycle.

## 5. Component freeze

Авторитетная таблица: `hardware/POWER_COMPONENT_FREEZE_REV_A.csv`.

Выбранные для capture позиции:
- reverse/reverse-current controller `LM74700QDBVRQ1`;
- MOSFET `CSD18540Q5B`;
- `3V8_MODEM` и `3V3_DIGITAL`: `LMR604403SRAKR`;
- `1V8_MIC`: `TPS7A2018PDBVR`;
- current monitor: `INA226AIDGSR`, final shunt pending;
- TVS `SMBJ18A` и PCB fuse `0451005.MRL` остаются кандидатами до измеренного transient/fault profile.

## 6. Требования к MPPT/BMS до RFQ

1. Профиль 4S LiFePO4 и регулируемые charge/float параметры.
2. Входное напряжение выше холодного Voc выбранной панели с запасом не менее 20%.
3. Ток заряда не менее 10 A и настраиваемое ограничение по паспорту батареи.
4. Запрет заряда ниже 0 °C, если батарея не имеет подтверждённого heater/low-temperature cut-off.
5. Собственное потребление и ночной reverse current указаны и измерены.
6. Защита reverse polarity/current, short circuit и overtemperature.
7. Клеммы, провод и предохранитель рассчитаны на максимальный ток с derating.
8. Протокол телеметрии желателен, но для EVT не обязателен при независимом мониторинге PCB-PWR.

## 7. Обязательные испытания

- холодный и горячий старт, восстановление после BMS cut-off;
- panel present/absent и LTE/2G transmit burst;
- reverse polarity, controlled-short, fuse coordination;
- температура DC/DC, MOSFET, разъёмов и проводов;
- токи S0-S4 на всех изделиях согласно EVT matrix;
- отдельное измерение S0 с четырьмя T5838 AAD + WAKE OR/translator;
- AAD false-wake / missed-wake / wake-latency при ветре, дороге, насекомых и целевых акустических записях;
- 72-часовой bench run и расчёт 30 суток по измеренному duty cycle;
- low-temperature charge inhibit.

Производственный release PCB-PWR запрещён до schematic/ERC, расчёта passives/thermal/fault, DRC/CAM и двух review gates.
