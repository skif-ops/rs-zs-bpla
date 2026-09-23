# ICD BLE v0.1 — Addendum C: межпроцессорный протокол STM32U585 ↔ nRF52840

Статус: `IMPLEMENTED 2026-09-22 — portable core + host tests (firmware/tests/test_ble_bridge.c) + STM32 app task +
nRF52840 application (Zephyr, firmware/targets/nrf52840_ble, плата evt_pre_20_ble); C.6 — MCUboot recovery path (sysbuild) + STM32 mcumgr client (zs_mcumgr_serial) + NOR image slot (zs_nor_image_store) + console `nrfimg`/`nrfupd` (tools/nrf_image_push.py); bench run on Rev.A pending`.

## C.1 Роли

nRF52840 — прозрачный мост GATT ↔ UART без собственной логики: собирает BLE‑кадры записи (B.2) в целые
значения, отдаёт чтения из кэша, превращает статусы/уведомления STM32 в кадрированные notify, включает
рекламу по команде. Все решения (сервисный режим, роли, валидация, хранение, аудит) — на STM32U585
(`zs_ipc_service`). Плата: USART3 PB10/PB11 (AF7), 115200 8N1, BLE_EN PE6 (active‑HIGH), BLE_DFU_REQ PB2.

## C.2 Кадр канала

```
COBS( [type:1][seq:1][payload…][crc16 BE] ) + 0x00
```
CRC‑16/CCITT‑FALSE по `type..payload` (то же семейство, что у этикетки). `seq` — счётчик отправителя (диагностика).
Максимальный payload — 4096 + 3 байта (одно GATT‑значение + идентификатор). Приёмник сбрасывает кадр при
ошибке CRC/COBS и ресинхронизируется по следующему нулю; между кадрами допустимы нули.

## C.3 Сообщения

| type | направление | payload | назначение |
|---|---|---|---|
| 0x01 PING / 0x02 PONG | любое | `[version]` | проверка канала, версия протокола 1 |
| 0x10 LINK_STATE | nRF → STM | `[state]` 0 нет связи, 1 подключён, 2 защищён (LESC) | при смене состояния; STM в ответ пушит кэши |
| 0x11 SERVICE_WINDOW | STM → nRF | `[open][seconds BE16]` | реклама вкл/выкл (открывается с S4 SERVICE, 600 с) |
| 0x12 IDENTITY_SET | STM → nRF | ASCII local name | серийник в рекламе (B.5) |
| 0x13 PAIRING_SECRET_SET | STM → nRF | 16 байт | секрет этикетки для OOB/passkey (способ — на прототипе) |
| 0x20 CHAR_WRITE | nRF → STM | `[char_id BE16][value…]` | целое значение после сборки кадров B.2 |
| 0x21 WRITE_STATUS | STM → nRF | `[char_id BE16][status]` | нотификация статуса (B.3/B.6) одним кадром |
| 0x22 READ_VALUE | STM → nRF | `[char_id BE16][value…]` | кэш для чтения (identity, config_read, installation_position, …) |
| 0x23 NOTIFY | STM → nRF | `[char_id BE16][value…]` | кадрированная нотификация (отчёт self_test) |
| 0x24 READ_REQUEST | nRF → STM | `[char_id BE16]` | промах кэша: чтение завершается ошибкой ATT, STM пушит READ_VALUE |

`char_id` — 16‑битный идентификатор из базы `d10eXXXX-…` (B.1).

## C.4 Семантика на STM32 (`zs_ipc_service`)

- `LINK_STATE ≠ 0` → push `identity` (B.4), `config_read` (если конфигурация сохранена), `installation_position`
  (B.6; пустая карта `0xa0`, если записи нет).
- `CHAR_WRITE config_write` → ворота: сервисный режим (0x03), защищённый пир (0x04) → `zs_station_config_apply_patch`
  (0x01/0x02) → `zs_station_config_store_commit` (0x05) → перечитать → push `config_read` → статус 0x00.
- `CHAR_WRITE installation_position` → декод B.6 (0x01) → `zs_installation_commissioning_apply` с аудитом
  (0x06 locked, 0x02 версия, 0x03/0x04/0x05) → push read‑back с `audit_committed` → 0x00.
