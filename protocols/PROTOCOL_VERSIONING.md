# Версионирование протоколов EVT-PRE-20

Статус: `DRAFT / OPEN`

Чтобы исключить прежнюю неоднозначность, используются независимые версии:

| Объект | Текущая версия | Значение |
|---|---:|---|
| Station-server interface release | 1.5 | Detection schema 4 и защищённый cellular heartbeat |
| MQTT namespace | v1 | Первый сегмент topic `zs/v1/...` |
| Detection compact CBOR `schema_ver` | 4 | Значение ключа 0 внутри detection payload |
| Message type detection | 2 | Значение ключа 1 внутри compact CBOR |
| Heartbeat compact CBOR schema | 1 | Полная LTE cellular telemetry через mTLS status topic |
| Message type heartbeat | 3 | Значение ключа 1 внутри compact heartbeat |
| LoRa regional profile | v0.1 | RU868 для всех 20 пилотных изделий; EU868 future template; TX disabled до RF gate |
| Cellular SIM/APN policy | v0.2 | Dual SIM Single Standby; только публичные APN и bounded failover между двумя SIM |
| BLE GATT | v0.3 | Заморожен 2026-09-24 (`BLE_GATT_OTA_ICD_v0_3.md`): v0.2 + 0x0206 station_secrets (патч/присутствие, политика «пустая станция — установщик, далее engineer», аудит); status/gnss/log/OTA STM32 зарезервированы до v0.4 |
| IPC STM32 ↔ nRF52840 | 1 | Версия в PING/PONG (addendum C.3) |

Названия `protocol v1.3` в комментариях старого compact-CBOR кода обозначают
историческую редакцию payload. Текущий detection использует `schema_ver=4`,
heartbeat использует собственную schema 1, а `/api/v1/health` сообщает interface
release `1.5`.

Изменение wire field, семантики, единицы измерения или обязательности поля требует новой версии payload. Изменение MQTT topic или поведения сессии требует новой interface release. Версия документа не заменяет эти номера.
