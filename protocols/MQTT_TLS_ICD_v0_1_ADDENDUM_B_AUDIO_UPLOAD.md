# ICD GSM/LTE MQTT/TLS v0.1 — Addendum B: audio upload for CMD_REQUEST_AUDIO (2026-09-25)

Статус: DRAFT. Закрывает разрыв v0.1: команда `CMD_REQUEST_AUDIO` (§2.1) определена, но канала, по которому
станция отдаёт аудио, в MQTT нет — есть только HTTP-маршрут `POST /api/v1/stations/{id}/events/{event_id}/audio`,
который §5 разрешает лишь на изолированном стенде. Аддендум переносит выгрузку в ту же mTLS-сессию и ACL.

## 1. Топик и ACL

| Topic | Направление | QoS | Retain | Payload |
|---|---|---:|---:|---|
| `zs/v1/{tenant}/{station_id}/audio` | station -> server | 1 | false | audio chunk CBOR (§2) |

ACL (генерируется `python -m pki.cli mosquitto-acl`): станция — `topic write zs/v1/{tenant}/{id}/audio`,
bridge — `topic read zs/v1/{tenant}/+/audio`. Остальные правила §2 без изменений.

## 2. Audio chunk CBOR (message type 7)

Канонический CBOR, ключи 0..12, ≤ 3200 байт (помещается в один BG95 `QMTPUB` ≤ 4096 байт).

| Key | Field | Encoding |
|---:|---|---|
| 0 | schema | uint, 1 |
| 1 | message type | uint, 7 |
| 2 | station_id | uint32, = станции топика |
| 3 | command_id | 16 байт, команда `CMD_REQUEST_AUDIO`, на которую отвечает выгрузка |
| 4 | event_id | uint64 |
| 5 | segment | 0 pre, 1 post (`both` = два сегмента; `range` — один сегмент pre/post по смещению) |
| 6 | chunk_index | uint16, 0..chunk_count-1 |
| 7 | chunk_count | uint16, 1..1024 |
| 8 | codec | 1 = независимые блоки IMA-ADPCM по `sample_rate` отсчётов (1 с), формат `zs_adpcm` |
| 9 | sample_rate | uint32, Гц |
| 10 | segment_start_time_us | int64, время первого отсчёта сегмента |
| 11 | segment_sha256 | 32 байта, SHA-256 всего сегмента (конкатенации блоков) |
| 12 | data | bstr, 1..3072 байт: срез сегмента [index·3072, …) |

Блок IMA-ADPCM: 4 байта заголовка (predictor int16 LE, step_index, 0), далее коды по 4 бита, младший нибл первым;
`step_index` в заголовке каждого блока — начальный (0). 1 с при 32 кГц = 16 004 байта; 30 с = 480 120 байт = 157 чанков.

Кросс-вектор: `tools/generate_audio_chunk_vector.py` → `firmware/generated/zs_audio_chunk_vector.h` (тон 50 Гц,
1 кГц, 2 с, один чанк). Энкодер прошивки (`zs_adpcm`) и серверное зеркало (`station/audio_chunk_codec.py`) обязаны
совпасть побайтно; проверяют `firmware/tests/test_audio_chunk.c` и `server/tests/test_audio_chunk_codec.py`
(в т.ч. актуальность сгенерированного заголовка).

## 3. Порядок работы

1. Станция проверяет команду (§2.1, Ed25519, TTL, dedup), записывает `ACCEPTED` в журнал команд.
2. Для каждого запрошенного сегмента читает блоки из кольца предыстории NOR (`zs_prehistory`), считает SHA-256
   сегмента, публикует чанки по порядку (QoS 1; следующий чанк — после broker-ACK предыдущего).
3. После последнего чанка — `COMPLETED` в журнал и ACK команды: `OK`, `detail_code` = число отправленных чанков.
4. Сервер собирает чанки по (station, command_id, segment), проверяет SHA-256, декодирует в PCM16, сохраняет WAV и
   ссылку на событие. QoS-1 дубли чанков игнорируются по индексу.

Отказы (ACK): `REJECTED` detail 2 — аудио события уже нет в кольце (перезаписано) или событие неизвестно;
`REJECTED` detail 3 — время станции недостоверно (сегмент не привязать к событию); `FAILED` detail 1 — ошибка
чтения NOR/CRC блока; `FAILED` detail 2 — сессия оборвалась посреди выгрузки (после рестарта journal возобновляет
выгрузку сегмента целиком; сервер дедуплицирует чанки). `REJECTED` detail 1 (не реализовано) остаётся для старых
прошивок.

## 4. Бюджет

LTE-M uplink ~100–300 кбит/с полезных: 30-секундный сегмент (480 КБ) — 15–40 с эфира плюс ~157 циклов QMTPUB.
Выгрузка удерживает S3 до завершения (сторожевой таймер S3 продлевается на время выгрузки, не более
`APP_AUDIO_UPLOAD_MAX_MS`). Кольцо предыстории ≈ 63 МиБ NOR: ~65 мин при непрерывной записи в S1/S2; запрос старше
кольца получает `REJECTED` detail 2. Трафик SIM: ~0,5 МБ на 30 с аудио.

## 5. Реализация

Кодеки: `firmware/src/zs_audio_chunk.c`, `server/station/audio_chunk_codec.py` (энкодер/декодер IMA-ADPCM,
`AudioAssembler`). Серверный bridge и ACL, кольцо предыстории на плате, исполнитель команды и сквозной сценарий
двойника — следующие шаги.
