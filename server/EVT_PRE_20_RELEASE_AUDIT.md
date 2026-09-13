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
2. ЧАСТИЧНО: server-side MQTT downstream/ACK реализован с Ed25519, canonical
   CBOR, TTL/retry до application ACK и тройной привязкой station_id. Открыты
   firmware subscribe/parser/signature verification/ACK на целевом STM32 и
   hardware end-to-end evidence.
3. ЗАКРЫТО: исходные диапазоны разрешены в хешированные Python 3.12 lockfiles;
   production image и CI используют `requirements.lock.txt` с
   `--require-hashes`, а `sbom/server.cdx.json` воспроизводимо генерируется из
   byte-exact lock и проходит отдельные QG-1/QG-2.
4. Нет подтверждённого clean deployment и backup/restore на Windows 11 и Ubuntu 24.04.
5. Нет load/reconnect/dedup теста для 20 реальных станций.
6. Нет OTA repository, canary rollout, pause и rollback audit.

Закрыто в исходном baseline EVT-PRE-20: MQTT bridge теперь fail-closed и требует CA, client certificate и key. Plaintext разрешён только явным флагом `--insecure-bench`, который используется в отдельном development compose и проверяется отрицательными тестами.

Частично закрыто после baseline: station HTTP ingress, command polling/ACK и
audio upload теперь fail-closed и доступны только при точном стендовом opt-in
`ZS_STATION_HTTP_INSECURE_BENCH=1`. Production telemetry должна поступать через
MQTT mTLS. Пункт 1 остаётся открытым до завершения auth/authz операторского
REST/WebSocket UI и deployment-проверок; это изменение не разрешает публикацию
FastAPI напрямую в интернет.

Частично закрыт пункт 2: production bridge публикует только подписанные команды,
не считает broker QoS ACK прикладным подтверждением и безопасно отключает
downstream без ключа. ACL разрешает каждой station credential только собственные
`down`/`ack`. Полное закрытие возможно после реализации и target-теста приёмника
команд в firmware, provisioning public key и проверки на собранных станциях.

До закрытия пунктов сервер разрешён только для разработки или изолированного стенда. Публикация напрямую в интернет запрещена.

## Выпускной gate

- `python -m compileall -q .`;
- core pytest;
- полный `pytest tests`;
- firmware CBOR -> server test;
- secret scan;
- clean deploy Windows 11 и Ubuntu 24.04;
- broker mTLS/ACL и API auth tests;
- 20-station soak не менее 24 часов;
- backup/restore и журнал отката OTA.
