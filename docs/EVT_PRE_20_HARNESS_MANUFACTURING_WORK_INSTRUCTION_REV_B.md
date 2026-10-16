# Рабочая инструкция по изготовлению и контролю жгутов Дионея EVT-PRE-20

**Документ:** EVT_PRE_20_HARNESS_MANUFACTURING_WORK_INSTRUCTION_REV_B  
**Ревизия:** Rev B  
**Дата:** 16.10.2026  
**Комплект:** EVT-PRE-20 REV_D10  
**Статус:** RELEASED FOR EVT BUILD; SUPPLIER FIRST ARTICLE REQUIRED  
**Назначение:** пошаговое изготовление, контроль, регистрация и приемка жгутов для 40 полевых и одной стендовой станции

## 1. Область применения Scope

RU: Инструкция обязательна для жгутов H-MIC1…H-MIC4, H-MAIN-PWR и H-BAT-PWR. На каждую станцию требуется шесть жгутов. Для программы зарезервированы `DIO-EVT-001…040` и `DIO-EVT-B01`, всего 41 комплект. Любая замена провода, контакта, корпуса, оснастки или технологического параметра допускается только по утвержденному отклонению или ECO.

EN: This instruction governs H-MIC1…H-MIC4, H-MAIN-PWR and H-BAT-PWR. Six harnesses are required per station. The program reserves `DIO-EVT-001…040` and `DIO-EVT-B01`, 41 sets total. Any wire, terminal, housing, tooling or process-parameter substitution requires an approved deviation or ECO.

## 2. Управляющие данные Governing data

| Источник Source | Назначение Purpose | Правило Rule |
|---|---|---|
| HARNESS_LOGICAL_PINOUT_REV_A.csv | Логическая распайка Logical pinout | Номер полости и сигнал не менять Do not change cavity or signal |
| HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv | Проводник за проводником Conductor schedule | Основной машинночитаемый источник Authoritative machine-readable source |
| HARNESS_EVT_LENGTH_BASIS_REV_A.csv | Длины Length basis | Длина и допуск обязательны Length and tolerance are mandatory |
| CONNECTOR_FREEZE_REV_A.csv | Корпуса и ответные части Housings and mating parts | Замена только по ECO Substitution by ECO only |
| MANUFACTURING_PARAMETER_APPROVAL_REGISTER_REV_B.csv | Параметры оснастки и процесса Tooling and process parameters | OPEN блокирует приемку OPEN blocks acceptance |

RU: При расхождении остановить работу и открыть NCR. Приоритет имеет документ с более новой утвержденной ревизией внутри одного release root. Смешивание файлов разных выпусков запрещено.

EN: Stop work and open an NCR on any conflict. The later approved revision within one release root governs. Mixing files from different releases is prohibited.

## 3. Состав одного комплекта One-station set

| Жгут Harness | Количество Qty | Длина Length | Провод Wire |
|---|---:|---:|---|
| H-MIC1…H-MIC4 | 4 | 275 ±5 mm | TE 55A0111-24, 24 AWG |
| H-MAIN-PWR | 1 | 440 ±5 mm | pins 1–6 TE 55A0111-18; pins 7–12 Alpha 3051 |
| H-BAT-PWR | 1 | 330 ±5 mm | TE 55A0111-18, 18 AWG |

## 4. Ответственность и остановка работ Responsibility and stop-work

1. RU: Оператор выполняет только действующую операционную карту и записывает фактические значения. EN: The operator follows only the current operation card and records actual values.
2. RU: Наладчик утверждает комплект оснастки и first-off образцы. EN: The setup technician approves tooling and first-off samples.
3. RU: ОТК проверяет записи, измерения и доказательства, не заполняя поля за оператора. EN: QC reviews records, measurements and evidence without completing operator fields.
4. RU: При повреждении жилы, нарушении геометрии обжима, неверной полости, неутвержденном параметре, неповеренном средстве измерения или утрате трассируемости присвоить HOLD и открыть NCR. EN: Assign HOLD and open an NCR for conductor damage, invalid crimp geometry, wrong cavity, unapproved parameter, expired calibration or lost traceability.

## 5. Подготовка рабочего места Workstation preparation

1. RU: Сверить release `EVT_PRE_20_REV_D10` и SHA-256 манифеста. EN: Verify the `EVT_PRE_20_REV_D10` release and manifest SHA-256.
2. RU: Очистить стол, включить ESD защиту, отделить партии материалов и установить контейнер для брака. EN: Clean the bench, enable ESD controls, segregate material lots and provide a reject container.
3. RU: Проверить идентификаторы резака, стриппера, обжимной оснастки, микрометра, динамометра и тестера жгутов; записать сроки калибровки. EN: Verify cutter, stripper, crimp tool, micrometer, pull tester and harness tester IDs and record calibration due dates.
4. RU: Загрузить в тестер только утвержденную распайку текущего жгута. EN: Load only the approved pinout for the current harness into the tester.

