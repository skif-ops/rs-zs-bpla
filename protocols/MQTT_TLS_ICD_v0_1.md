# ICD GSM/LTE - MQTT/TLS и HTTPS fallback v0.1

Статус: `DRAFT / OPEN / NOT RUN`
Interface release: `1.5`
Detection schema: `4`

## 1. Сетевая модель

Станция всегда инициирует исходящее соединение. Обычная SIM и публичный APN допустимы; работа за CGNAT обязательна. Статический IP, входящий порт и API оператора не требуются.

## 2. MQTT

| Topic | Направление | QoS | Retain | Payload | Статус реализации |
|---|---|---:|---:|---|---|
| `zs/v1/{tenant}/{station_id}/up` | station -> server | 1 | false | detection compact CBOR | EXISTS |
| `zs/v1/{tenant}/{station_id}/status` | station -> server | 1 | false | compact heartbeat CBOR schema 1 | HOST_END_TO_END_IMPLEMENTED; HARDWARE_PENDING |
| `zs/v1/{tenant}/{station_id}/down` | server -> station | 1 | false | signed command envelope | FIRMWARE_CODEC_IMPLEMENTED; TARGET_CRYPTO_AND_MODEM_BINDING_PENDING |
| `zs/v1/{tenant}/{station_id}/ack` | station -> server | 1 | false | command result | FIRMWARE_CODEC_IMPLEMENTED; TARGET_CRYPTO_AND_MODEM_BINDING_PENDING |

Client ID: `dioneya-{station_id}-{boot_id}`. Clean start запрещён после provisioning; session expiry и keepalive замораживаются после 24-часового теста сети. Повторная доставка QoS 1 ожидаема, дедупликация выполняется по `event_id`, а для команд по `command_id`.

`tenant` is a 1..32 character identifier limited to ASCII letters, digits,
underscore and hyphen, starting with a letter or digit. MQTT wildcard or path
characters are rejected before connection. `station_id` is canonical decimal
uint32 in topics; zero, signs, leading zeroes and overflow are rejected.

### 2.1 Signed command envelope schema 1

`down` uses deterministic canonical CBOR. Ed25519 signs the canonical encoding
of keys 0..8; key 9 carries the resulting 64-byte signature. The complete
envelope is limited to 2048 bytes. The server does not publish commands unless
an explicit signing key is loaded.

| Key | Field | Encoding |
|---:|---|---|
| 0 | schema version | uint, currently 1 |
| 1 | message type | uint, command = 4 |
| 2 | station_id | uint32 |
| 3 | command_id | UUID as 16 bytes |
| 4 | created_time_us | uint64 |
| 5 | expires_time_us | uint64; maximum and default server TTL is 15 minutes |
| 6 | command code | uint; `CMD_REQUEST_AUDIO` = 1 |
| 7 | command payload | CBOR map |
| 8 | signing key ID | first 8 bytes of SHA-256 over the raw Ed25519 public key |
| 9 | signature | 64-byte Ed25519 signature over canonical keys 0..8 |

`CMD_REQUEST_AUDIO` key 7 is a four-entry numeric map:

| Sub-key | Field | Encoding |
|---:|---|---|
| 0 | event_id | uint64, nonzero |
| 1 | segment | 0 pre, 1 post, 2 both, 3 range |
| 2 | start_offset_ms | signed int32 for range, otherwise null |
| 3 | duration_ms | positive uint32 for range, otherwise null |

The portable station codec rejects an unknown/rejected key ID, invalid
signature callback result, non-canonical encoding, wrong `station_id`, duplicate
`command_id`, expired validity interval, unsupported command code or malformed
payload before any side effect. It reconstructs the exact canonical keys 0..8
in caller-owned fixed memory and wipes that workspace after verification. A
deterministic server-generated Ed25519 vector locks the byte boundary in CI.
The portable trust adapter supports a bounded rotation set of four public keys,
derives each key ID from the raw key, rejects duplicates, zero keys, disabled-only
sets and unknown IDs, and delegates the actual signature operation to a required
backend. Production key provisioning, a reviewed target Ed25519 backend and the
BG95 MQTT subscription/receive binding remain open until the target receiver is
integrated and tested.

