# EVT-PRE-20 — инвентаризация и готовность к переносу в Altium Designer

Дата проверки: 2026-10-14. Ветка: `evt-pre-20`. Контрольный исходный commit: `4314cd6dddd189880b43a160c550e225acd31fc4`.

**Статус: CONVERSION NOT STARTED / NO ALTIUM CAD / NOT FOR MANUFACTURE.** Этот документ фиксирует исходную базу и входные условия переноса. Он не является результатом импорта, проверкой эквивалентности или разрешением на производство. Пока подтверждённого Altium-проекта нет, действующие KiCad-исходники остаются электрическим CAD source of record. Все прежние запреты на выпуск сохраняются.

## Инвентаризация исходников

Полный путь к каждому проекту: `hardware/kicad/native/<BOARD>/`. По дереву указанного commit там 76 файлов: 3 `.kicad_pcb`, 3 `.kicad_pro`, 16 `.kicad_sch`, 3 `.kicad_sym`, 40 локальных `.kicad_mod`, 2 `.kicad_dru` и 9 дополнительных файлов (таблицы библиотек, манифест/метаданные, legacy cache). Ветка целиком не содержит `.PrjPcb`, `.SchDoc`, `.PcbDoc`, `.OutJob`, `.SchLib` или `.PcbLib`.

| Плата | Проект, плата, схемы | Локальные библиотеки и правила | Формат платы в заголовке |
| --- | --- | --- | --- |
| PCB-MAIN | `PCB-MAIN.kicad_pro`; `PCB-MAIN.kicad_pcb`; `PCB-MAIN.kicad_sch` и дочерние `PCB-MAIN_01_POWER`, `02_MCU`, `03_AUDIO`, `04_GNSS`, `05_CELLULAR`, `06_LORA`, `07_BLE`, `08_STORAGE_SENSORS`, `09_CONNECTORS_TEST` (`.kicad_sch`, всего 10 листов) | `libs/DioneyaMain.kicad_sym`, 29 `.kicad_mod`, `fp-lib-table`, `sym-lib-table`; отдельного `.kicad_dru` нет | `20221018` |
| PCB-PWR | `PCB-PWR.kicad_pro`; `PCB-PWR.kicad_pcb`; `PCB-PWR.kicad_sch` и `PCB-PWR_01_INPUT_PROTECTION`, `02_3V8_MODEM`, `03_3V3_DIGITAL`, `04_AUX_HARNESS` (`.kicad_sch`, всего 5 листов) | `libs/DioneyaPWR.kicad_sym`, 9 `.kicad_mod`, `PCB-PWR.kicad_dru`, обе таблицы библиотек | `20241229`, `generator_version 9.0` |
| PCB-MIC | `PCB-MIC.kicad_pro`; `PCB-MIC.kicad_pcb`; `PCB-MIC.kicad_sch` (1 лист) | `libs/Dioneya.kicad_sym`, 2 `.kicad_mod`, `PCB-MIC.kicad_dru`, обе таблицы библиотек | `20241229`, `generator_version 9.0` |

Git blob IDs основных исходников на контрольном commit (это Git SHA-1, не SHA-256 производственного выпуска):

| Плата | `.kicad_pro` | корневой `.kicad_sch` | `.kicad_pcb` |
| --- | --- | --- | --- |
| PCB-MAIN | `7d71aaf4cf12647a6c565e8cdd5e8ba685025138` | `91be42fe715bc46c6eb5722a36d687aa5596cdb0` | `f1a17e4e536b378d18515cfa487c46794fbe4eff` |
| PCB-PWR | `d4c437576bbd85b8d1bbb54437b838bf1d5dfc5c` | `fa6908a0925cf48326b6bbfe5381fbb5bfb9ed8d` | `5b54725aa94108eeee2f204931c68740e11525a5` |
| PCB-MIC | `12f011e583ff99585b164014581acd5cfb0663cc` | `fbdd5cff0bbb38579b66abe96fee89155f84f8da` | `d401d4ea3e15b1a101d7d0264bafe7e04c225c86` |

Все исходные файлы остаются на прежних путях без перемещения, удаления или перезаписи; история Git сохраняется. При будущем переносе Altium-файлы нужно добавлять рядом, в отдельный каталог `hardware/altium/<BOARD>/`, после проверки.

## Доступность инструментов и ограничение формата