## 6. Входной контроль материалов Incoming material inspection

1. RU: Сверить MPN, производителя, партию, количество, целостность упаковки и сертификаты. EN: Verify MPN, manufacturer, lot, quantity, packaging integrity and certificates.
2. RU: Проверить соответствие сечения и наружного диаметра провода контакту и уплотнению. EN: Verify wire gauge and outer diameter against terminal and seal ranges.
3. RU: Осмотреть контакты под увеличением: деформация, коррозия, загрязнение и повреждение покрытия не допускаются. EN: Inspect terminals under magnification; deformation, corrosion, contamination and plating damage are prohibited.
4. RU: Материал со смешанной или потерянной партией изолировать. EN: Segregate mixed or untraceable lots.

## 7. Нарезка и маркировка Cut and identification

1. RU: Присвоить идентификатор `Serial-Harness-End`, например `DIO-EVT-001-H-MIC1-A`. EN: Assign a `Serial-Harness-End` identifier such as `DIO-EVT-001-H-MIC1-A`.
2. RU: Нарезать провод по HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv. Измерять между datum выхода проводника из задней плоскости корпуса или наконечника. EN: Cut wire per HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv. Measure between the conductor exit datum at the rear of each housing or terminal.
3. RU: Проверить цвет каждой цепи до зачистки. EN: Verify every circuit color before stripping.
4. RU: Закрепить временную маркировку так, чтобы она не попала под обжим и не закрыла дефект. EN: Apply temporary identification clear of the crimp and inspection area.

## 8. Зачистка и настройка обжима Strip and crimp setup

RU: Численные значения strip length, conductor crimp height, insulation crimp geometry и pull force берутся из действующей инструкции производителя конкретного контакта и провода либо из утвержденной карты наладки. Они не подменяются типовым значением. Поля PAR-H01…PAR-H12 в реестре параметров должны иметь статус APPROVED до приемки first article.

EN: Numeric strip length, conductor crimp height, insulation crimp geometry and pull force come from the current manufacturer instruction for the exact terminal and wire or from an approved setup sheet. Generic values are not substitutes. Parameter records PAR-H01…PAR-H12 must be APPROVED before first-article acceptance.

1. RU: Выполнить пробную зачистку; жилы не надрезаны и не отсутствуют, изоляция не расплавлена и не вытянута. EN: Make a trial strip; strands shall not be nicked or missing and insulation shall not be melted or stretched.
2. RU: Записать фактическую длину зачистки и идентификатор настройки. EN: Record actual strip length and setup ID.
3. RU: Установить терминал-специфичную матрицу, локатор и упор. EN: Install terminal-specific die, locator and stop.
4. RU: Выполнить first-off не менее чем на образцах, требуемых инструкцией поставщика и планом качества. EN: Produce first-off samples in the quantity required by the supplier instruction and quality plan.
5. RU: Измерить crimp height, выполнить разрушающий pull test, сохранить значения и фото поперечного сечения, если оно требуется планом. EN: Measure crimp height, perform destructive pull tests and retain readings and cross-section images when required by the quality plan.
6. RU: Наладчик и ОТК подписывают first-off до запуска остатка партии. EN: Setup and QC sign the first-off before the remainder of the lot is released.

## 9. Серийный обжим Production crimping

1. RU: Ввести провод до упора без подгиба жил. EN: Insert the conductor fully without folded strands.
2. RU: После каждого обжима проверить bellmouth, brush, conductor position, insulation support, seam, wings and terminal straightness. EN: After each crimp inspect bellmouth, brush, conductor position, insulation support, seam, wings and terminal straightness.
3. RU: Периодически измерять crimp height с частотой утвержденного плана контроля и после остановки, переналадки, смены рулона или оператора. EN: Measure crimp height at the approved control frequency and after stoppage, setup change, reel change or operator change.
4. RU: Не подправлять обжим плоскогубцами и не использовать контакт повторно. EN: Do not reform a crimp with pliers or reuse a terminal.

## 10. Установка контактов в корпуса Contact insertion

1. RU: До установки сверить вид со стороны mating face и нумерацию полостей. EN: Before insertion verify the mating-face view and cavity numbering.
2. RU: Вставлять контакт до фиксации первичного замка; выполнить легкую проверку удержания каждого контакта. EN: Insert until the primary lock engages and perform a light retention check on every contact.
3. RU: Установить secondary lock, если предусмотрен, и отметить его положение на фото. EN: Install the secondary lock when applicable and show its position in the evidence photo.
4. RU: Для H-BAT-PWR обеспечить правильную полярность M8 ring terminal и защитить наконечник от короткого замыкания. EN: For H-BAT-PWR preserve M8 ring-terminal polarity and protect the lug against short circuit.

## 11. Формирование жгута и защита Harness formation and protection

