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
   CBOR, TTL/retry до application ACK и тройной привязкой station_id. Portable
   firmware codec разбирает и валидирует envelope через обязательные signature и
   durable-dedup callbacks и формирует ACK; граница server/firmware закреплена
   детерминированным Ed25519 vector. Portable atomic journal фиксирует
   accepted/completed до ACK, а bounded trust adapter fail-closed выбирает
   provisioned public key. Portable application channel объединяет эти стадии и
   идемпотентный executor; portable binary MQTT boundary уже проверяет точный
   topic, QoS/retain и длину payload. Открыты target MQTT binding, reviewed
   Ed25519 backend, public-key provisioning, Flash page/endurance binding и
   hardware end-to-end evidence.
3. ЗАКРЫТО: исходные диапазоны разрешены в хешированные Python 3.12 lockfiles;
   production image и CI используют `requirements.lock.txt` с
   `--require-hashes`, а `sbom/server.cdx.json` воспроизводимо генерируется из
   byte-exact lock и проходит отдельные QG-1/QG-2.
4. Нет подтверждённого clean deployment и backup/restore на Windows 11 и Ubuntu 24.04.
5. Нет load/reconnect/dedup теста для 20 реальных станций.
6. Нет OTA repository, canary rollout, pause и rollback audit.
7. ЧАСТИЧНО: portable event outbox атомарно сохраняет schema-4 CBOR, metadata,
   SHA-256, приоритет и retry bitmap и проходит fault-injection. Серверная схема
   application receipt и portable firmware parser проверяют точный payload hash,
   station/event identity, QoS/retain и идемпотентный повтор. Portable uplink
   adapter сохраняет retry до выдачи exact binary publication и не освобождает
   slot по PUBACK. Portable NOR adapter изолирует slot отдельным erase block.
   Открыты exact BG95 binding, target NOR partition/OCTOSPI/endurance и аппаратный
   recovery.

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
`down`/`ack`. Полное закрытие возможно после target-интеграции MQTT приёмника,
production crypto/Flash binding/ACK publisher, provisioning public key и проверки
на собранных станциях.

Частично закрыт пункт 7: host outbox обеспечивает at-least-once и не вытесняет
pending events, а server/portable-firmware application receipt подтверждает
только exact payload после durable processing. MQTT PUBACK не считается таким
подтверждением. До exact BG95/target binding события после восстановления сети
не разрешено удалять в изделии.

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
