# Программа физической квалификации DIO-EVT-B01 и приемки EOL оснастки

**Ревизия:** Rev A

**Дата:** 09.10.2026

**Изделие:** DIO-EVT-B01, station ID 901, tenant bench

**Оснастка:** MFG-004

**Выпуск ПО:** EVT_PRE_20_BENCH_RELEASE_2026100601

**Исходное состояние:** NOT_RUN
**Разрешение на блокировку прошивки:** DENIED

## 1. Назначение и результат

Документ задает конкретный порядок изготовления, приемки и применения EOL оснастки MFG-004, а также физической квалификации стендовой станции DIO-EVT-B01. Оператор получает последовательность включения, назначение каждого контакта, места подключения приборов, измеряемые величины, обязательные evidence и правила решения PASS, FAIL или HOLD.

Программа готова для изготовления оснастки и начала испытаний. Фактические испытания не выполнялись, поэтому исходный результат остается NOT_RUN. Значения, которые зависят от собранного изделия, оснастки и акустического или RF стенда, имеют состояние OPEN_B01_FREEZE. Они переводятся в утвержденные пределы только после MSA, измерений B01, расчетной проверки и двух подписей. Пустой обязательный предел не может дать PASS.

Стендовый выпуск сохраняет SWD и BOOT0 recovery. RDP Level 0, отключенные TrustZone, BOOT_LOCK, WRP и PCROP сохраняются до полного аппаратного PASS и отдельного производственного выпуска. RDP Level 2 этой программой не разрешается.

## 2. Комплект и документы управления

| Документ или файл | Назначение / Purpose |
|---|---|
| `manufacturing/MFG_004_EOL_FIXTURE_CONTACT_MAP_REV_A.csv` | Точная карта 31 pogo контакта и координат / Exact 31-contact pogo map and coordinates |
| `manufacturing/MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_A.json` | Машиночитаемая последовательность / Machine-readable sequence |
| `manufacturing/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.xlsx` | Основной реестр измерений / Primary measurement register |
| `manufacturing/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.csv` | Машиночитаемый исходный реестр / Machine-readable source register |
| `manufacturing/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.xlsx` | Сводное решение по квалификации B01 / B01 qualification decision |
| `docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.docx` | Полная инструкция по прошивке, provisioning и испытаниям / Full flashing, provisioning and test manual |
| `hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv` | Электрический источник истины / Electrical authority |
| `hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv` | Координаты и механический источник истины / Coordinate and mechanical authority |
| `firmware/targets/evt_pre_20/release/bench_release_contract.json` | Точный стендовый выпуск / Exact bench release |

При расхождении оператор останавливает работу. Электрическая распиновка берется из authority CSV, координаты из mechanical authority, файлы прошивки и хэши из release contract и release manifest. Копирование значений по памяти запрещено.

## 3. Требования к рабочему месту

Нужны лабораторный источник с программируемым ограничением тока и журналом, DMM с действующей калибровкой, осциллограф не менее четырех каналов, логический анализатор, ST-LINK, отдельный nRF probe, изолированные UART 3,3 В и 1,8 В, open-drain I2C adapter, USB 2.0 recovery interface, тепловизор, управляемый power interrupter, RF нагрузки 50 ohm, экранированный или conducted LoRa стенд, утвержденная GNSS антенна или simulator, акустическая оснастка и компьютер EOL.

Каждый прибор записывается в реестр: тип, модель, серийный номер, дата калибровки, срок действия, диапазон, точность и канал. Скриншот без исходного файла измерения не считается достаточным evidence.

## 4. Механика оснастки MFG-004

PCB-MAIN имеет контур 110,00 x 75,00 мм. Координаты authority заданы в виде сверху платы: начало в левом нижнем углу, X вправо, Y вверх. Pogo входят к площадкам со стороны B.Cu.

Для чертежа контактной плиты, который рассматривают со стороны pogo, применяется преобразование:

