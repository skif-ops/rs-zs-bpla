# ICD BLE v0.2 — заморозка интерфейса станция ↔ приложение установщика (2026‑09‑23)

Статус: `FROZEN 2026-09-23 / STM32 + nRF52840 + ANDROID IMPLEMENTED ON THE HOST / HARDWARE CONFIRMATIONS LISTED IN §8`.

v0.2 объединяет ICD v0.1 и дополнения B (UUID, кадрирование, характеристики) и C (межпроцессорный протокол
STM32U585 ↔ nRF52840) в один зафиксированный интерфейс. Тексты дополнений остаются нормативными; этот документ
перечисляет, что заморожено, что зарезервировано и что подтверждается только на железе. Изменение любого
замороженного элемента = v0.3 с записью в журнале изменений (§9) и обновлением `PROTOCOL_VERSIONING.md`.

## 1. Роль и доступ (без изменений относительно v0.1 §1–2)

BLE — только рядом со станцией: commissioning, диагностика, обновление nRF‑моста. Сервисный режим (S4) —
TAMPER_IN ≥ 5 с, окно рекламы 600 с, связывание LESC по секрету этикетки, бондинга нет (сопряжение на каждый
сеанс). Все решения — на STM32 (`zs_ipc_service`), nRF52840 — прозрачный мост (C.1).

## 2. GATT (заморожено: addendum B.1, B.2, B.3)

База UUID `d10eXXXX-5a53-4c55-b0a1-000000000000`.

| id16 | характеристика | свойства | формат | статус |
|---|---|---|---|---|
| 0x0101 | identity | read (без сопряжения) | CBOR B.4 (6 ключей) | заморожено |
| 0x0201 | config_read | read, notify (authenticated) | CBOR 14 ключей, `STATION_CONFIG_CBOR_v0_1.md` §5 | заморожено |
| 0x0202 | config_write | write, notify (authenticated) | CBOR‑патч 11 ключей §3; ответ — статус B.3 | заморожено |
| 0x0203 | installation_position | read/write/notify (authenticated) | CBOR B.6 (запись 14 ключей, read‑back 16) | заморожено |
| 0x0204 | position_trust_policy | read/write/notify (authenticated) | входит в 0x0203 (ключи 10–14); отдельная характеристика зарезервирована | зарезервировано |
| 0x0205 | session_role | read/write/notify (authenticated) | B.9: `[role]`; `01` челлендж → `01‖nonce16`; `02‖tag16` → `03‖role` | заморожено |
| 0x0301 | status | read, notify | CBOR — формат v0.3 | зарезервировано |
| 0x0302 | gnss_integrity | read, notify | CBOR — формат v0.3 (поля по v0.1 §3.3) | зарезервировано |
| 0x0303 | self_test | write, notify | запись `01`; ответ — CBOR `{id: [code, detail]}` (`zs_selftest_encode`) | заморожено |
| 0x0401 | log_chunk | notify | формат v0.3 | зарезервировано |
| 0x0501–0x0503 | OTA STM32 manifest / image_chunk / control | — | формат и подпись — после crypto review (v0.1 §4) | зарезервировано |

Кадрирование длинных значений — B.2 (`[seq][flags][total_len BE16]…`, MTU 247 → 240/242 байт данных, MTU 23 → 16/18).
Статусы записи — B.3 (0x00 OK … 0x05 storage) + 0x06 position locked (B.6). Один WRITE_STATUS на запись; для
`self_test` ответ — отчёт по notify.

## 3. Данные (заморожено)

- **identity** — B.4: serial, station_id, hardware_revision, firmware_version, bootloader_version, region.
- **Конфигурация сервера** — `STATION_CONFIG_CBOR_v0_1.md` целиком: 14 ключей, правила патча, канонический хэш
  `ZS-STATION-CONFIG-V1` (281 байт), read‑back с обязательной сверкой хэша. Открытый вопрос §6 о фрагментации закрыт
  кадрированием B.2.
- **Позиция установки и политика доверия** — B.6 + v0.1 §3.1–3.2: канонический хэш `ZS-INSTALLATION-V1` (58 байт),
  INITIAL/RECOMMISSION, lock, аудит intent → commit, `audit_committed` в read‑back. Умолчания политики 25/75/250 м,
  3/10 фиксов; изменение — только роль engineer.
- **Самотест** — CBOR `{id: [code, detail]}`, коды и идентификаторы `zs_selftest.h`.

## 4. Связывание и роли (заморожено: B.7, B.9)

- passkey = BE32(SHA‑256("DIO‑PAIR‑V1" ‖ secret16)[0..3]) mod 10⁶; вектор `020559`. Секрет — из этикетки
  (`STATION_LABEL_QR_v0_1.md`), на станцию — `PAIRING_SECRET_SET` (C.3).
- installer — по защищённому линку в S4; engineer — HMAC‑челлендж ключом инженера станции: `tag16 =
  HMAC‑SHA256(engineer_key, "DIO‑ROLE‑V1" ‖ serial ‖ nonce16)[0..15]`, вектор `e3f70cf47e0a591490b501d6ba31be7b`;
  nonce одноразовый, 3 ошибки — блокировка до конца линка, роль умирает с линком. Ключ — `muhoed-pki engineer-key`,
  на этикетке отсутствует.

