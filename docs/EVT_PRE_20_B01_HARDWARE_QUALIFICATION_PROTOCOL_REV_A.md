# Квалификация DIO-EVT-B01 Дионея EVT-PRE-20

**Ревизия:** Rev A
**Дата:** 07.10.2026
**Изделие:** DIO-EVT-B01, station ID 901, tenant bench
**Выпуск:** EVT_PRE_20_BENCH_RELEASE_2026100601
**Исходное состояние:** NOT_RUN
**Разрешение на блокировку:** DENIED

## 1. Назначение

Настоящий протокол задает обязательную квалификацию стендового образца DIO-EVT-B01 перед решением о выпуске отдельного производственного профиля защиты. Форма не подтверждает прохождение испытаний. Все строки исходно имеют статус NOT_RUN и заполняются только по результатам работ на собранной станции.

Подписанная прошивка, успешная сборка, host-тесты, симулятор и работа цифрового двойника не заменяют испытания реального таргета. До полного PASS сохраняются RDP Level 0, SWD и BOOT0 recovery. BOOT_LOCK, TrustZone, WRP и PCROP остаются отключенными.

## 2. Связанные файлы

| Файл | Назначение |
|---|---|
| `manufacturing/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.xlsx` | Заполняемая форма и сводное решение |
| `manufacturing/EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.json` | Машиночитаемая запись и исходный безопасный шаблон |
| `tools/validate_evt_pre_20_b01_hardware_qualification.py` | Проверка структуры и допуска |
| `firmware/targets/evt_pre_20/release/firmware_lock_interlock_rev_a.json` | Нормативная межблокировка |
| `manufacturing/EOL_TEST_SPEC.md` | Полная последовательность EOL |
| `manufacturing/EOL_RESULT_REGISTER.csv` | Реестр результата изделия |

## 3. Правила заполнения

1. До начала оператор сверяет serial, station ID, tenant, ревизии трех PCB и идентификаторы выпуска.
2. Для каждой проверки записывают фактический результат, предел, путь к evidence, SHA-256, оператора, контролера и время UTC.
3. Статус PASS допускается только при наличии измерения или однозначного результата, утвержденного предела и проверяемого evidence.
4. Статусы OPEN, NOT_RUN, FAIL и HOLD в любой обязательной строке запрещают общий PASS.
5. N/A для обязательных строк не применяется. Если проверка неприменима, выпускают контролируемое изменение матрицы с обоснованием до испытаний.
6. Оператор и контролер одной строки должны быть разными лицами.
7. Закрытые ключи, pairing secret, engineer key, полные IMSI и пароли к evidence не прикладывают. Фиксируют только допустимые открытые идентификаторы и хэши.
8. Отклонение оформляют в журнале deviation или NCR. До закрытия отклонения общий результат остается HOLD или FAIL.

## 4. Идентификация выпуска

| Параметр | Контрольное значение |
|---|---|
| Serial | DIO-EVT-B01 |
| Station ID | 901 |
| Tenant | bench |
| Release ID | EVT_PRE_20_BENCH_RELEASE_2026100601 |
| Release code | 2026100601 |
| STM32 | STM32U585VIT6Q |
| STM32 image SHA-256 | 27a4e2ba3de7f3e6b9720cb1d1a1b25da62a5164cd6362349a99e3d48f884ef5 |
| nRF52840 | Raytac MDBT50Q-P1MV2 / nRF52840 |
| nRF signed image SHA-256 | 27a9e76b969ba6197de9b77874786a304dc0c04efe2f8994307fdc35560dd89b |
| nRF merged HEX SHA-256 | 7528e8a474283776162c9ac49d3de5082aa86a9a0d0f98d66603fdb2132a0f7f |
| Option bytes | option_bytes_bench_rev_a.json |

## 5. Последовательность квалификации

### 5.1. Подготовка

Проверяют калибровку измерительных средств, версию программы оснастки и MSA на golden unit и known-fault samples. Сохраняют исходное состояние option bytes, flash, калибровки и конфигурации. Станцию подключают к tenant bench. Использование production tenant для разрушающих и fault-injection проверок не допускается.