1. RU: Сохранить одинаковую длину H-MIC1…4; избыток укладывать сервисной петлей без перегиба. EN: Keep H-MIC1…4 equal in length and place excess in a service loop without kinking.
2. RU: Сигналы PDM_CLK, PDM_DATA и I2C вести согласно указаниям schedule, вдали от switching nodes. EN: Route PDM_CLK, PDM_DATA and I2C as specified in the schedule and away from switching nodes.
3. RU: Защита от истирания, edge guards, braid или heat-shrink не должны загрязнять acoustic ports или создавать натяг на контакте. EN: Abrasion protection, edge guards, braid or heat-shrink shall not contaminate acoustic ports or load the terminal.
4. RU: Не уменьшать радиус изгиба ниже утвержденного значения PAR-H13. EN: Do not reduce bend radius below approved parameter PAR-H13.

## 12. Контроль 100 percent electrical test

1. RU: Выполнить point-to-point continuity для каждой цепи. EN: Perform point-to-point continuity on every circuit.
2. RU: Проверить отсутствие cross-short между всеми несвязанными цепями и корпусом. EN: Verify absence of cross-shorts between all unrelated circuits and the enclosure.
3. RU: Проверить полярность H-BAT-PWR отдельным действием и независимым контролем. EN: Verify H-BAT-PWR polarity as a separate step with independent review.
4. RU: Сопротивление каждого проводника H-MIC и H-MAIN-PWR должно быть не более 0.15 ohm; H-BAT-PWR — не более 0.10 ohm. EN: Each H-MIC and H-MAIN-PWR conductor shall be no more than 0.15 ohm; H-BAT-PWR shall be no more than 0.10 ohm.
5. RU: Сохранить исходный экспорт тестера, его SHA-256 и идентификатор адаптера. EN: Retain the original tester export, its SHA-256 and adapter ID.

## 13. Размеры и внешний вид Dimensions and workmanship

1. RU: Проверить общую длину, ориентацию концов, маркировку, отсутствие острых кромок и натяга. EN: Verify overall length, end orientation, labels, absence of sharp edges and strain.
2. RU: Проверить полную посадку контактов, замков и strain relief. EN: Verify full seating of terminals, locks and strain relief.
3. RU: Критические фото: оба mating faces, first-off crimp, маркировка, общая длина и H-BAT polarity. EN: Required photos: both mating faces, first-off crimp, identification, overall length and H-BAT polarity.

## 14. First article and EVT validation

| Жгут Harness | Обязательная проверка Required validation | Решение Decision |
|---|---|---|
| H-MAIN-PWR | rail drop, heating, modem burst, I2C 100 kHz | HOLD до записи результата HOLD until recorded |
| H-BAT-PWR | 5 A load, +70 C and -40 C, polarity, ring retention, strain | HOLD до записи результата HOLD until recorded |
| H-MIC1…4 | PDM/AAD gain, phase, noise, wake, flex and strain | HOLD до записи результата HOLD until recorded |
| Все All | installed routing, clearance, edge protection, service loops | HOLD до записи результата HOLD until recorded |

## 15. Несоответствия и ремонт Nonconformance and rework

1. RU: Неверный контакт извлекать только утвержденным extractor; поврежденный контакт заменять новым. EN: Remove an incorrect terminal only with the approved extractor; replace any damaged terminal with a new one.
2. RU: После ремонта повторить визуальный контроль и полный электрический тест всего жгута. EN: After rework repeat visual inspection and the complete electrical test of the harness.
3. RU: Splice запрещен, если его нет в утвержденном чертеже и ECO. EN: A splice is prohibited unless present in the approved drawing and ECO.
4. RU: Записать NCR, исходный дефект, действие, замененные партии и повторный результат. EN: Record the NCR, original defect, action, replaced lots and retest result.

## 16. Упаковка и передача Packaging and handoff

1. RU: Закрыть mating faces защитными крышками или ESD-safe упаковкой. EN: Protect mating faces with caps or ESD-safe packaging.
2. RU: Упаковывать по серийному номеру станции, не смешивать принятые и непринятые жгуты. EN: Pack by station serial and do not mix accepted and unaccepted harnesses.
3. RU: Передать tester export, first-off record, material lots, operator/QC signatures and NCR list. EN: Hand off the tester export, first-off record, material lots, operator/QC signatures and NCR list.

## 17. Критерий PASS Gate

RU: PASS разрешен только при APPROVED всех применимых параметров, принятом first-off, полном электрическом тесте, принятых размерах и внешнем виде, наличии evidence SHA-256 и двух подписях. Пустое обязательное поле, OPEN parameter, просроченная калибровка или отсутствующий исходный лог дают HOLD.

EN: PASS requires all applicable parameters APPROVED, accepted first-off, complete electrical test, accepted dimensions and workmanship, evidence SHA-256 and two signatures. A blank mandatory field, OPEN parameter, expired calibration or missing source log produces HOLD.