`X_fixture = 110,00 - X_board`
`Y_fixture = Y_board`

Нельзя одновременно зеркалить импортированный Gerber или STEP и повторно применять формулу. Оснастка должна иметь несимметричный ключ. Смещенный H1 исключает установку платы с разворотом.

| Отверстие | X платы, мм | Y платы, мм | Диаметр |
|---|---:|---:|---:|
| H1 | 8,00 | 5,00 | 3,20 мм NPTH |
| H2 | 105,00 | 5,00 | 3,20 мм NPTH |
| H3 | 105,00 | 70,00 | 3,20 мм NPTH |
| H4 | 5,00 | 70,00 | 3,20 мм NPTH |

Все pogo площадки имеют диаметр 1,70 мм, шаг 2,54 мм и находятся на B.Cu. Прижим не должен изгибать плату, касаться компонентов или создавать боковую нагрузку на разъемы. Минимальный ход и усилие pogo устанавливает изготовитель оснастки после проверки реальных образцов. Эти значения записываются в паспорт MFG-004.

## 5. Группы контактов и правила безопасности

### 5.1. TP_EOL 13 контактов

| Контакт | Сигнал | Что подключать / Connection | Правило / Rule |
|---:|---|---|---|
| 1 | GND | Общая цифровая земля приборов | Соединяется первой, снимается последней |
| 2 | VTREF_3V3 | Высокоомный DMM и канал осциллографа | Только измерение, не питать |
| 3 | VSENSE_3V8 | Высокоомный DMM и канал осциллографа | Только измерение, не питать |
| 4 | VSENSE_1V8 | Высокоомный DMM и канал осциллографа | Только измерение, не питать |
| 5 | DUT_TX | Вход изолированного UART 3,3 В | Выход станции, не нагружать до valid VTREF |
| 6 | DUT_RX | Выход изолированного UART 3,3 В | High-Z до valid TP_EOL.2 |
| 7 | PWR_GOOD | Логический анализатор или осциллограф | Только наблюдение |
| 8 | FAULT | Логический анализатор или осциллограф | Только наблюдение |
| 9 | BOOT0 | Current-limited control 3,3 В | Управлять только при активном NRST |
| 10 | REV0 | Высокоомный цифровой вход | Только считывание |
| 11 | REV1 | Высокоомный цифровой вход | Только считывание |
| 12 | I2C_SCL | Изолированный open-drain adapter | Не добавлять pull-up без записи |
| 13 | I2C_SDA | Изолированный open-drain adapter | Не добавлять pull-up без записи |

### 5.2. TP_MCU_SWD 5 контактов

| Контакт | Сигнал | Подключение | Порядок |
|---:|---|---|---|
| 1 | VTREF | ST-LINK VTREF sense | После GND |
| 2 | SWDIO | ST-LINK SWDIO | После NRST |
| 3 | SWCLK | ST-LINK SWCLK | После SWDIO |
| 4 | NRST | ST-LINK NRST | До активных SWD сигналов |
| 5 | GND | ST-LINK GND | Первым |

ST-LINK не питает станцию. Подключение: 5, 1, 4, 2, 3. Отключение выполняется в обратном порядке.

### 5.3. TP_BLE_SWD 4 контакта

| Контакт | Сигнал | Подключение | Правило |
|---:|---|---|---|
| 1 | VTREF | nRF probe VTREF sense | Только измерение |
| 2 | NRF_SWDIO | nRF probe SWDIO | Не соединять со STM32 SWDIO |
| 3 | NRF_SWCLK | nRF probe SWCLK | Не соединять со STM32 SWCLK |
| 4 | GND | nRF probe GND | Соединяется первым |

TP_MCU_SWD и TP_BLE_SWD электрически и логически раздельны.

### 5.4. TP_CELL_DBG 5 контактов

