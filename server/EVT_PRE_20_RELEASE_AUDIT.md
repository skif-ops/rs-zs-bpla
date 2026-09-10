# «Мухоед» - аудит исходной версии для EVT-PRE-20

Дата: 2026-09-08
Статус: `SOURCE_BASELINE_IDENTIFIED / RELEASE_GATE_OPEN`

## Фактическая крайняя версия

При выделении `evt-pre-20` аудит общей истории подтвердил фактическую исходную базу
сервера `Мухоед 1.2.0` и interface release 1.4. Отдельной функциональной версии 1.3
в общей истории не было.

Для EVT-PRE-20 код сохраняет функциональную базу `Мухоед 1.2.0`, но использует
веточный runtime-идентификатор `1.2.0-evt-pre-20.1`. Специфичные release notes и
runtime-маркировка `evt-mb` в этой ветке не допускаются.

## Что существует

- decoder detection compact CBOR schema 3;
- FastAPI endpoints detection, heartbeat, events, command polling и audio upload;
- MQTT subscriber для `up` и `status` с привязкой station_id к topic;
- SQLite storage и дедупликация detection по event_id;
- Docker/compose материалы для Windows 11 и Ubuntu 24.04;
- core, full и firmware-to-server тестовые наборы.

## Блокеры предсерийного deployment

1. FastAPI station endpoints не имеют законченной взаимной аутентификации/authorization для internet-facing deployment.
2. MQTT downstream/ACK не реализован; server commands сейчас выдаются HTTP polling.
3. Requirements используют диапазоны версий, lockfile/SBOM отсутствуют.
4. Нет подтверждённого clean deployment и backup/restore на Windows 11 и Ubuntu 24.04.
5. Нет load/reconnect/dedup теста для 20 реальных станций.
6. Нет OTA repository, canary rollout, pause и rollback audit.

Закрыто в исходном baseline EVT-PRE-20: MQTT bridge теперь fail-closed и требует CA, client certificate и key. Plaintext разрешён только явным флагом `--insecure-bench`, который используется в отдельном development compose и проверяется отрицательными тестами.

До закрытия пунктов сервер разрешён только для разработки или изолированного стенда. Публикация напрямую в интернет запрещена.

## Выпускной gate

- `python -m compileall -q .`;
- core pytest;
- полный `pytest tests`;
- firmware CBOR -> server test;
- dependency lock и SBOM;
- secret scan;
- clean deploy Windows 11 и Ubuntu 24.04;
- broker mTLS/ACL и API auth tests;
- 20-station soak не менее 24 часов;
- backup/restore и журнал отката OTA.
