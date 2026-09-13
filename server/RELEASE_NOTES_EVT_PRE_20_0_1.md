# Мухоед EVT-PRE-20 source baseline 0.1

Статус: `CI PASS / NOT DEPLOYED`

- Сохранена фактическая база Мухоед 1.2.0, interface release 1.4.
- Runtime-идентификатор ветки: `1.2.0-evt-pre-20.1`; маркировка EVT-MB исключена.
- В CI добавлены полный pytest и compileall.
- Устранён collection blocker: `router.py` и `online_type_service.py` импортировали отсутствующие `FeatureUpdateMessage` и `OnlineTypeStatusMessage`.
- Добавлены Pydantic schemas для 43-feature update и fail-safe online type status.
- Добавлены regression tests точной длины features и безопасных значений UNKNOWN/false.
- Иерархическое решение переведено на bounded consensus последних 4-8 уникальных
  окон; повтор одного `boot_id/seq_no` не увеличивает evidence.
- В portable firmware добавлен тот же rolling-consensus 4-8 окон с порогом 5/8
  и явным отображением flat-классов в семейства; конкретный тип не назначается.
- Добавлены отдельные ветви неизвестного типа внутри известных семейств:
  `UNKNOWN_PROP_PISTON_UAV`, `UNKNOWN_TURBINE_JET_UAV`,
  `UNKNOWN_ROTOR_ELECTRIC_UAV`; конкретный тип по-прежнему не фиксируется без
  dataset-readiness gate.
- Temporal type model пересобрана для горизонтов 4/6/8 с и fail-closed отклоняет
  модель с несовместимым набором горизонтов.
- В `TargetEstimate` восстановлены поля `localization_mode` и `geometry_quality`, которые уже формировал solver.
- Full CI восстанавливает `dataset/features.csv` из версионированного `features.csv.gz` штатным скриптом до pytest.
- MQTT bridge переведён в fail-closed TLS mode: без CA, client certificate и key запуск отклоняется.
- Plaintext MQTT оставлен только для изолированного стенда с явным `--insecure-bench`; добавлены отрицательные тесты конфигурации.
- Станционный HTTP transport переведён в fail-closed mode: ingestion,
  command polling/ACK и audio upload включаются только точным стендовым
  `ZS_STATION_HTTP_INSECURE_BENCH=1`; полные IMSI/ICCID по HTTP по-прежнему
  запрещены.
- Добавлены universal Python 3.12 lockfiles с SHA-256 каждого допустимого
  distribution artifact; Docker и CI используют `pip --require-hashes`.
- Добавлен воспроизводимый CycloneDX 1.6 server SBOM, byte-exact привязанный к
  runtime lock, а также независимые QG-1/QG-2 проверки состава и хешей.
- Реализована серверная половина MQTT command downstream/ACK: canonical CBOR,
  Ed25519, 15-минутный TTL, QoS 1 retry до application ACK, station ownership и
  идемпотентная обработка повторов.
- Production bridge не публикует unsigned-команды и требует owner-only signing
  key; Docker build context исключает TLS private keys. Broker ACL разделён для
  20 station credentials и разрешает каждой станции только собственные topics.
- В portable firmware реализованы fixed-memory canonical CBOR parser команд и
  encoder ACK: station/time/TTL binding, точное восстановление подписанных байтов,
  обязательные callback проверки Ed25519 и durable dedup. Межъязыковой
  server-generated Ed25519 vector проверяется Python и C тестами.
- Открыты target MQTT subscription/URC binding, production Ed25519 backend,
  provisioning public key, durable result/ACK publisher и аппаратный end-to-end;
  они не объявлены PASS до сборки станций.

Изменение не закрывает security/deployment blockers из `EVT_PRE_20_RELEASE_AUDIT.md` и не является разрешением на internet-facing deployment.
