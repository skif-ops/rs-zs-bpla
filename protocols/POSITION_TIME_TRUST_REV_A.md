# EVT-PRE-20 Rev.A — доверенные координаты установки и GNSS integrity

Статус: `LOCKED ARCHITECTURE / PORTABLE STORE IMPLEMENTED / FLASH+BLE BINDING OPEN`

Основание: `DEC-018`.

## 1. Основной принцип

EVT-PRE-20 является стационарной системой. После commissioning физические координаты станции не должны автоматически изменяться вслед за текущим решением GNSS.

Для каждой станции сохраняется `installation_position`:
- latitude в `lat_e7`;
- longitude в `lon_e7`;
- высота MSL в `alt_dm`;
- оценка точности ввода `accuracy_m`;
- источник координат: `manual`, `phone_location`, `station_gnss_snapshot` или `surveyed`;
- версия конфигурации;
- флаг блокировки;
- commissioning record/hash и audit metadata.

После успешного commissioning именно `installation_position` является авторитетной позицией станции для сервера, межстанционной геометрии и TDOA.

Wi-Fi/BSSID geolocation для EVT-PRE-20 не требуется. Wi-Fi не обеспечивает необходимую точность геометрии и не является источником высокоточного времени.

## 2. Роль GNSS после commissioning

GNSS используется для:
1. PPS/time synchronization при доверенном состоянии времени;
2. контроля текущего GNSS position относительно `installation_position`;
3. мониторинга spoofing/jamming flags приёмника;
4. диагностики количества спутников, HDOP, reported accuracy и RF integrity;
5. обнаружения возможного реального перемещения станции совместно с акселерометром/tamper.

Текущее GNSS position после commissioning не заменяет `installation_position` автоматически.

## 3. Position trust states

- `UNCONFIGURED`: доверенные координаты ещё не заданы; изделие не получает статус FIELD_READY.
- `CONFIGURED_OK`: GNSS согласуется с установленными координатами.
- `CONFIGURED_WARN`: устойчивое превышение warning threshold.
- `CONFIGURED_SUSPECT`: spoof detector или устойчивое превышение suspect threshold / gross jump.
- `REVALIDATION_REQUIRED`: станция физически перемещалась или координаты были изменены в service mode.

Начальные EVT-PRE-20 thresholds:
- warning distance: 25 m;
- suspect distance: 75 m;
- gross single-fix jump: 250 m;
- warning persistence: 3 valid fixes;
- suspect persistence: 10 valid fixes.

Для учёта обычной ошибки GNSS эффективный warning threshold должен быть не меньше `max(25 m, 3 × reported horizontal accuracy)`, suspect threshold — не меньше `max(75 m, 5 × reported horizontal accuracy)`.

Spoofing indication приёмника переводит position trust в `CONFIGURED_SUSPECT` без ожидания distance persistence. Jamming отдельно фиксируется как RF-integrity fault и учитывается вместе с потерей/деградацией fix.

## 4. Effective station position

Если `installation_position.locked == true`, во всех detection/heartbeat данных поле `station` содержит сконфигурированные координаты установки.

GNSS observed position передаётся только как diagnostic/integrity information и не используется сервером для изменения station geometry.

Если станция ещё не commissioned, GNSS position может отображаться в service UI, но такое изделие не допускается к полевому режиму и полноценной TDOA геометрии.

## 5. Time trust отдельно от position trust

Фиксированные координаты не защищают от подмены GNSS времени.

Отдельно поддерживаются состояния:
- `GNSS_TIME_TRUSTED`;
- `HOLDOVER`;
- `GNSS_TIME_SUSPECT`;
- `UNSYNCED`.

При GNSS spoof/jam, необъяснимом скачке времени или PPS integrity fault:
- GNSS PPS не считается автоматически доверенным;
- станция переходит в holdover на SiT1552 32.768 kHz, если предыдущая дисциплина времени была валидна;
- продолжительность, в течение которой holdover допустим для TDOA, определяется только измеренной на EVT стабильностью, а не теоретической оценкой;
- после исчерпания подтверждённого holdover interval TDOA помечается degraded/invalid, при этом акустическое обнаружение и классификация продолжают работать.

## 6. Android commissioning workflow

Приложение должно работать без Google Play Services.

