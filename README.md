# РС ЗС-БПЛА - рабочий пакет разработки v0.3

Рабочий пакет создан поверх переданного исходного ПО `drone_acoustic_intelligence-2026-06-30` и согласованных ТЗ/ПМИ/протокола/архитектуры РС ЗС-БПЛА.

## Статус v0.3

- исходные алгоритмы `audio`, `classification`, `ml`, `localization` сохранены и покрыты регрессионными тестами;
- server: 36 pytest tests PASS;
- firmware core/drivers: CMake/GCC host build PASS, CTest 2/2 PASS, `-Wall -Wextra -Wpedantic` без warnings;
- реальный C encoder firmware -> compact CBOR -> Python server decoder: PASS, контрольный пакет 212 байт;
- 100 golden vectors: 1,0 с, 32 кГц, PCM16LE mono, 43 эталонных признака;
- EVT pin/peripheral map STM32U585ZIT6Q зафиксирован на уровне pre-CAD Design Freeze;
- BG95 UART 1,8 В и требование V_CELL >=2,7 A для 2G учтены;
- T5838 питается от V_MIC_1V8 и рассматривается как источник low-power AAD wake;
- RU868: штатный список каналов не использует центральную частоту 869,000 МГц;
- сервис MVP: Android only;
- химия АКБ не фиксирована - выбор по измеренной энергии при низкой температуре, габаритам и пиковому току.

## Каталоги

- `server/` - модифицированный сервер "Мухоед": station ingress, compact CBOR, fusion, TDOA/DOA, Kalman, SQLite WAL, WebSocket, MQTT bridge, Docker dev deployment.
- `firmware/` - MCU-independent C core, protocol/CBOR, LoRa state machine, PPS timebase, classifier и target contract STM32U585.
- `server/tools/golden/` - 100 golden vectors для переноса 43 признаков на MCU.
- `rkd/` - ТЗ/ПМИ/архитектура как входы и рабочая РКД v0.1-v0.2.

## Проверка server

```bash
cd server
python -m pytest -q
```

Ожидаемый результат v0.3: `36 passed`.

## Проверка firmware core

```bash
cd firmware
cmake -S . -B build
cmake --build build -j
ctest --test-dir build --output-on-failure
```

## End-to-end firmware packet -> server

После сборки firmware:

```bash
cd server
python tools/test_firmware_packet.py
```

Ожидается сообщение `firmware -> server compact CBOR OK`.

## Golden vectors

`server/tools/golden/manifest.json` описывает формат. Входы находятся в `pcm16le/`, эталоны - `vectors.csv`, порядок признаков - `feature_order.txt`.

Критерий переноса на MCU:
- median normalized error <=3%;
- p95 normalized error <=5%;
- для F0/harmonic признаков вводятся отдельные абсолютные допуски.

## Pre-CAD hardware baseline

- MCU: STM32U585ZIT6Q, LQFP144;
- cellular: Quectel BG95-M3;
- LoRa: SX1262;
- GNSS timing: u-blox MAX-M10S + TIMEPULSE;
- audio: 4 x TDK T5838;
- BLE: nRF52832-class module;
- external storage: 512 Mbit / 64 MB serial NOR;
- temperature: TMP117;
- motion/tamper: LIS2DW12 + Hall/reed;
- solar charger architecture: configurable chemistry class, final АКБ selected by test.

## Что ещё НЕ закрыто

- нативная принципиальная схема/PCB/Gerber в KiCad ещё не выпущены: v0.3 фиксирует pin map и electrical constraints для ввода схемы;
- измеренный CPU/RAM профиль на реальном STM32U585 ещё не закрыт;
- отсутствует исходная FP-1 аудиозапись, на которую ссылается исторический `features.csv`, поэтому полное воспроизведение обучения модели из raw archive невозможно;
- Android service application ещё не включено в пакет;
- окончательный аккумулятор и RF TX profile закрываются испытаниями.

## GitHub workflow

- `main` - стабильные принятые снимки.
- `develop` - интеграционная ветка текущей разработки.
- `feature/*` - отдельные изменения hardware/firmware/server.
- `.github/workflows/ci.yml` запускает CMake/CTest, Python pytest и firmware-CBOR-to-server contract test.

Большие raw WAV и golden PCM не хранятся в обычной Git history. Их следует вести через release artifacts / Git LFS / отдельное защищённое хранилище данных.
