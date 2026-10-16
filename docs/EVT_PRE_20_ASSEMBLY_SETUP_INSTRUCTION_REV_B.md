# Руководство по сборке, первому включению и передаче на EOL Дионея EVT-PRE-20

**Документ:** EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_B  
**Ревизия:** Rev B  
**Дата:** 16.10.2026  
**Комплект:** EVT-PRE-20 REV_D10  
**Статус:** RELEASED FOR EVT ASSEMBLY; PHYSICAL EXECUTION AND LIMIT FREEZE OPEN  
**Назначение:** подробная сборка 40 полевых станций и одной стендовой станции B01 с контролем каждой операции

## 1. Основная конфигурация Baseline configuration

| Узел Assembly | Решение Baseline | Контроль Control |
|---|---|---|
| PCB-MAIN | Rev B, 8 copper layers, Altium master | DFM, stackup, impedance, DRC, AOI/X-ray and first article |
| PCB-PWR | 4 copper layers, Altium master | protection, polarity, power load and thermal test |
| PCB-MIC | 2 copper layers, Altium master, four per station | port cleanliness, identity, gain, phase and noise |
| Серийность Serials | DIO-EVT-001…040 plus DIO-EVT-B01 | 41 unique identities, no duplicates |

RU: Закупка может выполняться вариантом 21 или 41 станции, но производственный реестр и формы охватывают все 41 идентичность. Вариант закупки не изменяет плату, прошивку, распайку или критерии приемки.

EN: Procurement may use the 21- or 41-station option, while manufacturing registers and forms cover all 41 identities. Procurement quantity does not change hardware, firmware, pinout or acceptance criteria.

## 2. Условия допуска Release gate

1. RU: Сверить имя архива, SHA-256, release metadata и отсутствие файлов KiCad в производственной папке. EN: Verify archive name, SHA-256, release metadata and absence of KiCad files from the manufacturing folder.
2. RU: Использовать Altium/CAM только из вложенного архива REV_D10. EN: Use Altium/CAM only from the nested REV_D10 archive.
3. RU: Проверить подписанные отклонения, NCR и ECO до вскрытия комплекта. EN: Review signed deviations, NCRs and ECOs before opening the kit.
4. RU: Назначить serial и traveller до начала сборки. EN: Assign the serial and traveller before assembly begins.

## 3. Безопасность, ESD и инструменты Safety, ESD and tools

1. RU: Работать на проверенном ESD месте; платы хранить в защитной упаковке. EN: Use a verified ESD workstation and keep boards in protective packaging.
2. RU: Батарея, солнечная панель и внешнее питание отключены до шага первого включения. EN: Battery, solar panel and external power remain disconnected until first power.
3. RU: RF тракт не включать без антенны или 50 ohm load. EN: Do not enable the RF path without an antenna or 50 ohm load.
4. RU: Записать ID и калибровку DMM, лабораторного источника, torque tool, thermal camera, insulation tester and geometry jig. EN: Record IDs and calibration for the DMM, bench supply, torque tool, thermal camera, insulation tester and geometry jig.
5. RU: Не применять численный torque или test limit со слов оператора. EN: Do not use a numeric torque or test limit based on verbal instruction.

## 4. Входной контроль комплекта Kit inspection

1. RU: Сверить serial на traveller, корпусе, платах и labels; до provisioning допустима временная метка. EN: Match the traveller, enclosure, PCB and label serials; a temporary label is allowed before provisioning.
2. RU: Проверить PCBA records: paste/reflow profile, AOI, visual, X-ray where required, repair log and board serial. EN: Review PCBA records: paste/reflow profile, AOI, visual, required X-ray, repair log and board serial.
3. RU: Проверить четыре PCB-MIC как отдельные принятые изделия. EN: Verify four PCB-MIC assemblies as separately accepted units.
4. RU: Проверить шесть жгутов по EVT_PRE_20_HARNESS_MANUFACTURING_WORK_INSTRUCTION_REV_B. EN: Verify six harnesses under EVT_PRE_20_HARNESS_MANUFACTURING_WORK_INSTRUCTION_REV_B.
5. RU: Проверить корпус, mounts, membranes, vents, seals, fasteners, antenna/coax, battery, MPPT and labels. EN: Inspect enclosure, mounts, membranes, vents, seals, fasteners, antenna/coax, battery, MPPT and labels.

## 5. Подготовка корпуса Enclosure preparation

1. RU: Очистить посадочные места без ворса и растворителя, разрушающего пластик или мембраны. EN: Clean mounting surfaces with lint-free materials and no solvent that attacks plastics or membranes.
2. RU: Проверить отверстия, inserts, резьбу, плоскостность и отсутствие трещин. EN: Inspect holes, inserts, threads, flatness and absence of cracks.
3. RU: Выполнить сухую примерку плат и кабельных вводов; ничего не подрезать без NCR/ECO. EN: Dry-fit PCBs and glands; do not trim parts without an NCR/ECO.
4. RU: Записать lot корпуса и 3D-printed/vacuum-cast part IDs. EN: Record enclosure lot and 3D-printed/vacuum-cast part IDs.