## 5. Межпроцессорный протокол STM32 ↔ nRF52840 (заморожено: C.1–C.5)

COBS‑кадр `[type][seq][payload…][crc16 BE]`, CRC‑16/CCITT‑FALSE, payload ≤ 4099 байт; сообщения 0x01/0x02 PING/PONG
(версия 1), 0x10 LINK_STATE, 0x11 SERVICE_WINDOW, 0x12 IDENTITY_SET, 0x13 PAIRING_SECRET_SET, 0x20 CHAR_WRITE,
0x21 WRITE_STATUS, 0x22 READ_VALUE, 0x23 NOTIFY, 0x24 READ_REQUEST. Кэш чтения моста — 7 слотов × 1024 байта
(identity, config_read, installation_position, policy, session_role, status, gnss_integrity). USART3 115200 8N1,
BLE_EN PE6, BLE_DFU_REQ PB2.

## 6. Обновление nRF52840 (заморожено: C.6)

MCUboot serial recovery по IPC UART, вход по проводу (BLE_EN + BLE_DFU_REQ), STM32 — клиент mcumgr SMP
(`image upload` по 384 байта, `os reset`), образ из слота NOR (`ZSNRFIMG`, 512 КиБ @0x03F7C000), подпись ECDSA P‑256
ключом `nrf-boot.key.pem`, самоподтверждение образа после первого IDENTITY_SET. Доставка образа nRF на станцию — по
OTA STM32 (§2, зарезервировано); на стенде — `nrfimg`/`nrfupd`.

## 7. Что реализовано и чем проверено

| часть | код | проверка |
|---|---|---|
| STM32 | `zs_ipc_service`, `zs_station_config`, `zs_installation_commissioning`, `zs_selftest`, `zs_mcumgr_serial`, `zs_nor_image_store` | `test_ble_bridge.c` (сквозной клиент ↔ мост ↔ сервис, MTU 247/23, роль B.9), `test_station_config.c`, `test_installation_commissioning.c`, `test_mcumgr_serial.c`, `test_nor_image_store.c` |
| nRF52840 | `zs_ble_bridge`, `firmware/targets/nrf52840_ble` (Zephyr, плата `evt_pre_20_ble`, MCUboot sysbuild) | хост‑тест моста; сборка NCS — приёмка партии |
| Android | `core/ble/*`, `core/scan/*`, `core/position/*`, `core/role/*`, `security/EngineerKeyStore`, `ServerActivity`, `InstallationActivity`, `StationPickerActivity` | JUnit с эмулятором станции (общие векторы B.4/B.6/B.7/B.9, CRC этикетки) |
| PKI | `muhoed-pki label-qr / server-qr / engineer-key / nrf-boot-key` | `test_pki_labels.py`, `test_pki_engineer_key.py` |

Android реализует диалог «Инженер» (B.9) с 2026‑09‑23: `core/role/EngineerKey` (импорт экспорта реестра
`<serial>.engineer-key.json`, тег по вектору), `core/role/SessionRoleController` (челлендж → nonce → `02‖tag16` →
`03‖02`; коды 03/04, блокировка после трёх ошибок), ключ на телефоне запечатан AES‑GCM ключом Android Keystore
(`security/EngineerKeyStore`, один файл на серийник, наружу не выдаётся); роль экрана установки берётся со станции,
локального переключателя роли больше нет. Формат не изменился.

## 8. Подтверждается только на железе (не меняет формат)

1. Раскладка рекламного пакета (B.5): UUID 0x0100 + local name = серийник; при нехватке 31 байта — сокращённое имя.
2. UX системного диалога сопряжения Android с passkey из этикетки (B.7); резерв — HMAC‑сверка секрета на уровне
   приложения (новая характеристика в v0.3).
3. Тайм‑аут окна 600 с и TAMPER_IN как сервисный триггер.
4. `nrfupd` на Rev.A с реальным MCUboot; тайм‑ауты SMP.
5. Время окна конвейера на M33 не относится к интерфейсу.

## 9. Журнал изменений v0.1 → v0.2

- добавлены 0x0205 session_role (B.9) и 0x0303 self_test; 0x0204 переведён в резерв (политика внутри 0x0203);
- зафиксированы UUID, кадрирование, статусы, CBOR‑форматы identity/config/installation, passkey и роли;
- межпроцессорный протокол C.1–C.6 включён в интерфейс как нормативная часть;
- OTA STM32 по BLE, status/gnss_integrity/log — зарезервированы до v0.3 (формат не определён, код не пишет).

Ссылки: `BLE_GATT_OTA_ICD_v0_1.md` (роль, доступ, требования §3.1–3.3, gate), `…_ADDENDUM_B_UUID_FRAMING.md`,
`…_ADDENDUM_C_IPC_STM32_NRF.md`, `STATION_CONFIG_CBOR_v0_1.md`, `STATION_LABEL_QR_v0_1.md`, `MQTT_TLS_ICD_v0_1.md` +
addendum A (идентичность пилота, tenant), `PROTOCOL_VERSIONING.md`.
