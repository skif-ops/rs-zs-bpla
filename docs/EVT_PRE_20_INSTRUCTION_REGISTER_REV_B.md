# Реестр инструкций и рабочих форм производственного комплекта EVT-PRE-20

**Документ:** EVT_PRE_20_INSTRUCTION_REGISTER_REV_B  
**Ревизия:** Rev B  
**Дата:** 16.10.2026  
**Комплект:** EVT-PRE-20 REV_D10  
**Статус:** RELEASED DOCUMENT SET; PHYSICAL RESULTS REMAIN NOT RUN UNTIL RECORDED

## 1. Назначение Purpose

RU: Реестр указывает авторитетный документ для закупки, изготовления, сборки, первого включения, прошивки, EOL, монтажа и эксплуатации. Комплект рассчитан на две группы по 20 станций и DIO-EVT-B01, всего 41 идентичность. Варианты закупки — 21 или 41. Наличие документа не закрывает физическую проверку.

EN: This register identifies the authoritative document for procurement, fabrication, assembly, first power, programming, EOL, installation and operation. The program covers two groups of 20 plus DIO-EVT-B01, 41 identities total. Procurement options are 21 or 41. Document availability does not close a physical test.

## 2. Архивы Archives

| Архив Archive | Назначение Purpose | Основное содержимое Key content |
|---|---|---|
| EVT_PRE_20_REV_D10_FULL.zip | закупка, производство, сборка, ввод | all documents, BOM, Altium/CAM, harnesses, enclosures, software, checklists |
| EVT_PRE_20_REV_D10_ALTIUM.zip | PCB/PCBA factory | PCB-MAIN 8L, PCB-PWR 4L, PCB-MIC 2L, Altium and CAM |
| EVT_PRE_20_REV_D10_TESTS.zip | program, methods, reports, Muhoed training | DOCX/PDF methods, XLSX/CSV records, validators and training source |

RU: KiCad исключен из FULL и ALTIUM, чтобы не смешивать производственный master; исходники и история сохранены в Git. Платы REV_D10 наследуют проверенное содержимое REV_D9 без изменений.

EN: KiCad is excluded from FULL and ALTIUM to prevent confusion with the manufacturing master; sources and history remain in Git. REV_D10 inherits the verified REV_D9 board content unchanged.

## 3. Управляющие инструкции Governing instructions

| Этап Stage | Документ Document | Статус Status |
|---|---|---|
| PCB/PCBA | Altium factory package and fabrication notes | vendor DFM and first article open |
| Жгуты Harnesses | EVT_PRE_20_HARNESS_MANUFACTURING_WORK_INSTRUCTION_REV_B | released; first article and supplier parameters open |
| Сборка Assembly | EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_B | released; physical execution open |
| Прошивка и EOL Firmware/EOL | EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D | candidate released; hardware qualification open |
| Сертификаты PKI | EVT_PRE_20_PKI_CERTIFICATE_LIFECYCLE_INSTRUCTION_REV_A | released; device binding validation open |
| Время и координаты Time/location | EVT_PRE_20_TIME_SYNCHRONIZATION_TRUST_INSTRUCTION_REV_A | released; numeric limits open |
| Сервер Server | EVT_PRE_20_SERVER_DEPLOYMENT_BACKUP_OPERATIONS_INSTRUCTION_REV_A | released; protected host required |
| Монтаж Installation | EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_B | released; site execution open |

## 4. Рабочие формы Work forms

| Форма Form | Назначение Purpose | Охват Coverage |
|---|---|---|
| EVT_PRE_20_OPERATION_CARDS_AND_CHECKLISTS_REV_B.xlsx | единая книга операций и решений | all 41 identities |
| ASSEMBLY_ROUTE_REV_B.csv | авторитетный маршрут производства | lot plus every station |
| HARNESS_OPERATION_CARDS_REV_B.csv | порядок изготовления жгутов | six harnesses per station |
| STATION_ASSEMBLY_CHECKLIST_REV_B.csv | сборка и закрытие traveller | 41 rows |
| FIRST_POWER_CHECKLIST_REV_B.csv | первое питание и измерения | 41 rows plus repeated attempts |
| INSTALLATION_COMMISSIONING_CHECKLIST_REV_B.csv | монтаж и ввод | 41 rows |
| EVT_PRE_20_41_STATION_TRAVELLER_REGISTER_REV_B.csv | сквозной статус | 40 field plus B01 |
| MANUFACTURING_PARAMETER_APPROVAL_REGISTER_REV_B.csv | численные process limits | open/approved with source and signatures |
| EOL_RESULT_REGISTER.csv | полный EOL | 41 rows |

## 5. Последовательность применения Sequence

1. RU: Заказчик выбирает закупку 21 или 41 и фиксирует выбранный вариант. EN: The customer selects procurement quantity 21 or 41 and records it.
2. RU: Фабрика выполняет DFM, first article, PCBA inspection and records. EN: The factory completes DFM, first article, PCBA inspection and records.
3. RU: Участок жгутов закрывает first-off and 100 percent electrical test. EN: The harness area closes first-off and 100 percent electrical testing.
4. RU: Сборка выполняет traveller, mechanical assembly, torque records and initial power. EN: Assembly completes the traveller, mechanical assembly, torque records and initial power.
5. RU: Programming/EOL выполняет identities, firmware, Android, certificates, communications and full functional tests. EN: Programming/EOL completes identities, firmware, Android, certificates, communications and full functional testing.
6. RU: Монтажник закрывает site readiness, mechanical/electrical installation and commissioning. EN: The installer closes site readiness, mechanical/electrical installation and commissioning.
7. RU: QA разрешает переход только при evidence, APPROVED limits and required signatures. EN: QA authorizes transition only with evidence, APPROVED limits and required signatures.

## 6. Правило HOLD Mandatory HOLD rule

RU: Пустое обязательное поле, отсутствующий исходный лог, несовпадающий hash, OPEN parameter, просроченная калибровка, незакрытый NCR или неподписанный контроль дают HOLD. Типовое инженерное решение можно использовать для планирования и DFM, но численное значение становится приемочным только после записи источника и утверждения.

EN: A blank mandatory field, missing source log, hash mismatch, OPEN parameter, expired calibration, unresolved NCR or missing sign-off produces HOLD. A typical engineering practice may support planning and DFM, but a numeric value becomes an acceptance limit only after its source and approval are recorded.

## 7. Открытые физические ворота Open physical gates

RU: Открыты vendor DFM/first article, crimp setup limits, mechanical torques, first-power numeric envelope, leak-test limit, site anchor/grounding limits, RF/acoustic/time/GNSS numeric criteria, enclosure fit, full target pass and final firmware lock. Они закрываются данными фабрики, B01 и собранных станций. До закрытия соответствующая операция имеет HOLD, а не PASS.

EN: Vendor DFM/first article, crimp setup limits, mechanical torques, first-power numeric envelope, leak-test limit, site anchor/grounding limits, RF/acoustic/time/GNSS numeric criteria, enclosure fit, full target pass and final firmware lock remain open. Factory data, B01 and assembled units close them. Until closure the affected operation is HOLD, not PASS.