- Доступны GitHub API, дерево файлов, исходные документы и прежние CI-доказательства. Workflow `.github/workflows/pcb-engineering-snapshot.yml` использует контейнер KiCad `9.0.9`; проверяемый инженерный KiCad-снимок находится в `hardware/manufacturing/engineering-snapshot/EVT-PRE-20_2026-09-24/` и прямо помечен **NOT FOR MANUFACTURE**.
- Локальная командная среда не запустилась до исполнения команд из-за ошибки инициализации, связанной с заблокированным резервным диском `D:`. Этот диск не используется для проекта. Наличие локального Altium Designer, лицензии, расширения KiCad Importer и возможность запуска KiCad CLI в текущем рабочем сеансе **не подтверждены**.
- [Документация Altium по импорту KiCad](https://www.altium.com/documentation/altium-designer/design-tools-interfacing/kicad-import) описывает Import Wizard, импорт схем/PCB/библиотек и создание `.PrjPcb`; для работы требуется расширение KiCad Importer. [Таблица совместимости Altium](https://www.altium.com/documentation/altium-designer/interfacing-to-other-design-tools-overview) указывает импорт KiCad **до версии 8.x**. Поэтому прямой импорт плат PCB-PWR и PCB-MIC, записанных KiCad 9, нельзя считать поддержанным без испытания на конкретной версии Altium. Подмена номера версии в заголовке файла не является проверкой совместимости.
- [Output Jobs](https://www.altium.com/documentation/altium-designer/preparing-for-manufacture/output-jobs) позволяют настроить производственные выходы после появления проверенного Altium-проекта. На текущем шаге ни один такой выход из Altium не был создан.

## Контрольный порядок конверсии

1. Зафиксировать точный source commit и SHA-256 каждого используемого KiCad-файла; не использовать устаревший инженерный снимок как текущий manufacturing release. На рабочей копии открыть каждый проект в KiCad 9 и получить свежие ERC, DRC, netlist/pin-net map, footprint/pad map, BOM, координаты, стек, контур, отверстия и CAM-эталон.
2. На рабочей станции с установленным Altium Designer и KiCad Importer сначала выполнить пробный импорт PCB-PWR и PCB-MIC формата KiCad 9, сохранив полный import log и явное сопоставление слоёв. Если конкретная версия не читает формат, определить и документировать проверяемый путь совместимости; исходники в репозитории не понижать и не переписывать.
3. Импортировать три проекта отдельно, включая все дочерние схемы, локальные символы и footprint-библиотеки. Сохранить реальные `.PrjPcb`, `.SchDoc`, `.PcbDoc`, `.SchLib`/`.PcbLib` и импортные журналы. Не создавать пустые файлы с расширениями Altium вместо результатов CAD.
4. Сравнить KiCad и Altium по полному набору refdes–pin–net (с количеством и именами цепей), отображению выводов в номера площадок, вариантам/DNP и BOM MPN; каждое расхождение зарегистрировать и устранить. Проверить синхронизацию SchDoc ↔ PcbDoc отдельно.
5. Сравнить геометрию и технологию: габариты и контур, монтажные и NPTH/PTH отверстия, координаты/повороты/стороны компонентов, pad shapes, via/trace/zone, маску/пасту, keepout, стек и толщины/типы меди. В особенности сохранить MAIN 6 слоёв и RF 50/90 Ω, PWR 4 слоя и силовые правила, MIC 2 слоя, акустическое отверстие и запрет пасты/маски в акустическом тракте.
6. Для PCB-MAIN отдельно проверить cellular/GNSS/LoRa RF, BLE antenna keepout, USB differential pair, stitching/return path и разделение `GND_MODEM`, `GND_DIGITAL`, `GND_MIC`. Для PCB-PWR проверить путь `J1 → F1 → TVS → LM74700/CSD18540 → INA226/shunt → VBAT_SYS → LMR60440`, bootstrap/VCAP, Kelvin sense, FB, токовые полигоны и тепловые переходы. Для PCB-MIC проверить T5838, локальный return path, порт и крепёж.
7. Выполнить Altium compile/ERC и DRC; закрыть реальные ошибки и unrouted. Сверить Altium Gerber/NC Drill/IPC-356 с Altium PCB в CAM viewer. Создать и прогнать `.OutJob` для Gerber X2 или RS-274X, разделённых plated/non-plated drill, IPC-D-356, BOM/AVL, pick-and-place, сборочных/фабричных чертежей, stackup и STEP. Записать SHA-256 и commit каждого выходного комплекта.
8. Получить независимые Review A и Review B и выполнить действующий `hardware/EVT_BUILD_RELEASE_GATE_REV_A.md`. Только после этого менять source-of-record на Altium и выдавать пакет фабрике.

## Текущее состояние gate

Согласно `hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json`, `hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json` и `hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json`, `manufacturing_release=false` для всех трёх плат. У MAIN и PWR остаются трассировка/DRC и Review B; у MIC Review B и физико-технологические пункты открыты. Эти статусы прочитаны из репозитория, а не повторно измерены CAD-инструментом в этом сеансе. Эквивалентность KiCad ↔ Altium и готовность к производству **не подтверждены**.

## Требуемый итоговый архив EVT-PRE-20

После завершения конверсии и release gate выдать один ZIP-архив, например `EVT-PRE-20_RevA_Altium_Production_<commit>.zip`, и записать его SHA-256. В архиве предусмотреть по отдельному каталогу для PCB-MAIN, PCB-PWR и PCB-MIC:

- `altium/`: проверенные `.PrjPcb`, все `.SchDoc`, `.PcbDoc`, локальные `.SchLib`/`.PcbLib`, рабочий `.OutJob` и import/compile logs;
- `fabrication/`: Gerber, plated/non-plated NC Drill, IPC-D-356, stackup/impedance, fabrication drawing/notes, board-only STEP и CAM comparison;
- `assembly/`: BOM/AVL с MPN и DNP, pick-and-place, TOP/BOTTOM assembly drawings, paste/stencil data, варианты сборки и специальные монтажные указания;
- `verification/`: KiCad↔Altium pin-net/footprint/geometry comparison, ERC/DRC, RF/power review, Review A/B, DFM, решения по всем расхождениям;
- `kicad_source/`: неизменённая копия каждого исходного проекта и его локальных библиотек из зафиксированного source commit, с указанием исходных путей.

В корне архива: `README.md` со статусом разрешения к производству, списком трёх плат и ревизий, commit исходников и Altium-проекта, перечнем версий CAD/импортера, `SHA256SUMS` для всех файлов и контрольной суммой самого ZIP вне архива. Историю изменений сохранять в Git: архив является поставочным снимком, не заменяет репозиторий. Собирать или маркировать архив как производственный до закрытия всех gate нельзя.
