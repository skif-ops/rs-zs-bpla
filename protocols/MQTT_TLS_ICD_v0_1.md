# ICD GSM/LTE - MQTT/TLS и HTTPS fallback v0.1

Статус: `DRAFT / OPEN / NOT RUN`
Interface release: `1.5`
Detection schema: `4`

## 1. Сетевая модель

Станция всегда инициирует исходящее соединение. Обычная SIM и публичный APN допустимы; работа за CGNAT обязательна. Статический IP, входящий порт и API оператора не требуются.

## 2. MQTT

| Topic | Направление | QoS | Retain | Payload | Статус реализации |
|---|---|---:|---:|---|---|
| `zs/v1/{tenant}/{station_id}/up` | station -> server | 1 | false | detection compact CBOR | PORTABLE_BG95_SESSION_FIXED_LENGTH_QMTPUB_QG_PASS; TARGET_USART_DMA_AND_HARDWARE_PENDING |
| `zs/v1/{tenant}/{station_id}/status` | station -> server | 1 | false | compact heartbeat CBOR schema 1 / 2 (§3.2) | HOST_END_TO_END_IMPLEMENTED; HARDWARE_PENDING |
| `zs/v1/{tenant}/{station_id}/down` | server -> station | 1 | false | signed command envelope | PORTABLE_BG95_SESSION_FRAMED_SERIALIZED_QG_PASS; TARGET_CRYPTO_USART_DMA_RETAIN_POLICY_AND_HARDWARE_PENDING |
| `zs/v1/{tenant}/{station_id}/ack` | station -> server | 1 | false | command result | PORTABLE_BG95_SESSION_FRAMED_SERIALIZED_QG_PASS; TARGET_CRYPTO_USART_DMA_RETAIN_POLICY_AND_HARDWARE_PENDING |
| `zs/v1/{tenant}/{station_id}/receipt` | server -> station | 1 | false | event application receipt | PORTABLE_BG95_SESSION_LENGTH_DELIMITED_QMTRECV_QG_PASS; TARGET_USART_DMA_RETAIN_POLICY_AND_HARDWARE_PENDING |

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
backend. Production key provisioning, a reviewed target Ed25519 backend and
target USART/DMA/ISR integration remain open. The portable BG95
subscription/receive/ACK path has host evidence only and is not a production
crypto or assembled-station PASS.

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
fail-closed conflict. The portable NOR adapter maps every 88-byte journal slot to its own full
physical erase block, bounds all reads/programs to the logical record, and
reuses a torn uncommitted slot without erasing a neighbouring record. Restart
roundtrip, commit-write failure and partition guards pass host QG. The shared
layout/binding in section 6 keeps the command journal disjoint from
both audio archive and event outbox. Production exact slot count, OCTOSPI
binding and measured endurance remain target blockers.

The portable application channel enforces this order and emits no ACK for an
invalid envelope, transient executor failure or storage failure. It re-verifies
every broker redelivery, resumes an accepted idempotent operation, and returns a
stored ACK for a completed duplicate. Calls must be serialized by the target task.

The portable MQTT boundary consumes a complete binary publication as independent
`topic+length` and `payload+length` pairs. It accepts only the exact canonical
station `down` topic at QoS 1 with `retain=false`, so wrong-tenant, wrong-station,
leading-zero and trailing-NUL topic variants never reach command verification.
On durable completion it returns the exact station `ack` topic and binary CBOR
length at QoS 1 with `retain=false`.

The portable BG95 command binding requires the pre-`QMTOPEN` length-enabled
receive mode, then subscribes to the exact `down` topic with QoS 1. It parses a
complete `+QMTRECV` by explicit topic/payload bounds, so NUL, quote, CR/LF and
`0x1a` inside the signed CBOR do not terminate the command. Only after signature
verification, journal `ACCEPTED`, idempotent execution, journal `COMPLETED` and
durable ACK reconstruction does it issue
`AT+QMTPUB=<client>,<msgID>,1,0,"<ack-topic>",<ack-len>`, wait for `>` and write
exactly `<ack-len>` bytes without Ctrl+Z. Partial UART, timeout and mismatched
result paths invalidate the modem transport. A completed duplicate recreates
the same ACK without repeating execution.

The `+QMTRECV` URC exposes no retain flag, so command initialization requires
the same externally verified station credential, exact ACL, server-only
publisher and non-retained-route assertion described below.

The portable BG95 MQTT session is the sole caller of command, receipt and event
bindings. Its 2304-byte bounded framer consumes arbitrary raw UART chunks,
distinguishes line responses and data prompts, and reconstructs `QMTRECV` by the
declared payload length. One transaction owns MQTT transmit at a time: command
subscription, receipt subscription, event publish or command ACK. If a command
arrives while another transaction owns transmit, one complete frame is retained
in a bounded RAM slot; further frames are dropped with an explicit server-retry
counter. The server continues to republish until application ACK, and the
durable command journal prevents repeated side effects. Disconnect discards the
RAM slot and forces ordered resubscription. Target USART DMA/ISR wiring, buffer
cache ownership, selected-modem firmware, broker policy and hardware recovery
remain blockers; the portable session is not target evidence.