## 6. Монтаж PCB-MAIN, антенн и коаксиалов Upper electronics module

1. RU: Установить стойки и isolators по mechanical drawing. EN: Install standoffs and isolators per the mechanical drawing.
2. RU: Убедиться, что под платой нет стружки, провода или выступающего крепежа. EN: Ensure no chips, wires or protruding fasteners remain below the board.
3. RU: Установить PCB-MAIN без изгиба. Крепеж затягивать крест-накрест в два прохода. EN: Install PCB-MAIN without bending and tighten fasteners in a cross pattern in two passes.
4. RU: Фактический torque записать; PASS возможен только при APPROVED параметре PAR-A01. EN: Record actual torque; PASS requires parameter PAR-A01 APPROVED.
5. RU: Подключить antenna/coax, проверить mating, bend radius, strain relief and antenna keepout. EN: Connect antenna/coax and verify mating, bend radius, strain relief and antenna keepout.
6. RU: Сохранить фото до закрытия модуля. EN: Retain a photo before closing the module.

## 7. Геометрия четырех микрофонов Four-microphone geometry

1. RU: Установить PCB-MIC1…4 по идентификаторам, не менять местами после calibration record. EN: Install PCB-MIC1…4 by identity and do not swap after the calibration record.
2. RU: Не касаться MEMS port инструментом, клеем, герметиком или сжатым воздухом. EN: Keep tools, adhesive, sealant and compressed air away from the MEMS port.
3. RU: Установить mounts, membranes and acoustic path in the documented orientation. EN: Install mounts, membranes and acoustic path in the documented orientation.
4. RU: Подключить H-MIC1…4, сохранив одинаковые длины; сервисные петли не пережимать. EN: Connect H-MIC1…4 at equal lengths and do not pinch service loops.
5. RU: Измерить triangle sides, MIC4 offset, heights and orientation with the approved jig; записать actual values and photo. EN: Measure triangle sides, MIC4 offset, heights and orientation with the approved jig and record actual values and a photo.
6. RU: До заморозки численных геометрических пределов B01 результат остается HOLD. EN: Until B01 freezes numeric geometry limits the result remains HOLD.

## 8. PCB-PWR, аккумулятор и нижний модуль Lower power module

1. RU: Проверить полярность battery, fuse, BMS and MPPT на обесточенном узле. EN: Verify battery, fuse, BMS and MPPT polarity while unpowered.
2. RU: Установить PCB-PWR по drawing; фактический torque записать и сопоставить с PAR-A02. EN: Install PCB-PWR per drawing, record actual torque and compare with PAR-A02.
3. RU: Подключить H-BAT-PWR: negative остается отсоединенным до финальной проверки полярности. EN: Connect H-BAT-PWR while leaving negative disconnected until final polarity review.
4. RU: M8 torque и направление наконечника принимаются только при APPROVED PAR-A03. EN: M8 torque and lug orientation are accepted only when PAR-A03 is APPROVED.
5. RU: Установить strain relief так, чтобы нагрузка не передавалась на разъем и вывод батареи. EN: Install strain relief so no load reaches the connector or battery terminal.

## 9. Межмодульные соединения Interconnect

1. RU: Подключить H-MAIN-PWR при снятом питании и проверить keying. EN: Connect H-MAIN-PWR with power removed and verify keying.
2. RU: Выполнить continuity and polarity from battery input through PCB-PWR to PCB-MAIN. EN: Check continuity and polarity from battery input through PCB-PWR to PCB-MAIN.
3. RU: Проверить отсутствие cross-short и rail-to-ground short по утвержденным пределам. EN: Verify no cross-short or rail-to-ground short against approved limits.
4. RU: Уложить силовые, RF и микрофонные линии раздельно, исключить switching-node coupling. EN: Separate power, RF and microphone routes and avoid switching-node coupling.
5. RU: Зафиксировать routing photos до закрытия корпуса. EN: Capture routing photos before closing the enclosure.

## 10. Уплотнения и закрытие Seals and closure

1. RU: Осмотреть seals, membranes, vents and glands; загрязненные или поврежденные одноразовые элементы заменить. EN: Inspect seals, membranes, vents and glands and replace contaminated or damaged single-use parts.
2. RU: Уложить seal без перекручивания, растяжения или discontinuity. EN: Seat the seal without twist, stretch or discontinuity.
3. RU: Закрывать корпус по утвержденной sequence and torque plan PAR-A04/PAR-A05. EN: Close the enclosure under approved sequence and torque plan PAR-A04/PAR-A05.
4. RU: Записать фактические torques, tool ID and calibration due date. EN: Record actual torques, tool ID and calibration due date.
5. RU: Leak test выполняется после электрической безопасности и до уличного воздействия. EN: Perform leak testing after electrical safety and before outdoor exposure.

## 11. Предпусковой контроль Pre-power checklist

