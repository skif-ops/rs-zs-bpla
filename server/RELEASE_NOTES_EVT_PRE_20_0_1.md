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

Изменение не закрывает security/deployment blockers из `EVT_PRE_20_RELEASE_AUDIT.md` и не является разрешением на internet-facing deployment.
