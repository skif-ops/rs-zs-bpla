# Android commissioning app - архитектура v0.1

Статус: `DRAFT / SOURCE BASELINE STARTED / BLE NOT IMPLEMENTED`

## Модули

| Модуль | Ответственность |
|---|---|
| `app` | навигация, роли, lifecycle, разрешения |
| `ble` | scan, connect, GATT, retry, MTU/flow control |
| `protocol` | CBOR models, schema validation, version negotiation |
| `security` | QR bootstrap, trust store, package hash/signature verification |
| `configuration` | form validation, diff, atomic apply, read-back |
| `location` | manual/phone/station-GNSS coordinate capture, validation, distance display; Android framework only, no GMS dependency |
| `position_trust` | installation position lock, trust-policy presentation, GNSS drift/spoof/jam/time-integrity status |
| `ota` | package import, compatibility check, resume, progress, result |
| `diagnostics` | health snapshot, guided checks, redacted export |
| `storage` | encrypted local records without station private keys |

Реализация: Kotlin, Android framework BLE and location APIs, без обязательных Google libraries. Toolchain зафиксирован в `TOOLCHAIN.md`. Первый baseline содержит state machine, identity/config/installation-position validation и OTA preflight; BLE transport и cryptographic signature verifier остаются fail-closed до freeze ICD.

## Поток commissioning

1. Монтажник физически переводит станцию в service mode.
2. Приложение сканирует QR с serial и одноразовым bootstrap secret.
3. BLE scan допускает только устройство с ожидаемым serial/service UUID.
4. Выполняется authenticated pairing и чтение identity.
5. Приложение сравнивает serial, HW revision, current FW, region и station_id с QR/заданием.
6. Монтажник вводит APN, endpoint и несекретные параметры.
7. Конфигурация проходит локальную schema validation, записывается атомарно и считывается обратно.
8. Обязательный экран `Координаты установки`: manual, phone location через Android framework, station GNSS snapshot или surveyed coordinates.
9. Приложение показывает вводимые координаты, declared accuracy/source, текущий station GNSS и расстояние между ними.
10. После явного подтверждения с serial приложение атомарно записывает `installation_position` + `position_trust_policy`, выполняет read-back/version/hash и lock.
11. Станция выполняет self-test cellular/GNSS/PPS/position-trust/storage/power; приложение показывает фактический результат.
12. Только после успешной проверки разрешается `FIELD_READY`.
13. Формируется commissioning record без паролей, IMSI, полного ICCID и private keys; запись содержит координаты установки, source, accuracy, version/hash и факт lock.

Изменение locked installation coordinates требует нового физического service mode, авторизованной роли, новой версии конфигурации и audit record. Удалённая смена координат через сервер для EVT-PRE-20 не поддерживается.

## GNSS integrity UI

Экран диагностики показывает отдельно:
- `Установленные координаты` — авторитетные для геометрии/TDOA;
- `GNSS сейчас` — диагностические;
- расстояние между ними;
- fix/satellites/HDOP/reported accuracy;
- receiver jam/spoof state;
- position trust: OK/WARN/SUSPECT/REVALIDATION_REQUIRED;
- time trust: GNSS_TIME_TRUSTED/HOLDOVER/GNSS_TIME_SUSPECT/UNSYNCED;
- PPS state и expected time error.

Даже при GNSS drift приложение не предлагает автоматически заменить installation coordinates.

## Поток OTA

Приложение получает firmware bundle через файловый выбор или MDM, проверяет manifest, аппаратную ревизию, anti-rollback counter, SHA-256 и подпись. Оно только доставляет уже подписанный образ и не имеет права создавать подпись.

Передача идёт chunked/resumable через BLE GATT. После verify станция пишет неактивный A/B slot, перезагружается, подтверждает health или откатывается. Приложение сохраняет только результат, версию, hash и время.

## Состояния соединения

`IDLE -> SCANNING -> CONNECTING -> AUTHENTICATING -> READY -> CONFIGURING -> POSITIONING -> POSITION_VERIFYING -> DIAGNOSTICS -> FIELD_READY`.

Из `READY/FIELD_READY` отдельно доступны OTA и повторная диагностика по разрешённым переходам state machine.

Каждый переход имеет timeout, cancel и безопасное повторение. Потеря Bluetooth не должна оставлять конфигурацию или installation coordinates частично применёнными либо образ активированным без проверки.