Шаги:
1. Вход в физический service mode станции.
2. BLE Secure Connections + проверка QR/serial.
3. Экран `Координаты установки`.
4. Выбор источника:
   - ручной ввод;
   - координаты телефона через Android framework location API;
   - текущий GNSS fix станции;
   - геодезические/заранее известные координаты.
5. Отображение latitude, longitude, altitude, accuracy/source и текущего расхождения с GNSS станции.
6. Явное подтверждение оператора с отображением serial станции.
7. Атомарная запись `installation_position` и `position_trust_policy` по authenticated BLE.
8. Read-back и сравнение version/hash.
9. Lock coordinates.
10. Экспорт commissioning record с serial, координатами, источником, точностью, временем, версиями HW/FW/app и hash конфигурации.

Повторное изменение координат допускается только после нового физического service mode и авторизованной роли. Оно создаёт отдельную audit запись и переводит станцию в `REVALIDATION_REQUIRED` до завершения self-test.

### 6.1 Атомарное хранение на станции

Portable firmware сохраняет запись в двух чередующихся слотах по 96 байт. Новая
версия сначала записывается в стёртый неактивный слот с generation и CRC32, а
commit-marker записывается последней операцией. После записи выполняются полный
read-back, CRC и сравнение полей. При сбое питания до commit-marker предыдущий
слот остаётся авторитетным.

Первая запись и recommission разрешены только при одновременно активном
физическом service mode и подтверждённой локальной роли. Для locked-записи
recommission должен быть указан явно, а `version` обязан монотонно увеличиваться.
Нулевой commissioning hash и невалидные координаты/thresholds отклоняются до
операции erase.

CRC не заменяет BLE Secure Connections, авторизацию роли или commissioning
hash. Текущий модуль задаёт переносимый формат и power-loss-safe алгоритм;
STM32 Flash binding, адреса страниц, endurance и fault-injection на целевой плате
остаются открытыми до target port и аппаратного EVT.

## 7. BLE configuration objects

### installation_position
- `lat_e7: int32`
- `lon_e7: int32`
- `alt_dm: int32`
- `accuracy_m: uint16`
- `source: enum`
- `version: uint32`
- `locked: bool`

### position_trust_policy
- `warning_distance_m: uint16` default 25
- `suspect_distance_m: uint16` default 75
- `gross_jump_distance_m: uint16` default 250
- `warning_consecutive_fixes: uint8` default 3
- `suspect_consecutive_fixes: uint8` default 10

### gnss_integrity_status
Read/notify diagnostic object:
- observed GNSS coordinates;
- horizontal accuracy;
- distance from configured position;
- fix type / satellites / HDOP;
- receiver spoof state;
- receiver jamming/interference state;
- position trust state;
- time trust state;
- PPS state / expected time error;
- station movement/revalidation flag.

## 8. Server/Mukhoyed rules

- station registry stores authoritative configured coordinates independently of incoming GNSS observations;
- incoming `station` position is checked against registry and may not silently overwrite it;
- TDOA/fusion uses configured installation coordinates;
- mismatch, spoof, jam and time-integrity states are persisted as diagnostics/security events;
- server UI shows both `Установлено` and `GNSS сейчас`, plus delta when observed GNSS telemetry is available;
- any remote coordinate-change command is rejected for EVT-PRE-20; coordinate change is local commissioning only.

## 9. EVT tests

Mandatory:
- manual coordinate commissioning + read-back;
- commissioning from phone location without GMS;
- commissioning from station GNSS snapshot;
- reject invalid latitude/longitude/altitude/accuracy;
- power cycle retains locked coordinates;
- GNSS offset 10 m: no alert;
- sustained offset > warning threshold: WARN but configured position remains effective;
- sustained offset > suspect threshold: SUSPECT and configured position remains effective;
- gross jump > 250 m: immediate suspect;
- injected receiver spoof flag: immediate suspect;
- jamming/loss of fix: RF integrity fault without station-position drift;
- physical movement detected by accelerometer/tamper: REVALIDATION_REQUIRED;
- attempt remote coordinate modification: rejected;
- coordinate modification in authorized physical service mode: audit record required;
- GNSS time jump/spoof: independent TIME_SUSPECT/HOLDOVER behavior;
- TDOA uses installation coordinates under simulated GNSS drift.

## 10. Release gate

FIELD_READY is prohibited unless installation coordinates are present, validated, read back, locked and included in commissioning record.
