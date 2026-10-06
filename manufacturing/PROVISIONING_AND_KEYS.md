# Provisioning и ключи EVT-PRE-20

Статус: `BENCH FLOW RELEASED / PRODUCTION DEVICE-SIDE KEYGEN AND BG95 HARDWARE VALIDATION PENDING`.

## Разделение доверия

Контрактный производитель получает проверяемые образы и открытые ключи. Root CA private key, firmware release private key, command signing private key, Android keystore и station private keys в производственный пакет не входят.

Уникальное provisioning выполняется после входного контроля на изолированном рабочем месте владельца проекта или доверенного интегратора. Root CA уже выпущен и хранится offline. Issuing CA находится в защищенном PKI-контуре `dioneya.ru`. Обычная регистрация станции не требует и не разрешает повторный выпуск CA.

## Типы ключей

| Ключ | Назначение | Закрытая часть |
|---|---|---|
| Root CA | Корень mTLS | Offline machine |
| Issuing CA | Подпись station CSR | Сервер PKI |
| Station ECDSA P-256 | mTLS одной станции | Устройство или EOL fixture; server-side только для B01 |
| Pairing secret | LESC passkey по QR | Реестр PKI и этикетка |
| Engineer key | Роль B.9 | Реестр, станция, Android Keystore инженера |
| Command signing key | Удаленные команды | Сервер; на станцию записывается public key |
| Firmware release key | STM32 и model packages | Offline signing workstation |
| nRF MCUboot key | nRF image | Внешнее signing storage |
| Android release key | APK | Внешний keystore |
| SIM Ki/OPc | Аутентификация в сети оператора | Только SIM и контур оператора, проект их не выпускает и не считывает |

Pairing secret уникален для станции, но не является одноразовым. BLE bonding не сохраняется, поэтому защищенный сеанс создается заново. При утрате этикетки секрет ротируется командой `pairing-secret-rotate`, затем этикетка и значение на станции заменяются согласованно.

ICCID и IMSI являются идентификаторами, а не ключами SIM. Для EVT используются SIM с отключенным PIN, потому что target проверяет `AT+CPIN?`, но не вводит PIN. APN берется только из утвержденного публичного профиля.

## Идентичность

- `DIO-EVT-001` - `DIO-EVT-040`: station ID 1-40, tenants `pilot1` или `pilot2`;
- `DIO-EVT-B01`: station ID 901, tenant `bench`;
- IDs 9001-9040 принадлежат цифровым двойникам и физическим станциям не назначаются;
- device UUID не является простым преобразованием serial;
- hardware revision, PCB serials, IMEI, ICCID slot mapping, APN profile, calibration ID и certificate fingerprint входят в receipt;
- полные IMSI, pairing secret, engineer key и private keys в обычный evidence не входят.

## Регистрация B01

1. Проверить `pki list` и `pki audit`.
2. При отсутствии записи выполнить `station-add DIO-EVT-B01`.
3. Только для B01 выполнить `station-keygen DIO-EVT-B01 --allow-server-side-key`.
4. Выпустить `bundle`, защищенный `station-package`, защищенный `label-qr` и публичный `server-qr`.
5. Защищенно передать bench station key и station package на изолированное EOL-рабочее место.
6. Через TEST_UART выполнить `factoryid DIO-EVT-B01 <pairing_secret_hex>` из `station.json`, сделать холодный перезапуск и проверить `factory DIO-EVT-B01`, `pairing set`.
7. Отсканировать соответствующую этикетку и выполнить первое LESC-сопряжение.
8. Считать реальные ICCID и сформировать `station-secrets` с command public key `/run/tls/command-signing-bench.key`.
9. Обновить ACL и CRL.
10. Записать station secrets по BLE 0x0206 и TLS material в BG95.
11. Проверить mTLS, MQTT heartbeat, event, application receipt и command ACK.
12. Только после EOL выполнить `station-commission`.

## Регистрация DIO-EVT-001 - DIO-EVT-040

1. Один раз инициализировать реестр `station-add --all-lots`, если записей еще нет.
2. На станции или EOL fixture сгенерировать уникальный ECDSA P-256 private key и CSR с CN, равным serial, штатным `05_EOL_TOOLS/generate_evt_station_csr.py`.
3. Передать на сервер только CSR и выполнить `station-sign <SERIAL> --csr <CSR>`.
4. Проверить CN, lot, fingerprint, срок, `clientAuth`, chain и соответствие private key инструментом `05_EOL_TOOLS/verify_evt_station_certificate.py`.
5. Выпустить station package и этикетку. Station package не содержит station private key, но содержит pairing secret и engineer key, поэтому защищается как секретный EOL-материал.
6. На EOL-рабочем месте объединить certificate, CA chain и локальный private key.
7. Через TEST_UART выполнить `factoryid <SERIAL> <pairing_secret_hex>`, холодный перезапуск и read-back только признаков serial/pairing.
8. Сформировать station secrets с `/run/tls/command-signing.key`, обновить ACL и выполнить commissioning по инструкции Rev C.

## BG95

В BG95 до соединения загружаются CA, client certificate и client key. Реализованная последовательность `zs_bg95_provision` удаляет прежний файл, выполняет `QFUPL`, сверяет `+QFUPL` size/checksum и `QFLST`, затем задает `QSSLCFG clientcert/clientkey`. Ответ `OK` без проверки size, checksum и списка файлов не является доказательством загрузки.

Для действующего профиля используются `dioneya.ru:8883`, SSL context 1 и `ca_reference=dioneya-root`. Связка с фактической EOL UART и выбранной версией BG95 проверяется на `DIO-EVT-B01`.

## Station secrets

Команда `station-secrets` формирует `DIO-SECRETS-V1` с engineer key, ICCID1, ICCID2 и command public key. Файл записывается один раз на пустую станцию, не сохраняется приложением и удаляется с телефона и переносного носителя после read-back presence. Повторная запись требует роли engineer. Engineer key для авторизованного инженерного телефона экспортируется отдельно и хранится через Android Keystore.

## Завершение

Provisioning receipt содержит serial, station ID, tenant, публичные идентификаторы, маскированные ICCID references, certificate fingerprint, key generation mode, firmware release, tool versions, операторов, timestamps, ACL revision и результаты connection tests. Временные файлы с секретами удаляются. Старые сертификаты при ротации отзываются, CRL и ACL обновляются, Mosquitto перезапускается.

Полная пошаговая процедура приведена в `docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.md`.
