# ICD BLE v0.1 — Addendum B (proposal): UUID, MTU, framing, config/self-test characteristics

Статус: `PROPOSAL 2026-09-22 / ANDROID SIDE IMPLEMENTED (core + BluetoothGatt binding) / STM32 SIDE IMPLEMENTED (zs_ipc_service, addendum C) / NRF52840 APP WRITTEN (Zephyr, firmware/targets/nrf52840_ble, not built in CI)`.
Заморозка — после совместного прототипа Android/прошивка (ICD §3). Это предложение реализовано в Android
(`core/ble/GattContractV01.kt`, `core/ble/LongValueFraming.kt`, `core/ble/BleSession.kt`,
`ble/AndroidBleTransport.kt`, экран `ui/ServerActivity.kt`) и проверено юнит‑тестами с эмулированной станцией.

## B.1 UUID

Одна 128‑битная база, 16‑битный идентификатор в позиции XXXX: `d10eXXXX-5a53-4c55-b0a1-000000000000`.

| id16 | Объект | Свойства | Содержимое |
|---|---|---|---|
| 0x0100 | Service Device Info | | |
| 0x0101 | identity | read | serial, HW rev, FW rev, region, station_id (CBOR) |
| 0x0200 | Service Configuration | | |
| 0x0201 | config_read | read, notify | read‑back станции: CBOR 14 ключей (`STATION_CONFIG_CBOR_v0_1.md`), кадрированный |
| 0x0202 | config_write | authenticated write, notify | CBOR‑патч 11 ключей, кадрированный; ответ — 1 байт статуса по notify |
| 0x0203 | installation_position | authenticated read/write | ICD §3.1 |
| 0x0204 | position_trust_policy | authenticated read/write | ICD §3.2 |
| 0x0300 | Service Diagnostics | | |
| 0x0301 | status | read, notify | питание, GNSS, modem, LoRa, storage, faults |
| 0x0302 | gnss_integrity | read, notify | ICD §3 |
| 0x0303 | self_test *(новое)* | write, notify | запись `0x01` = выполнить все; ответ — CBOR‑отчёт `zs_selftest_encode` `{id: [code, detail]}`, кадрированный |
| 0x0400 | Service Logs | | |
| 0x0401 | log_chunk | authenticated notify | |
| 0x0500 | Service OTA | | |
| 0x0501 / 0x0502 / 0x0503 | manifest / image_chunk / control | ICD §3 | |

CCCD стандартный `0x2902`.

## B.2 MTU и кадрирование длинных значений

Android запрашивает ATT MTU 247 (полезная нагрузка ATT = MTU − 3 = 244 байта); при отказе работает от 23.
Значения длиннее одного пакета передаются кадрами (запись — write with response по кадру, чтение — повторные
read до кадра LAST, notify — по кадру):

```
[seq:1][flags:1][total_len:2 BE — только в первом кадре][data…]
seq   — счётчик кадров 0..255 с переполнением, приёмник требует последовательность
flags — bit0 FIRST, bit1 LAST (одиночное значение несёт оба)
total_len ≤ 4096; любое нарушение (пропуск seq, переполнение, неверная длина) сбрасывает приём
```
При MTU 247 первый кадр несёт 240 байт данных, последующие — 242.

## B.3 Статус config_write (первый байт notify)

| код | значение |
|---|---|
| 0x00 | OK — патч сохранён, можно читать `config_read` |
| 0x01 | отклонён валидацией (`zs_station_config_apply_patch`) |
| 0x02 | версия не новее текущей |
| 0x03 | станция не в сервисном режиме |
| 0x04 | пир не авторизован (роль/пара) |
| 0x05 | ошибка хранения |

Android после `0x00` обязательно выполняет read‑back `config_read`, декодирует 14 ключей и сравнивает
станционный хеш с `StationConfigPatch.stationHash()` намерения; расхождение отображается как
«не подтверждено» (экран `ServerActivity`, состояние `MISMATCH`).

## B.4 identity (0x0101)

Каноническая CBOR‑карта, ключи по возрастанию; Android — `core/scan/IdentityCodec.kt`:

| ключ | тип | поле |
|---|---|---|
| 1 | text | serial (`DIO-EVT-001…040`, `DIO-EVT-B01`) |
| 2 | uint | station_id (1…40, стенд 901) |
| 3 | text | hardware_revision (`Rev.A`) |
| 4 | text | firmware_version |
| 5 | text | bootloader_version |
| 6 | uint | region: 1 = RU868, 2 = EU868 |

