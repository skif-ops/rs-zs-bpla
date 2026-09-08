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

Статус: `REQUIREMENTS_DRAFT / SOURCE_NOT_STARTED / APK_NOT_BUILT`.

Документы:

- `APP_ARCHITECTURE_v0_1.md`;
- `REQUIREMENTS_v0_1.md`;
- `SECURITY_MODEL_v0_1.md`;
- `ACCEPTANCE_TESTS_v0_1.csv`;
- `track_status.yaml`.
