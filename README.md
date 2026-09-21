# Дионея / РС ЗС-БПЛА — EVT-PRE-20

Эта ветка содержит инженерную базу предсерийного EVT с выбранной партией 20 станций. Расчёты для 4 и 10 станций сохранены для сравнения и контролируемого перепланирования.
Текущий контрольный срез: `EVT-PRE-20 Rev.A v0.3`, дата 14.09.2026.

## Зафиксированный baseline

- количество: выбран `EVT-20`, 20 изделий; активирован диапазон `DIO-EVT-001`…`DIO-EVT-020`; столбцы 4 и 10 изделий не являются разрешением закупки;
- собственная PCB станции, без отладочной платы WeAct в составе изделия;
- вычислительная платформа: `STM32U585VIT6Q`, корпус `LQFP100_14x14`;
- акустическая геометрия: четыре одинаковых микрофона, схема 3+1, база 120 мм, верхний микрофон +150 мм;
- питание: LiFePO4 12,8 В, 40–60 А·ч; солнечная панель 60–80 Вт;
- основной канал: GSM/LTE через исходящее MQTT/TLS, резерв HTTPS/TLS;
- пилот использует обычные SIM МТС, МегаФон, Билайн, T2/Tele2 либо SIM, предоставленную оператором ГЛОНАСС; публичный IP и API оператора не требуются;
- PCB содержит два nano-SIM слота с режимом Dual SIM Single Standby; пилот использует только профили `public APN`;
- резервный канал: LoRa `RU868` на каждом изделии выбранного EVT-лота; допустимые окна пилота 864-865 и 868,7-869,2 МГц;
- общая PCB сохраняет возможность будущего профиля `EU868`, но он не входит в пилотную партию;
- BLE: локальная настройка, диагностика и безопасное обновление;
- корпус: для выбранного лота из 20 изделий принято вакуумное литьё; 3D-печать является условным резервом на те же 20 изделий, а для ТПА готовится отдельный комплект исходных данных без изготовления пилотной оснастки;
- сервер: «Мухоед», развёртывание на Windows 11 и Ubuntu 24.04;
- Android: отдельный трек, не смешанный с firmware станции.

## Статус

`OPEN / NOT RUN`.

Создание ветки и документов не является аппаратным EVT. Статус `PASS` допускается только после изготовления, сборки и сохранения первичных измерений.