### 5.2. Микроконтроллеры и восстановление

STM32 и nRF52840 прошивают через раздельные SWD. Выполняют verify, разрешенный read-back и холодный запуск. Для STM32 отдельно подтверждают SWD, BOOT0, system memory и A/B trial, confirmation и rollback. Обрыв питания выполняют на всех стадиях, указанных в методике. Для nRF52840 подтверждают MCUboot signed boot, update, rollback и serial recovery. После перезапуска каждого МК проверяют восстановление UART IPC.

### 5.3. Каналы и накопители

Проверяют соответствие MIC1 - MIC4, полярность, усиление, шум, фазу и клиппирование. Активная калибровка должна иметь утвержденный SHA-256. QSPI и microSD проходят чтение, запись, проверку SHA-256, контроль свободного места и восстановление после прерванной записи.

### 5.4. Связь, сервер и время

Для BG95 проверяют IMEI, обе полные ICCID, соответствие слотов, разрешенный APN и failover. Включают проверку CA и hostname. На dioneya.ru в tenant bench подтверждают DNS, время, mutual TLS, MQTT, heartbeat, тестовое событие, application receipt, command ACK и reconnect. GNSS и PPS измеряют по утвержденным пределам. LoRa испытывают только в разрешенной RF-оснастке с правильным регионом и нагрузкой.

### 5.5. Питание, среда и механика

Измеряют напряжения и токи S0 - S4, запуск, заряд, MPPT и защиты. Выполняют температурные и силовые циклы. Проверяют корпус, кабельные вводы, герметичность и отвод конденсата. Численные пределы выпускают после MSA оснастки и измерений golden unit и B01.

### 5.6. Приложение и provisioning

Устанавливают release APK и проверяют QR, физическое окно сервиса, BLE LESC, авторизацию, запись и read-back конфигурации и подписанный OTA. Проверяют уникальный сертификат, цепочку, ACL, CRL, pairing и station secrets. После commissioning формируют receipt без закрытых ключей и секретов.

### 5.7. EOL и регрессия

Выполняют полный EOL. В строке DIO-EVT-B01 файла EOL_RESULT_REGISTER.csv заполняют все обязательные поля и ставят PASS только после проверки evidence. Затем повторяют полную регрессию прошивки, приложения, provisioning и связки со стендовым контуром Мухоеда.

## 6. Решение

Общий результат PASS допускается только если все обязательные строки матрицы имеют PASS, все evidence доступны и проверены, численные пределы утверждены, полная регрессия имеет PASS и два разных ответственных лица подписали решение.

Даже полный PASS настоящего протокола не включает блокировку автоматически. Он разрешает подготовить отдельный production release ID и отдельный профиль option bytes. Применение защиты к конкретной станции допускается только после ее собственного EOL PASS и требует обязательной проверки загрузки, версии, heartbeat, тестового события и receipt после применения защиты.

RDP Level 2 запрещен. Для него требуется отдельное решение, которое прямо фиксирует необратимость.

## 7. Подписи

| Роль | Фамилия, имя | Решение | Дата и время UTC | Подпись |
|---|---|---|---|---|
| Ответственный за испытания |  |  |  |  |
| Ответственный за выпуск |  |  |  |  |
| Контролер качества |  |  |  |  |

## 8. English summary

This protocol is the mandatory real-hardware qualification record for DIO-EVT-B01. Its initial state is NOT_RUN and firmware locking is DENIED. Every mandatory row requires a PASS, a result, an approved limit, an evidence path and SHA-256, an operator, an independent reviewer and a UTC timestamp.

Complete qualification does not enable locking. It only permits preparation of a separate production release and option-byte profile. Every production station still requires its own EOL PASS before protection is applied, followed by boot, version, heartbeat, test-event and server-receipt checks. RDP Level 2 remains prohibited without a separate explicit irreversible decision.