| Контакт | Сигнал | Подключение | Правило |
|---:|---|---|---|
| 1 | VREF_1V8 | Высокоомный DMM и reference вход level shifter | Только измерение |
| 2 | DUT_TX | Вход UART, tolerant 1,8 В | Активировать после valid VREF |
| 3 | DUT_RX | Выход UART 1,8 В | High-Z до valid VREF |
| 4 | USB_BOOT | Current-limited output 1,8 В | Recovery only, 3,3 В запрещены |
| 5 | GND_MODEM | Земля modem fixture | Первой |

### 5.5. TP_CELL_USB 4 контакта

| Контакт | Сигнал | Подключение | Правило |
|---:|---|---|---|
| 1 | HOST_VBUS | Отдельный current-limited USB VBUS | Единственный разрешенный источник в pogo группах |
| 2 | USB_DP | Дифференциальный USB D+ | Не соединять с J11 USB_DP |
| 3 | USB_DM | Дифференциальный USB D- | Не соединять с J11 USB_DM |
| 4 | GND_MODEM | Земля USB recovery | Соединяется первой |

J11 обслуживает STM32 и не питает станцию. TP_CELL_USB обслуживает только BG95. Их VBUS, D+, D- и контакты оснастки не объединяются.

## 6. Приемка оснастки без DUT

1. Сверить ID MFG-004, ревизию, серийный номер и электрическую схему.
2. Проверить правильную ориентацию платы по H1-H4 и ключу.
3. Измерить путь каждого pogo до соответствующего разъема или прибора. Приемочный предел оснастки: не более 1,0 ohm вместе с проводом. Для низкоомных путей применяется четырехпроводное измерение.
4. При напряжении проверки не более 5 В измерить изоляцию сигнальных каналов оснастки от соседних каналов и земли. Для пустой оснастки требуется не менее 10 Mohm. DUT при этом не устанавливается.
5. Проверить, что rail sense, VTREF, PWR_GOOD, FAULT, REV0, REV1 и VREF_1V8 не имеют источника напряжения.
6. Проверить, что UART, SWD, BOOT0, USB_BOOT и I2C находятся в high-Z до valid reference.
7. Проверить, что I2C выходы open-drain.
8. Проверить current limit на CELL_USB_VBUS и USB_BOOT 1,8 В.
9. Проверить аварийное отключение. Оно одновременно снимает питание DUT, CELL_USB_VBUS и активные выходы.
10. Сохранить raw CSV, фото верхней и нижней части оснастки, электрическую схему и хэши.

Оснастка получает статус FIXTURE_ACCEPTED только после PASS всех десяти действий и MSA. Если канал перепутан, контакт нестабилен или interlock не срабатывает, результат FAIL. Если нет калибровки или numeric limit, результат HOLD.

## 7. Общий порядок работы с DIO-EVT-B01

1. Проверить документы, release manifest, серийные номера и калибровку приборов.
2. Отключить батарею, солнечную панель и все внешние источники.
3. Выполнить визуальный контроль PCB-MAIN, PCB-PWR, четырех PCB-MIC, жгутов и RF кабелей.
4. Установить RF нагрузки или разрешенные антенны до возможности передачи.
5. Установить плату в MFG-004. Проверить pogo по контрольным меткам.
6. Соединить grounds. Затем подключить пассивные sense inputs. Активные выходы оставить high-Z.
7. Измерить сопротивления 3V3_DIGITAL, 3V8_MODEM и 1V8_MIC относительно GND на TP_EOL.2, .3, .4 к TP_EOL.1.
8. Подать питание только через штатный J_PWR_IN от лабораторного источника. Не подавать питание через VTREF, J11 или rail sense.
9. Проверить три rails, PWR_GOOD и FAULT до подключения UART, SWD, I2C и modem debug.
10. После valid TP_EOL.2 подключить UART и STM32 SWD. После valid TP_BLE_SWD.1 подключить nRF SWD. После valid TP_CELL_DBG.1 подключить BG95 debug.
11. Выполнить прошивку, verify, cold boot и recovery по точному стендовому release.
12. Выполнить электрические, storage, audio, GNSS, LTE, LoRa, BLE, OTA/A-B и серверные проверки.
13. Провести MSA и known-fault проверки оснастки.
14. Утвердить численные пределы. До утверждения строки OPEN_B01_FREEZE имеют HOLD или MEASURED, но не PASS.
15. Выполнить полный повторный EOL по утвержденным пределам.
16. Проверить evidence, хэши, отсутствие секретов и получить подписи оператора и независимого контролера.

