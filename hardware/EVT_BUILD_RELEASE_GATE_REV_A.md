# EVT-PRE-20 — выпуск на сборку EVT (EVT build release), Rev.A

Статус: `ACTIVE / BLOCKING`

## Назначение

EVT-PRE-20 — это программа из двух лотов по 20 станций и одного стендового образца
(20 + 20 + 1 = 41 изделие). Серия — отдельная конфигурация, которая дорабатывается
по результатам EVT.

Критерий готовности ветки `evt-pre-20` по железу — **выпуск на сборку EVT**:
комплект передаётся на фабрику для изготовления плат и монтажа, на изготовление
корпусов и на сборку станций. Физические доказательства (термо, ток, крепления,
RF, первые образцы жгутов и корпусов) собираются на построенной партии EVT и
питают ревизию для серии; они не являются входом этого гейта.

Решение принято заказчиком 2026-09-24. Риски поставок и выбор поставщиков
остаются на стороне заказчика и в гейт не входят.

Рабочий температурный диапазон EVT-PRE-20 — **−20…+60 °C** (решение заказчика
2026-09-24). Целевой диапазон серии остаётся по DEC-019 (−40…+70 °C,
`ENVIRONMENT_REV_A.md`) и уточняется по результатам EVT.

## Аудит

Гейт проверяет `tools/audit_evt_pre_20_evt_build_release.py` (CI: задача
`evt-build-release-audit` из `ci/jobs.json`; строгий режим `--strict` на передаче).
Базовый `tools/audit_evt_pre_20_hardware_release.py` не меняется и продолжает вести
`hardware_design_release` и `purchase_release`.

Правила наследования:

- каждая проверка базового аудита, блокирующая `hardware_design_release`, блокирует
  и выпуск на сборку, если она явно не перенесена в физическую область EVT;
- проверки базового аудита, закрепляющие историческое число элементов трассировки
  PCB-PWR, пересчитываются с теми же условиями, но против фактической платы, поэтому
  шаги трассировки не приводят к ложному «регрессу».

## Перенесено в физическую область EVT (не блокирует выпуск на сборку)

- `pcb_pwr_input_protection_release`: 16 из 20 строк квалификации входной защиты
  (+70 °C при 5 А, ожидаемый ток КЗ, координация с предохранителем АКБ и SMBJ18A);
  пакет квалификации (`pcb_pwr_input_protection_qualification_packet`) остаётся
  обязательным;
- `harness_manufacturing_release`: первый обжим и разрывное усилие, 100 %
  электрический контроль, проверка трассы в сборе; пакет жгутов с
  `build_authorized=True` остаётся обязательным.

Также остаются доказательствами EVT, а не входом гейта: образцы по позициям
`SELECTED_PENDING_SAMPLE`, RF-валидация U.FL, физическая проверка покупных изделий,
первые образцы корпуса, повторная серийная проверка DIM-003.

## Проверки, добавленные только для выпуска на сборку EVT

| Проверка | Условие PASS |
|---|---|
| `pcb-main/pcb-pwr/pcb-mic_evt_cam_package` | в `hardware/manufacturing/evt-build-release/` лежит выпуск `tools/export_pcb_engineering_snapshot_rev_a.py` в той же раскладке, что инженерный снапшот: `SHA256SUMS.json` сходится; копия `native/<BOARD>.kicad_pcb` совпадает с авторитетной платой; есть `gerber/`, `drill/`, `drc.json`, `STATUS.json`, `<BOARD>_jlc_bom.csv`, `<BOARD>_jlc_cpl.csv`, `FAB_NOTES.md`; в `drc.json` нет ошибок и unconnected; в `STATUS.json` `review_b = ACCEPTED` |
| `pcb-main/pcb-pwr/pcb-mic_pads_within_outline` | ни один контакт не пересекает контур платы и не лежит за ним (DRC KiCad этого не ловит) |
| `evt_pcba_assembler_part_map` | каждая установленная электрическая позиция PCB-MAIN/PWR/MIC есть в `hardware/EVT_PRE_20_PCBA_ASSEMBLER_PART_MAP_REV_A.csv` с `Supply_mode=LCSC` и номером `C…` либо `Supply_mode=CONSIGNED` |
| `evt_bom_paper_closure` | нет строк BOM в статусах, закрываемых расчётом или ревью: `SELECTED_PENDING_REVIEW_A`, `LOCKED_CANDIDATE_PENDING_DERATING`, `LOCKED_CANDIDATE` |
| `evt_station_mechanical_bom` | `hardware/EVT_PRE_20_MECHANICAL_BOM_REV_A.csv` содержит категории `HOUSING_PART`, `CABLE_GLAND`, `ACOUSTIC_MEMBRANE`, `SEAL`, `FASTENER`, `THREADED_INSERT`, `INTER_MODULE_FUSE`, `POWER_CABLE`, `MOUNT` с MPN или номером чертежа |
| `evt_ots_temperature_coverage` | паспортный рабочий диапазон каждой покупной системной позиции (`EVT_SYSTEM_OTS_PROCUREMENT_IDENTITY_REV_A.json`) покрывает рабочий диапазон EVT −20…+60 °C (`ENVIRONMENT_REV_A.md`, раздел 6 п. 1, применённый к диапазону EVT); диапазон заряда LiFePO4 проверяется отдельно по разделу 4 |
| `evt_housing_manufacturing_package` | в `mechanics/vacuum_casting/` есть master STEP, чертёж PDF и `HOUSING_BOM*.csv` |

Размеры `DIM-*` остаются блокирующими: без них нельзя выпустить корпус. Строки,
закрытые для EVT по паспортам, ведутся в `mechanics/common/DIM_EVT_CLOSURE_REV_A.csv`
(статус `CLOSED_*`): реестр `OPEN_DIMENSIONS.csv` не правится, потому что его SHA-256
привязан к принятым пакетам DIM-003.

Инженерный снапшот `hardware/manufacturing/engineering-snapshot/` остаётся
рабочим срезом с пометкой `NOT FOR MANUFACTURE` и в этот гейт не засчитывается;
выпуск на сборку формируется тем же экспортёром в отдельный каталог.

## Что не меняется

Правила изоляции EVT-линий из `BRANCH_SCOPE.md`, двухступенчатое ревью
(Review A/B) и независимое принятие Review B человеком сохраняются.
