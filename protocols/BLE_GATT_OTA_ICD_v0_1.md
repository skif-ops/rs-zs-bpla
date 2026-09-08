# ICD BLE configuration and OTA v0.1

Статус: `DRAFT / OPEN / NOT IMPLEMENTED`

## 1. Роль BLE

BLE используется только рядом со станцией для commissioning, диагностики и обновления. Основные события по BLE не передаются. Android-приложение должно работать без Google Play Services и без интернет-соединения.

## 2. Доступ

- сервисный режим открывается физической кнопкой не менее 5 секунд;
- окно advertising ограничено 10 минутами;
- первичное связывание использует уникальный QR/секрет изделия и BLE Secure Connections;
- после commissioning разрешены только ранее авторизованные устройства или новый физический сервисный цикл;
- заводской секрет, OTA signing key и private keys не входят в APK и GitHub.

## 3. GATT services

| Service | Characteristic | Свойство | Назначение |
|---|---|---|---|
| Device Info | identity | read | serial, HW rev, FW rev, region, station_id |
| Configuration | config_read | read/notify | версия и безопасные параметры |
| Configuration | config_write | authenticated write | CBOR patch с validation |
| Diagnostics | status | read/notify | питание, GNSS, modem, LoRa, storage, faults |
| Logs | log_chunk | authenticated notify | ограниченный журнал без секретов |
| OTA | manifest | authenticated write | version, size, SHA-256, signature metadata |
| OTA | image_chunk | authenticated write without response | resumable firmware chunks |
| OTA | control | write/notify | start, resume, verify, install, rollback status |

UUID, MTU, chunk size и flow control замораживаются после совместного Android/firmware prototype.

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