Execution is allowed only inside `[created_time_us, expires_time_us)`. A station
without sufficiently trusted time must reject the remote command rather than
bypass this validity interval.

### 2.2 Command ACK schema 1

`ack` is canonical CBOR limited to 128 bytes. Its authenticity and station
identity come from MQTT mutual TLS plus the per-station broker ACL. The bridge
requires equality between the topic station ID, payload station ID and command
owner in SQLite. Repeated ACK of the same command is idempotent.

| Key | Field | Encoding |
|---:|---|---|
| 0 | schema version | uint, currently 1 |
| 1 | message type | uint, ACK = 5 |
| 2 | station_id | uint32 |
| 3 | command_id | UUID as 16 bytes |
| 4 | result_code | 0 OK, 1 REJECTED, 2 FAILED, 3 EXPIRED |
| 5 | completed_time_us | uint64 |
| 6 | detail_code | uint16, 0 when absent |

Broker receipt is not an application ACK. The server persists a command and
retries it after the configured interval until a valid application ACK arrives
or the TTL expires. `retain` is always false. For inbound QoS 1 messages the
bridge uses manual MQTT acknowledgement: valid input is acknowledged only after
processing and durable storage, malformed input is acknowledged and discarded
to avoid a poison-message loop, while a transient processing/storage failure is
left unacknowledged for broker redelivery.

Firmware treats a successful decode as eligibility, not completion. The portable
journal atomically records `ACCEPTED` before an idempotent side effect and appends
`COMPLETED` before allowing ACK encoding. An interrupted completion leaves the
accepted record recoverable; restart must resume the idempotent operation keyed
by `command_id`. A completed duplicate reuses the durable result without repeating
the side effect. Reuse of a UUID with different signed command semantics is a
fail-closed conflict. Target Flash page allocation and endurance validation remain
open.

## 3. Detection compact CBOR

| Key | Назначение |
|---:|---|
| 0 | `schema_ver`, сейчас 4 |
| 1 | message type, detection = 2 |
| 2 | station_id |
| 3 | seq_no |
| 4 | boot_id |
| 5 | event_id |
| 6 | event_time_us |
| 7 | GNSS/security flags |
| 8 | position, GNSS, classification, detector profile, sample rate |
| 9 | 43 float16 features, только full packet |
| 10 | power and route status; INA226 extension described below |
| 11 | DOA block, только full packet |
| 12 | hierarchical classification |
| 13 | single-station estimate |
| 14 | 3+1 spatial block, `geometry_id=1` |

### 3.1 Key 10 power/route sub-map

Keys 0..8 remain compatible with schema 3:

| Sub-key | Field | Presence |
|---:|---|---|
| 0 | battery_pct | summary + full |
| 1 | battery_mv | summary + full; for Rev.A source shall be the measured/validated battery bus value when INA226 is healthy |
| 2 | solar_mv | summary + full |
| 3 | temperature_c10 | summary + full |
| 4 | transport | summary + full |
| 5 | hop_count | summary + full |
| 6 | rssi_dbm | summary + full |
| 7 | snr_db10 | summary + full |
| 8 | gateway_id | summary + full |
| 9 | battery_bus_mv | full only, INA226 |
| 10 | battery_current_ma | full only, signed, INA226 |
| 11 | battery_power_mw | full only, INA226 |
| 12 | power_monitor_status | full only; 0 means valid, nonzero is firmware monitor/error bitmask |

The INA226 extension is deliberately excluded from P0 summary so the LoRa worst-case limit is not increased. Current and power are delivered through LTE/full packet and shall also be included in the station heartbeat implementation.

P0 summary должен оставаться не более 220 bytes до LoRa framing. Full packet size is monitored in CI and is not a LoRa payload contract.

## 3.2 Compact heartbeat CBOR schema 1

