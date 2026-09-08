# Версионирование протоколов EVT-PRE-20

Статус: `DRAFT / OPEN`

Чтобы исключить прежнюю неоднозначность, используются независимые версии:

| Объект | Текущая версия | Значение |
|---|---:|---|
| Station-server interface release | 1.4 | Совместимость набора transport/API/decoder |
| MQTT namespace | v1 | Первый сегмент topic `zs/v1/...` |
| Detection compact CBOR `schema_ver` | 3 | Значение ключа 0 внутри detection payload |
| Message type detection | 2 | Значение ключа 1 внутри compact CBOR |
| LoRa regional profile | v0.1 | Отдельно RU868 и EU868; пока TX disabled |
| BLE GATT | v0.1 | Черновой сервис конфигурации/OTA |

Названия `protocol v1.3` в комментариях старого compact-CBOR кода обозначают историческую редакцию payload и не меняют фактический `schema_ver=3`. Серверный `/api/v1/health` корректно сообщает interface release `1.4`.

Изменение wire field, семантики, единицы измерения или обязательности поля требует новой версии payload. Изменение MQTT topic или поведения сессии требует новой interface release. Версия документа не заменяет эти номера.

