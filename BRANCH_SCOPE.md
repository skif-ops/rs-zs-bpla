# Scope интеграционных веток `develop` и `main`

## Назначение

`develop` и `main` содержат общий проверенный код проекта и раздельные контрольные
срезы линий `evt`, `evt-mb` и `evt-pre-20`. Наличие нескольких линий в интеграционной
ветке не делает их поставочные комплекты взаимозаменяемыми.

## Допускается

- продвигать проверенные общие изменения из feature- и EVT-линий;
- хранить release/evidence каждой линии только в её выделенном пространстве;
- обновлять единый реестр статуса без изменения фактических результатов испытаний;
- продвигать `develop` в `main` только одним и тем же проверенным деревом.

## Запрещается

- копировать release/evidence из `evt-mb` в `evt-pre-20` или наоборот;
- применять BOM, распиновку, прошивку или инструкцию одной линии к другой линии;
- отмечать аппаратные проверки `PASS` без первичных измерений;
- объявлять производственный BOM или PCB готовыми до закрытия authority, Review A и Review B.

## Действующий срез

- интеграционная версия: `DIONEA-INTEGRATION-v0.14`;
- EVT-MB: `v1.3`, статус `OPEN`;
- EVT-PRE-20: Rev.A от `7ed5b021b1e7eddfda616b54fbc79e1bf0221702`, статус `OPEN`;
- PCB-MAIN: hierarchy принята только как `ACCEPT_HIERARCHY_ONLY`; routing, Review B и manufacture открыты;
- PCB-PWR: F1 value-only ECO и commit-bound ERC/PDF evidence прошли; независимый post-ECO hierarchy review открыт, qualification 1/20; `DIM-003` — 0/18, stackup/copper — 0/24 и 0/2 фабрик;
- PCB-MIC: copper-return subgate принят; общий Review B открыт;
- аппаратный EVT: `NOT RUN`.