### 2.3 Event application receipt schema 1

`receipt` is canonical CBOR limited to 128 bytes. It is published only for a
schema-4 detection whose exact binary payload has completed server processing and
whose ingestion state is durable. Its authenticity and station scope come from
MQTT mutual TLS plus the per-station broker ACL; the receipt is not separately
signed. The station accepts only its exact canonical topic at QoS 1 with
`retain=false`.

| Key | Field | Encoding |
|---:|---|---|
| 0 | schema version | uint, currently 1 |
| 1 | message type | uint, receipt = 6 |
| 2 | station_id | uint32, nonzero |
| 3 | boot_id | uint32 |
| 4 | seq_no | uint32 |
| 5 | event_id | uint64, nonzero |
| 6 | payload_sha256 | byte string, exactly 32 bytes |

Before reclaiming an outbox slot, firmware verifies topic, QoS/retain, canonical
encoding, `station_id`, `boot_id`, `seq_no`, `event_id` and `payload_sha256`
against the still-pending item. An exact duplicate receipt is idempotent. A torn
delivered-marker write leaves the event pending for at-least-once retry.

The portable station MQTT adapter emits only the current priority/FIFO outbox
item on the exact canonical `up` topic. It persists the retry attempt before
exposing the binary payload to the modem layer; storage failure or retry
exhaustion therefore emits no publication. A broker PUBACK does not change the
outbox. A queued QoS-1 receipt can locate and close its exact durable slot after
a station restart, without volatile in-flight state.

The BG95 uplink uses fixed-length data mode
`AT+QMTPUB=<client>,<msgID>,1,0,"<topic>",<msglen>`. Only after the `>` prompt
does firmware write exactly `<msglen>` binary bytes; no Ctrl+Z delimiter is used,
so embedded NUL, quote or `0x1a` values remain payload. Partial UART writes,
timeouts, offline transitions and malformed or mismatched `+QMTPUB` results
fail closed and preserve the durable event. A successful `+QMTPUB` remains a
broker ACK, not the application receipt defined above.

Before `QMTOPEN`, the portable BG95 connection state machine configures direct
delivery with an explicit payload byte count using
`AT+QMTCFG="recv/mode",<client>,0,1`. After `QMTCONN`, the receipt path refuses
to subscribe unless that pre-connect step completed, then requests the exact station receipt topic with
`AT+QMTSUB=<client>,<msgID>,"<receipt-topic>",1`. Subscription completes only
after the matching successful `+QMTSUB` result grants QoS 1. The receiver parses
one complete `+QMTRECV: <client>,<msgID>,"<topic>",<payload_len>,"<payload>"`
frame by bounds and `<payload_len>`, so embedded NUL, quote, CR/LF and `0x1a`
are not delimiters. Because the granted maximum QoS is 1, message ID zero is
treated as QoS 0 and rejected; a nonzero ID is passed as QoS 1.

BG95 `+QMTRECV` does not report the MQTT retain flag. The portable binding may
therefore assert `retain=false` only when target integration has independently
verified the station credential, exact per-station ACL, server-only publisher
and broker rule forbidding retained receipt publication. The API requires that
external assertion at initialization. This is a documented residual boundary,
not an inferred modem property; selected-firmware URC behavior, USART DMA wiring
and broker policy still require assembled-station evidence.

The server stores the exact payload hash and processing state before publishing
the receipt. A byte-identical broker redelivery after processing skips fusion
side effects and republishes the same receipt. Reuse of an `event_id` with
different metadata or payload hash is acknowledged and discarded without a
receipt, preventing a poison-message loop. If receipt publication cannot be
queued, the inbound MQTT message is not broker-ACKed and is eligible for retry.
Server process state and MQTT callbacks must remain serialized per deployment;
multi-worker receipt processing requires an equivalent transactional claim.

The deterministic server-generated receipt vector is checked by both Python and
C tests. Fixed-length BG95 event publication, length-delimited receipt parsing
and their single-owner raw-UART session have portable host evidence. Target USART
DMA/ISR integration,
selected-modem-firmware framing, retain-policy verification and target outbox
storage are still release blockers; portable host evidence is not
assembled-station evidence.

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

## 3.2 Compact heartbeat CBOR schema 1 / 2

Heartbeat предназначен только для LTE/NB-IoT/2G транспорта и не включается в
LoRa/P0. Верхний map использует message type `3` и следующие ключи (schema 2 =
schema 1 плюс необязательный ключ 13; сервер принимает обе, ключ 13 в schema 1
игнорируется):