Heartbeat предназначен только для LTE/NB-IoT/2G транспорта и не включается в
LoRa/P0. Верхний map использует message type `3` и следующие ключи:

| Key | Назначение |
|---:|---|
| 0 | heartbeat schema, сейчас 1 |
| 1 | message type, heartbeat = 3 |
| 2 | station_id |
| 3 | time_us |
| 4 | configured station position |
| 5 | GNSS/time trust status |
| 6 | full INA226 power status |
| 7 | route status |
| 8 | firmware version |
| 9 | model version |
| 10 | hardware revision |
| 11 | self-test result |
| 12 | protected cellular telemetry |

Cellular sub-map key 12:

| Sub-key | Field | Требование |
|---:|---|---|
| 0 | full IMSI | 14..16 decimal digits; required |
| 1 | full ICCID | 18..22 decimal digits; required |
| 2 | home PLMN | approved 5/6-digit prefix or empty for legacy explicit APN |
| 3 | registered operator | diagnostic |
| 4 | active APN | required |
| 5 | local address and subnet | required |
| 6 | gateway | required |
| 7 | primary DNS | required |
| 8 | secondary DNS | optional |
| 9 | access technology | modem numeric AcT |
| 10 | APN source | 1 explicit, 2 network, 3 controlled catalog |
| 11 | settings valid | must be true |

Полные IMSI/ICCID разрешены только в `status` через MQTT с взаимным TLS. Plain
HTTP heartbeat с cellular block и insecure-bench MQTT status с cellular block
отклоняются. Сервер хранит полные значения во внутренней записи станции, но
общий station-list API возвращает только маскированные идентификаторы. Raw modem
lines и validation payload с IMSI/ICCID запрещено выводить в открытые логи.

## 4. TLS и идентификация

- TLS 1.2 minimum, TLS 1.3 preferred;
- уникальная credential на каждую станцию;
- ключ станции не экспортируется после provisioning;
- broker ACL ограничивает station_id и разрешённые topics;
- CA, certificate и key обязательны. Запуск production bridge без CA запрещён;
- сертификат сервера проверяется по hostname и доверенному CA;
- ротация credential выполняется через подписанную команду или сервисный BLE/USB режим.

Текущий `mqtt_bridge.py` запускается в производственном режиме только при наличии
CA, клиентского сертификата и ключа. Явный `--insecure-bench` допускается только
для изолированного стенда и отклоняет heartbeat с cellular identity. До полевого
развёртывания остаются обязательными provisioning уникальных credentials и
проверка broker ACL для каждого `station_id`.

Для `down` требуется отдельный Ed25519 private key в unencrypted PKCS#8 PEM.
Его отсутствие безопасно отключает публикацию команд, не понижая transport до
unsigned режима. Файл не хранится в Git; raw 32-byte public key provisioned на
станции отдельным контролируемым процессом. Ротация использует новый key ID и
период явного доверия к старому и новому public key.

## 5. HTTPS fallback

Основной endpoint detection: `POST /api/v1/stations/{station_id}/detection.cbor`. Команды текущего сервера доступны через HTTP polling, но до добавления взаимной аутентификации этот путь допускается только в изолированном стенде. Internet-facing deployment запрещён.

## 6. Store-and-forward

Запись содержит `station_id`, `boot_id`, `seq_no`, `event_id`, timestamp, payload, priority, retry_count и SHA-256. Станция подтверждает удаление только после application ACK. Повторная передача того же `event_id` не создаёт второе событие.

## 7. Gate

После сборки станций требуются modem log с маскированием IMSI/ICCID, broker log,
packet capture без идентификаторов/секретов, 24 часа MQTT, потеря сети/питания,
CGNAT, DNS failure, certificate failure, повторная доставка, 20 одновременных
станций и store-and-forward recovery. Для Rev.A дополнительно требуется проверка
end-to-end декодирования INA226 и cellular heartbeat, а также отсутствие роста
P0 summary выше 220 bytes. До сборки эти аппаратные пункты имеют статус
`DEFERRED_UNTIL_STATIONS_ASSEMBLED`, а не PASS.
