# Дионея EVT-PRE-20 Rev.A — интерфейс T5838 AAD

Статус: `AUTHORITATIVE ELECTRICAL BASELINE / CUBEMX AND EVT PENDING`

## 1. Причина изменения

T5838 имеет два отдельных интерфейсных вывода для Acoustic Activity Detect:

- `WAKE` (pin 4) — выход события AAD;
- `THSEL` (pin 5) — однопроводный вход конфигурации/активации AAD.

Следовательно, сохранение только `WAKE` без управляемого `THSEL` не позволяет прошивке полноценно задавать и восстанавливать режим/порог AAD после power cycle. Rev.A поэтому использует оба сигнала.

## 2. MIC-leaf pinout

Каждый `PCB-MIC` имеет один T5838 и один 6-контактный разъём J1:

1. `1V8_MIC` -> T5838 pin 7 VDD;
2. `GND` -> T5838 pin 3 GND;
3. `PDM_CLK` -> T5838 pin 6 CLK;
4. `PDM_DATA` <- T5838 pin 1 DATA;
5. `MIC_WAKE` <- T5838 pin 4 WAKE;
6. `AAD_CFG` -> T5838 pin 5 THSEL.

T5838 pin 2 `SELECT` фиксируется локально на leaf в одном одинаковом состоянии для всех четырёх каналов, потому что каждый микрофон имеет отдельную PDM data line и не требует L/R multiplexing. Выбранное состояние фиксируется в схеме/assembly drawing до Review A.

## 3. MAIN-side AAD_CFG

- STM32 source: `PA15`, LQFP100 physical pin 77, GPIO output.
- `AAD_CFG` проходит через свободный канал MCU->1.8 V банка `SN74AXC8T245PWR` U7, того же направления, что и `PDM_CLK`.
- Один 1.8 V `AAD_CFG` fanout идет на pin 6 всех четырёх MIC-разъёмов.
- Все четыре микрофона получают одинаковую AAD-конфигурацию синхронно. Это соответствует одинаковому MPN/геометрии и упрощает детерминированность wake policy.
- Если EVT покажет необходимость индивидуальных порогов, это будет Rev.B change; для EVT-PRE-20 Rev.A индивидуальные THSEL-линии не закладываются.

## 4. MAIN-side WAKE

- `MIC_WAKE1..4` приходят отдельно с pin 5 четырёх MIC-разъёмов.
- Они объединяются в 1.8 V domain через U17 `SN74LVC32APWR`.
- Объединённый wake переводится через U18 `SN74AXC1T45DRLR` в 3.3 V.
- STM32 input: `PA8`, LQFP100 physical pin 67, EXTI/wakeup candidate.
- Индивидуальные wake-линии сохраняются до U17 как test points, чтобы на EVT можно было проверить каждый канал отдельно.

## 5. Low-power sequence

1. При commissioning/boot firmware подает необходимые one-wire write sequence через `AAD_CFG/THSEL`.
2. Firmware подтверждает корректную активацию AAD по предусмотренной последовательности/WAKE behavior и записывает конфигурацию/версию.
3. В S0 отключается полноценный PDM clock согласно выбранному AAD режиму, но `1V8_MIC` остаётся включенным.
4. T5838 AAD обнаруживает акустическое событие и поднимает соответствующий `MIC_WAKEn`.
5. PA8 будит STM32.
6. STM32 переводит аудиотракт в рабочий режим и запускает полный PDM capture/feature pipeline.
7. После обработки и guard-time станция возвращается в AAD listen.

Конкретный AAD mode (Analog/D1/D2), threshold, LPF/band settings и guard-time являются EVT tuning parameters и не должны быть зашиты в PCB.

## 6. Разъём Rev.A

Из-за необходимости `THSEL` физический MIC connector Rev.A имеет 6 контактов:

- Molex Pico-Lock board header `5040500691`;
- mating housing `5040510601`;
- terminal `5040520098` (24–28 AWG);
- operating range −40…+105 °C.

Ранее выбранные 5-contact `5040500591/5040510501` superseded и запрещены для Rev.A production output.

## 7. Verification gates

До выпуска PCB:

- exact PA15/pin77 checked against CubeMX for `STM32U585VITxQ`;
- U7 bank direction/OE mapping reviewed so `PDM_CLK` and `AAD_CFG` are MCU->1.8 V while four `PDM_DATA` are 1.8 V->MCU;
- THSEL fanout edge/rise-time and one-wire write timing checked on four connected leaf boards;
- AAD configuration verified after cold boot, brownout and mic-rail power cycle;
- each WAKE channel verified independently and through aggregate PA8;
- AAD current and wake latency measured at −40, room and +70 °C;
- false wake rate evaluated on negative acoustic set and field noise.