Входной набор PCB-MAIN синхронизирован с проверенным authority-срезом:
`MAIN-AUTH-001…011` закрыты, native-схема прошла Review A, а PCB-MAIN
имеет частично разведённый engineering-кандидат. Ограниченные механические ECO
`PCB-MAIN-MECH-ECO-001/002` приняты и применены: конфликтная геометрия внутри
`MAIN-AUTH-011`, включая J_PWR/J6/H1, устранена; сами ECO не давали
разрешения на трассировку.
После этого контролируемый функциональный repack
зафиксировал координаты всех 225 незаблокированных позиций, а 169 ранее
screening-проверявшихся установленных пассивов получили явные контролируемые
courtyard (184 с учётом DNP). Независимый строгий 2D clearance-аудит теперь
показывает 227/227 установленных footprint с courtyard и нулевые пересечения
компонентов, монтажных исключений и U.FL tool-зон; отдельный layout-аудит также
не допускает чужие функциональные группы в locked RF/audio-зоны и BLE antenna
keepout. Отдельный воспроизводимый pre-route manifest теперь однозначно
классифицирует все 186 native nets: 7 RF 50-ohm цепей, четыре независимые USB
дифференциальные пары, домены возврата и критичные ветви питания модема проходят
независимый аудит. Публичный `JLC06161H-3313` задаёт ограниченную
engineering-геометрию RF/USB; финальная production-геометрия остаётся
заблокированной до согласования job-specific stackup. Для этого подготовлен
машинно-проверяемый одинаковый запрос двум независимым фабрикам и пустой
22-строчный реестр ответов; принято `0/2` ответов, конструкция не выбрана.
В authoritative PCB приняты ограниченные ground-domain, hard-signal, OctoSPI,
семисетевой RF P0, оба RF-remediation subgate, точная placement-дельта
`R91/R92`, MCU-side USB-пара, cellular-modem USB-пара и cellular-fixture
USB-пара. Текущий successor содержит 738 сегментов,
285 via, 4 copper zones и
4 rule areas; SHA-256
`2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273`.
`PCB-MAIN-RF-RETURN-001` добавлен первым как точный кандидат с локальной
`GND_MODEM` L2-зоной. Затем точная принятая дельта
`PCB-MAIN-GNSS-RF-ECO-001` оставила U9/J9 на месте, переставила только FL1/C64
и сократила пост-SAW участок до 1.327 mm, не стирая cellular-зону.
Детерминированная композиция, строгий clearance и commit-bound combined KiCad 9
gate прошли. PCB Native `#277` подтвердил ноль новых DRC errors, отсутствие
регрессии `429` unconnected items и полное L2-покрытие всех `623` cellular и
`406` GNSS контрольных точек; bounded repeat RF/SI return-path review закрыт.
Для следующего USB-подэтапа `PCB-MAIN-USB-PLACEMENT-ECO-001` переносит только
неразведённые `R91/R92`. Решение принято и точный кандидат применён к
authoritative PCB; вся медь и RF-remediation predecessor сохранены.
Commit `ad3745e7` прошёл CI `#554` и PCB Native `#281`: новых DRC errors нет,
unconnected остаётся `429`, strict clearance — PASS. Точный application commit
`1f8c0bad` прошёл CI `#557` и PCB Native `#284`: новых ошибок нет,
`429→429` unconnected. Placement subgate закрыт; USB-трассировка и финальная
impedance-геометрия пока не разрешены. Следующий ограниченный кандидат
`PCB-MAIN-USB-SOURCE-ROUTING-001` соединяет только MCU-side пару
`U1.71/U1.70 → R91.1/R92.1`: 13 сегментов `F.Cu`, без signal-via, оба плеча
по `4.178827774173 mm`, minimum pair gap `0.2032 mm`. Для освобождения
единственного clearance-clean канала предложение локально переносит один
`GND_DIGITAL` via и его сегмент без изменения геометрии via или ground-domain
топологии. Proposal commit `f4ed1a4d` прошёл static gate, CI `#559` и PCB
Native `#286`: violations `232→232`, новых errors нет, unconnected `429→427`.
Machine gate закрыт; решение `ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE` записано,
и точный кандидат применён к authoritative PCB. Точный application commit
`6c27d3ae` прошёл CI `#562` и PCB Native `#289`:
violations `232→232`, новых errors нет, unconnected `429→427`. MCU-source
application gate закрыт; на этом этапе main-connector и fixture USB оставались
отдельными незакрытыми сегментами. Следующий bounded proposal
`PCB-MAIN-USB-CELL-MODEM-ROUTING-001` закрывает BG95-side участок
`U8.9/U8.10 → R39.1/R40.1`: шесть сегментов F.Cu, без via, оба плеча по
`4.765484866498 mm` над непрерывной `GND_MODEM` L2-зоной. Статическая
регенерация, точное совпадение длин и minimum pair gap `0.2032 mm` проходят.
Proposal `5c73ffe5` прошёл CI `#564` и PCB Native `#291`: violations
`232→232`, новых errors нет, unconnected `427→425`. Main-connector отдельно
удерживается до подтверждённой фабрикой via/annular/clearance-геометрии:
официальная однорядная распиновка J11 корректна, но стандартные `0.5/0.3 mm`
via не дают clearance-clean escape между чередующимися D+/D- контактами с
шагом 0.5 mm. Точный cellular-modem кандидат принят и применён; application
commit `4c9a2a85` прошёл CI `#566` и PCB Native `#293`: violations `232→232`,
новых errors нет, unconnected `427→425`. Этот application gate закрыт.
Следующий кандидат `PCB-MAIN-USB-CELL-FIXTURE-ROUTING-001` соединяет
`R39/R40.2` через U26 с `TP_CELL_USB.2/.3`: 27 сегментов, две
`0.50/0.30 mm` signal-via, точно равные основные пути
`76.293814073931 mm` и ESD-шунты `1.007782218537 mm`. Proposal commit
`11af5c9d` прошёл CI `#568` и PCB Native `#295`: violations `232→232`,
новых errors нет, unconnected `425→421`. Точный кандидат принят и применён в
commit `8acd6579`; gate-source commit `c48217af` прошёл CI `#570` и PCB Native
`#297` с теми же `232→232`, без новых errors и с `425→421` unconnected.
Artifact `10615386189` имеет digest
`sha256:39b47e938a23aece20d62a269352334af1ca3d5b0e3f37d156726eac840eaabd`.
Application gate закрыт. Только main-connector USB-сегмент остаётся
DFM-заблокирован до job-specific via/drill/annular/clearance evidence или
отдельного локального ECO.
Отдельно подготовлен ограниченный запрос для будущего
выбранного сборщика по DFM/трафарету `U2/U25/U26/U9` и пустой 14-строчный реестр: принято
`0/14` ответов, сборщик и процесс не выбраны, паста U9 и производственный выпуск
не разрешены. Это закрывает только перечисленные bounded subgates:
оставшаяся трассировка, финальный SI/PI review, финальный KiCad DRC, STEP-проверка
высот/доступов, CAM/DFM и Review B остаются заблокированными. Подписанный
электрический Review A сохраняется. Полный native source set PCB-MIC и
PCB-PWR также отслеживается и проверяется в CI: все девять обязательных
`.kicad_sch/.kicad_pcb/.kicad_pro` файлов присутствуют. Плата PCB-PWR остаётся
неразведённым электрическим placement-canvas, но `DIM-003` принят для EVT:
контур `90 x 60 mm`, толщина `1.6 +/-0.16 mm`, четыре круглых NPTH M3 H1-H4,
сервисные зоны J1/J2, DFT datum и консервативная STEP-огибающая связаны с native
PCB. Реестр принят `18/18`; слоты не применяются, а допуски обеспечиваются
зазором крепежа и diamond pin оснастки. Это разрешает механический вход в
трассировку EVT, но требует повторной проверки с серийным корпусом и не снимает
силовые, DRC, DFM, Review B или производственный запрет. Для PCB-PWR выбран
стандартный EVT ordering profile `JLC04161H-3313`, 1.6 mm, outer 2 oz / inner
1 oz. Машинно-проверяемый stackup/copper-запрос сохраняет все 24 строки пустыми
(`0/24`, `0/2`) как канал job-specific DFM-отклонений и не блокирует
engineering-routing. Официальный публичный `JLC04161H-3313` и консервативный
35 µm / ΔT 10 °C screen
задают bounded EVT engineering routing basis: 4.0 mm для 5 A, 3.0 mm для 4 A,
2.1 mm для локальных switch-node и 0.5 mm для 0.3 A. Все 31 native-сети
покрыты отдельным числовым rule manifest. Он разрешает только следующий
engineering-кандидат и не меняет `0/24`; выбранный профиль заказа не закрывает
job DFM, via-current, +70 °C evidence, DRC, Review B или производство. Отдельный
строгий подгейт PCB-PWR теперь подтверждает `44/44` fitted-courtyard,
минимальный зазор `0.22 mm` при требовании `0.20 mm` и ноль конфликтов. Для H1-H4
проверены D10 fitted-body и D8 copper exclusions: ноль конфликтов и минимальный
запас `0.53 mm`. Серийная механика, routing, STEP с точными моделями компонентов
и Review B остаются открыты. После
ограниченного copper ECO повторный PCB-MIC Review A подписан
`PASS` по commit `e17a86bc`, а copper-return subgate Review B принят по commit
`7aeec13a` и PCB SHA-256 `a292a6ec…e4031`. Контролируемый manufacturing-handoff
packet готов, но все ответы фабрики и сборщика остаются `PENDING`. Это не разрешает производство:
PCB-MAIN и PCB-PWR routing/Review B, оставшиеся PCB-MIC Review B gates и
технический BOM QG-2 контролируется отдельно; Gerber и аппаратный
производственный выпуск заблокированы. Firmware
сохраняет статус `TARGET_PORT_REQUIRED`.
На PCB-PWR уже контролируются J1 `Molex 43045-0213`, U1 `LM74700-Q1`,
U2 `INA226`, Q1 `CSD18540Q5B`, RSH1 `WSK2512R0100FEA`, U3/U4
`LMR60440`, L1/L2 `XAL7030-472MEC`, U5 `TPS7A20` и J2
`Molex 43045-1202`. Все 49 пассивных, net-tie и DFT-позиций PCB-PWR имеют
единый per-reference authority с точным candidate MPN/идентификатором, корпусом,
состоянием установки и pin/net-привязкой; генератор BOM и независимый QG-2 читают
этот источник без скрытых MPN-констант. Производственный выпуск кандидатов,
финальная механика и job-specific силовая геометрия, фактическая трассировка
PCB-PWR, Review B и аппаратные доказательства остаются открыты.

