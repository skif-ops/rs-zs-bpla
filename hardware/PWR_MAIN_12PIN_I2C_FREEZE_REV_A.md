# Дионея EVT-PRE-20 Rev.A - freeze интерфейса PCB-PWR <-> PCB-MAIN

Статус: `ELECTRICAL FROZEN / MECHANICS PENDING / NOT FOR MANUFACTURE`
Дата: 2026-09-09
Решение: вариант A - 12-pin, полноценный INA226 на PCB-PWR с I2C.

## 1. Решение

В Rev.A межплатный интерфейс PCB-PWR <-> PCB-MAIN выполняется 12-контактным Molex Micro-Fit 3.0. Старый 10-pin контракт отменён.

Выбранная электрическая пара:
- board header: Molex `43045-1202` / `0430451202`, 12 circuits, dual row, right-angle, through-hole, gold, -40...+125 C;
- cable housing: Molex `43025-1200` / `0430251200`, 12 circuits, dual row, polarized/latching, -40...+105 C;
- 18 AWG power contacts: Molex `43030-0038`;
- 20-24 AWG control/I2C contacts: Molex `43030-0001`.

Окончательная ориентация разъёма и keepout остаются входом механического freeze, но электрический pin contract изменению без ECO не подлежит.

## 2. Pinout Rev.A

| Pin | Net | Direction at MAIN | Class | Wire |
|---:|---|---|---|---|
| 1 | 3V8_MODEM | IN | power | 18 AWG / 0.75 mm2 |
| 2 | GND_MODEM | RETURN | power | 18 AWG / 0.75 mm2 |
| 3 | 3V3_DIGITAL | IN | power | 18 AWG / 0.75 mm2 |
| 4 | GND_DIGITAL | RETURN | power | 18 AWG / 0.75 mm2 |
| 5 | 1V8_MIC | IN | power | 18 AWG / 0.75 mm2 |
| 6 | GND_MIC | RETURN | power | 18 AWG / 0.75 mm2 |
| 7 | PWR_GOOD | IN | control | 20-24 AWG |
| 8 | FAULT | IN | control | 20-24 AWG |
| 9 | EN_MODEM | OUT | control | 20-24 AWG |
| 10 | EN_AUX | OUT | control | 20-24 AWG |
| 11 | I2C2_SCL | BIDIR open-drain | I2C 3.3 V | 20-24 AWG |
| 12 | I2C2_SDA | BIDIR open-drain | I2C 3.3 V | 20-24 AWG |

Pins 1-10 сохраняют предыдущий логический порядок. I2C добавляется только pins 11/12.

## 3. INA226 on PCB-PWR

- device: Texas Instruments `INA226AIDGSR`;
- location: PCB-PWR;
- role: измерение общего потребления станции от батарейной шины, а не только отдельной нагрузки;
- shunt capture: 10 mOhm, 4-terminal/Kelvin, >=1 W, low TCR;
- I2C address Rev.A: `0x40`;
- I2C bus: STM32 `I2C2`, PB13=SCL, PB14=SDA;
- initial bus speed: 100 kHz;
- pull-ups: на PCB-MAIN к 3V3_DIGITAL; дублирующие pull-up footprints на PCB-PWR допускаются только DNP;
- firmware baseline: Current_LSB 200 uA/bit, CAL=2560, Power_LSB=5 mW/bit for 10 mOhm capture shunt;
- telemetry fields: battery_bus_voltage_V, battery_current_A, battery_power_W, monitor_status/calibration_valid.

INA226 `ALERT` может быть включён в агрегированный `FAULT` через корректную open-drain/logic схему, но `FAULT` не заменяет I2C. Потеря I2C считается диагностической неисправностью телеметрии.

## 4. I2C electrical rules

1. Bus 3.3 V only; level shifting между PCB-MAIN и PCB-PWR не требуется.
2. Для Rev.A ограничить bus speed 100 kHz до измерения rise/fall time на фактическом жгуте.
3. Pull-up source должен быть один авторитетный - PCB-MAIN. Номинал freeze после измерения общей ёмкости; стартовая расчётная зона 2.2-4.7 kOhm.
4. Предусмотреть 22-47 Ohm series-damping footprints у master side для SCL/SDA, старт DNP/0 Ohm по SI review.
5. SCL/SDA вести вдали от 3V8_MODEM switching/burst current conductors; в жгуте держать рядом с GND_DIGITAL и минимизировать петлю.
6. Проверка на финальной длине жгута обязательна при -40 C, +70 C и LTE burst.

## 5. EVT verification

Минимальный набор:
- continuity всех 12 pins и защита от перепутывания;
- отсутствие просадки 3V8/3V3/1V8 из-за контактов жгута;
- I2C enumeration INA226 at 0x40;
- сравнение напряжения с эталонным DMM;
- сравнение тока минимум в точках 0.05 A, 0.2 A, 1 A, 3 A и в representative LTE burst;
- расчёт мощности и проверка знака/масштаба;
- I2C rise/fall time и NACK/error counter на 100 kHz;
- fault injection: disconnect SCL, disconnect SDA, monitor reset/power loss;
- 72 h run с контролем расхождения накопленной энергии по INA226 и эталонному измерителю.

## 6. Propagation requirement

Этот freeze обязан быть отражён в schematic/PCB обеих плат, BOM, harness drawing, firmware HAL/driver, telemetry schema, Android diagnostics и EVT report forms. Любой документ с 10-pin MAIN/PWR interface после этого решения считается stale и подлежит исправлению до Review A.
