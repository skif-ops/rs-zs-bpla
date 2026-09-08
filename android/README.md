# Android track — Dioneya Station Service

Отдельный трек приложения для локальной настройки, диагностики и обновления станции. Его версия не совпадает автоматически с версией firmware станции.

## MVP для EVT-PRE-20

- работа без Google Mobile Services;
- Android 10+; основной целевой ABI — arm64-v8a;
- обнаружение станции по BLE только после физического включения сервисного режима;
- взаимная аутентификация и подтверждение станции пользователем;
- чтение station id, serial, hardware revision, firmware version, protocol schema, battery, GNSS/time quality и состояния каналов;
- настройка APN/operator profile, server endpoint, LoRa region/profile и порогов сервисного уровня;
- проверка конфигурации до записи и экспорт диагностического отчёта;
- подписанное обновление firmware по BLE с A/B slot, проверкой хеша/подписи и rollback;
- сервисное восстановление по USB-C/SWD остаётся отдельным производственным процессом;
- журнал действий без записи SIM PIN, private keys и паролей в открытом виде.

## Запрещено в первом EVT-релизе

- неподписанные firmware images;
- OTA при неизвестной аппаратной ревизии;
- запись региона LoRa без проверки совместимости firmware/hardware;
- постоянный доступ BLE вне сервисного окна;
- зависимость от облака для базовой локальной настройки;
- хранение production signing key внутри APK или репозитория.

## Пакет выпуска

Исходники, Gradle wrapper/version catalog, reproducible build instructions, signed release APK, test APK, SBOM, third-party notices, BLE GATT ICD, UX flow, test plan, compatibility matrix, release notes, SHA-256 и подпись.

## Статус

`PLANNED / NOT IMPLEMENTED`. Детальная архитектура и протокол GATT выпускаются после freeze BLE-компонента и bootloader/OTA format.
