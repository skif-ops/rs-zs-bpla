# ICD GSM/LTE - MQTT/TLS и HTTPS fallback v0.1

Статус: `DRAFT / OPEN / NOT RUN`  
Interface release: `1.4`  
Detection schema: `3`

## 1. Сетевая модель

Станция всегда инициирует исходящее соединение. Обычная SIM и публичный APN допустимы; работа за CGNAT обязательна. Статический IP, входящий порт и API оператора не требуются.

## 2. MQTT

| Topic | Направление | QoS | Retain | Payload | Статус реализации |
|---|---|---:|---:|---|---|
| `zs/v1/{tenant}/{station_id}/up` | station -> server | 1 | false | detection compact CBOR | EXISTS |
| `zs/v1/{tenant}/{station_id}/status` | station -> server | 1 | false | heartbeat CBOR | SERVER_DECODER_EXISTS; FIRMWARE_ENCODER_OPEN |
| `zs/v1/{tenant}/{station_id}/down` | server -> station | 1 | false | signed command envelope | MISSING_BLOCKER |
| `zs/v1/{tenant}/{station_id}/ack` | station -> server | 1 | false | command result | MISSING_BLOCKER |

Client ID: `dioneya-{station_id}-{boot_id}`. Clean start запрещён после provisioning; session expiry и keepalive замораживаются после 24-часового теста сети. Повторная доставка QoS 1 ожидаема, дедупликация выполняется по `event_id`, а для команд по `command_id`.

## 3. Detection compact CBOR

| Key | Назначение |
|---:|---|
| 0 | `schema_ver`, сейчас 3 |
| 1 | message type, detection = 2 |
| 2 | station_id |
| 3 | seq_no |
| 4 | boot_id |
| 5 | event_id |
| 6 | event_time_us |
| 7 | GNSS/security flags |
| 8 | position, GNSS, classification, detector profile, sample rate |
| 9 | 43 float16 features, только full packet |
| 10 | power and route status |
| 11 | DOA block, только full packet |
| 12 | hierarchical classification |
| 13 | single-station estimate |
| 14 | 3+1 spatial block, `geometry_id=1` |

P0 summary должен оставаться не более 220 bytes до LoRa framing. Full packet имеет release target не более 272 bytes, но gate закрывается только worst-case тестом в CI.

## 4. TLS и идентификация

- TLS 1.2 minimum, TLS 1.3 preferred;
- уникальная credential на каждую станцию;
- ключ станции не экспортируется после provisioning;
- broker ACL ограничивает station_id и разрешённые topics;
- CA, certificate и key обязательны. Запуск production bridge без CA запрещён;
- сертификат сервера проверяется по hostname и доверенному CA;
- ротация credential выполняется через подписанную команду или сервисный BLE/USB режим.

Текущий `mqtt_bridge.py` допускает работу без параметра CA и потому не готов к прямому размещению в интернете. Это `BLOCKER_SECURITY` для EVT deployment.

## 5. HTTPS fallback

Основной endpoint detection: `POST /api/v1/stations/{station_id}/detection.cbor`. Команды текущего сервера доступны через HTTP polling, но до добавления взаимной аутентификации этот путь допускается только в изолированном стенде. Internet-facing deployment запрещён.

## 6. Store-and-forward

Запись содержит `station_id`, `boot_id`, `seq_no`, `event_id`, timestamp, payload, priority, retry_count и SHA-256. Станция подтверждает удаление только после application ACK. Повторная передача того же `event_id` не создаёт второе событие.

## 7. Gate

Требуются modem log, broker log, packet capture без секретов, 24 часа MQTT, потеря сети/питания, CGNAT, DNS failure, certificate failure, повторная доставка, 20 одновременных станций и store-and-forward recovery.

