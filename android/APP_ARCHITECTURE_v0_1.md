# Android commissioning app - архитектура v0.1

Статус: `DRAFT / SOURCE NOT STARTED`

## Модули

| Модуль | Ответственность |
|---|---|
| `app` | навигация, роли, lifecycle, разрешения |
| `ble` | scan, connect, GATT, retry, MTU/flow control |
| `protocol` | CBOR models, schema validation, version negotiation |
| `security` | QR bootstrap, trust store, package hash/signature verification |
| `configuration` | form validation, diff, atomic apply, read-back |
| `ota` | package import, compatibility check, resume, progress, result |
| `diagnostics` | health snapshot, guided checks, redacted export |
| `storage` | encrypted local records without station private keys |

Реализация: Kotlin, Android framework BLE API, без обязательных Google libraries. UI toolkit и точные Gradle/SDK versions замораживаются перед началом source baseline.

## Поток commissioning

1. Монтажник физически переводит станцию в service mode.
2. Приложение сканирует QR с serial и одноразовым bootstrap secret.
3. BLE scan допускает только устройство с ожидаемым serial/service UUID.
4. Выполняется authenticated pairing и чтение identity.
5. Приложение сравнивает serial, HW revision, current FW, region и station_id с QR/заданием.
6. Монтажник вводит APN, endpoint и несекретные параметры.
7. Конфигурация проходит локальную schema validation, записывается атомарно и считывается обратно.
8. Станция выполняет self-test cellular/GNSS/storage/power; приложение показывает фактический результат.
9. Формируется подписываемый акт commissioning без паролей, IMSI, полного ICCID и private keys.

## Поток OTA

Приложение получает firmware bundle через файловый выбор или MDM, проверяет manifest, аппаратную ревизию, anti-rollback counter, SHA-256 и подпись. Оно только доставляет уже подписанный образ и не имеет права создавать подпись.

Передача идёт chunked/resumable через BLE GATT. После verify станция пишет неактивный A/B slot, перезагружается, подтверждает health или откатывается. Приложение сохраняет только результат, версию, hash и время.

## Состояния соединения

`IDLE -> SCANNING -> CONNECTING -> AUTHENTICATING -> READY -> CONFIGURING/DIAGNOSTICS/OTA -> VERIFYING -> REBOOT_WAIT -> CONFIRMED/ROLLED_BACK/FAILED`.

Каждый переход имеет timeout, cancel и безопасное повторение. Потеря Bluetooth не должна оставлять конфигурацию частично применённой или образ активированным без проверки.

