# ICD Station configuration (`config_write` / `config_read`) v0.1

Статус: `DRAFT / PORTABLE FIRMWARE + ANDROID DOMAIN IMPLEMENTED / GATT BINDING OPEN`

Дополняет `BLE_GATT_OTA_ICD_v0_1.md` (сервис Configuration, характеристики `config_write` и `config_read`) и закрывает пункт AND-F-004: адрес сервера «Мухоед», порты, CA, tenant, префикс топиков, публичные APN и предпочтительный слот SIM.

## 1. Реализация

- прошивка: `firmware/include/zs_station_config.h`, `firmware/src/zs_station_config.c`, host-тест `firmware/tests/test_station_config.c` (схема v1, A/B слоты по 320 байт, CRC32 + commit-маркер, канонический SHA-256, fail-closed разбор CBOR);
- Android: `android/app/src/main/java/ru/dioneya/commissioning/core/StationConfigPatch.kt` (модели `ServerEndpoint`, `StationConfigPatch`, `HostValidator`, `CanonicalCbor`), тест `StationConfigPatchTest.kt`;
- известные ответы (REF_HASH, REF_PATCH, REF_READBACK) печатает C-тест и проверяет Kotlin-тест: обе стороны сходятся побайтно.

## 2. Поля

| Ключ | Имя | Тип CBOR | Ограничение | Кто пишет |
|---|---|---|---|---|
| 1 | version | uint32 | > текущей версии на станции, обязателен в каждом патче | приложение |
| 2 | server_host | tstr ≤ 64 | IPv4-литерал, IPv6-литерал или RFC 1123 hostname; без схемы `mqtts://` | приложение |
| 3 | mqtt_port | uint16 | 1..65535, MQTT поверх TLS (умолчание 8883) | приложение |
| 4 | https_port | uint16 | 0 = нет резерва, иначе 1..65535 и ≠ mqtt_port | приложение |
| 5 | ca_reference | tstr ≤ 32 | `[A-Za-z0-9._-]`, ссылка на CA продукта в UFS модема | приложение |
| 6 | server_fingerprint | bstr 32 | SHA-256 сертификата сервера; 32 нуля = без pinning | приложение |
| 7 | tenant | tstr ≤ 16 | `[A-Za-z0-9._-]` | приложение |
| 8 | topic_prefix | tstr ≤ 32 | `[A-Za-z0-9._/-]`, без ведущего и замыкающего `/` | приложение |
| 9 | preferred_sim | uint | 1 или 2 | приложение |
| 10 | apn1 | tstr ≤ 32 | `[A-Za-z0-9.-]`, публичный APN; пустая строка = не задан | приложение |
| 11 | apn2 | tstr ≤ 32 | как apn1; непуст только при непустом apn1 | приложение |
| 12 | region | uint | 1 = RU868, 2 = EU868; в патче допускается только равный текущему (AND-F-013) | только чтение |
| 13 | station_id | uint32 | заводская идентичность | только чтение |
| 14 | config_hash | bstr 32 | канонический SHA-256, вычисленный станцией | только чтение |

## 3. Правила патча (`config_write`)

- definite-length map с целыми ключами по возрастанию; дубликаты, indefinite-length, неминимальные длины, лишние байты, неизвестные ключи, неверные типы отвергаются целиком;
- патч частичный: незаданные поля берутся из текущей записи;
- `version` обязателен и должен быть больше сохранённого;
- попытка изменить `region` или передать `station_id` отвергается (`PATCH_IMMUTABLE_FIELD` / `PATCH_UNKNOWN_KEY`);
- после применения запись проверяется целиком (`zs_station_config_validate`) и хэшируется станцией;
- запись во Flash только в физическом сервисном режиме и аутентифицированной ролью; пишется неактивный слот, commit-маркер последним, затем read-back и сравнение хэша.

## 4. Канонический хэш

SHA-256 над 281 байтом: домен `ZS-STATION-CONFIG-V1` (20), schema (1), version BE32, station_id BE32, region, preferred_sim, mqtt_port BE16, https_port BE16, затем поля `len(1) + data(max, дополнено нулями)`: host 64, ca_reference 32, fingerprint 32 (без длины), tenant 16, topic_prefix 32, apn1 32, apn2 32. Метаданные хранения (generation) в хэш не входят.

## 5. Read-back (`config_read`)

Каноническая map из 14 ключей (2 и 14 включительно). Приложение обязано: разобрать, сравнить все поля с намерением записи, пересчитать хэш по разделу 4 и сравнить с ключом 14. Только полное совпадение переводит шаг «Сервер» в состояние `VERIFIED`.

## 6. Открытые вопросы

- UUID характеристик, MTU и фрагментация патча > 244 байт (полный патч эталона 141 байт, максимум 240 байт при всех полях по верхним границам) - после GATT-прототипа;
- загрузка CA/сертификата станции в UFS BG95 по `ca_reference` - отдельная процедура сервисного режима;
- сохранение адреса сервера в самом приложении (профили «пилот»/«стенд») - локальные настройки, не часть ICD.
