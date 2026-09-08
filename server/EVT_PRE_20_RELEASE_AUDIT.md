# «Мухоед» - аудит исходной версии для EVT-PRE-20

Дата: 2026-09-08  
Статус: `SOURCE_BASELINE_IDENTIFIED / RELEASE_GATE_OPEN`

## Фактическая крайняя версия

Ветки `evt-pre-20` и `evt-mb` содержат одинаковые SHA основных файлов и каталогов server. Файл `RELEASE_NOTES_v1_3_EVT_MB.md` в `evt-mb` побайтно совпадает с `RELEASE_NOTES_v1_2_EVT_MB.md` и внутри называет релиз `Мухоед 1.2.0 EVT-MB`. Следовательно, отдельной серверной версии 1.3 в репозитории нет.

Для EVT-PRE-20 текущей исходной базой является фактический код `Мухоед 1.2.0` с interface release 1.4. Переименование без изменения кода запрещено.

## Что существует

- decoder detection compact CBOR schema 3;
- FastAPI endpoints detection, heartbeat, events, command polling и audio upload;
- MQTT subscriber для `up` и `status` с привязкой station_id к topic;
- SQLite storage и дедупликация detection по event_id;
- Docker/compose материалы для Windows 11 и Ubuntu 24.04;
- core, full и firmware-to-server тестовые наборы.

## Блокеры предсерийного deployment

1. MQTT bridge может стартовать без CA, то есть TLS не является fail-closed.
2. FastAPI station endpoints не имеют законченной взаимной аутентификации/authorization для internet-facing deployment.
3. MQTT downstream/ACK не реализован; server commands сейчас выдаются HTTP polling.
4. Requirements используют диапазоны версий, lockfile/SBOM отсутствуют.
5. Нет подтверждённого clean deployment и backup/restore на Windows 11 и Ubuntu 24.04.
6. Нет load/reconnect/dedup теста для 20 реальных станций.
7. Нет OTA repository, canary rollout, pause и rollback audit.

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

