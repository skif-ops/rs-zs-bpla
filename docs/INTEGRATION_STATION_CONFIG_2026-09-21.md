# Поставка: конфигурация станции и адрес сервера «Мухоед» (v0.1, 2026-09-21)

Ветка `feature/station-config-pki` поверх `evt-pre-20`. Все файлы новые; единственное изменение существующего файла - регистрация модулей и тестов в `firmware/CMakeLists.txt` (восемь строк, отдельный коммит).

Состав:
- firmware/include/zs_station_config.h, firmware/src/zs_station_config.c, firmware/tests/test_station_config.c
- firmware/include/zs_bg95_provision.h, firmware/src/zs_bg95_provision.c, firmware/tests/test_bg95_provision.c
- android/app/src/main/java/ru/dioneya/commissioning/core/StationConfigPatch.kt
- android/app/src/test/java/ru/dioneya/commissioning/core/StationConfigPatchTest.kt
- protocols/STATION_CONFIG_CBOR_v0_1.md

Проверено локально на срезе 63d8715 (и перепроверено на 4a1114f): прошивка собирается с -Wall -Wextra -Wpedantic -Werror, host-тесты 35/35 PASS; Kotlin-тесты 8/8 PASS (kotlinc 2.0.21, JVM 21); известные ответы REF_HASH/REF_PATCH/REF_READBACK совпадают между C и Kotlin побайтно.

Проверка:
1. `cmake -S firmware -B firmware/build && cmake --build firmware/build && ctest --test-dir firmware/build`;
2. `./gradlew :app:testDebugUnitTest` (JUnit 4.13.2 уже в зависимостях).

Что это закрывает и что нет:
- закрывает: хранилище конфигурации станции (A/B, CRC, хэш, torn-write), разбор `config_write`, кодирование `config_read`, доменную модель и валидацию адреса сервера в приложении, общий контракт хэша, загрузку сертификатов в UFS BG95 и привязку clientcert/clientkey, адаптер записи конфигурации к `zs_bg95_t` (host/port/ca_reference, client id, tenant);
- не закрывает: GATT-транспорт (UUID/MTU), UI экрана «Сервер», привязку хранилища к разделу NOR через OCTOSPI, вызов провижининга из сервисного режима (точки входа и планировщика пока нет).
