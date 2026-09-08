# Android track - Dioneya commissioning

Этот каталог отделён от firmware станции. Приложение предназначено для монтажника и сервис-инженера: локальная BLE-настройка, диагностика и доставка подписанного OTA-пакета.

Принципы:

- работает без Google Play Services и без интернета;
- не требует API мобильного оператора;
- не содержит product signing key, ключи станций или общие заводские пароли;
- не позволяет менять RU868/EU868 после manufacturing provisioning;
- импортирует только подписанный firmware package;
- поддерживает resume, A/B status и rollback report;
- USB-C используется как отдельный сервисный recovery path.

Статус: `SOURCE_BASELINE / BLE_NOT_IMPLEMENTED / RELEASE_APK_NOT_BUILT`.

В каталоге `app` находится минимальный Kotlin/Android проект с unit tests, но он не является commissioning APK: BLE UUID, authenticated pairing и формат OTA signature ещё не заморожены.

Документы:

- `APP_ARCHITECTURE_v0_1.md`;
- `REQUIREMENTS_v0_1.md`;
- `SECURITY_MODEL_v0_1.md`;
- `ACCEPTANCE_TESTS_v0_1.csv`;
- `track_status.yaml`.