## 8. Конкретные измерения на TP_EOL

### 8.1. До питания

Черный щуп DMM подключают к TP_EOL.1. Красным щупом последовательно измеряют TP_EOL.2, TP_EOL.3 и TP_EOL.4. Записывают полярность подключения, режим DMM, фактическое значение и время. До утверждения golden limits эти значения имеют статус MEASURED или HOLD.

### 8.2. Первое питание

Канал CH1 осциллографа подключают к TP_EOL.2, CH2 к TP_EOL.3, CH3 к TP_EOL.4, CH4 поочередно к TP_EOL.7 и TP_EOL.8. Земля каждого пассивного пробника подключается к TP_EOL.1 только если осциллограф и источник имеют безопасную общую землю. При сомнении применяется дифференциальный или изолированный пробник.

Записывают пуск, установившееся состояние, modem startup, LTE traffic burst, AAD idle, переход PDM и active capture. Для 3V8_MODEM действует уже установленный минимум: на всех VBAT pads U8 не ниже 3,3 В в EVT-PWR-01. Верхний предел, rail tolerance, ток и длительность провала замораживаются после B01.

### 8.3. UART и сигналы состояния

Сначала измеряют idle уровень TP_EOL.5 относительно .1 без подключенного входа оснастки. Затем подключают приемник UART к .5. Выход UART оснастки подключают к .6 только после valid TP_EOL.2. Выполняют `help`, чтение identity и полный self-test. Полный UART log сохраняют без закрытых ключей, IMSI и pairing secret.

TP_EOL.7 и .8 являются sense only. TP_EOL.10 и .11 считываются и сопоставляются с ревизией traveller. TP_EOL.12 и .13 подключаются только к open-drain adapter. INA226 ожидается по адресу 0x40, а его показания сравниваются с эталонным прибором.

### 8.4. BOOT0 recovery

1. Оставить TP_EOL.9 high-Z.
2. Прижать NRST через TP_MCU_SWD.4.
3. Задать BOOT0 через TP_EOL.9 current-limited 3,3 В.
4. Отпустить NRST.
5. После входа в system memory вернуть BOOT0 в high-Z.
6. Проверить service USB J11 или утвержденный системный интерфейс.
7. Снять питание, убрать BOOT0 drive и подтвердить обычную загрузку.

Нельзя подавать BOOT0 при свободном NRST и нельзя оставлять его активным после recovery.

## 9. Прошивка и recovery двух микроконтроллеров

Для STM32 подключение выполняется 5 GND, 1 VTREF, 4 NRST, 2 SWDIO, 3 SWCLK. Считывают device ID, flash size и полный профиль option bytes. Затем записывают точный HEX стендового выпуска, выполняют verify, reset и cold boot. До и после записи сохраняют option bytes. Mass erase выполняется только по оформленному recovery сценарию.

Для nRF52840 подключение выполняется 4 GND, 1 VTREF, 2 NRF_SWDIO, 3 NRF_SWCLK. Записывают точный `merged.hex`, выполняют verify, reset, MCUboot signed image check, BLE advertisement, GATT и UART IPC. STM32 SWD при этом не используется как общий интерфейс.

После прошивки должны совпасть точные SHA-256 из release contract. Несовпадение target, device ID, option bytes, signature или verify немедленно дает HOLD или FAIL.

## 10. BG95 recovery