| Key | Назначение |
|---:|---|
| 0 | heartbeat schema, 1 или 2 |
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
| 13 | detector health (schema 2, необязательный; прошивка `zs_detector_health_t`, сервер `DetectorHealth`) |

Detector sub-map key 13 (schema 2, счётчики с момента загрузки; станция шлёт его с 2026‑09‑23):

| Sub-key | Field | Назначение |
|---:|---|---|
| 0 | boot_id | NOR‑счётчик загрузок (`zs_boot_counter`); `event_id = (boot_id << 32) + seq_no` |
| 1 | uptime_s | секунд с загрузки |
| 2 | windows | окон 1 с проанализировано |
| 3 | windows_dropped | пропущенных шагов (анализ отстал от кольца) |
| 4 | confirmed_windows | окон уровня 1 CONFIRMED |
| 5 | suspect_windows | окон уровня 1 SUSPECT |
| 6 | engine_windows | окон уровня 1 ENGINE_UNCONFIRMED |
| 7 | events_emitted | событий детекции положено в outbox |
| 8 | events_refused | отказов outbox (переполнение/ошибка хранения) |
| 9 | outbox_pending | событий, ещё не подтверждённых квитанцией сервера |
| 10 | window_max_ms | самое долгое окно анализа |
| 11 | presence_level | текущий уровень 1: 0 NONE, 1 SUSPECT, 2 ENGINE_UNCONFIRMED, 3 CONFIRMED |

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

Portable outbox сохраняет полный binary CBOR detection вместе с `station_id`,
`boot_id`, `seq_no`, `event_id`, timestamp, priority, persistent `retry_count` и
SHA-256 payload. Metadata защищена CRC32; body и SHA-256 записываются до отдельного
commit marker. Незавершённая запись после потери питания не становится событием.

Выборка выполняется по убыванию priority и FIFO внутри одного priority. Pending
событие никогда не вытесняется; при заполнении возвращается `FULL`. Повторная
постановка идентичного `station_id/event_id` идемпотентна, а тот же идентификатор
с другой metadata или SHA-256 отклоняется как conflict. Счётчик попыток использует
128-битную one-way bitmap без erase текущего события.

Portable W25Q-class adapter maps every 616-byte logical outbox slot to its own
complete 4-KiB erase block. Partition base alignment, capacity and slot bounds
are checked before use, so reclaiming one event cannot erase an adjacent pending
event. Before returning any archive, command-journal or outbox interface, the
shared binding requires exact W25Q512JV JEDEC ID `EF 40 20`, a valid SFDP header
and BFPT density of 64 MiB, the expected 4-byte read/program/erase geometry and
Status Register-2 QE. A cleared QE is restored with `35h`/`31h`, wait-ready and
read-back; any mismatch leaves all returned interfaces zeroed. The portable
layout planner assigns the erase-aligned NOR prefix to the
audio archive, derives a command-journal partition from a caller-supplied slot
count, and places the caller-sized outbox at the tail. It rejects insufficient
or unaligned geometries and proves that all three ranges do not overlap. The
64-MiB / 4-KiB / 16-command / 256-event host reference produces a 62.9375-MiB
archive prefix, a 64-KiB command journal and a 1-MiB outbox tail. This example
does not freeze the production slot counts. All three adapters are created by
one fail-closed binding; its archive storage view ends exactly at the derived
command base, and both tail adapters are bounded to their own partitions. The
production slot counts, reviewed target memory map, OCTOSPI HAL binding and
measured endurance remain open. Host emulation does not replace probe and
power-loss evidence on the assembled W25Q512JV sample.

MQTT PUBACK не является application ACK. Станция помечает событие доставленным
только после проверенного server application receipt из раздела 2.3; torn ACK
marker остаётся pending, поэтому recovery имеет семантику at-least-once и может
повторить тот же `event_id`. Серверная схема и portable firmware parser проходят
host QG-1/QG-2. Portable BG95 receive binding и bounded single-owner raw-UART
session также проходят host QG; production command/outbox slot counts, target
USART-DMA/OCTOSPI binding, retain policy,
wear/endurance и аппаратная recovery-проверка пока открыты; portable QG не
закрывает `REQ-CELL-003`.

## 7. Gate

После сборки станций требуются modem log с маскированием IMSI/ICCID, broker log,
packet capture без идентификаторов/секретов, 24 часа MQTT, потеря сети/питания,
CGNAT, DNS failure, certificate failure, повторная доставка, 20 одновременных
станций и store-and-forward recovery. Для Rev.A дополнительно требуется проверка
end-to-end декодирования INA226 и cellular heartbeat, а также отсутствие роста
P0 summary выше 220 bytes. До сборки эти аппаратные пункты имеют статус
`DEFERRED_UNTIL_STATIONS_ASSEMBLED`, а не PASS.
