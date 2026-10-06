# Android track - Dioneya commissioning

Этот каталог отделён от firmware станции. Приложение предназначено для монтажника и сервис-инженера: локальная BLE-настройка, диагностика и доставка подписанного OTA-пакета.

Принципы:

- работает без Google Play Services и без интернета;
- не требует API мобильного оператора;
- не содержит product signing key, ключи станций или общие заводские пароли;
- не позволяет менять зафиксированный RU868 после manufacturing provisioning;
- показывает два SIM-слота и управляет только разрешёнными публичными APN; private APN в пилоте отклоняется;
- импортирует только подписанный firmware package;
- поддерживает resume, A/B status и rollback report;
- USB-C используется как отдельный сервисный recovery path.

Статус: `BENCH RELEASE APK SIGNED / UNIT TESTS PASS / HARDWARE VALIDATION PENDING`.

В каталоге `app` находится Kotlin/Android проект с unit tests и Android
`BluetoothGatt` transport, подключённым к экранам выбора станции, установки и
настройки сервера. Стендовый release APK `0.1.0-bench.20261005`
(`versionCode 2026100501`) собран с обязательной внешней конфигурацией подписи.
Формат подписанного OTA, release signing и CycloneDX SBOM закрыты стендовым
релизным пакетом. BLE UUID, authenticated pairing, station GATT и OTA end-to-end
проверяются на физическом стендовом изделии `DIO-EVT-B01`.

Domain-слой installation commissioning независимо воспроизводит станционный
58-byte SHA-256 contract, контролирует installer/service-engineer policy,
monotonic recommission version и принимает read-back только при совпадении
полей, hash, storage generation и `auditCommitted`. Он не передаёт hash как
источник доверия станции. Android BLE transport в исходниках есть; закрытие
готовности требует проверки на nRF52840 GATT реальной станции.

Debug source baseline успешно собран CI на commit `6e561637c03856b6bfb963a5b16a481888925991`, workflow run `34240158982`. Стендовый release APK собран с Gradle 9.6.0, AGP 9.4.0, JDK 21 и API 36 после unit tests. APK Signature Scheme v2 и fingerprint сертификата фиксируются в `firmware/targets/evt_pre_20/release/bench_release_contract.json`. Закрытый ключ и пароль находятся только во внешнем локальном хранилище и в Git не попадают.

Gradle wrapper 9.6.0 закреплён официальной SHA-256 суммой. Для release-задач обязательны переменные `DIONEA_ANDROID_KEYSTORE`, `DIONEA_ANDROID_STORE_PASSWORD`, `DIONEA_ANDROID_KEY_ALIAS` и `DIONEA_ANDROID_KEY_PASSWORD`; без них сборка прекращается.

Документы:

- `APP_ARCHITECTURE_v0_1.md`;
- `REQUIREMENTS_v0_1.md`;
- `SECURITY_MODEL_v0_1.md`;
- `ACCEPTANCE_TESTS_v0_1.csv`;
- `track_status.yaml`.
