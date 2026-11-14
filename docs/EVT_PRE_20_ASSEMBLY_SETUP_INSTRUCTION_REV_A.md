# Руководство по сборке и настройке станций Дионея EVT PRE 20

**Ревизия:** Rev A  
**Дата:** 16.10.2026  
**Комплект:** EVT-PRE-20 REV_D8  
**Назначение:** последовательность фабричной сборки, входного контроля, первичного включения и передачи станции на прошивку и EOL

## 1. Статус документа

RU: Руководство готово к применению для документарной подготовки и сборки EVT. Окончательные численные EOL-пределы фиксируются после измерений DIO-EVT-B01 и собранных станций. До фиксации обязательный параметр без утвержденного предела получает HOLD.

EN: This guide is released for EVT document preparation and assembly. Final numeric EOL limits are frozen after measurements on DIO-EVT-B01 and assembled stations. Until then, a mandatory parameter without an approved limit receives HOLD.

## 2. Входной контроль Incoming inspection

1. RU: Сверить номер комплекта, SHA-256 архивов, ревизию плат, BOM и разрешенные отклонения. EN: Verify bundle ID, archive SHA-256, PCB revisions, BOM and approved deviations.
2. RU: Проверить MPN, количество, упаковку, срок годности, ESD и MSL. EN: Check MPN, quantity, packaging, shelf life, ESD and MSL status.
3. RU: Изолировать несоответствующий материал и открыть NCR. EN: Segregate nonconforming material and open an NCR.
4. RU: Для плат использовать только Altium и CAM из папки 03 Платы. EN: Use only the Altium and CAM data from folder 03 Boards.

## 3. Конфигурация плат PCB configuration

| Узел Assembly | Основное решение Primary decision | Контроль Check |
|---|---|---|
| PCB-MAIN | Rev B, 8 медных слоев, Altium master | Stackup, impedance, DRC, Gerber X2, drill, PnP and assembly drawing |
| PCB-PWR | 4 медных слоя, Altium master | Power copper, protection, polarity, load test |
| PCB-MIC | 2 медных слоя, Altium master | Four identical boards, acoustic port, phase and cable identity |

## 4. Последовательность сборки Assembly sequence

1. RU: Назначить serial и traveller до начала работ. EN: Assign the serial number and traveller before work starts.
2. RU: Изготовить и принять PCB и PCBA по отдельному фабричному архиву Altium. EN: Fabricate and accept PCB and PCBA from the separate Altium factory archive.
3. RU: Выполнить AOI, визуальный контроль и требуемый X-ray. EN: Complete AOI, visual inspection and required X-ray.
4. RU: Проверить сопротивление шин на обесточенной плате. EN: Check rail resistance on the unpowered board.
5. RU: Подать первое питание через лабораторный источник с ограничением тока. EN: Apply first power through a current-limited laboratory supply.
6. RU: Изготовить жгуты, выполнить 100 процентов continuity, polarity и маркировку. EN: Build harnesses and complete 100 percent continuity, polarity and label checks.
7. RU: Установить PCB-MAIN, PCB-PWR, четыре PCB-MIC, антенны и коаксиальные кабели. EN: Install PCB-MAIN, PCB-PWR, four PCB-MIC boards, antennas and coaxial cables.
8. RU: Уложить четыре микрофонных жгута одинаковой длины, избыток оставить сервисной петлей. EN: Route four equal-length microphone harnesses and retain surplus as a service loop.
9. RU: Установить мембраны, уплотнения и вентиляционные элементы без загрязнения акустических портов. EN: Install membranes, seals and vents without contaminating acoustic ports.
10. RU: Проверить геометрию микрофонов и отсутствие механического натяга. EN: Verify microphone geometry and absence of mechanical strain.

## 5. Первичное включение Initial power up

1. RU: Батарею и солнечную панель держать отключенными. EN: Keep the battery and solar panel disconnected.
2. RU: Проверить полярность входа и предохранитель. EN: Verify input polarity and the fuse.
3. RU: Подключить GND и измерительные точки до активных сигналов оснастки. EN: Connect GND and sense points before active fixture signals.
4. RU: Записать пусковой ток, установившийся ток и напряжения 3V3, 3V8 и 1V8. EN: Record inrush current, steady-state current and the 3V3, 3V8 and 1V8 rails.
5. RU: При ограничении тока, перегреве, запахе или нестабильной шине немедленно снять питание и открыть NCR. EN: Remove power and open an NCR after current limit, overheating, odor or an unstable rail.

## 6. Передача на прошивку Handoff to programming

RU: Передавать станцию только с traveller, результатами AOI и X-ray, измерениями сопротивлений и первого питания, перечнем отклонений и идентификаторами плат. Прошивка выполняется по документу `EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D` и только файлами кандидата 2026101601.

EN: Transfer the station with its traveller, AOI and X-ray results, resistance and first-power measurements, deviation list and PCB identities. Programming follows `EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D` and uses only candidate 2026101601 files.

## 7. Записи и критерий перехода Records and gate

RU: Для каждого шага фиксируют оператора, дату, средство измерения, срок калибровки, ревизию процедуры, результат и SHA-256 evidence. Пустое обязательное поле блокирует PASS. После ремонта повторяют затронутую проверку и полный регрессионный EOL.

EN: Record operator, date, instrument, calibration validity, procedure revision, result and evidence SHA-256 for every step. A blank mandatory field blocks PASS. After rework, repeat the affected check and the complete regression EOL.
