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

T5838 pin 2 `SELECT` напрямую соединяется с GND на каждом leaf. Это фиксирует right-channel timing для всех четырёх одинаковых плат. Каждый микрофон имеет отдельную PDM data line, поэтому L/R multiplexing не используется.

## 3. MAIN-side AAD_CFG

- STM32 source: `PA15`, LQFP100 physical pin 77, GPIO output.
- `AAD_CFG` приходит на U7 pin 16 `B6` и переводится на pin 8 `A6` как физический net `AAD_CFG_1V8`.
- `PDM_CLK` приходит на U7 pin 17 `B5` и переводится на pin 7 `A5` как физический net `PDM_CLK_1V8`.
- `PDM_DATA1_1V8`..`PDM_DATA4_1V8` приходят на U7 pins 3..6 `A1..A4` и переводятся на pins 21..18 `B1..B4` как MCU nets `PDM_DATA1`..`PDM_DATA4`.
- Для группы U7 pins A1..A4/B1..B4 pin 2 `DIR1` напрямую соединён с `1V8_MIC`, поэтому направление фиксировано A-to-B.
- Для группы U7 pins A5..A8/B5..B8 pin 11 `DIR2` напрямую соединён с GND, поэтому направление фиксировано B-to-A.
- Один 1.8 V `AAD_CFG` fanout идет на pin 6 всех четырёх MIC-разъёмов.
- Все четыре микрофона получают одинаковую AAD-конфигурацию синхронно. Это соответствует одинаковому MPN/геометрии и упрощает детерминированность wake policy.
- Если EVT покажет необходимость индивидуальных порогов, это будет Rev.B change; для EVT-PRE-20 Rev.A индивидуальные THSEL-линии не закладываются.

## 4. MAIN-side WAKE

- `MIC_WAKE1..4` приходят отдельно с pin 5 четырёх MIC-разъёмов.
- Каждый вход имеет 100 kOhm pull-down к GND и отдельную Review A test point, поэтому отключённый жгут соответствует неактивному LOW.
- U17 `SN74LVC32APWR` питается от `1V8_MIC`. Pins 1/2/3 объединяют `MIC_WAKE1/2`, pins 4/5/6 объединяют `MIC_WAKE3/4`, pins 9/10/8 формируют итоговый `MIC_WAKE_OR_1V8`.
- Неиспользуемые U17 inputs pins 12/13 напрямую соединены с GND, output pin 11 оставлен NC.
- U18 `SN74AXC1T45DRLR` использует pin 1 VCCA=`1V8_MIC`, pin 6 VCCB=`3V3_DIGITAL`, pin 5 DIR=`1V8_MIC`, pin 3 A=`MIC_WAKE_OR_1V8`, pin 4 B=`MIC_WAKE`.
- MCU-side `MIC_WAKE` имеет 100 kOhm pull-down к GND, чтобы PA8 оставался LOW при high-Z U18.
- STM32 input: `PA8`, LQFP100 physical pin 67, EXTI/wakeup candidate.
- Индивидуальные wake-линии сохраняются до U17 как test points, чтобы на EVT можно было проверить каждый канал отдельно.

## 5. Low-power sequence

1. При commissioning/boot firmware подает необходимые one-wire write sequence через `AAD_CFG/THSEL`.
2. Firmware подтверждает корректную активацию AAD по предусмотренной последовательности/WAKE behavior и записывает конфигурацию/версию.
3. В S0 для AAD A или AAD D2 `PDM_CLK` и `AAD_CFG` удерживаются в LOW, но `1V8_MIC` остаётся включенным.
4. U7 остаётся включённым при фиксированном `OE=LOW`. Внутренние weak pull-downs на data I/O и статические LOW на MCU-side inputs не создают clock или THSEL transitions; гарантированный U7 static current включается в S0 budget.
5. T5838 AAD обнаруживает акустическое событие и поднимает соответствующий `MIC_WAKEn`.
6. PA8 будит STM32.
7. STM32 переводит аудиотракт в рабочий режим и запускает полный PDM capture/feature pipeline.
8. После обработки и guard-time станция возвращается в AAD listen.

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
- exact 44-pin U7/U17/U18 authority passes both `tools/audit_pcb_main_capture_authority_rev_a.py` and `tools/verify_pcb_main_audio_logic_authority_rev_a.py`;
- U7 `DIR1=HIGH`, `DIR2=LOW`, and `OE=LOW` verified so `PDM_CLK` and `AAD_CFG` are MCU-to-1.8 V while four `PDM_DATA` are 1.8 V-to-MCU;
- no external pull-up or pull-down is fitted to any PDM DATA line; T5838 tri-state intervals and U7 internal 288 kOhm typical weak pull-down behavior are checked on the final harness;
- THSEL fanout edge/rise-time and one-wire write timing checked on four connected leaf boards;
- AAD configuration verified after cold boot, brownout and mic-rail power cycle;
- each WAKE channel verified independently, with an open connector, through both U17 OR stages, U18, and aggregate PA8;
- AAD current and wake latency measured at −40, room and +70 °C;
- false wake rate evaluated on negative acoustic set and field noise.

Точная pin-level authority: `hardware/PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv`. Электрическое обоснование и datasheet hashes: `hardware/PCB_MAIN_AUDIO_LOGIC_AUTHORITY_REV_A.md`.
