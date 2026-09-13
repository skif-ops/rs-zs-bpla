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
- Portable atomic journal записывает `ACCEPTED` до идемпотентного действия и
  `COMPLETED` до разрешения ACK; fault-injection проверяет потерю питания между
  body/commit marker, повтор и заполнение ограниченного журнала.
- Bounded trust adapter проверяет SHA-256-derived key ID, дубликаты, disabled
  rotation entries и неизвестные ключи до вызова обязательного crypto backend;
  production public keys в portable source отсутствуют.
- Portable application channel связывает decode/trust/dedup, atomic journal и
  idempotent executor; ACK появляется только после read-back `COMPLETED`, а
  transient execution/storage failure оставляет команду для безопасного retry.
- Portable binary MQTT boundary принимает topic и CBOR только с точными длинами,
  проверяет canonical tenant/station topic, QoS 1 и `retain=false`, затем выдаёт
  ACK topic/payload только после durable completion.
- Portable event outbox атомарно сохраняет полный schema-4 CBOR с metadata CRC32
  и SHA-256, выбирает priority/FIFO, не вытесняет pending events и при torn ACK
  обеспечивает безопасную at-least-once повторную доставку.
- Server/portable-firmware application receipt использует canonical CBOR,
  station/boot/sequence/event binding и SHA-256 точных detection bytes. Сервер
  сохраняет processing state до receipt, exact retry не повторяет fusion, а
  firmware освобождает outbox slot только после строгой проверки receipt.
- Portable event MQTT adapter выдаёт только exact binary `up` publication после
  durable retry accounting, оставляет PUBACK без влияния на outbox и применяет
  queued receipt после рестарта через поиск durable event identity.
- Portable W25Q-class outbox adapter использует один полный erase block на slot,
  проверяет alignment/capacity и сохраняет соседний pending slot при reclaim;
  portable planner размещает audio archive в выровненном префиксе NOR, outbox в
  хвосте и QG-проверяет их непересечение. Production slot count, target
  memory-map/OCTOSPI/endurance остаются blockers.
- Открыты target MQTT subscription/URC binding, reviewed Ed25519 backend,
  provisioning public key, Flash/outbox slot-count/OCTOSPI/endurance binding, command ACK
  publisher, BG95 event-receipt binding и аппаратный end-to-end;
  они не объявлены PASS до сборки станций.

Изменение не закрывает security/deployment blockers из `EVT_PRE_20_RELEASE_AUDIT.md` и не является разрешением на internet-facing deployment.