В обычном режиме TP_CELL_DBG.4 должен быть LOW, а выход оснастки high-Z. После штатного включения BG95 измеряют TP_CELL_DBG.1 относительно .5. Только при valid VREF_1V8 подключают 1,8 В UART: DUT_TX .2 к входу оснастки, DUT_RX .3 к выходу оснастки.

Для USB recovery соединяют TP_CELL_USB.4, затем .2 и .3, после этого current-limited HOST_VBUS к .1. Если recovery требует USB_BOOT, current-limited 1,8 В HIGH подается через TP_CELL_DBG.4 только во время утвержденной power-on sequence. После enumeration выход возвращается high-Z.

На обесточенной плате отдельно подтверждают отсутствие непрерывности TP_CELL_USB.1-.3 с J11 VBUS, D+ и D-. Подключать TP_CELL_USB к обычному USB кабелю без изолированного current limiter запрещено.

## 11. Проверка микрофонов 3+1

На всех J_MIC1-J_MIC4 используется одинаковый порядок: pin 1 1V8_MIC, pin 2 GND, pin 3 PDM_CLK, pin 4 индивидуальный PDM_DATA, pin 5 индивидуальный MIC_WAKE, pin 6 общий AAD_CFG.

1. Измерить 1V8_MIC pin 1 относительно pin 2 на всех четырех жгутах.
2. Измерить общий PDM_CLK pin 3 при THSEL, active PDM и останове для AAD. Во время THSEL и PDM частота должна быть выше 50 кГц. Полные частотные и edge limits утверждаются после B01.
3. Захватить PDM_DATA1-4 на pin 4. Подтвердить четыре отдельных канала, отсутствие dropout и соответствие MIC1-MIC4 физической схеме 3+1.
4. Подать калиброванное событие и измерить MIC_WAKE1-4 на pin 5, агрегированное пробуждение, latency и false wake.
5. На pin 6 записать THSEL/AAD_CFG, stop symbol и возврат линии.
6. Сохранить WAV, raw PDM или утвержденный decoded capture, channel map, calibration hash и waveform.

Перестановка двух каналов должна быть обнаружена known-fault тестом. Если оснастка не обнаруживает перестановку, MSA имеет FAIL.

## 12. RF, GNSS, LTE и LoRa

J8 является LTE, J9 GNSS, J10 LoRa. До включения передатчика ставят 50 ohm load или разрешенную антенну. Открытый J8 или J10 блокирует передачу.

GNSS проверяется по valid fix, RMC, PPS и holdover. LTE проверяется по обеим SIM, public APN, attach, TLS, hostname, MQTT, heartbeat, event, application receipt, reconnect и store-and-forward. DIO-EVT-B01 работает только в tenant bench и не влияет на реальные станции. LoRa TX выполняется только в conducted или экранированной оснастке с утвержденным RU868 profile.

Мощность, чувствительность, GNSS PPS accuracy, holdover, antenna match и coexistence имеют OPEN_B01_FREEZE до калибровки RF стенда и измерения B01.

## 13. MSA и known-fault проверки

1. Выполнить десять полных повторов на одном B01 или golden unit без переустановки.
2. Выполнить по три переустановки тремя операторами.
3. Рассчитать повторяемость и воспроизводимость по каждой измеряемой величине.
4. Утвердить пределы MSA до применения оснастки к партии.
5. Проверить swapped MIC, отсутствующую RF нагрузку, wrong region, поврежденный storage, invalid TLS chain, serial mismatch и station ID mismatch.
6. Каждый known-fault должен дать ожидаемый FAIL и однозначно указать причину.

Golden unit не используют для разрушающего fault injection. Для таких проверок применяется отдельный sample.

## 14. Реестр измерений

Оператор заполняет XLSX. Для каждой строки обязательны attempt, фактическое значение или однозначный результат, единица, утвержденный нижний и верхний предел или discrete criterion, прибор, срок калибровки, evidence path, SHA-256, оператор, независимый контролер, UTC и статус.