Для внутренних жгутов контролируется 38-проводная предварительная раскладка.
Отдельный capability-пакет теперь задаёт 16 обязательных ответов будущего
изготовителя по площадке, supplier assembly MPN, температуре, точному wire AVL,
оснастке и численным параметрам обжима, FAI, трассируемости и цене. Принято
`0/16`: до возврата ответов и закрытия `DIM-001`, `DIM-012` и финального маршрута
в корпусе численные длины, выбор изготовителя и производство жгутов остаются запрещены.

## Контроль выпуска

Каждый поставочный объект проходит два последовательных контроля:

1. `QG-1 Completeness` — наличие, версия, взаимные ссылки, контрольная сумма.
2. `QG-2 Technical` — ERC/DRC, сборка, тест, визуальная проверка или измерение по типу объекта.

Gerber, прошивки, бинарники, корпуса и серверный релиз не считаются выпущенными, пока оба контроля не отмечены `PASS` в реестре.
Отдельный hardware-only gate оценивает BOM, три PCB, механику, жгуты, DFM и
выбор закупочного лота без блокировки со стороны Android/server/обычного firmware.

## Навигация

- [`BRANCH_SCOPE.md`](BRANCH_SCOPE.md) — границы ветки.
- [`config/EVT_PRE_20_BASELINE.yaml`](config/EVT_PRE_20_BASELINE.yaml) — машинно-читаемая конфигурационная база.
- [`docs/DELIVERABLE_REGISTER_EVT_PRE_20.csv`](docs/DELIVERABLE_REGISTER_EVT_PRE_20.csv) — полный реестр комплекта и gates.
- [`docs/OPEN_INPUTS_FOR_FREEZE.csv`](docs/OPEN_INPUTS_FOR_FREEZE.csv) - входные данные заказчика, блокирующие финальный выпуск.
- [`protocols/CELLULAR_CONNECTIVITY_BASELINE.md`](protocols/CELLULAR_CONNECTIVITY_BASELINE.md) — SIM/APN и исходящая связь.
- [`hardware/DUAL_SIM_SINGLE_STANDBY.md`](hardware/DUAL_SIM_SINGLE_STANDBY.md) - двух-SIMная аппаратная архитектура и безопасное переключение.
- [`hardware/EVT_PRE_20_BOM_POLICY_REV_A.md`](hardware/EVT_PRE_20_BOM_POLICY_REV_A.md) - правила производственного BOM, формулы количества и двойной контроль QG-1/QG-2.
- [`hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md`](hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md) - независимый hardware design/purchase release gate без нерелевантных software-блокеров.
- [`config/cellular/dual_sim_apn_profiles.yaml`](config/cellular/dual_sim_apn_profiles.yaml) - машинно-читаемая политика SIM/APN failover.
- [`manufacturing/README.md`](manufacturing/README.md) — маршрут партии, traceability, provisioning и EOL.
- [`manufacturing/HOUSING_LOT_PLAN.csv`](manufacturing/HOUSING_LOT_PLAN.csv) - резерв ёмкости на 20 серийных номеров; активируется только ведущий диапазон выбранного лота 4, 10 или 20.
- [`tests/EVT_MASTER_PLAN.md`](tests/EVT_MASTER_PLAN.md) — последовательность и правила принятия EVT.
- [`docs/REQUIREMENTS_TRACEABILITY.csv`](docs/REQUIREMENTS_TRACEABILITY.csv) — требования, проверки и evidence.
- [`android/README.md`](android/README.md) — отдельный Android-трек.

## Наследование

Ветка создана от `evt` commit `2ec1d6dc81e3a16b7c127f1bbfe03f3945a72c45`.
Поставочные материалы `evt-mb` в эту ветку не включаются и не переносятся. Общие
проверенные изменения могут отдельно продвигаться в `develop` и `main`. Макетная плата
70×90 мм и WeAct STM32U585CIU6 не являются производственной документацией предсерийной партии.

Срез v0.3 выборочно синхронизирует только собственные Rev.A authority, схемные входы,
проверки и общие программные исправления из проверенного интеграционного дерева
`f3411e51938aa1423fdbaeeef9585aeea385c239`. Merge поставочных веток не выполнялся.
