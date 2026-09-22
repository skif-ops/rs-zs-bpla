# ICD BLE v0.1 — Addendum C: межпроцессорный протокол STM32U585 ↔ nRF52840

Статус: `IMPLEMENTED 2026-09-22 — portable core + host tests (firmware/tests/test_ble_bridge.c) + STM32 app task;
nRF52840 application (Zephyr) — следующий шаг`.

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
