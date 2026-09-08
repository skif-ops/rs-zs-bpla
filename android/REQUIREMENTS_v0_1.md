# Android commissioning app - требования v0.1

Статус: `DRAFT / OPEN`

## Функциональные требования

- AND-F-001: обнаруживать только станции в физически активированном service mode.
- AND-F-002: связывать BLE identity с QR/serial до чтения или изменения конфигурации.
- AND-F-003: показывать serial, station_id, HW revision, FW/bootloader version и region.
- AND-F-004: настраивать APN, порядок RAT, roaming policy, MQTT/HTTPS endpoint и CA reference.
- AND-F-005: проверять формат адресов, диапазоны и обязательные поля до записи.
- AND-F-006: применять конфигурацию атомарно, считывать обратно и сравнивать hash/version.
- AND-F-007: запускать self-test питания, GNSS/PPS, cellular attach/TLS, LoRa receive-only, storage и microphones.
- AND-F-008: импортировать offline OTA bundle, не изменяя его содержимое.
- AND-F-009: проверять совместимость HW, anti-rollback, hash и цифровую подпись до передачи.
- AND-F-010: поддерживать resume OTA после обрыва BLE и экрана/процесса приложения.
- AND-F-011: показывать A/B trial, confirmation и rollback reason.
- AND-F-012: экспортировать redacted diagnostic report и commissioning record.
- AND-F-013: не позволять пользователю менять manufacturing region RU868/EU868.
- AND-F-014: выдавать пошаговую инструкцию USB-C recovery без хранения recovery secrets.
- AND-F-015: показывать наличие SIM1/SIM2, redacted ICCID, активный слот, оператора, RAT и результат последнего attach.
- AND-F-016: настраивать упорядоченные public/private APN profiles и preferred SIM slot без экспорта PIN/PUK/APN password.
- AND-F-017: разрешать ручное переключение SIM/APN только авторизованной роли, с явным предупреждением о разрыве связи и сохранением audit record.
- AND-F-018: показывать причину автоматического failover, предыдущий и новый профиль, число попыток и состояние store-and-forward.

## Нефункциональные требования

- AND-N-001: работа без Google Play Services.
- AND-N-002: работа без интернета после загрузки APK и OTA bundle.
- AND-N-003: интерфейс на русском; английская локализация обязательна до China factory use.
- AND-N-004: поддержка arm64-v8a, кандидат minimum Android 9.
- AND-N-005: отсутствие analytics, advertising SDK и скрытой телеметрии.
- AND-N-006: reproducible release build, dependency lock, SBOM и SHA-256.
- AND-N-007: APK подписывается отдельным Android release key; firmware signing key не используется.
- AND-N-008: crash/log export не содержит PIN, APN password, TLS private key, QR secret, полного ICCID/IMSI.
- AND-N-009: critical actions требуют явного подтверждения и отображают station serial.
- AND-N-010: все ошибки имеют recoverable state или понятный переход к USB-C recovery.

## Не входит в первую версию

- карта объектов и постоянный мониторинг;
- облачная учётная запись пользователя;
- изменение классификационных моделей отдельно от подписанного release bundle;
- доступ к API оператора;
- одновременная работа двух SIM;
- ручная установка RF frequency/power;
- извлечение private keys станции.

## Gate

Требования получают `LOCKED` после утверждения UX двух ролей, GATT prototype, security review, проверки минимум на трёх смартфонах включая устройство Huawei без GMS и совместного теста с target firmware.
