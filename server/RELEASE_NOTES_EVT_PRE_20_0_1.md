# Мухоед EVT-PRE-20 source baseline 0.1

Статус: `CI PENDING / NOT DEPLOYED`

- Сохранена фактическая база Мухоед 1.2.0, interface release 1.4.
- В CI добавлены полный pytest и compileall.
- Устранён collection blocker: `router.py` и `online_type_service.py` импортировали отсутствующие `FeatureUpdateMessage` и `OnlineTypeStatusMessage`.
- Добавлены Pydantic schemas для 43-feature update и fail-safe online type status.
- Добавлены regression tests точной длины features и безопасных значений UNKNOWN/false.
- В `TargetEstimate` восстановлены поля `localization_mode` и `geometry_quality`, которые уже формировал solver.
- Full CI восстанавливает `dataset/features.csv` из версионированного `features.csv.gz` штатным скриптом до pytest.

Изменение не закрывает security/deployment blockers из `EVT_PRE_20_RELEASE_AUDIT.md` и не является разрешением на internet-facing deployment.