- `CHAR_WRITE self_test` `0x01` → `zs_selftest_run_all` → `NOTIFY self_test` с CBOR‑отчётом.
- Ответ на каждую запись — ровно один WRITE_STATUS (кроме self_test, где ответ — отчёт).

## C.5 Семантика на nRF52840 (`zs_ble_bridge`)

- Кэш чтения: 6 слотов × 1024 байта; каждое ATT‑чтение выдаёт следующий кадр, после LAST следующее чтение
  начинается с кадра 0; смена подключения сбрасывает курсоры и незавершённую запись.
- Запись: одна активная сборка; смена характеристики или ошибка кадра сбрасывает её (ATT‑ошибка записи).
- Нотификации: split по текущему `MTU − 3`; если подписки нет — счётчик `dropped_notifications`.
- Проверка: `firmware/tests/test_ble_bridge.c` гоняет Android‑подобного клиента через мост, канал и сервис на
  реальных модулях станции (config store, commissioning + audit, selftest) при MTU 247 и 23.

## C.6 Обновление прошивки nRF52840 (MCUboot serial recovery по IPC UART)

Мост не имеет собственного канала обновления: образ nRF приходит на станцию по штатному OTA STM32 и
загружается в модуль через тот же UART, что и IPC.

1. STM32 держит новый образ nRF в слоте NOR (карта B3: 128 блоков @0x03F7C000, `zs_nor_image_store`: заголовок с
   SHA‑256 пишется после сверки записанного). На стенде образ загружается по консоли: `tools/nrf_image_push.py COM7
   zephyr.signed.bin --version N [--update]` → `nrfimg begin/put/end`; образ подписан ключом `nrf-boot.key.pem` из PKI
   (`muhoed-pki nrf-boot-key`, ECDSA P‑256; публичный ключ вшит в MCUboot модуля). Штатный путь доставки — OTA STM32.
2. Вход в recovery — только по проводу (pin authority): `BLE_EN` ↓ (nRESET удерживается) → `BLE_DFU_REQ` ↓ (P0.15,
   open‑drain, active LOW) → 20 мс → `BLE_EN` ↑ → MCUboot стартует, видит LOW на P0.15 (`CONFIG_BOOT_SERIAL_ENTRANCE_GPIO`,
   задержка обнаружения 50 мс) и остаётся в serial recovery на `uart0` → через 500 мс STM32 отпускает `BLE_DFU_REQ`
   (`bledfu` в консоли B1). Без запроса MCUboot проверяет подпись `slot0` и запускает приложение.
3. В recovery STM32 — клиент mcumgr SMP по UART: `firmware/src/zs_mcumgr_serial.c` (кадры «06 09»/«04 14» + base64 +
   CRC‑16/XMODEM, строки ≤ 127 байт; SMP‑заголовок 8 байт; `image upload` частями по 384 байта в пакетах ≤ 512 байт с
   `len`/`sha` в первом запросе, ответ `{rc, off}` — клиент продолжает с `off`, который сообщил модуль, потерянный или
   искажённый ответ просто ведёт к повтору; затем `os reset`). Хост‑тест `firmware/tests/test_mcumgr_serial.c` гоняет
   клиента против имитации `boot_serial` (образ 64 КиБ за 171 запрос, потерянный и искажённый ответы, сброс).
   MCUboot помечает загруженный образ pending, `image test/confirm` не нужен. На стенде всё это — команда `nrfupd`
   (`app_nrf_update.c`, задача ble): вход в recovery, выгрузка из слота с тайм‑аутом 2 с и 5 повторами, `os reset`,
   переинициализация IPC; прогресс по 10 % в консоль.
4. MCUboot (swap‑using‑move) переносит образ в `slot0` и запускает его в режиме «test». Приложение подтверждает себя
   (`boot_write_img_confirmed`) только после первого `IDENTITY_SET` от STM32 — то есть когда IPC реально работает.
   Образ, который не заговорил с STM32, откатывается MCUboot при следующем сбросе (STM32 делает сброс по `BLE_EN`, если
   мост «silent» дольше тайм‑аута).
5. Карта флеша: MCUboot 48 KiB @0 | primary 472 KiB @0xC000 | secondary 472 KiB @0x82000 | settings 32 KiB @0xF8000
   (`pm_static.yml` = `fixed-partitions` платы).

Версия протокола IPC (`PING`/`PONG`) — первый признак несовместимости после обновления: STM32 показывает её в `ble`.