1. RU: Отключить battery, solar input, USB-C and external interfaces, кроме измерительных. EN: Disconnect battery, solar input, USB-C and external interfaces except measurement connections.
2. RU: Проверить ориентацию всех полярных разъемов, fuse rating and protective devices. EN: Verify all polarized connectors, fuse rating and protective devices.
3. RU: Измерить resistance to ground каждой rail и записать meter range, settling time and value. EN: Measure each rail resistance to ground and record meter range, settling time and value.
4. RU: Подключить лабораторный источник с current limit, утвержденным в PAR-P01. EN: Connect a bench supply with the current limit approved in PAR-P01.
5. RU: Подключить thermal camera and voltage probes до подачи питания. EN: Connect the thermal camera and voltage probes before applying power.

## 12. Первое включение Initial power-up

1. RU: Подать входное напряжение по утвержденному B01 профилю; не подключать батарею одновременно. EN: Apply input voltage under the approved B01 profile and do not connect the battery simultaneously.
2. RU: Записать inrush current, steady current, 3V3, 3V8, 1V8, input voltage and timestamps. EN: Record inrush current, steady current, 3V3, 3V8, 1V8, input voltage and timestamps.
3. RU: Наблюдать thermal image и rails в течение времени PAR-P02. EN: Observe thermal image and rails for the duration in PAR-P02.
4. RU: Немедленно снять питание при current limit, smoke, odor, abnormal sound, unstable rail or abnormal heating. EN: Remove power immediately on current limit, smoke, odor, abnormal sound, unstable rail or abnormal heating.
5. RU: Не повторять включение после аварийного события без NCR disposition. EN: Do not reapply power after an abnormal event without NCR disposition.
6. RU: Сохранить source log, waveform, thermal image and SHA-256. EN: Retain source log, waveform, thermal image and SHA-256.

## 13. Подключение аккумулятора Battery connection

1. RU: Разрешается только после PASS лабораторного первого включения и независимой проверки полярности. EN: Allowed only after laboratory first-power PASS and independent polarity verification.
2. RU: Подключить positive then negative with insulated tools; disconnect in reverse order. EN: Connect positive then negative with insulated tools and disconnect in reverse order.
3. RU: Проверить отсутствие искрения, перегрева, BMS trip and reverse current. EN: Verify absence of arcing, overheating, BMS trip and reverse current.
4. RU: Выполнить charging/MPPT check по утвержденному профилю; до утверждения профиля оставить HOLD. EN: Perform charging/MPPT checks under the approved profile; keep HOLD until the profile is approved.

## 14. Передача на прошивку и provisioning Handoff

RU: Передавать станцию только с закрытыми assembly and first-power checklists, PCBA evidence, harness records, torque records, board/harness IDs, NCR list and evidence SHA-256. Firmware, Android APK, certificates, time synchronization and EOL выполняются по `EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D`, PKI and synchronization instructions. Candidate 2026101601 не считать final production lock до аппаратной квалификации.

EN: Transfer the station only with closed assembly and first-power checklists, PCBA evidence, harness records, torque records, board/harness IDs, NCR list and evidence SHA-256. Firmware, Android APK, certificates, time synchronization and EOL follow `EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D` plus PKI and synchronization instructions. Candidate 2026101601 is not the final production lock until hardware qualification closes.

## 15. EOL, ремонт и повторная проверка EOL and rework

1. RU: Полный EOL обязателен для каждой из 41 station identities. EN: Complete EOL is mandatory for every one of the 41 station identities.
2. RU: После ремонта повторить затронутую операцию, electrical safety, first power and полный regression EOL. EN: After rework repeat the affected operation, electrical safety, first power and complete regression EOL.
3. RU: Результат PASS запрещен при blank mandatory field, missing evidence, OPEN parameter, expired calibration or unresolved NCR. EN: PASS is prohibited with a blank mandatory field, missing evidence, OPEN parameter, expired calibration or unresolved NCR.

## 16. Записи и подписи Records and sign-off

| Запись Record | Обязательные поля Mandatory fields | Подпись Sign-off |
|---|---|---|
| Traveller | serial, HW IDs, operation, timestamp, result, evidence | operator plus QC |
| Torque record | joint, approved parameter, actual value, tool, calibration | operator plus QC |
| First power | setup, currents, rails, thermal, source logs, SHA-256 | operator plus reviewer |
| NCR/rework | defect, cause, action, replaced parts, retest | MRB authorization |
| Unit passport | HW/FW revisions, certificates, EOL, site handoff | QA release |

RU: Рабочие формы находятся в `EVT_PRE_20_OPERATION_CARDS_AND_CHECKLISTS_REV_B.xlsx` и соответствующих CSV. Формула или автоматически вычисленный PASS не заменяет подпись контролера.

EN: Working forms are in `EVT_PRE_20_OPERATION_CARDS_AND_CHECKLISTS_REV_B.xlsx` and the corresponding CSV files. A formula or automatically calculated PASS does not replace reviewer approval.
