# Реестр инструкций производственного комплекта EVT PRE 20

Ревизия A. Дата 16 октября 2026 года. Комплект REV D9.

RU: Реестр показывает, какой документ управляет каждым этапом закупки, изготовления, сборки, прошивки, настройки, монтажа, испытаний и эксплуатации. Наличие инструкции не закрывает физическую проверку. Там, где требуется собранная станция или данные фабрики, статус остаётся HOLD или NOT RUN.

EN: This register maps each procurement, fabrication, assembly, programming, commissioning, installation, test and operation activity to its governing document. The existence of an instruction does not close a physical test. Where an assembled station or factory data is required, the status remains HOLD or NOT RUN.

## 1 Комплект и архивы

| Архив Archive | Назначение Purpose | Состав Scope |
|---|---|---|
| EVT PRE 20 REV D9 FULL | Закупка производство сборка ввод Procurement production assembly commissioning | Документы BOM Altium CAM корпуса жгуты прошивка APK регламенты |
| EVT PRE 20 REV D9 ALTIUM | Фабрика PCB and PCBA | PCB MAIN 8L PCB PWR 4L PCB MIC 2L Altium CAM assembly |
| EVT PRE 20 REV D9 TESTS | ПМИ отчёты EOL и дообучение Мухоеда | Methods forms validators server and training source |

RU: KiCad отсутствует в FULL и ALTIUM, чтобы не смешивать производственный master. Исходники KiCad сохранены в Git и истории. EN: KiCad is excluded from FULL and ALTIUM to avoid mixing the production master. KiCad sources remain in Git and history.

## 2 Реестр по этапам

| Этап Stage | Управляющий документ Governing document | Формат Language | Статус Status |
|---|---|---|---|
| Паспорт и состав Package passport | Паспорт производственного комплекта и README FIRST | DOCX PDF TXT RU EN | RELEASED |
| Технический проект Technical design | Технический проект EVT PRE 20 | DOCX PDF | RELEASED |
| Техническое задание Requirements | Актуализированное техническое задание | DOCX PDF | RELEASED |
| Варианты закупки Procurement variants | Notice 21 and 41 plus BOM workbook | DOCX PDF XLSX CSV RU EN | RELEASED customer selects one |
| Платы PCB | Задание Altium plus board factory packages | DOCX PDF Altium Gerber drill IPC STEP CSV | VENDOR DFM and first article open |
| PCB MAIN stackup | PCB MAIN 8L factory package | Altium CAM PDF RU EN | 8 layers fixed |
| PCB PWR stackup | PCB PWR 4L factory package | Altium CAM PDF | 4 layers fixed |
| PCB MIC stackup | PCB MIC 2L factory package | Altium CAM PDF | 2 layers fixed |
| Жгуты Harnesses | Задание и схемы подключения и распайки | DOCX PDF XLSX CSV | Supplier review open |
| Корпуса Enclosures | Задание на литьё и 3D печать drawings and models | DOCX PDF STEP STL DXF | Fit check on B01 open |
| Сборка станции Station assembly | Assembly setup instruction and station assembly guide | DOCX PDF RU EN | RELEASED physical execution open |
| Первичное питание Initial power | Assembly setup and firmware commissioning manual | DOCX PDF | HOLD until B01 measurement |
| Прошивка STM32 nRF | Firmware commissioning test manual | DOCX PDF binaries hashes | Software candidate released hardware test open |
| Установка Android Android install | Firmware commissioning manual and signed APK evidence | DOCX PDF APK PEM TXT | Release candidate |
| Сертификаты и PKI Certificates and PKI | PKI certificate lifecycle instruction | DOCX PDF RU EN plus tools | RELEASED device BG95 validation open |
| Синхронизация Sync and trust | Time synchronization and position trust instruction | DOCX PDF RU EN plus CSV protocol | RELEASED numeric limits open |
| Сервер Мухоед Server | Server deployment backup and operations instruction | DOCX PDF RU EN plus scripts | RELEASED protected host required |
| Ввод станции Commissioning | Installation commissioning instruction | DOCX PDF RU EN | Physical site execution open |
| EOL | Program methods measurement workbook and firmware manual | DOCX PDF XLSX CSV JSON | 21 numeric criteria open |
| OTA rollback | Firmware commissioning manual and protocol addenda | DOCX PDF MD | Hardware power cut test open |
| Монтаж на объекте Field installation | Installation commissioning instruction | DOCX PDF RU EN | Site evidence required |
| Дообучение Мухоеда Muhoed training | Руководство дообучения и source package | DOCX PDF code models dataset | Separate TESTS archive |
| Отчётность Evidence | Report forms travellers registers receipts | DOCX PDF XLSX CSV JSON | Fill per station |
| Rework recovery | Firmware manual PKI instruction server operations | DOCX PDF RU EN | Controlled approval required |

## 3 Последовательность применения

1. RU: Заказчик выбирает вариант закупки 21 или 41. EN: The customer selects procurement option 21 or 41.
2. RU: Фабрика выполняет DFM and first article по ALTIUM archive. EN: The factory performs DFM and first article review from the ALTIUM archive.
3. RU: Сборочный участок выполняет incoming inspection, assembly and initial power. EN: The assembly area performs incoming inspection, assembly and initial power checks.
4. RU: EOL выполняет flashing, identity, PKI, BG95, functional tests and evidence. EN: EOL performs flashing, identity, PKI, BG95, functional tests and evidence.
5. RU: Монтажник выполняет site installation, coordinates, synchronization and commissioning. EN: The installer performs site installation, coordinates, synchronization and commissioning.
6. RU: Серверный администратор выполняет deployment, PKI, backup, monitoring and restore tests. EN: The server administrator performs deployment, PKI, backup, monitoring and restore tests.
7. RU: Контролёр разрешает переход только при наличии требуемых evidence and approved limits. EN: The reviewer authorizes the next gate only when the required evidence and approved limits exist.

## 4 Открытые ворота

RU: На дату выпуска не закрыты числовые пределы питания и токов, acoustic gain phase noise, PPS accuracy and holdover, LTE GNSS LoRa RF, thermal behavior, герметичность, enclosure fit, полный target pass, firmware lock and final DFM first article. Они закрываются измерениями DIO-EVT-B01 и последующих изделий либо данными фабрики. Undefined mandatory limit означает HOLD.

EN: As of release, numeric power and current limits, acoustic gain phase and noise, PPS accuracy and holdover, LTE GNSS and LoRa RF, thermal behavior, sealing, enclosure fit, full target pass, firmware lock and final DFM first article remain open. They require measurements on DIO-EVT-B01 and subsequent units or factory data. An undefined mandatory limit produces HOLD.

RU: Правило актуальности: использовать только файлы из одного release root и сверять MANIFEST SHA256. При несовпадении имени, revision or hash с register or release metadata остановить работу. EN: Currency rule: use files from one release root and verify MANIFEST SHA256. Stop work if a name, revision or hash does not match the register or release metadata.
