# Дионея / РС ЗС-БПЛА — EVT-PRE-20

Эта ветка содержит инженерную базу одного управляемого предсерийного лота
`EVT-20`. Актуальная программа закупки — два отдельных набора по 20 станций и
один стендовый образец, всего 41 станция. Расчёты для 4 и 10 станций сохранены
для сравнения, но не являются разрешением закупки.

## Зафиксированный baseline

- производственная единица управления: `EVT-20`, 20 изделий;
- программа: `2 × EVT-20 + 1 bench`, 41 станция;
- резервы: два независимых EVT-20 пула; стендовый образец не создаёт третий;
- первый диапазон серийных номеров: `DIO-EVT-001…DIO-EVT-020`; второй лот и
  стендовый образец получают отдельные serial/traveller до начала сборки;
- собственная PCB станции, без отладочной платы WeAct в составе изделия;
- вычислительная платформа: `STM32U585VIT6Q`, `LQFP100_14x14`;
- четыре одинаковых микрофона, схема 3+1, база 120 мм, верхний микрофон +150 мм;
- LiFePO4 12.8 В / 40 А·ч и солнечная панель 80 Вт по точным MPN baseline;
- GSM/LTE через исходящее MQTT/TLS, резерв HTTPS/TLS, два nano-SIM в режиме
  Dual SIM Single Standby и только `public APN` в пилоте;
- LoRa `RU868` на каждом изделии; будущий `EU868` профиль в пилот не прошивается;
- BLE используется для локальной настройки, диагностики и безопасного обновления;
- корпус первого EVT-20 лота — вакуумное литьё; 3D-печать остаётся управляемым
  резервом, а ТПА — только комплектом исходных данных;
- сервер — «Мухоед» для Windows 11 и Ubuntu 24.04; Android ведётся отдельным треком.

## Текущий статус

Общий статус аппаратного выпуска: `BLOCKED / EVT NOT RUN`. Наличие документов и
успешные структурные проверки не являются завершённым аппаратным EVT.

| Область | Принято | Остаётся открытым |
|---|---|---|
| PCB-MAIN | 186-net authority; `JLC06161H-3313`; 50 Ω `0.1509 mm`; 90 Ω `0.1537/0.2032 mm`; 1023 trace items; 8 zones | оставшаяся трассировка, final SI, DRC, CAM, checkout DFM, STEP/service review, Review B |
| PCB-PWR | `DIM-003` `18/18`; 90×60×1.6 mm; H1-H4 M3 NPTH; `JLC04161H-3313A`; 70/35 µm copper; ≥18 µm hole wall; расчётная силовая геометрия; 4 принятых сегмента, включая `VBAT_RAW` | применение принятого `REV_GATE` candidate 004, input-protection qualification, оставшаяся трассировка, rail-drop/load-step/fault/+70 °C evidence, DRC, CAM, checkout DFM, Review B |
| PCB-MIC | copper subgate и стандартный двухслойный/PCBA процесс; 9/9 engineering closures | first-panel bore/acoustic inspection, CAM comparison, общий Review B и physical EVT |
| Жгуты | 38 проводников; точные wire MPN; длины `275/440/330 mm` с 10% запасом; 16/16 engineering closures | first-off crimp height/pull, 100% continuity/polarity/cross-short/resistance, installed-route SI/thermal/cold/strain EVT |
| BOM | QG-1 PASS; technical QG-2 PASS; per-lot 4/10/20 и aggregate 41-station procurement plan | коммерческий заказ и hardware manufacturing release |
| Внешние ответы | бывшие wait gates закрыты `85/85` инженерным EVT baseline | factory e-mail не требуется; реальные checkout parser/DFM ошибки останавливают заказ и идут через ECO |

Закрытия в response-регистрах принадлежат проектной инженерии по решению
заказчика и не выдаются за ответы фабрик. Стандартные процессы приняты только для
тестовой EVT-программы; при переходе в серию повторяются supplier/site, tooling,
DFM и process qualification.

PCB-PWR `VBAT_RAW` routing 003 применён и прошёл application gate. Следующий
`REV_GATE` routing 004 принят человеком и остаётся отдельным неприменённым
кандидатом до точного application gate.

Серверная часть включает обновлённую обработку подтверждённого класса «лютый» в
трёх проверенных аудиосценариях «Мухоеда»; это программное изменение не закрывает
аппаратные гейты.

## Контроль выпуска

Каждый поставочный объект проходит два последовательных контроля:

1. `QG-1 Completeness` — наличие, версия, взаимные ссылки и контрольная сумма.
2. `QG-2 Technical` — ERC/DRC, сборка, тест, визуальная проверка или измерение.

Основные команды:

```bash
python tools/validate_evt_pre_20_bom_qg1.py
python tools/audit_evt_pre_20_bom_qg2.py --strict
python tools/audit_evt_engineering_manufacturing_baseline_rev_a.py
python tools/audit_evt_pre_20_hardware_release.py
python tools/kicad_native_gate.py
```

Gerber, прошивки, бинарники, корпуса и серверный релиз не считаются выпущенными,
пока их собственные гейты не имеют требуемые evidence. Hardware-only gate не
блокируется Android/server/обычным firmware, кроме явных аппаратных зависимостей.

## Навигация

- [`BRANCH_SCOPE.md`](BRANCH_SCOPE.md) — границы ветки и актуальный срез.
- [`config/EVT_PRE_20_BASELINE.yaml`](config/EVT_PRE_20_BASELINE.yaml) — машинно-читаемая конфигурация.
- [`docs/DELIVERABLE_REGISTER_EVT_PRE_20.csv`](docs/DELIVERABLE_REGISTER_EVT_PRE_20.csv) — реестр поставки и gates.
- [`docs/OPEN_INPUTS_FOR_FREEZE.csv`](docs/OPEN_INPUTS_FOR_FREEZE.csv) — входные данные, блокирующие финальный выпуск.
- [`hardware/EVT_PRE_20_BOM_POLICY_REV_A.md`](hardware/EVT_PRE_20_BOM_POLICY_REV_A.md) — BOM и количества.
- [`hardware/EVT_PROGRAM_2X20_PLUS_1_PROCUREMENT_REV_A.csv`](hardware/EVT_PROGRAM_2X20_PLUS_1_PROCUREMENT_REV_A.csv) — aggregate-план на 41 станцию.
- [`hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md`](hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md) — hardware release gate.
- [`manufacturing/README.md`](manufacturing/README.md) — маршрут сборки, traceability и EOL.
- [`tests/EVT_MASTER_PLAN.md`](tests/EVT_MASTER_PLAN.md) — последовательность EVT.
- [`android/README.md`](android/README.md) — отдельный Android-трек.

## Наследование

Ветка создана от `evt` commit `2ec1d6dc81e3a16b7c127f1bbfe03f3945a72c45`.
Поставочные материалы `evt-mb` сюда не переносятся. Общие проверенные изменения
могут отдельно продвигаться в `develop` и `main`. Макетная плата 70×90 мм и
WeAct STM32U585CIU6 не являются производственной документацией EVT-PRE-20.