Статус PASS допускается только если обязательный предел имеет состояние APPROVED, фактический результат соответствует пределу, evidence существует и SHA-256 корректен. OPEN_B01_FREEZE дает HOLD. MEASURED означает, что значение получено, но приемочное решение еще не утверждено. Старую попытку не удаляют. После ремонта создают новую attempt со ссылкой на NCR.

Сводный лист XLSX вычисляет общий gate. Пустое обязательное поле, незакрытый known-fault, просроченная калибровка, совпадение оператора и контролера или отсутствие evidence запрещают PASS.

## 15. Утверждение численных пределов

1. Выполнить MSA и подтвердить пригодность оснастки.
2. Получить минимум десять повторов B01 и данные golden unit, если он назначен.
3. Сопоставить данные с расчетом схемы, datasheet компонентов, безопасными абсолютными пределами и энергобюджетом.
4. Установить пределы с запасом, который превышает неопределенность измерения и variation оснастки.
5. Зафиксировать версию fixture, software, PCB, корпуса, жгутов и условий среды.
6. Получить подпись ответственного за разработку и независимого контролера качества.
7. Обновить JSON, XLSX и EOL software limits отдельным контролируемым изменением.
8. Повторить полный B01 EOL по утвержденным пределам.

Нельзя вычислять производственный предел только из одного измерения B01 или автоматически применять min/max наблюдаемой выборки.

## 16. Решение

PASS требует PASS каждой обязательной строки, PASS MSA, утвержденные численные пределы, полную регрессию, полный evidence manifest и две разные подписи. FAIL применяется при результате вне утвержденного предела или доказанной функциональной ошибке. HOLD применяется при отсутствии предела, калибровки, документа, однозначного результата или evidence.

Полный PASS разрешает подготовить отдельный production release и отдельный option-byte profile. Он не включает блокировку автоматически. Каждая станция DIO-EVT-001 - DIO-EVT-040 проходит собственный EOL PASS до применения производственной защиты и повторную проверку boot, version, heartbeat, event и receipt после нее.

## 17. Краткий порядок оператора

1. Verify configuration and calibration.
2. Keep all fixture outputs high impedance.
3. Install RF loads.
4. Power off and seat the PCB using H1-H4 and the orientation key.
5. Connect ground first, then sense inputs.
6. Measure unpowered rail resistance.
7. Apply current-limited power through J_PWR_IN only.
8. Verify TP_EOL.2, .3, .4, .7 and .8.
9. Enable UART, SWD, I2C or BG95 debug only after the matching reference voltage is valid.
10. Execute the register from top to bottom without skipping mandatory rows.
11. Save raw evidence and SHA-256 for every row.
12. Use HOLD for every undefined limit or missing record.
13. Obtain independent review before overall PASS.

## 18. English safety summary

The fixture contacts the bottom side of PCB-MAIN. The authoritative coordinates use the top-view board system. For a bottom fixture plate viewed from the pogo side use X fixture equals 110.00 minus X board and keep Y unchanged. Do not mirror the data twice.

Ground contacts mate first. VTREF and rail-sense contacts never source power. Fixture outputs remain high impedance until the related DUT voltage reference is valid. BOOT0 may be driven only while STM32 reset is asserted. BG95 debug uses 1.8 V only. TP_CELL_USB is isolated from J11. Its VBUS contact is the only controlled source in the pogo groups.

An undefined mandatory limit produces HOLD, not PASS. Firmware protection remains disabled until physical B01 qualification, fixture MSA, full regression and a separate production release are approved.

## 19. Подписи

| Роль / Role | Фамилия и имя / Name | Решение / Decision | Дата UTC | Подпись / Signature |
|---|---|---|---|---|
| Оператор испытаний / Test operator |  |  |  |  |
| Ответственный за оснастку / Fixture owner |  |  |  |  |
| Ответственный за выпуск / Release owner |  |  |  |  |
| Контролер качества / Quality reviewer |  |  |  |  |
