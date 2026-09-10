# ICD BLE configuration and OTA v0.1

Статус: `DRAFT / OPEN / NOT IMPLEMENTED`

## 1. Роль BLE

BLE используется только рядом со станцией для commissioning, диагностики и обновления. Основные события по BLE не передаются. Android-приложение должно работать без Google Play Services и без интернет-соединения.

Для EVT-PRE-20 BLE также является единственным штатным каналом локальной записи доверенных координат установки. Wi-Fi для commissioning/позиционирования не требуется.

## 2. Доступ

- сервисный режим открывается физической кнопкой не менее 5 секунд;
- окно advertising ограничено 10 минутами;
- первичное связывание использует уникальный QR/секрет изделия и BLE Secure Connections;
- после commissioning разрешены только ранее авторизованные устройства или новый физический сервисный цикл;
- изменение installation coordinates требует нового физического service mode и авторизованной роли;
- заводской секрет, OTA signing key и private keys не входят в APK и GitHub.

## 3. GATT services

| Service | Characteristic | Свойство | Назначение |
|---|---|---|---|
| Device Info | identity | read | serial, HW rev, FW rev, region, station_id |
| Configuration | config_read | read/notify | версия и безопасные параметры |
| Configuration | config_write | authenticated write | CBOR patch с validation |
| Configuration | installation_position | authenticated read/write | lat_e7, lon_e7, alt_dm, accuracy_m, source, version, lock |
| Configuration | position_trust_policy | authenticated read/write | warning/suspect/gross-jump thresholds и persistence |
| Diagnostics | status | read/notify | питание, GNSS, modem, LoRa, storage, faults |
| Diagnostics | gnss_integrity | read/notify | observed GNSS, delta от installation coordinates, jam/spoof, position/time trust, PPS/holdover |
| Logs | log_chunk | authenticated notify | ограниченный журнал без секретов |
| OTA | manifest | authenticated write | version, size, SHA-256, signature metadata |
| OTA | image_chunk | authenticated write without response | resumable firmware chunks |
| OTA | control | write/notify | start, resume, verify, install, rollback status |

UUID, MTU, chunk size и flow control замораживаются после совместного Android/firmware prototype.

### 3.1 installation_position

Логический CBOR объект:
- `lat_e7: int32`;
- `lon_e7: int32`;
- `alt_dm: int32`;
- `accuracy_m: uint16`;
- `source: enum {manual, phone_location, station_gnss_snapshot, surveyed}`;
- `version: uint32`;
- `locked: bool`.

Правила:
- запись разрешена только в физическом service mode;
- первая запись выполняется атомарно;
- Android обязан выполнить read-back и проверить version/hash;
- после lock обычная запись отклоняется;
- изменение locked coordinates возможно только как отдельная re-commission operation с audit event;
- удалённая команда через MQTT/HTTPS не имеет права изменять это поле в EVT-PRE-20.

### 3.2 position_trust_policy

Начальные defaults:
- warning distance 25 m;
- suspect distance 75 m;
- gross jump 250 m;
- warning persistence 3 valid fixes;
- suspect persistence 10 valid fixes.

Приложение показывает значения, но обычный оператор не редактирует их. Изменение policy относится к инженерной роли и фиксируется в audit.

### 3.3 gnss_integrity

Read/notify объект содержит:
- current GNSS coordinates and reported accuracy;
- configured installation coordinates version;
- horizontal delta;
- fix type, satellites, HDOP;
- receiver jamming state;
- receiver spoof detector state;
- `position_trust`;
- `time_trust`;
- PPS valid / expected time error;
- holdover active;
- movement/revalidation state.

Отсутствие spoof indication не трактуется как доказательство отсутствия spoofing; приложение отображает это как detector state, а не как абсолютный статус безопасности.

## 4. OTA

1. Android проверяет совместимость manifest с hardware revision.
2. Станция проверяет anti-rollback counter, размер и доступное место.
3. Передача допускает resume по offset и chunk hash.
4. После получения станция проверяет SHA-256 и цифровую подпись доверенным product root.
5. Образ записывается в неактивный A/B slot.
6. Bootloader запускает trial image и требует health confirmation.
7. При потере питания, watchdog или отсутствии confirmation выполняется rollback.

Алгоритм подписи и формат manifest получают статус `LOCKED` только после crypto review. До этого OTA release запрещён.

## 5. Gate

Требуются Android compatibility, неправильный QR, повторная попытка, обрыв на каждом этапе, неверный hash/signature, downgrade, неподходящая HW rev, потеря питания, resume, rollback, factory recovery через USB-C и журналирование результата.

Дополнительно для position commissioning:
- valid manual coordinates;
- phone location без GMS;
- station GNSS snapshot;
- invalid coordinate rejection;
- atomic write/read-back/hash;
- lock and power-cycle retention;
- rejected write outside physical service mode;
- authorized re-commission with audit;
- live GNSS drift/jam/spoof display;
- effective station position remains configured while GNSS drifts.
