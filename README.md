# Дионея / РС ЗС-БПЛА — EVT-PRE-20

Эта ветка содержит инженерную базу одного управляемого предсерийного лота
`EVT-20`. Актуальная программа закупки — два отдельных набора по 20 станций и
один стендовый образец, всего 41 станция. Закупочная выдача имеет два явно
разделённых варианта: 21 станция (один EVT-20 плюс стендовая) и 41 станция
(два EVT-20 плюс стендовая). Расчёты для 4 и 10 станций сохранены для
сравнения, но не являются разрешением закупки.

## Зафиксированный baseline

- производственная единица управления: `EVT-20`, 20 изделий;
- программа: `2 × EVT-20 + 1 bench`, 41 станция;
- варианты закупки: `21 = EVT-20 + bench` и `41 = 2 × EVT-20 + bench`;
- резервы: два независимых EVT-20 пула; стендовый образец не создаёт третий;
- серийные номера: первый лот `DIO-EVT-001…020`, второй `DIO-EVT-021…040`,
  стендовый образец `DIO-EVT-B01`; индивидуальные travellers заполняются до
  начала сборки;
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
| PCB-MAIN | 8L COMPLETE-105 Rev.B; `JLC08161H-3313`; 5969 route segments; 251 components; KiCad DRC 0 errors / 0 unconnected | selected-stack impedance/return-path review, POFV confirmation, Altium antenna-warning disposition, checkout DFM, Review B |
| PCB-PWR | `DIM-003` `18/18`; 90×60×1.6 mm; H1-H4 M3 NPTH; `JLC04161H-3313A`; 70/35 µm copper; ≥18 µm hole wall; расчётная силовая геометрия; точный ECO-002 применён, 14 принятых сегментов; application gate PASS | input-protection qualification, оставшаяся трассировка, rail-drop/load-step/fault/+70 °C evidence, DRC, CAM, checkout DFM, Review B |
| PCB-MIC | copper subgate и стандартный двухслойный/PCBA процесс; 9/9 engineering closures | first-panel bore/acoustic inspection, CAM comparison, общий Review B и physical EVT |
| Жгуты | 38 проводников; точные wire MPN; длины `275/440/330 mm` с 10% запасом; 16/16 engineering closures | first-off crimp height/pull, 100% continuity/polarity/cross-short/resistance, installed-route SI/thermal/cold/strain EVT |
| BOM | QG-1 PASS; technical QG-2 PASS; per-lot 4/10/20 и aggregate 41-station procurement plan | коммерческий заказ и hardware manufacturing release |
| Внешние ответы | бывшие wait gates закрыты `85/85` инженерным EVT baseline | factory e-mail не требуется; реальные checkout parser/DFM ошибки останавливают заказ и идут через ECO |

Закрытия в response-регистрах принадлежат проектной инженерии по решению
заказчика и не выдаются за ответы фабрик. Стандартные процессы приняты только для
тестовой EVT-программы; при переходе в серию повторяются supplier/site, tooling,
DFM и process qualification.

PCB-PWR `VBAT_RAW` routing 003 и `REV_GATE` routing 004 применены и прошли
точные application gates. Точный `PCB-PWR-BUCK-POWER-STAGE-ECO-002` теперь
применён к authoritative board; активная плата содержит 14 принятых сегментов,
ноль vias и ноль zones. Commit-bound application gate прошёл CI #692,
PCB-PWR Schematic #103 и PCB Native #357. Физический first-article +70 °C,
оставшаяся трассировка и все выпускные гейты открыты.

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
- [`docs/EVT_PRE_20_LONG_RANGE_ACOUSTIC_HEAD_TRADE_STUDY_REV_A.pdf`](docs/EVT_PRE_20_LONG_RANGE_ACOUSTIC_HEAD_TRADE_STUDY_REV_A.pdf) — физика дальнего акустического тракта, сравнение микрофонов, отражателей и резонаторов, план прототипа LR-1.
- [`hardware/EVT_PRE_20_BOM_POLICY_REV_A.md`](hardware/EVT_PRE_20_BOM_POLICY_REV_A.md) — BOM и количества.
- [`hardware/EVT_PROGRAM_PROCUREMENT_VARIANTS_REV_A.csv`](hardware/EVT_PROGRAM_PROCUREMENT_VARIANTS_REV_A.csv) — реестр вариантов закупки 21 и 41.
- [`hardware/EVT_PROGRAM_1X20_PLUS_1_PROCUREMENT_REV_A.csv`](hardware/EVT_PROGRAM_1X20_PLUS_1_PROCUREMENT_REV_A.csv) — вариант на 21 станцию.
- [`hardware/EVT_PROGRAM_2X20_PLUS_1_PROCUREMENT_REV_A.csv`](hardware/EVT_PROGRAM_2X20_PLUS_1_PROCUREMENT_REV_A.csv) — полный план на 41 станцию.
- [`hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md`](hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md) — hardware release gate.
- [`manufacturing/README.md`](manufacturing/README.md) — маршрут сборки, traceability и EOL.
- [`tests/EVT_MASTER_PLAN.md`](tests/EVT_MASTER_PLAN.md) — последовательность EVT.
- [`android/README.md`](android/README.md) — отдельный Android-трек.

## Наследование

Ветка создана от `evt` commit `2ec1d6dc81e3a16b7c127f1bbfe03f3945a72c45`.
Поставочные материалы `evt-mb` сюда не переносятся. Общие проверенные изменения
могут отдельно продвигаться в `develop` и `main`. Макетная плата 70×90 мм и
WeAct STM32U585CIU6 не являются производственной документацией EVT-PRE-20.

## Финальный производственный комплект REV_D7

Финальная документальная выдача для закупки и производства EVT-PRE-20 находится в
[`releases/EVT_PRE_20_REV_D7`](releases/EVT_PRE_20_REV_D7/README.md). PCB-MAIN Rev.B
зафиксирована как восьмислойная. Фабричный архив содержит Altium/CAM для PCB-MAIN,
PCB-PWR и PCB-MIC без KiCad. Физические first article, EOL и EVT заполняются после
изготовления и не отмечены как выполненные заранее.