Приложение проверяет запись через `StationIdentity.validate()` (серийник пилотного состава, регион RU868)
и при заданном ожидаемом серийнике (этикетка/QR) отказывается продолжать при расхождении.

## B.5 Advertising (предложение)

Станция в сервисном окне рекламирует UUID сервиса Device Info (0x0100) и local name = серийник
(`DIO-EVT-012`); приложение принимает любой из двух признаков, поэтому итоговую раскладку рекламного
пакета (31 байт: 128‑битный UUID занимает 18) выбираем на прототипе nRF52840.

## B.6 installation_position (0x0203) — запись и read‑back

Каноническая CBOR‑карта, целые ключи, координаты — знаковые целые (major 0/1), флаги — bool.
Android: `core/position/InstallationPositionCodec.kt`; проверка по `InstallationCommissioningContract` (канонический
хеш `ZS-INSTALLATION-V1`, 58 байт).

Запись (телефон → станция), 14 ключей: 1 operation (0 INITIAL, 1 RECOMMISSION), 2 lat_e7, 3 lon_e7, 4 alt_dm,
5 accuracy_m, 6 source (0 manual, 1 phone, 2 station gnss, 3 surveyed), 7 version, 8 locked, 9 commissioned_time_us,
10 warning_m, 11 suspect_m, 12 gross_jump_m, 13 warning_fixes, 14 suspect_fixes. Ответ — байт статуса по notify
(B.3) плюс `0x06` = позиция заблокирована (INITIAL при существующей записи; нужна RECOMMISSION инженера).

Read‑back (станция → телефон): ключи 2…14 как выше плюс 15 storage_generation, 16 commissioning_hash (32 байта),
17 audit_committed (bool). Пустая карта `0xa0` — записи нет. Приложение сверяет позицию, политику, время,
поколение хранения, хеш и флаг аудита; любое расхождение — «не подтверждено».

## B.7 Связывание по секрету этикетки (предложение к прототипу)

LE Secure Connections, метод Passkey Entry с фиксированным ключом на стороне станции:

```
passkey = BE32( SHA-256( "DIO-PAIR-V1" || secret16 )[0..3] ) mod 1 000 000
```
`secret16` — 16 байт секрета этикетки (`K` в QR, base32). Известный ответ для секрета из вектора этикетки
(`JBSWY3DPEHPK3PXPJBSWY3DPEH`): дайджест начинается с `e6f81f0f`, passkey `020559` (тесты Android и nRF).

- STM32 передаёт секрет мосту сообщением `PAIRING_SECRET_SET` (addendum C) после провижининга; nRF
  вызывает `bt_passkey_set`.
- Все характеристики, кроме `identity`, требуют аутентифицированной связи (MITM): первый доступ к
  `config_read`/`config_write` вызывает системный диалог сопряжения на телефоне; приложение показывает
  код, вычисленный из отсканированной этикетки (`StationLabel.pairingPasskey()`). Без этикетки код неизвестен.
- Бондинг выключен (`CONFIG_BT_BONDABLE=n`): сопряжение на каждый сервисный сеанс; уровень безопасности
  ≥ L3 → `LINK_STATE = 2` → STM32 считает пира защищённым (`peer_secure`).
- Сверка секрета на уровне приложения (HMAC‑челлендж) остаётся вариантом на случай, если UX passkey не устроит.

## B.8 Что остаётся открытым до прототипа

- роль installer/engineer на стороне прошивки (B1: installer; выбор роли по сеансу — после прототипа);
- подтверждение B.7 на реальном UX Android‑диалога сопряжения; способ применения секрета зафиксировать в ICD v0.2;
- таймер сервисного окна и трактовка TAMPER_IN как сервисного триггера (решение 2026‑09‑21) — реализовано в B1
  (600 с с S4 SERVICE), подтвердить на железе;
- межпроцессорный протокол — реализован (addendum C), заморозить после прототипа;
- плата nRF52840 для Rev.A (U11 Raytac MDBT50Q-P1MV2, UARTE P0.06/P0.08, nRESET P0.18 от BLE_EN, BLE_DFU_REQ P0.15) —
  описана в `firmware/targets/nrf52840_ble/boards/dioneya/evt_pre_20_ble/`; MCUboot/DFU по BLE_DFU_REQ — отдельный шаг.
