# Инструкция по прошивке, настройке и испытаниям станции «Дионея» EVT-PRE-20

**Ревизия:** Rev C
**Дата:** 06.10.2026
**Объект:** станция «Дионея» EVT-PRE-20, PCB-MAIN на STM32U585VIT6Q, модуль BLE nRF52840, PCB-PWR и четыре PCB-MIC
**Основание:** стендовый программный комплект `EVT_PRE_20_BENCH_RELEASE_2026100601`; точный commit указан в `release_manifest.json`

## 1. Назначение и границы применения

Документ устанавливает единый порядок проверки программного комплекта, прошивки двух микроконтроллеров, выпуска уникальных данных станции, регистрации в PKI и MQTT, настройки через приложение монтажника, первичного подключения к `dioneya.ru`, проведения EOL и EVT, оформления результатов и восстановления после типовых отказов.

Инструкция применяется к двум партиям по 20 станций и одному стендовому изделию. Серийные номера берутся только из контролируемых реестров `manufacturing/LOT_SERIAL_REGISTER.csv` и `manufacturing/LOT_SERIAL_REGISTER_LOT2_AND_BENCH.csv`. Сопоставление фиксировано: `DIO-EVT-001` - `DIO-EVT-040` имеют station ID 1-40 и tenants `pilot1` или `pilot2`; стендовая станция `DIO-EVT-B01` имеет station ID 901 и tenant `bench`. Диапазон 9001-9040 зарезервирован за цифровыми двойниками и физическим станциям не назначается.

Текущий стендовый комплект содержит подписанный STM32U585, подписанный nRF52840 с MCUboot и подписанный release APK. Комплект разрешен для прошивки `DIO-EVT-B01` и аппаратной проверки. Он использует прикладную Ed25519-проверку образа STM32 и A/B-логику с сохраненным SWD recovery. Неизменяемый production root of trust и необратимая защита option bytes этим комплектом не вводятся.

Для 40 полевых станций используются те же проверенные программные компоненты после аппаратного подтверждения, выпуска уникального сертификата каждой станции, загрузки TLS-материала в BG95, положительного EOL и отдельного решения по production protection profile. Закрытые ключи, пароли, Android keystore и ключи CA не входят в передаваемый архив.

Документ не разрешает программирование необратимых option bytes, включение RDP Level 2, окончательную блокировку отладки, загрузку закрытых ключей в Git, передачу производственных секретов контрактному сборщику и радиопередачу LoRa вне согласованного стенда до выпуска утвержденного профиля RU868.


### 1.1. Обязательная сквозная последовательность

Для одной станции применяется только следующая последовательность. Перестановка шагов допускается лишь там, где это прямо указано.

1. Назначить serial, station ID, tenant, номера плат и SIM в traveller. Физическим станциям разрешены только `DIO-EVT-001` - `DIO-EVT-040` и `DIO-EVT-B01`.
2. Проверить релизный ZIP, `release_manifest.json`, `SHA256SUMS.txt`, подписи STM32, nRF52840 и APK. При несовпадении хотя бы одного хэша остановить работу.
3. Выполнить входной контроль платы, снять исходные option bytes STM32 и сохранить их до записи.
4. Прошить и проверить STM32. Затем через отдельный SWD прошить и проверить nRF52840.
5. Проверить или создать запись станции в PKI. Выпустить уникальный station certificate, защищенный station package и этикетку. Для полевых станций private key создается на изолированном EOL-месте и не передается на сервер.
6. Через изолированный TEST_UART выполнить однократную команду `factoryid` с serial и pairing secret из station package. Сделать полный цикл снятия питания.
7. Проверить factory identity командой `secrets`, открыть service window и выполнить первое LESC-сопряжение только по этикетке этого serial.
8. Считать фактические ICCID обеих SIM, выпустить station secrets и записать их через приложение. После read-back удалить временный export.
9. Загрузить в BG95 CA, station certificate и station private key. Проверить размер, checksum, список файлов и привязку SSL context.
10. Записать server profile, APN, SIM mapping, координаты и остальные параметры. Выполнить read-back и сверить canonical SHA-256.
11. Обновить CRL и ACL. Проверить SIM registration, PDP, DNS, TLS, MQTT, heartbeat, событие, application receipt, signed command ACK, store-and-forward и вторую SIM.
12. Выполнить полный EOL. Только после PASS оформить receipt и перевести станцию командой `station-commission`.

Контрольные точки:

| Точка | Что уже должно быть подтверждено | Переход запрещен, если |
|---|---|---|
| G1, до прошивки | Serial, платы, релиз, хэши, fixture, исходные option bytes | Есть расхождение идентификатора или хэша |
| G2, после MCU | STM32 и nRF записаны, verify и cold boot PASS | Есть boot loop, verify FAIL или неизвестные option bytes |
| G3, до первого BLE | PKI-запись, station package и label согласованы; `factoryid` записан | Serial, station ID, tenant или pairing material расходятся |
| G4, до выхода в LTE | Station secrets и BG95 TLS files проверены; ACL обновлен | SIM, APN, certificate или key не подтверждены |
| G5, до commissioned | EOL, heartbeat, event receipt, command ACK и evidence PASS | Есть FAIL, HOLD, необработанный NCR или временный секрет не удален |

## 2. Роли и ответственность

| Роль | Ответственность | Обязательная запись |
|---|---|---|
| Ответственный за выпуск | Выбирает commit, присваивает номер версии, утверждает manifest и хэши | Release manifest и подпись решения |
| Оператор прошивки | Проверяет изделие, подключает SWD, выполняет запись и verify | Лог STM32CubeProgrammer по серийному номеру |
| Специалист provisioning | Назначает UUID, сертификат, SIM, APN, endpoint, профиль и калибровку | Контролируемая receipt без секретов |
| Испытатель | Выполняет EOL и EVT, сохраняет первичные данные | EOL bundle и протокол испытаний |
| Контролер качества | Проверяет полноту, взаимную согласованность и отклонения | Подпись traveller и решение PASS, FAIL или HOLD |
| Администратор сервера | Создает разрешенную запись станции и проверяет обмен с `dioneya.ru` | Серверный журнал регистрации и приема телеметрии |

Один оператор не должен единолично создавать ключ выпуска, подписывать образ и подтверждать успешное программирование. Для производственного выпуска требуется принцип двойного контроля.

## 3. Состояние программного комплекта на дату выпуска инструкции

| Объект | Подтверждено | Что остается проверить на железе |
|---|---|---|
| Host-тесты firmware | 74 из 74 PASS | GPIO, периферия, питание, timing и RF |
| STM32U585 | Подписанный образ версии 2026100601, Ed25519 key ID `04b418857c5001b2`; заводские serial и pairing secret сохраняются в NOR | SWD read-back, option bytes, cold boot, A/B power-cut, первое `factoryid` на B01 |
| STM32 Flash | 249024 байт из 1016 КиБ, 23,94 процента | Фактическое время записи и запуска |
| STM32 SRAM1-3 | 714008 байт из 786432 байт, 90,79 процента | Runtime watermark heap и стеков |
| Максимальный stack frame | 2304 байт, gate PASS | Watermark каждой FreeRTOS-задачи |
| nRF52840 | `0.1.0+2026100501`, MCUboot ECDSA P-256, подпись проверена | SWD, BLE LESC, GATT, UART IPC, serial recovery |
| Android | Release APK `0.1.0-bench.20261005`, unit tests PASS, APK Signature Scheme v2 PASS | Установка на утвержденные телефоны и реальный GATT |
| STM32 A/B | Прикладная подпись и A/B-логика собраны | Отключение питания на всех стадиях, rollback, recovery |
| PKI сервера | `dioneya.ru:8883`, root и issuing CA, реестр, ACL и CRL реализованы | Выпуск сертификата конкретной станции и mTLS с BG95 |
| Секреты станции | BLE ICD v0.3, фабричные serial/pairing, station secrets, engineer role и command public key реализованы и проверены host-тестами | Запись `factoryid`, cold boot, первое LESC и сохранность в NOR на B01 |
| BG95 TLS material | Загрузчик `QFUPL/QFLST/QSSLCFG` реализован и host-тестирован | Привязка к EOL-оснастке или прямому сервисному UART, проверка на модеме |
| LoRa RU868 | Профиль-кандидат и fail-closed политика | `tx_enabled: false` до RF release |

Контрольные данные комплекта `EVT_PRE_20_BENCH_RELEASE_2026100601`:

| Файл | Размер | SHA-256 |
|---|---:|---|
| STM32 signed BIN | 249024 байт | `27a4e2ba3de7f3e6b9720cb1d1a1b25da62a5164cd6362349a99e3d48f884ef5` |
| nRF52840 signed BIN | 208227 байт | `27a9e76b969ba6197de9b77874786a304dc0c04efe2f8994307fdc35560dd89b` |
| nRF52840 merged HEX | по manifest | `7528e8a474283776162c9ac49d3de5082aa86a9a0d0f98d66603fdb2132a0f7f` |
| Android APK | 353026 байт | `39f45d4cd24cb2ce318d6e748cb9a581857e98ceeee0a4f2ddfcec9d6e7519fe` |
| Полный ZIP | по фактическому файлу | Сверить с внешней ведомостью передачи; хэш архива не может быть записан внутрь самого архива |

Внутри архива `release_manifest.json` связывает файлы с точным commit и содержит SHA-256 каждого вложенного файла. Перед каждой прошивкой оператор повторно вычисляет SHA-256 локального архива по внешней ведомости передачи и каждого выбранного файла по manifest.

## 4. Требования к рабочему месту

### 4.1. Оборудование

- ESD-рабочее место с заземленным ковриком и браслетом.
- Лабораторный источник с регистрацией тока, регулируемым напряжением и аппаратным ограничением тока.
- ST-LINK/V3 с известным серийным номером, актуальной прошивкой probe и линией NRST.
- Переходник или pogo fixture для `TP_MCU_SWD`, `TP_EOL` и при необходимости `TP_BLE_SWD`.
- Цифровой мультиметр, осциллограф, токовые щупы или регистратор питания, тепловизор.
- USB-UART 3,3 В для LPUART1, вход fixture должен быть высокоомным до появления VTREF.
- Android-устройство без обязательной зависимости от Google Mobile Services. Для приемки нужен минимум один Huawei без GMS и еще два утвержденных устройства.
- Две тестовые SIM с публичными APN, разрешенными проектом, и достаточным балансом.
- Антенны или согласованные 50-омные нагрузки для LTE, GNSS и LoRa. Передача LoRa до RF release выполняется только через conducted/shielded setup.
- GNSS-антенна с видимостью неба либо GNSS-симулятор.
- Акустический стенд: калиброванный излучатель, опорный микрофон, геометрический шаблон 3+1.
- Утвержденные microSD и W25Q512JV на изделии.

### 4.2. Программное обеспечение

| Компонент | Проверенная версия или правило |
|---|---|
| Git | Версия фиксируется в build log |
| CMake | 4.4.3 для воспроизведения доказанной сборки |
| Ninja | 1.13.2 для воспроизведения доказанной сборки |
| Arm GNU Toolchain | 14.2.Rel1 |
| Python | 3.11 или 3.12, разрядность и версия фиксируются в EOL log |
| Python cryptography | 46.0.0 - 46.0.3 по `05_EOL_TOOLS/requirements-eol-pki.txt` |
| STM32CubeMX | 6.12.0, база DB.6.0.120 для проверки `.ioc` |
| STM32CubeProgrammer | Утвержденная на день выпуска версия, версия и ST-LINK firmware пишутся в лог |
| Android Gradle Plugin | 9.4.0 |
| Gradle | 9.6.0 |
| Android compile SDK | 36 |
| Android Build Tools | 36.0.0 |
| nRF Connect SDK | v2.7.0 |
| Zephyr SDK | 0.16.5 |
| JDK | 21.0.12.1+1; полная версия пишется в build log |

Сборка target впервые получает зависимости из официальных репозиториев ST и FreeRTOS. Для производственного повторения зависимости предварительно зеркалируют и сверяют по закрепленным commit и tag. Сборка с незаписанным происхождением зависимостей не принимается.

## 5. Входные данные перед началом работ

До подачи питания оператор должен получить и зарегистрировать:

- серийный номер станции и номера всех плат по traveller;
- ревизии PCB-MAIN, PCB-PWR и четырех PCB-MIC;
- утвержденный release manifest с commit, версией, размерами и SHA-256;
- инженерное разрешение, если используется неподписанная лабораторная сборка;
- распиновку оснастки и дату ее калибровки;
- назначение SIM1 и SIM2, их контролируемые ссылки ICCID и preferred slot;
- разрешенный tenant, station ID, endpoint и набор public APN;
- идентификатор набора калибровки микрофонов;
- решение по режиму LoRa. При отсутствии подписанного профиля TX остается выключенным;
- форму EOL record и каталог хранения первичных данных.

Если хотя бы один идентификатор расходится между traveller, QR, serial register и release manifest, работа останавливается со статусом HOLD. Исправлять идентификатор вручную в одном документе без ECO запрещено.

## 6. Проверка платы до подключения программатора

1. Убедиться, что питание отключено, батарея и солнечная панель отсоединены.
2. Осмотреть PCB-MAIN, PCB-PWR и PCB-MIC под увеличением. Не допускаются перемычки припоя, незаполненные обязательные позиции, трещины, обратная полярность, загрязнение RF и акустических областей.
3. Проверить DNP по сборочной документации. DNP-резисторы не должны быть установлены. Net tie являются рисунком меди платы и не устанавливаются как детали.
4. Проверить сопротивление основных шин относительно GND и сравнить с утвержденными лимитами платы. Поскольку окончательные числовые EOL limits еще открыты, исходные значения каждой первой платы сохраняются и сравниваются с golden unit только после его утверждения.
5. Убедиться, что в SIM-слотах и microSD нет посторонних предметов.
6. Проверить установку LTE, GNSS и LoRa коаксиальных кабелей. Не подавать питание на передатчик без антенны или 50-омной нагрузки.
7. Проверить полярность соединения PCB-PWR и PCB-MAIN, положение ключей разъемов, фиксацию жгутов и отсутствие натяжения.
8. Для первого питания установить источник в режим ограничения тока. Конкретное напряжение и лимит берутся из утвержденного листа питания изделия и traveller, а не выбираются оператором по памяти.

## 7. Подключение SWD и EOL fixture

### 7.1. TP_MCU_SWD

| Контакт | Сигнал | Подключение ST-LINK | Правило |
|---:|---|---|---|
| 1 | VTREF | VTREF sense | Только измерение напряжения цели, не питать станцию от ST-LINK |
| 2 | SWDIO | SWDIO | Прямой управляемый контакт к PA13 |
| 3 | SWCLK | SWCLK | Прямой управляемый контакт к PA14 |
| 4 | NRST | NRST | Нужен для режима Connect Under Reset |
| 5 | GND | GND | Земля должна соединиться раньше активных сигналов |

Порядок подключения: GND, VTREF, NRST, SWDIO, SWCLK. Порядок отключения обратный. До появления корректного VTREF выходы fixture должны оставаться высокоомными.

### 7.2. TP_EOL

| Контакт | Сигнал | Назначение |
|---:|---|---|
| 1 | GND | Общая цифровая земля fixture |
| 2 | VTREF_3V3 | Высокоомное измерение 3V3_DIGITAL |
| 3 | VSENSE_3V8 | Высокоомное измерение 3V8_MODEM |
| 4 | VSENSE_1V8 | Высокоомное измерение 1V8_MIC |
| 5 | DUT_TX | TEST_UART_TX, выход станции |
| 6 | DUT_RX | TEST_UART_RX, вход станции |
| 7 | PWR_GOOD | Только наблюдение |
| 8 | FAULT | Только наблюдение |
| 9 | BOOT0 | Управлять только при активном reset, затем высокий импеданс |
| 10 | REV0 | Только считывание аппаратной ревизии |
| 11 | REV1 | Только считывание аппаратной ревизии |
| 12 | I2C_SCL | Open-drain, не добавлять pull-up без отдельного разрешения |
| 13 | I2C_SDA | Open-drain, не добавлять pull-up без отдельного разрешения |

USB-C J11 является сервисным USB устройства STM32 и не является входом питания станции. VBUS используется только как защищенное высокоомное sense. Нельзя соединять J11 с изолированным BG95 USB fixture.

## 8. Получение исходников и фиксация версии

1. Создать чистый каталог сборки.
2. Получить утвержденную ветку и checkout exact commit из release manifest.
3. Проверить отсутствие незакоммиченных изменений.
4. Записать вывод `git rev-parse HEAD`, `git status --short`, версии toolchain и время UTC.
5. Проверить manifest зависимостей STM32CubeU5, CMSIS и FreeRTOS.
6. Не собирать производственный пакет из рабочей копии с локальными изменениями.

Контрольные команды:

```text
git rev-parse HEAD
git status --short
cmake --version
ninja --version
arm-none-eabi-gcc --version
STM32_Programmer_CLI.exe --version
```

## 9. Проверка host-части прошивки

Из корня репозитория выполнить:

```text
cmake -S firmware -B build-host -DCMAKE_BUILD_TYPE=Release
cmake --build build-host --parallel
ctest --test-dir build-host --output-on-failure
```

Критерии:

- конфигурация, компиляция и линковка завершаются без ошибки;
- все 74 текущих host-теста проходят;
- в журнале нет пропущенных тестов, которые release manifest объявляет обязательными;
- журнал сохраняется в каталог evidence вместе с commit и версиями инструментов.

Host PASS подтверждает переносимую логику, но не заменяет проверку GPIO, питания, PDM, GNSS, BG95, RF, памяти и timing на собранной плате.

## 10. Проверка и воспроизведение target STM32U585

### 10.1. Основной путь для стендового образца

Для `DIO-EVT-B01` сборка оператором не требуется. Используется только архив `EVT_PRE_20_BENCH_RELEASE_2026100601.zip`. Оператор обязан:

1. Проверить SHA-256 ZIP.
2. Распаковать архив в новый каталог с ограниченным доступом.
3. Выполнить `tools/validate_evt_pre_20_bench_release.py` из точного commit, если исходники доступны.
4. Сверить `source_git_head`, `source_tree_clean`, release ID и все строки `SHA256SUMS.txt`.
5. Проверить подпись STM32 штатным валидатором, подпись nRF через `imgtool verify`, подпись APK через `apksigner verify --verbose --print-certs`.
6. Не заменять ни один файл после проверки. Любое изменение требует нового release ID и нового manifest.

### 10.2. Воспроизведение сборки разработчиком

Воспроизведение выполняется только из commit, указанного в manifest. Для STM32 используется Arm GNU 14.2.Rel1 и target CMake. Значение `ZS_FW_VERSION_CODE` должно равняться 2026100601, а `ZS_FW_RELEASE_PUBLIC_KEYS` должно содержать выпущенный public key. После сборки обязательны анализ map, контроль stack usage и повторная подпись на изолированном signing workstation.

Закрытый firmware release key уже выпущен. Его нельзя регенерировать для каждой станции. Команда `fw-release-key` применяется только при формально утвержденной ротации с новым public key, переходным выпуском и планом восстановления. Обычный выпуск образа выполняется командой `fw-sign` на offline workstation. Закрытый ключ не передается на сервер, телефон, станцию или производственную площадку.

### 10.3. Контроль результата

1. Проверить ELF, BIN, HEX, MAP, manifest и signature.
2. Сверить target, hardware revision, размер, SHA-256, version code и key ID.
3. Проверить Flash, SRAM и stack usage.
4. Проверить встроенную строку `0.1.0-bench.20261006` и version code 2026100601.
5. Проверить отсутствие закрытых ключей, паролей и keystore в каталоге результата.
6. Сохранить build evidence и полный журнал подписи.

Текущий комплект является стендовым. Производственная блокировка отладки, неизменяемый root of trust и окончательная карта защиты выпускаются отдельным решением после аппаратного EVT.

## 11. Прошивка STM32 через SWD

### 11.1. Подготовка

1. Отключить батарею и солнечную панель.
2. Подключить лабораторное питание через штатный вход с утвержденным ограничением тока.
3. Подключить fixture по разделу 7.
4. Проверить VTREF около номинала 3V3_DIGITAL.
5. Записать серийный номер ST-LINK, версию probe и рабочее место.
6. Сверить SHA-256 `01_STM32/dioneya_evt_pre_20_2026100601.hex` с `SHA256SUMS.txt`.

### 11.2. Идентификация и снимок option bytes

Сначала подключиться в режиме Connect Under Reset и считать device ID, flash size, option bytes и уровень RDP. Снимок сохранить до любой записи. Профиль `option_bytes_bench_rev_a.json` разрешает только RDP Level 0, отключенный TrustZone, отключенный BOOT_LOCK, сохраненный BOOT0 recovery, отсутствие WRP и PCROP. Неизвестные поля сохраняются без изменения.

### 11.3. Запись и verify

Пример для STM32CubeProgrammer CLI:

```text
STM32_Programmer_CLI.exe -c port=SWD mode=UR freq=1000 -w 01_STM32/dioneya_evt_pre_20_2026100601.hex -v -rst
```

После записи выполнить отдельный read-back или verify, сохранить лог и повторно считать option bytes. HEX используется для первичной SWD-записи. Файлы `2026100601.manifest.cbor`, `2026100601.sig` и signed BIN используются для проверки выпуска и последующих OTA/A/B испытаний; отсутствие подписи внутри HEX не заменяется переименованием файла.

### 11.4. Первый запуск

1. Отключить SWD-сессию и выполнить полный цикл снятия и подачи питания.
2. Подключить TEST_UART 3,3 В.
3. До ввода `factoryid` допустим только заводской placeholder. После ввода проверить serial `DIO-EVT-B01`, версию `0.1.0-bench.20261006`, release code 2026100601, bank и boot status.
4. Проверить, что firmware release key count не равен нулю.
5. Проверить отсутствие boot loop, HardFault и повторных watchdog reset.
6. Записать Flash/RAM watermark после базового self-test.

### 11.5. Ошибки

При несовпадении MCU, option bytes, SHA-256 или verify работа прекращается. Повторную запись допускается выполнить один раз после проверки питания и контактов. Второй FAIL переводит изделие в HOLD. Не применять mass erase, RDP Level 2 или блокировку recovery без отдельного утвержденного профиля.

## 12. Восстановление STM32

### 12.1. SWD не подключается

1. Проверить GND, VTREF, NRST, SWDIO и SWCLK по fixture.
2. Уменьшить SWD frequency до 100 кГц.
3. Использовать `mode=UR reset=HWrst`.
4. Проверить, что fixture действительно управляет NRST, а не только подает SWDIO/SWCLK.
5. Проверить отсутствие воздействия BOOT0 и внешних цепей на debug pins.
6. Считать option bytes, если соединение восстановилось. Не выполнять readout unprotect без разрешения, так как операция может стереть память.
7. Если защита соответствует производственному профилю, применять только утвержденную процедуру debug authentication или secure recovery.

### 12.2. System memory recovery через USB

USB-C J11 предназначен для service and system memory recovery, но не питает станцию. Вход BOOT0 разрешается fixture только при reset. Конкретная последовательность USB DFU должна быть подтверждена на первой собранной PCB-MAIN и закреплена после сверки с AN2606 для STM32U585. До подтверждения USB recovery не считается закрытым EOL-путем.

### 12.3. Ошибка verify

- повторно сверить SHA-256 локального файла;
- проверить питание и падение напряжения во время erase/program;
- проверить надежность pogo-контактов и NRST;
- повторить запись один раз после полного power cycle;
- при повторном FAIL перевести плату в HOLD, сохранить лог и не переходить к provisioning.

## 13. Прошивка и восстановление nRF52840

PCB-MAIN содержит отдельный nRF52840 Raytac MDBT50Q-P1MV2. Его SWD не совмещен со SWD STM32. Перед подключением сверить VTREF, NRF_SWDIO, NRF_SWCLK и GND.

Для первой записи используется `02_NRF52840/merged.hex`, включающий MCUboot и приложение. SHA-256 merged HEX должен быть `7528e8a474283776162c9ac49d3de5082aa86a9a0d0f98d66603fdb2132a0f7f`. Пример команды Nordic:

```text
nrfjprog --family NRF52 --program 02_NRF52840/merged.hex --chiperase --verify --reset
```

Если производственная оснастка использует J-Link или другое утвержденное средство, команда меняется, но последовательность erase, program, verify, reset и сохранение лога остается обязательной. Не стирать STM32 при работе с nRF SWD.

До прошивки проверить подпись `nrf52840_ble_0.1.0+2026100501.signed.bin` с public key из пакета. Ожидаемая версия: `0.1.0+2026100501`; SHA-256 signed BIN: `27a9e76b969ba6197de9b77874786a304dc0c04efe2f8994307fdc35560dd89b`.

После reset проверить MCUboot, advertisement, local name, LESC pairing, GATT service, UART IPC со STM32 и передачу identity. Затем проверить serial recovery и обновление application slot через mcumgr. Ошибка SWD, MCUboot, подписи или UART IPC блокирует переход к provisioning.

## 14. Установка приложения монтажника

### 14.1. Проверка APK

Используется только `03_ANDROID/dioneya-commissioning-0.1.0-bench.20261005.apk`. Перед установкой проверить:

- SHA-256 `39f45d4cd24cb2ce318d6e748cb9a581857e98ceeee0a4f2ddfcec9d6e7519fe`;
- package ID `ru.dioneya.commissioning`;
- versionCode 2026100501 и versionName `0.1.0-bench.20261005`;
- APK Signature Scheme v2;
- один подписант;
- SHA-256 сертификата `64b9b31cc6e64bdbc09457254501812634872a8e05de1a95e7d8c638dbfed90a`.

### 14.2. Установка

На выделенном телефоне включить режим разработчика и выполнить:

```text
adb devices -l
adb install -r 03_ANDROID/dioneya-commissioning-0.1.0-bench.20261005.apk
```

Сверить точный serial подключенного телефона. После установки отключить USB debugging, если он не нужен для испытаний. Приложение работает без GMS и не требует доступа к ключам подписи APK.

### 14.3. Данные на телефоне

Файл station secrets используется только для одной записи 0x0206 и приложением не сохраняется. Исходный файл в Downloads или на съемном носителе оператор удаляет после подтвержденной записи. Ключ инженера хранится в Android Keystore только на авторизованном инженерном телефоне. На обычном телефоне монтажника ключ инженера после commissioning не оставляют.

Перед использованием на партии выполнить проверку на трех утвержденных моделях, включая Huawei без GMS, и проверить запрет вывода секретов, полного ICCID, IMSI и private key в export и log.

## 15. Вход станции в сервисный режим

На Rev A отдельного service-button pin нет. Вход TAMPER_IN PC7 совмещает функцию датчика корпуса и сервисного триггера:

1. Короткое открытие контура трактуется как tamper event.
2. Удержание активного состояния 5 секунд запрашивает сервисный режим.
3. Сервисное окно ограничено 10 минутами.
4. Вне сервисного окна конфигурация по BLE должна быть отклонена.
5. Для стенда доступна команда консоли `svc`, но она не является полевой процедурой.

Перед использованием этого механизма на изделии проверить полярность фактического концевика: штатно контур замкнут на GND, разрыв означает alarm или неисправность кабеля.

## 16. Выпуск ключей, регистрация и настройка станции

### 16.1. Какие ключи используются

| Объект | Назначение | Где находится закрытая часть | Действие для каждой станции |
|---|---|---|---|
| Root CA | Корень сертификатов MQTT | Offline machine | Не выпускать повторно |
| Issuing CA | Подпись station CSR | Сервер PKI | Использовать существующий CA |
| Station ECDSA P-256 key | mTLS конкретной станции | Устройство или EOL fixture; для B01 допустим защищенный server-side key | Новый уникальный ключ и сертификат |
| Pairing secret | LESC passkey из этикетки | Реестр PKI и этикетка | Уникальный на станцию, действует до ротации |
| Engineer key | Повышение роли B.9 | Реестр, станция, Android Keystore инженера | Уникальный на станцию |
| Command signing key | Подпись удаленных команд | Только сервер | На станцию записывается public key |
| Firmware release key | Подпись STM32 и модели | Offline signing workstation | Один ключ выпуска, не ключ станции |
| nRF MCUboot key | Подпись nRF image | Внешнее signing storage | Один ключ выпуска, public key в MCUboot |
| Android release key | Подпись APK | Внешний keystore | Один ключ приложения |
| SIM Ki/OPc | Аутентификация SIM в сети оператора | Только SIM и защищенный контур оператора | Проект не выпускает, не читает и не копирует |

Pairing secret на этикетке не является одноразовым. Связывание выполняется заново для каждого сеанса без bonding, а секрет действует до формальной ротации. При утрате или компрометации этикетки выполнить `pairing-secret-rotate`, перепечатать этикетку и перезаписать секрет станции.

ICCID и IMSI являются идентификаторами SIM, а не ключами. Для EVT применяются SIM с отключенным PIN: текущая прошивка проверяет `AT+CPIN?`, но не вводит PIN. Если ответ отличается от `+CPIN: READY`, дальнейшая регистрация запрещена. APN берется только из утвержденного профиля, не подбирается оператором вручную.

Материалы разделяются так:

- публичные: CA chain, server fingerprint, `bundle.json`, server QR, certificate станции и CSR;
- защищенные EOL: `station-package`, `station.json`, label QR и его текст, `station-secrets`, engineer key;
- закрытые: station private key, Root CA private key, Issuing CA private key, command signing private key, firmware signing keys и Android keystore.

`station-package` не содержит station private key, но содержит pairing secret и engineer key. Поэтому его нельзя помещать в Git, общий сетевой каталог, паспорт изделия или обычный производственный архив. QR этикетки также содержит pairing secret. Вывод команды `label-qr` не печатает payload в консоль, но созданные `.txt`, `.svg` и `.png` остаются защищенными файлами.

### 16.2. Предварительная проверка сервера

PKI для `dioneya.ru` уже создана. Не выполнять `root-init`, `issuing-request`, `issuing-sign`, `issuing-install`, `server-cert` или принудительную ротацию CA при регистрации обычной станции.

С управляющего компьютера используется `F:\Проекты\muhoed-deploy\muhoed.ps1`. Сначала выполнить:

```text
F:\Проекты\muhoed-deploy\muhoed.ps1 status
F:\Проекты\muhoed-deploy\muhoed.ps1 pki list
F:\Проекты\muhoed-deploy\muhoed.ps1 pki audit --limit 50
```

Проверить MQTT host `dioneya.ru`, port 8883, server fingerprint из действующего `bundle.json`, сроки root, issuing и server certificates, состояние CRL и наличие tenant `bench`, `pilot1`, `pilot2`. Секреты и passphrase не помещать в историю PowerShell, журналы или скриншоты.

Действующий публичный профиль на дату выпуска: MQTT `dioneya.ru:8883`, `ca_reference=dioneya-root`, server fingerprint SHA-256 `1d21adc6b68c70c652bf2030e1c8a37f41e558f601257b03f2ca95055c711544`. Перед каждой партией значение повторно считывается из `bundle.json`; значение в настоящем документе не заменяет проверку действующего bundle.

### 16.3. Регистрация стендовой станции DIO-EVT-B01

1. Проверить, что реестр содержит `DIO-EVT-B01`, station ID 901, lot `BENCH`, tenant `bench`.
2. Если записи нет, выполнить `F:\Проекты\muhoed-deploy\muhoed.ps1 pki station-add DIO-EVT-B01 --note "EVT bench"`.
3. Только для B01 разрешена генерация station key на стороне защищенного PKI: `F:\Проекты\muhoed-deploy\muhoed.ps1 pki station-keygen DIO-EVT-B01 --allow-server-side-key`.
4. Повторная команда keygen без процедуры ротации запрещена. При уже выпущенном сертификате использовать существующий ключ или формальную revoke/reissue процедуру.
5. Сформировать публичный bundle и защищенный station package:

```text
F:\Проекты\muhoed-deploy\muhoed.ps1 pki bundle --mqtt-host dioneya.ru --mqtt-port 8883
F:\Проекты\muhoed-deploy\muhoed.ps1 pki station-package DIO-EVT-B01 --out /app/output/eol
```

6. Сформировать защищенную этикетку и публичный server QR:

```text
F:\Проекты\muhoed-deploy\muhoed.ps1 pki label-qr DIO-EVT-B01 --out /app/output/labels --png
F:\Проекты\muhoed-deploy\muhoed.ps1 pki server-qr --out /app/output/server-qr --https-port 443 --png
```

7. Команда `get` копирует один файл, а не каталог. Забрать по одному `station.crt.pem`, `ca-chain.pem`, `station.json`, файлы этикетки и server QR из host-путей `/opt/muhoed/server/output/...`. Пример:

```text
F:\Проекты\muhoed-deploy\muhoed.ps1 get /opt/muhoed/server/output/eol/DIO-EVT-B01/station.json C:\Dioneya-EOL\DIO-EVT-B01\station.json
```

8. Передать закрытый bench station key `/opt/muhoed/server/data/pki/stations/DIO-EVT-B01/DIO-EVT-B01.key.pem` на изолированное EOL-рабочее место отдельной командой `get` и защищенным каналом. Не добавлять его в station package, Git, общий каталог или паспорт изделия.
9. Проверить certificate CN, station ID, tenant, fingerprint, срок действия и соответствие private key сертификату. Зафиксировать только публичный fingerprint и режим `server-side key for B01`.

### 16.4. Регистрация полевых станций DIO-EVT-001 - DIO-EVT-040

1. Выполнить `F:\Проекты\muhoed-deploy\muhoed.ps1 pki list` и сверить serial, station ID, lot и tenant с traveller.
2. Если реестр еще не инициализирован, один раз выполнить `F:\Проекты\muhoed-deploy\muhoed.ps1 pki station-add --all-lots`. Не создавать вторую запись с измененным serial.
3. На станции или изолированной EOL fixture сгенерировать уникальный ECDSA P-256 private key и CSR с `CN`, точно равным serial. Private key не покидает станцию или fixture.
4. Проверить CSR локально: алгоритм P-256, подпись CSR, CN, отсутствие посторонних SAN и читаемость файла. CSR является публичным, private key остается закрытым.
5. Загрузить только CSR на VPS:

```text
F:\Проекты\muhoed-deploy\muhoed.ps1 put C:\Dioneya-EOL\<SERIAL>\<SERIAL>.csr.pem /opt/muhoed/server/data/pki/inbox/<SERIAL>.csr.pem
F:\Проекты\muhoed-deploy\muhoed.ps1 pki station-sign <SERIAL> --csr /app/data/pki/inbox/<SERIAL>.csr.pem
```

6. Проверить certificate CN, serial number, SHA-256 fingerprint, срок действия и цепочку до Dioneya Issuing CA 1 и Dioneya Root CA. После контролируемого архивирования удалить входной CSR из `inbox` по процедуре администратора.
7. Выполнить `station-package`, `label-qr` и server QR по образцу B01, заменив serial. Забрать результаты по одному файлу.
8. На EOL-рабочем месте объединить station certificate, CA chain и локальный private key. Проверить соответствие public key сертификата private key. Не копировать private key на сервер.


#### 16.4.1. Точная процедура создания private key и CSR полевой станции

Процедура выполняется в PowerShell на изолированном EOL-компьютере штатным инструментом `05_EOL_TOOLS/generate_evt_station_csr.py`. OpenSSL для этого шага не требуется. Инструмент принимает только физические serial `DIO-EVT-001` - `DIO-EVT-040` и `DIO-EVT-B01`, запрещает serial цифровых двойников, создает ECDSA P-256 key и подписанный CSR, проверяет CN и не перезаписывает существующие файлы.

До начала партии один раз подготовить контролируемую Python-среду. На производственном компьютере зависимости устанавливаются из заранее проверенного локального каталога wheel-файлов. Подключение производственного EOL-компьютера к публичному PyPI не допускается. Если локальное зеркало еще не подготовлено, среду собирают на инженерном компьютере, фиксируют SHA-256 wheel-файлов и переносят утвержденным носителем.

```text
py -3 -m venv C:\Dioneya-EOL\pki-venv
C:\Dioneya-EOL\pki-venv\Scripts\python.exe -m pip install --no-index --find-links C:\Dioneya-EOL\wheels -r 05_EOL_TOOLS\requirements-eol-pki.txt
C:\Dioneya-EOL\pki-venv\Scripts\python.exe -c "import cryptography; print(cryptography.__version__)"
C:\Dioneya-EOL\pki-venv\Scripts\python.exe 05_EOL_TOOLS\generate_evt_station_csr.py <SERIAL> --out C:\Dioneya-EOL\<SERIAL>
```

Если утвержденная среда уже создана, повторная установка пакетов перед каждой станцией не нужна. Перед сменой версии Python, `cryptography` или EOL-инструмента требуется повторная валидация на тестовом сертификате. Каталог `C:\Dioneya-EOL\<SERIAL>` создается отдельно для изделия и закрывается ACL от других пользователей. Ограничение ACL проверяется средствами Windows; атрибут файла и `chmod` не заменяют Windows ACL.

Перед передачей CSR оператор проверяет:

- stdout содержит правильные serial, station ID и lot из traveller;
- созданы только `<SERIAL>.key.pem`, `<SERIAL>.csr.pem` и `<SERIAL>.csr.json`;
- JSON указывает `ECDSA P-256 / SHA-256`, а `csr_sha256` совпадает с вычисленным SHA-256 CSR;
- инструмент завершился с кодом 0, что означает успешную проверку подписи CSR и CN;
- private key имеет доступ только у назначенного EOL-оператора;
- на сервер уходит только `.csr.pem`.

Файл `<SERIAL>.csr.json` не содержит ключа и используется как публичная запись операции. Поля `private_key_created_locally: true` и `private_key_sent_to_server: false` фиксируют выбранный порядок: ключ создан на EOL-месте, на сервер передается только CSR. Эти поля не доказывают отсутствие иных копий, поэтому оператор отдельно проверяет каталоги, носители и журнал передачи.

После `station-sign` забрать сертификат и station package:

```text
F:\Проекты\muhoed-deploy\muhoed.ps1 get /opt/muhoed/server/data/pki/stations/<SERIAL>/<SERIAL>.crt.pem C:\Dioneya-EOL\<SERIAL>\station.crt.pem
F:\Проекты\muhoed-deploy\muhoed.ps1 get /opt/muhoed/server/output/eol/<SERIAL>/ca-chain.pem C:\Dioneya-EOL\<SERIAL>\ca-chain.pem
F:\Проекты\muhoed-deploy\muhoed.ps1 get /opt/muhoed/server/output/eol/<SERIAL>/station.json C:\Dioneya-EOL\<SERIAL>\station.json
```

Проверить цепочку, срок действия, `clientAuth`, CN, lot и соответствие сертификата локальному private key штатным инструментом:

```text
C:\Dioneya-EOL\pki-venv\Scripts\python.exe 05_EOL_TOOLS\verify_evt_station_certificate.py <SERIAL> --key C:\Dioneya-EOL\<SERIAL>\<SERIAL>.key.pem --cert C:\Dioneya-EOL\<SERIAL>\station.crt.pem --ca-chain C:\Dioneya-EOL\<SERIAL>\ca-chain.pem
```

Ожидается строка `EVT station certificate verification: PASS`, правильные serial и lot, SHA-256 fingerprint, даты действия, `Dioneya Issuing CA 1` и `Dioneya Root CA`. Вывод сохранить в evidence. Любая ошибка завершает шаг как FAIL. Не пытаться подменить key, certificate или chain файлом от другой станции.

После подтвержденной загрузки ключа в BG95, успешного mTLS и закрытия evidence удалить незашифрованные локальные копии private key с EOL-компьютера и временного носителя по утвержденной процедуре очистки. Обычное удаление файла не считается гарантированным стиранием с SSD. Если утвержден offline escrow, сохранить только зашифрованную копию в контролируемом хранилище с двойным доступом. Замена BG95 без escrow требует отзыва старого сертификата и выпуска нового ключа и сертификата.

### 16.5. Запись заводского serial и pairing secret до первого BLE-сеанса

Один подписанный STM32 image применяется для B01 и всех 40 полевых станций. Уникальные serial, station ID и pairing secret вводятся после прошивки через изолированный TEST_UART 3,3 В, 115200 bit/s. Этот шаг выполняется до первого LESC pairing.

1. Открыть защищенный `station.json` из station package и сверить `serial`, `station_id`, `tenant`, `pairing_secret_hex`. Значение pairing secret не копировать в traveller или обычный лог.
2. Подключить TEST_UART, убедиться, что линии имеют уровень 3,3 В и общий GND, а консоль недоступна из внешнего разъема готового изделия.
3. Выполнить:

```text
factoryid <SERIAL> <pairing_secret_hex>
```

Для стенда точная форма: `factoryid DIO-EVT-B01 <32 hex>`. Для партии допустимы только `DIO-EVT-001` - `DIO-EVT-040`. Диапазон 9001-9040 зарезервирован за цифровыми двойниками и отвергается физической станцией.

4. Ожидать ответ с serial, station ID, признаком `pairing set` и требованием cold reboot. Ошибка NOR commit, неверный serial или неверная длина секрета означает FAIL.
5. Полностью снять питание, выждать разряд шин, затем включить изделие. Программного reset недостаточно для приемки cold boot.
6. Выполнить команду `secrets`. Сверить только serial, station ID и признаки `pairing set`; секрет в консоль не выводится.
7. Убедиться, что nRF получает pairing secret при инициализации BLE. Затем сканировать именно этикетку с тем же serial и выполнить первое LESC pairing.

Повторный `factoryid` на уже инициализированной станции запрещен и отклоняется. Команда `secrets clear` очищает все заводские и эксплуатационные данные и применяется только по оформленному решению rework. Обычная очистка BLE operational secrets сохраняет factory identity и pairing secret.


#### 16.5.1. Ожидаемый журнал factory identity

Допустимый сокращенный журнал без раскрытия секрета:

```text
factoryid: DIO-EVT-NNN id N stored; pairing set; cold reboot required
secrets loaded (nor, vN): factory DIO-EVT-NNN/id N, pairing set, engineer -, iccid1 -, iccid2 -, command key -
```

Для B01 ожидаются serial `DIO-EVT-B01` и station ID 901. После первого cold boot оператор повторно выполняет `secrets` и сохраняет журнал. В журнале не должно быть pairing secret, engineer key, PEM или полного IMSI.

Если питание пропало во время записи, после запуска выполнить только `secrets`. При отсутствии согласованной factory identity повторить `factoryid` с тем же station package. Если записан неправильный serial или неизвестно, какой secret сохранен, не применять `secrets clear` самостоятельно: оформить rework, отозвать или перевыпустить связанные материалы, очистить станцию под двойным контролем и начать provisioning заново.

### 16.6. Выпуск station secrets

После считывания фактических ICCID выполнить на сервере PKI:

```text
F:\Проекты\muhoed-deploy\muhoed.ps1 pki station-secrets <SERIAL> --out /app/output/eol-secrets --to installer --iccid1 <ICCID1> --iccid2 <ICCID2> --command-signing-key <SERVER_COMMAND_SIGNING_KEY_PEM>
```

Для tenant `bench` использовать `/run/tls/command-signing-bench.key`. Для `pilot1` и `pilot2` использовать `/run/tls/command-signing.key`. На сервер передается путь внутри контейнера, а не путь Windows.

Экспорт `DIO-SECRETS-V1` содержит engineer key, полные ICCID и только public key подписания команд. Забрать `<SERIAL>.station-secrets.json` из `/opt/muhoed/server/output/eol-secrets/` по защищенному каналу. До передачи проверить serial и последние четыре цифры ICCID. На пустой станции установщик записывает bundle один раз через BLE 0x0206. Повторная запись заполненной станции требует роли engineer. Read-back показывает только presence map и key ID, значения секретов не читаются.

После успешного read-back удалить файл с телефона, съемного носителя и каталога server export по процедуре zeroization. Запись об удалении входит в provisioning receipt. Не удалять единственную серверную запись engineer key из контролируемого PKI.

Ключ инженера для авторизованного инженерного телефона экспортируется отдельно командой `engineer-key <SERIAL> --to <ФИО_ИЛИ_РОЛЬ> --out <SECURE_OUTPUT>`. Он не печатается на этикетке и не передается обычному монтажнику.

### 16.7. Загрузка mTLS-материала в BG95

До первого MQTT-подключения в файловое хранилище BG95 должны быть загружены:

- файл CA с содержимым `ca-chain.pem`, записанный под точным именем `dioneya-root`, совпадающим с `ca_reference`;
- station client certificate;
- station private key.

Для текущего профиля endpoint равен `dioneya.ru:8883`, SSL context равен 1. Рекомендуемые имена client files: `station.crt` и `station.key`. Загрузка выполняется только через изолированную EOL-оснастку или прямой сервисный интерфейс BG95. Для каждого файла обязательна последовательность:

```text
AT+QFDEL="<name>"
AT+QFUPL="<name>",<точный размер>,60
<точно указанное число бинарных байтов после CONNECT>
AT+QFLST="<name>"
```

После трех загрузок выполнить:

```text
AT+QSSLCFG="clientcert",1,"station.crt"
AT+QSSLCFG="clientkey",1,"station.key"
AT+QSSLCFG="cacert",1,"dioneya-root"
AT+QSSLCFG="sslversion",1,4
AT+QSSLCFG="seclevel",1,2
```

Нельзя считать загрузку успешной только по `OK`. Необходимы совпадение размера, checksum, результат `QFLST`, повторное чтение настроек и успешный mTLS handshake. Логи не должны содержать PEM private key. Текущий код `zs_bg95_provision` реализует эту последовательность и прошел host-тесты, но его соединение с фактическим EOL UART и выбранной версией BG95 подтверждается на B01. До такой проверки операция имеет статус HARDWARE VALIDATION PENDING.


#### 16.7.1. Карта файлов BG95 и критерии приемки

| Файл в BG95 | Источник | Секретность | Проверка |
|---|---|---|---|
| `dioneya-root` | Содержимое `ca-chain.pem` из действующего bundle | Публичный | Размер, QFUPL checksum, QFLST, CA verification |
| `station.crt` | `<SERIAL>.crt.pem` или `station.crt.pem` | Публичный, но привязан к станции | CN, fingerprint, срок, размер, QFLST |
| `station.key` | Локальный `<SERIAL>.key.pem` | Закрытый | Соответствие cert, размер/checksum, отсутствие в логах |

Порядок для каждого файла: удалить прежнюю одноименную запись, загрузить точное число байтов, дождаться `+QFUPL`, сверить размер и checksum, затем сверить `QFLST`. Только после этого задавать `clientcert`, `clientkey`, `cacert`, `sslversion` и `seclevel`.

Если `QFDEL` сообщает, что файл отсутствует, это допустимо только перед первой загрузкой. Timeout после `CONNECT`, несовпадающий checksum, другой размер, отсутствие файла в `QFLST` или сбой настройки SSL context означает FAIL. Повторять загрузку разрешено только с удаления этого файла и с начала его последовательности.

### 16.8. Настройка через приложение

1. Сверить QR и видимый serial станции.
2. Удерживать TAMPER_IN в активном состоянии 5 секунд и открыть сервисное окно 600 секунд.
3. Выбрать BLE advertisement только с ожидаемым serial.
4. Выполнить LESC pairing по секрету этикетки. Сверить вычисленный passkey на телефоне и изделии.
5. Прочитать identity и проверить station ID, hardware revision, firmware и region.
6. Записать station secrets через диалог 0x0206. Read-back показывает только presence map, значения секретов не читаются.
7. Импортировать server QR и записать station config: host `dioneya.ru`, MQTT port 8883, server fingerprint, tenant, station ID, CA reference, APN allowlist, preferred SIM и slot mapping.
8. Выполнить atomic write и read-back. Сверить все поля, storage generation и canonical SHA-256.
9. Записать координаты только на месте установки. Сверить recommission version, position hash и `auditCommitted`.
10. Закрыть сервисное окно и подтвердить отказ конфигурации вне окна.

### 16.9. Обновление ACL и запуск соединения

После выпуска или отзыва station certificate выполнить:

```text
F:\Проекты\muhoed-deploy\muhoed.ps1 acl
```

Команда обновляет CRL, генерирует Mosquitto ACL и перезапускает MQTT. Проверить, что CN сертификата станции имеет право публиковать только `zs/v1/<tenant>/<station_id>/up`, `status`, `ack`, `audio`, `fwreq`, `bearing` и читать только свои `down`, `receipt`, `fw`. Wildcard и чужой tenant должны отклоняться.

### 16.10. Проверка регистрации SIM и подключения к dioneya.ru

Проверка выполняется по слоям. Переход к следующему слою разрешен только после PASS предыдущего.

| Слой | Команда или наблюдение | Условие PASS | Типовая причина FAIL |
|---|---|---|---|
| SIM ready | `AT+CPIN?` | `+CPIN: READY` | PIN включен, SIM отсутствует, питание или слот |
| Идентичность SIM | `AT+QCCID`, `AT+CIMI` | ICCID совпадает со slot mapping; IMSI имеет допустимый формат | Перепутан слот, неизвестная SIM |
| APN | `AT+CGDCONT=1,"IP","<APN>"` | APN входит в allowlist для этой SIM | Ручной или закрытый APN не из профиля |
| Регистрация сети | `AT+CEREG?` | registered home или roaming по разрешенному профилю | Нет покрытия, SIM barred, антенна, roaming |
| PDP | `AT+QIACT=1`, `AT+CGCONTRDP=1` | Контекст активен и получен IP | APN, баланс, сеть, питание модема |
| Время и DNS | `AT+QLTS=1`, разрешение `dioneya.ru` | Время правдоподобно либо используется разрешенный резервный clock; DNS успешен | Нет NITZ, DNS или PDP |
| TLS | SSL context 1, CA, cert, key | TLS 1.2, hostname и CA проверены, client cert принят | Файл, время, цепочка, отозванный cert |
| MQTT transport | `AT+QMTOPEN`, `AT+QMTCONN` | `+QMTOPEN: 0,0`, `+QMTCONN: 0,0,0` | DNS, TLS, client ID, broker |
| MQTT authorization | подписки и публикация | Только собственные topics разрешены | ACL, tenant, station ID, certificate CN |
| Application | heartbeat, event, receipt, command ACK | Сервер сохранил сообщение и вернул прикладное подтверждение | Schema, binding, bridge, dedup |

Полная процедура:

1. Подключить LTE-антенну или утвержденный RF-стенд, установить обе SIM с отключенным PIN и подать питание.
2. В UART-логе последовательно проверить SIM detect, `AT+CPIN?`, точный ICCID, IMSI, выбор public APN, `CEREG`, PDP, DNS и сетевое время. Полный IMSI не помещать в обычный протокол.
3. Проверить TLS 1.2, CA verification, hostname `dioneya.ru`, client certificate и MQTT connect на port 8883.
4. Проверить подписки на свои `down` и `receipt` и публикацию heartbeat в `zs/v1/<tenant>/<station_id>/status` с QoS 1 и retain false.
5. На сервере выполнить `F:\Проекты\muhoed-deploy\muhoed.ps1 logs mqtt_bridge_<tenant> 200` и убедиться, что нет ошибок certificate, ACL, tenant, station ID или payload binding.
6. Открыть `https://dioneya.ru/stations` под учетной записью с разрешенным tenant. Станция должна перейти из `never` или `offline` в `online`, показать правильные serial, firmware, SIM, питание, GNSS и время последнего heartbeat.
7. Сформировать тестовое событие. Проверить topic `up`, серверное сохранение, dedup и application receipt. MQTT PUBACK подтверждает только прием брокером и не считается приемом приложением.
8. Если записан command public key, отправить разрешенную подписанную тестовую команду. Проверить `down`, выполнение и `ack` с тем же command ID.
9. Отключить сеть, создать событие, затем восстановить сеть. Outbox должен сохранить событие и закрыть его только после application receipt с совпадающими identifiers и payload hash.
10. Переключить SIM штатной safe-off процедурой: отключить BG95, дождаться снятия питания USIM, переключить mux, заново включить модем. Повторить SIM identity, APN, registration, PDP, DNS, TLS, MQTT и heartbeat.
11. Проверить fail closed: неизвестный ICCID, APN вне allowlist, чужой topic, неверный server fingerprint, просроченный или отозванный cert не должны давать рабочее соединение.

### 16.11. Ротация pairing secret

Ротация требуется при утрате этикетки, раскрытии QR, замене внешней этикетки после компрометации или оформленном rework. Выполнить:

```text
F:\Проекты\muhoed-deploy\muhoed.ps1 pki pairing-secret-rotate <SERIAL> --reason "<причина>"
F:\Проекты\muhoed-deploy\muhoed.ps1 pki station-package <SERIAL> --out /app/output/eol
F:\Проекты\muhoed-deploy\muhoed.ps1 pki label-qr <SERIAL> --out /app/output/labels --png
```

На изолированном TEST_UART выполнить `pairsec <новый pairing_secret_hex>`, сделать cold reboot, проверить `pairing set`, уничтожить старую этикетку и выполнить LESC только по новой. Новый и старый секреты не фиксировать в обычном журнале. Ротация только на сервере без `pairsec`, либо только на станции без новой этикетки, оставляет изделие недоступным для приложения.

### 16.12. Завершение commissioning

Только после положительного EOL, heartbeat, тестового события, receipt и проверки evidence выполнить:

```text
F:\Проекты\muhoed-deploy\muhoed.ps1 pki station-commission <SERIAL> --detail "<место, EOL record, дата>"
F:\Проекты\muhoed-deploy\muhoed.ps1 pki audit --limit 50
```

Сохранить certificate fingerprint, redacted ICCID references, ACL revision, серверные журналы и screenshot страницы stations. В evidence запрещены private key, pairing secret, engineer key, command private key, полные IMSI и незащищенный station secrets bundle. Receipt должен отдельно подтвердить удаление временных защищенных экспортов с телефона, съемного носителя и EOL-рабочего каталога.

## 17. Первичный запуск после прошивки

### 17.1. Контролируемая подача питания

1. Отключить RF-передачу программно или подключить согласованные нагрузки.
2. Включить регистратор тока, UART log и тепловизор.
3. Подать питание с утвержденным ограничением.
4. При уходе источника в current limit, запахе, локальном перегреве или повторном reset немедленно снять питание.
5. Записать пусковой ток, установившийся ток, напряжения 3V3_DIGITAL, 3V8_MODEM и 1V8_MIC, состояния PWR_GOOD и FAULT.

### 17.2. Ожидаемые признаки

- UART запускается без мусора и непрерывного reset;
- печатаются версия firmware, активный bank, boot status, attempts, other bank, release key count и flash error count;
- аппаратные ревизии REV0/REV1 читаются и совпадают с traveller;
- PWR_FAULT не активен;
- задача watchdog обслуживается;
- доступны диагностические команды `st`, `lag`, `pps`, `audio`, `svc`, `modes`, `heap`;
- heap и минимальный свободный stack фиксируются в лог.

Если фактические команды консоли отличаются от списка target baseline, использовать `help` и зафиксировать расхождение как документационное замечание. Нельзя считать тест пройденным по отсутствию сообщений об ошибке без проверки требуемого результата.

## 18. Общий порядок испытаний

Испытания выполняются в следующей последовательности:

1. Проверка документов и идентичности.
2. Визуальный контроль и сопротивления.
3. Первое питание PCB-PWR и PCB-MAIN.
4. Прошивка и verify STM32.
5. Проверка nRF52840 и сервисного интерфейса.
6. Boundary self-test PCB-MAIN.
7. Нагрузочные проверки PCB-PWR.
8. Индивидуальная проверка каждой PCB-MIC.
9. Сборка станции и проверка геометрии 3+1.
10. Trusted provisioning.
11. Полный EOL каждого изделия.
12. Негативные тесты на выделенных экземплярах.
13. Длительные и климатические EVT.
14. Регрессионный EOL после ремонта или изменения firmware.

Любой обязательный FAIL блокирует изделие. Старый FAIL не удаляется. После ремонта создается новая attempt со ссылкой на NCR, затем повторяется затронутый тест и полный EOL.

## 19. EOL каждого изделия

| ID | Проверка | Действие | Критерий |
|---|---|---|---|
| EOL-ID-01 | Идентичность | Сверить serial, QR, PCB SN, ревизии, manifest | Все идентификаторы уникальны и согласованы |
| EOL-PWR-01 | Питание и защиты | Измерить rails и события защиты | Нет latch-up, перегрева и защитного события |
| EOL-PWR-02 | S0-S4 | Измерить ток каждого режима | Raw values записаны, лимиты frozen после golden unit |
| EOL-FW-01 | Boot и rollback | Считать версию, подпись, counter, bank | Для production только подписанный образ и правильный anti-rollback |
| EOL-STO-01 | NOR и microSD | ID, запись, чтение, verify, recovery | Все операции проходят, емкость и ID правильные |
| EOL-AUD-01 | Четыре канала | Захват синхронного тестового сигнала | Нет dropout, clipping и перепутанных каналов |
| EOL-AUD-02 | Геометрия | Сверить MIC1-MIC4 и calibration hash | Mapping 3+1 однозначен |
| EOL-TIM-01 | GNSS/PPS | Получить fix, RMC и timepulse | PPS bind растет, time quality валидно |
| EOL-CELL-01 | SIM | Считать IMEI и обе ICCID refs, выполнить attach | Slot mapping правильный, attach проходит |
| EOL-CELL-02 | MQTT/TLS | Подключить к серверу, publish, ACK, reconnect | CA и hostname проверены, обмен проходит |
| EOL-CELL-03 | Store-and-forward | Отключить сеть, создать событие, восстановить сеть | Событие сохранено и доставлено без потери, receipt подтвержден |
| EOL-CELL-04 | Failover | Переключить SIM штатной процедурой | Очередь сохраняется, ICCID проверен, TLS восстановлен |
| EOL-LORA-01 | Module/region | Считать модуль и профиль | RU868 locked, TX только на разрешенном стенде |
| EOL-LORA-02 | Packet | Обмен с test peer | Auth, counter, dedup и retry проходят |
| EOL-BLE-01 | Service mode | Проверить физическое окно и отказ вне окна | Неавторизованный доступ отклонен |
| EOL-BLE-02 | Android | Read, write, signed OTA smoke | Проходит с утвержденным APK и реальным GATT |
| EOL-SEN-01 | Sensors | Проверить temperature, motion и self-test | ID и значения правдоподобны, self-test PASS |
| EOL-MECH-01 | Механика | Осмотр, torque, seals, cable routing | Все записи и фото присутствуют |
| EOL-IP-01 | Герметичность | Pressure decay или утвержденный метод | Соответствует frozen enclosure limit |
| EOL-REC-01 | Комплектность | Проверить все evidence и хэши | Нет пустого обязательного поля |

## 20. Подробные функциональные проверки

### 20.1. Питание и режимы S0-S4

Для каждого режима записать входное напряжение, средний ток, peak current, длительность перехода, температуру критических компонентов, состояние EN_MODEM, EN_AUX, PWR_GOOD и FAULT. Окончательные числовые пределы не придумываются: они замораживаются после измерения golden unit и расчетной проверки энергобюджета.

Проверить:

- безопасное состояние GPIO сразу после reset;
- EN_MODEM и SIM mux остаются выключенными до стабильного питания;
- пробуждение по MIC_WAKE, CELL_RI, tamper и служебному событию согласно режиму;
- отсутствие wake storm;
- корректный переход в safe-off при brownout и PWR_FAULT;
- восстановление после короткого пропадания питания;
- отсутствие повреждения записи при power cut.

### 20.2. Аудиотракт и PCB-MIC

1. Проверить питание 1V8_MIC и общий PDM_CLK.
2. Проверить четыре линии PDM_DATA и соответствие MIC1, MIC2, MIC3, MIC4.
3. Подать общий акустический сигнал и выполнить `audio`, затем `lag`.
4. Убедиться, что block count растет, overrun равен нулю, все каналы присутствуют.
5. Сравнить gain, phase, noise и clipping с лимитами калиброванного fixture.
6. Проверить AAD: THSEL sequence, wake, false wake, latency, ток S0.
7. Повторить AAD при -40 и +70 градусов Цельсия на выбранных EVT-образцах.
8. Сохранить calibration set и hash для каждого изделия.

Четыре MIC-жгута имеют одинаковую нарезку 275 мм. Избыток укладывается сервисной петлей без перегиба. Изменение длины одного канала влияет на фазу и требует повторной калибровки.

### 20.3. GNSS и PPS

1. Подключить утвержденную GNSS-антенну с учетом активного bias через J9.
2. Получить валидный fix и RMC с датой и UTC.
3. Выполнить `pps`, убедиться, что bound count растет.
4. Проверить timestamp TIM2 CH1 на PA0 и соответствие sample counter.
5. Отключить PPS и проверить переход в holdover, затем в unsynced не позднее программного лимита 120 секунд.
6. Измерить фактическую ошибку holdover. Значение проекта `1 мс/с` является консервативной host-моделью, а не приемочным доказательством железа.
7. Восстановить PPS и проверить возврат без скачка, нарушающего временную метку события.

### 20.4. NOR и microSD

- проверить JEDEC ID W25Q512JV `EF 40 20`, SFDP/BFPT, 64 МиБ, 4-byte addressing и QE;
- записать, прочитать и сравнить тестовый блок в каждой выделенной области;
- убедиться, что archive, command journal и event outbox не перекрываются;
- выполнить power cut во время commit на выделенном образце;
- проверить, что pending event не удаляется по MQTT PUBACK и закрывается только application receipt;
- проверить CID и фактическую емкость microSD, полный write/readback, card detect и восстановление после извлечения;
- не выполнять разрушительный полный тест на карте с ценными данными.

### 20.5. BG95, SIM и MQTT/TLS

1. Проверить 3V8_MODEM и VDD_EXT до активного управления UART.
2. Запустить modem state machine и сохранить AT-log без секретов.
3. Считать IMEI, полные ICCID и IMSI только в контролируемой локальной сессии.
4. Проверить auto network discovery, public APN и post-activation readback APN, IP, gateway, DNS.
5. Проверить цепочку CA, hostname, время и mTLS.
6. Опубликовать тестовое событие, получить canonical receipt и подтвердить совпадение SHA-256 payload.
7. Разорвать сеть после durable commit, затем восстановить и проверить at-least-once delivery без потери.
8. Выполнить штатный failover SIM1 к SIM2 и обратно.
9. Повторить 100 циклов переключения на выбранных EVT-образцах.
10. Выполнить 24-часовой тест с реальными SIM и регистрацией attach, reconnect, тока и очереди.

### 20.6. BLE и приложение

Выполнить все строки `android/ACCEPTANCE_TESTS_v0_1.csv`. Особое внимание:

- станция вне service mode не конфигурируется;
- wrong QR и expired bootstrap secret отклоняются;
- valid configuration записывается атомарно и читается обратно;
- invalid APN, endpoint и region command не дают частичного изменения;
- export не содержит secret, полный ICCID, IMSI или password;
- разрыв BLE на 30 процентах OTA позволяет resume без повторной активации;
- поворот экрана и background не теряют состояние;
- Huawei без GMS проходит полный сценарий.

### 20.7. LoRa

До выпуска подписанного RU868 loader `tx_enabled` остается false. Разрешенные действия:

- проверить SPI, reset, BUSY, DIO1, TXEN и RXEN;
- проверить, что TXEN и RXEN инициализируются LOW и не активны одновременно;
- считать идентификатор модуля;
- на экранированном или conducted стенде загрузить временный утвержденный тестовый профиль и проверить packet integrity;
- сохранить мощность, частоту, спектр, duty cycle, counter, authentication и retry.

Нельзя выполнять полевую передачу по candidate frequency list без отдельного RF release.

### 20.8. Серверная связка

1. Убедиться, что physical station зарегистрирована отдельно от twin IDs 9001-9040.
2. Проверить первый heartbeat и отметку времени.
3. Сверить online/offline, питание, GNSS, SIM, firmware version и ошибки на странице состояния станций.
4. Сформировать тестовую тревогу утвержденным методом.
5. Проверить обязательный переход на экран сопровождения.
6. Проверить, что положение станции отображается по фактическим координатам, а не по сеточной позиции.
7. Подтвердить получение события, dedup, receipt и отсутствие влияния на реальные станции другого tenant.
8. Проверить повтор после временной недоступности сервера.

## 21. OTA, A/B и rollback

Стендовый комплект содержит выпущенные ключи проверки и позволяет испытать signed OTA и A/B. Это прикладная защита с сохраненным recovery, а не окончательный production immutable secure boot.

Порядок проверки:

1. Зафиксировать active bank, version 2026100601, anti-rollback counter и boot record.
2. Импортировать только подписанный совместимый bundle и проверить manifest, target, hardware revision, size, SHA-256, key ID и signature.
3. Начать transfer и прервать соединение на 10, 30, 70 и 99 процентах в отдельных попытках. Продолжение допускается только с подтвержденного offset.
4. После полной загрузки выполнить read-back hash неактивного bank.
5. Снять питание до activation. Должен загрузиться старый bank.
6. Повторить загрузку, активировать trial bank и проверить health confirmation.
7. Испытать watchdog до confirmation. Должен выполняться rollback.
8. Испытать power cut во время boot record update и confirmation.
9. Проверить corrupted bundle, wrong target, wrong hardware revision, unknown key ID, invalid signature и version ниже anti-rollback baseline. Все варианты должны быть отклонены до activation.
10. Проверить сохранность station config, station secrets, certificate material, outbox и installation position.
11. Проверить nRF MCUboot update отдельно, включая serial recovery и rollback.

Положительный host-тест не заменяет физический power-cut test. До его завершения производственный PASS по A/B не выставляется.

## 22. Негативные и fault-injection испытания

| Сценарий | Воздействие | Ожидаемый результат |
|---|---|---|
| Неверный firmware hash | Изменить один байт файла | Verify или signature FAIL, программирование партии запрещено |
| Потеря питания при flash write | Снять питание на выделенном образце | Recovery доступен, старый release не считается PASS автоматически |
| Застрявший PWR_GOOD | Эмулировать ложное состояние | Модем не включается небезопасно, ошибка журналируется |
| CELL_STATUS не стал LOW | Заблокировать shutdown | Mux и rail не переключаются |
| Неизвестная SIM | Установить неразрешенный ICCID/APN | Fail closed, соединение не поднимается |
| Недействительная TLS chain | Подменить test endpoint | Соединение отклоняется |
| Поврежденный storage | Эмулировать read/write FAIL | Событие не объявляется доставленным, диагностика FAIL |
| Потеря PPS | Отключить timepulse | Переход holdover, затем unsynced |
| Перепутанный MIC | Поменять два канала на fixture sample | Geometry/mapping test FAIL |
| BLE вне service window | Попытка read/write | Доступ отклоняется |
| Raw region command | Измененная app отправляет команду | Станция отклоняет изменение RU868 |
| Сервер недоступен | Отключить сеть | Outbox сохраняет событие и отправляет после восстановления |

Fault injection выполняется на выделенных образцах и не должна разрушать единственный golden unit.

## 23. Длительные и климатические испытания EVT

Минимальный набор после закрытия EOL:

- 24 часа связи с реальными SIM, автоматическими reconnect и контролем очереди;
- 100 циклов безопасного переключения SIM;
- power cycling с разной фазой startup и shutdown;
- brownout и кратковременные провалы питания;
- режимы S0-S4 с регистрацией энергопотребления;
- AAD false wake, latency и ток при комнатной температуре, -40 и +70 градусов Цельсия;
- GNSS cold/warm start, PPS loss и holdover;
- хранение и восстановление NOR/microSD;
- акустическая калибровка в собранном корпусе с поролоном и отводом конденсата;
- LTE/GNSS/LoRa RF в окончательном корпусе;
- leak test и осмотр конденсата после температурных циклов;
- вибрация, кабельная разгрузка, гермовводы и повторный EOL.

Количество EVT-образцов, профиль температуры, длительность выдержки и frozen limits задаются отдельной ПМИ. Если лимит не утвержден, тест фиксируется как MEASURED или HOLD, но не PASS.

## 24. Критерии решения

### 24.1. PASS

- exact release и exact hardware revision совпадают;
- программирование и verify успешны;
- все обязательные EOL имеют числовые пределы и PASS;
- provisioning receipt полный, секреты не раскрыты;
- серверная связка подтверждена;
- нет незакрытого NCR, влияющего на безопасность или функцию;
- хэши всех evidence разрешаются.

### 24.2. FAIL

- обязательный тест имеет измерение вне утвержденного предела;
- signature, identity, hardware revision или verify не совпадает;
- обнаружена потеря данных, небезопасное управление питанием, несанкционированная конфигурация или неконтролируемая RF-передача.

### 24.3. HOLD

- обязательный предел, release package, firmware coprocessor, credential, fixture calibration или исходный документ отсутствует;
- есть противоречие идентификаторов;
- тест не может быть выполнен с имеющимся оборудованием;
- результат неоднозначен.

HOLD не переводится в PASS формулировкой «замечаний нет». Нужен закрывающий документ или повторное испытание.

## 25. Состав evidence по каждому изделию

Рекомендуемая структура каталога:

```text
DIO-EVT-NNN/
  00_identity/
  01_incoming/
  02_power/
  03_programming/
  04_provisioning/
  05_eol/
  06_environment/
  07_server/
  08_rework/
  manifest.json
```

Обязательные поля `manifest.json`:

- serial, lot, PCB serials и revisions;
- release ID, source commit, artifact names, sizes и SHA-256;
- tool versions и ST-LINK serial;
- operator, controller, timestamps UTC;
- option bytes before/after без секретов;
- programming result и путь к полному логу;
- provisioning receipt и certificate fingerprint;
- калибровки, fixture IDs и сроки действия;
- все raw values, units, limits и PASS/FAIL/HOLD;
- NCR/rework links;
- итог и подписи.

## 26. Типовые неисправности и действия

| Симптом | Вероятная причина | Действие |
|---|---|---|
| VTREF отсутствует | Нет питания 3V3, fixture не сел, обрыв GND | Снять питание, проверить PCB-PWR, GND и pogo |
| ST-LINK видит неверный MCU | Ошибка комплектации или контакт | HOLD, сверить маркировку U1 и fixture |
| Verify FAIL | Нестабильное питание, контакт, неверный файл | Сверить хэш, питание, повторить один раз, затем HOLD |
| Boot loop | HardFault, watchdog, clock, питание | Сохранить UART/reset flags, подключиться under reset |
| Нет UART | Неверный уровень, TX/RX, VTREF | Проверить TP_EOL 5/6 и GND, fixture high-Z policy |
| Ток выше ожидаемого | Короткое, modem on, clock mode, периферия | Немедленно снять питание, тепловизор, локализовать rail |
| Нет PDM канала | Питание MIC, жгут, translator, mapping | Проверить 1V8, PDM_CLK, DATA, continuity и `lag` |
| PPS не привязывается | Нет fix/timepulse, неверный TIM2 capture | Проверить антенну, RMC, PA0 и clock |
| BG95 не выключается | `AT+QPOWD`/CELL_STATUS/rail sequence | Не переключать mux, проверить PD13 и PWRKEY |
| TLS FAIL | Время, CA, hostname, APN, credential | Проверить GNSS time, chain, endpoint и redacted modem state |
| BLE не видит станцию | Не открыт service window, nRF reset, GATT отсутствует | Проверить tamper 5 s, BLE_EN, nRF image и UART |
| Конфигурация не записывается | Auth/session/version/hash mismatch | Не повторять вслепую, проверить audit intent и read-back |
| OTA отклоняется | Неверная подпись, target, key ID или anti-rollback version | Проверить manifest, release key, target и boot record |
| LoRa не передает | `tx_enabled: false` | Не обходить блокировку, ждать signed RU868 release |
| `factoryid` отклонен | Неверный serial/secret, запись уже существует, NOR commit FAIL | Сверить station.json и serial; не очищать NOR без rework решения |
| LESC passkey не совпадает | Этикетка от другой станции или server/station pairing secret рассинхронизированы | Остановить ввод; сверить serial и выполнить согласованную ротацию |
| `+CPIN` не READY | PIN включен, SIM отсутствует или нет питания слота | Отключить PIN штатным средством оператора либо заменить SIM; не хранить PIN в firmware |
| MQTT есть, станции на странице нет | PUBACK получен, но bridge/schema/binding не приняты | Проверить bridge log, tenant, ID, topic, schema и application receipt |
| Сервер не показывает станцию | Tenant/ID/cert/topic/time mismatch | Сверить server registry, certificate и canonical topics |

## 27. Нюансы, требующие особого контроля

1. **Высокое использование RAM.** SRAM1-3 занята на 90,79 процента. Новая функция или увеличение буфера требует повторного map и runtime watermark.
2. **Стендовый secure update не равен production root of trust.** Подпись приложения и A/B готовы, но SWD recovery и RDP Level 0 сохранены намеренно.
3. **STM32 и nRF имеют разные SWD.** Нельзя соединять их сигналы или стирать соседний MCU.
4. **USB-C не питает станцию.** J11 используется для device service и recovery, VBUS только sense.
5. **BOOT0 управляется только под reset.** После запуска fixture возвращает линию в высокий импеданс.
6. **Option bytes могут быть необратимыми.** Для B01 применяется только `option_bytes_bench_rev_a.json`.
7. **Есть несколько независимых ключей.** Station TLS key, engineer key, command signing key, firmware release key, nRF key и Android key нельзя заменять друг другом.
8. **Pairing secret не одноразовый.** Он уникален для станции и действует до ротации; каждый BLE-сеанс новый и bonding не сохраняется.
9. **Private station key не входит в station package.** Для производства он остается на станции или EOL fixture; для B01 server-side key передается отдельно защищенным путем.
10. **BG95 требует предварительной загрузки TLS-файлов.** Наличие certificate в серверном реестре само по себе не дает станции mTLS.
11. **SIM switching требует полного выключения BG95.** Переключение mux при активной USIM запрещено.
12. **Полные ICCID и IMSI чувствительны.** В обычный export и общий API попадают только маскированные ссылки.
13. **Физические станции не используют IDs цифровых двойников.** IDs 9001-9040 остаются только в bench tenant двойников; B01 использует 901.
14. **MQTT PUBACK не закрывает событие.** Outbox освобождается только по application receipt с совпадающими identifiers и payload hash.
15. **Время требуется для TLS и подписанных команд.** При недоверенном времени удаленная команда отклоняется.
16. **Координаты задаются локально.** Удаленное изменение через MQTT или HTTPS не заменяет recommission в service window.
17. **RU868 заблокирован.** Candidate channel list не является разрешением на передачу.
18. **Зеленый CI не заменяет физику.** Питание, RF, акустика, температура, герметичность и power-loss проверяются на EVT.
19. **Вся партия заказывается без паузы.** Это решение закупки не отменяет EOL каждого изделия и регистрацию отклонений.
20. **Удаление временных секретов обязательно.** Station secrets bundle удаляется после записи, а логи проверяются на отсутствие PEM и полных credentials.
21. **Station package и label QR являются защищенными.** Они содержат pairing secret; station package также содержит engineer key.
22. **SIM PIN для EVT отключен.** Текущая прошивка умеет проверить `CPIN`, но не вводит PIN и не хранит его.
23. **Один STM32 image используется для всех физических изделий.** Уникальность задается командой `factoryid`; изменение бинарного образа под каждый serial запрещено.

## 28. Краткий чек-лист оператора

### До прошивки

- [ ] Serial, station ID, tenant и PCB revisions совпадают с traveller.
- [ ] ZIP, release manifest и SHA-256 проверены.
- [ ] Рабочее место ESD, fixture и приборы в сроке калибровки.
- [ ] Питание ограничено, антенны или нагрузки подключены.
- [ ] SWD STM32 и nRF не перепутаны.
- [ ] Считаны MCU ID и option bytes.

### После прошивки

- [ ] STM32 write, verify, cold boot и версия PASS.
- [ ] nRF merged HEX write, verify, MCUboot и IPC PASS.
- [ ] Полные логи сохранены.
- [ ] BOOT0 отпущен, SWD recovery доступен.
- [ ] Нет перегрева, current limit, boot loop или watchdog storm.

### Перед provisioning

- [ ] Запись станции в PKI существует и уникальна.
- [ ] Certificate CN, fingerprint, срок и chain проверены.
- [ ] Pairing secret, engineer key и station secrets относятся к этому serial.
- [ ] `factoryid` записан через изолированный TEST_UART, выполнен cold boot, serial и `pairing set` прочитаны обратно.
- [ ] ICCID1 и ICCID2 считаны с фактических SIM.
- [ ] ACL и CRL обновлены.

### После настройки

- [ ] TLS CA, station cert и station key загружены в BG95 и проверены по size/checksum/list.
- [ ] QR, serial, station ID, UUID, tenant и certificate согласованы.
- [ ] LESC pairing работает, service window закрывается.
- [ ] Station secrets presence показывает engineer key, обе ICCID и command public key.
- [ ] Server config, APN, preferred SIM, coordinates и hashes прочитаны обратно.
- [ ] RU868 не изменяем.
- [ ] Временные station secrets удалены.

### Проверка сети

- [ ] `CPIN READY`, ICCID/slot, IMSI format, APN allowlist, `CEREG`, PDP, DNS, network time и TLS PASS.
- [ ] MQTT connect к `dioneya.ru:8883` PASS.
- [ ] Heartbeat виден на `/stations` с правильным tenant и ID.
- [ ] Test event, dedup и application receipt PASS.
- [ ] Signed command и ACK PASS, если provisioned command key.
- [ ] Store-and-forward и SIM failover PASS.

### Перед выпуском

- [ ] Все обязательные EOL имеют утвержденные пределы и PASS.
- [ ] Server registry переведен в commissioned только после EOL.
- [ ] Evidence manifest, PKI audit и журналы полные.
- [ ] Evidence не содержит private keys, passwords, pairing secret или полный IMSI.
- [ ] NCR закрыты или имеют утвержденную disposition.
- [ ] Traveller и unit passport подписаны.

## 29. Основные источники

| Источник | Путь |
|---|---|
| Стендовый release contract | `firmware/targets/evt_pre_20/release/bench_release_contract.json` |
| Профиль стендового выпуска | `firmware/targets/evt_pre_20/release/BENCH_RELEASE_PROFILE_REV_B.md` |
| Option bytes | `firmware/targets/evt_pre_20/release/option_bytes_bench_rev_a.json` |
| Target status | `firmware/targets/evt_pre_20/target_status.yaml` |
| nRF52840 target | `firmware/targets/nrf52840_ble/README.md` |
| Android release evidence | `android/release_build_evidence.json` |
| PKI CLI и политика | `server/pki/README.md`, `server/pki/cli.py`, `manufacturing/PROVISIONING_AND_KEYS.md` |
| BLE provisioning | `protocols/BLE_GATT_OTA_ICD_v0_3.md` |
| Label и pairing | `protocols/STATION_LABEL_QR_v0_1.md` |
| Station configuration | `protocols/STATION_CONFIG_CBOR_v0_1.md` |
| MQTT и TLS | `protocols/MQTT_TLS_ICD_v0_1.md` и addenda |
| EOL | `manufacturing/EOL_TEST_SPEC.md`, `manufacturing/EOL_SOFTWARE_LIMITS_REV_A.json` |
| Fixture authority | `hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv` |
| Развертывание | `F:\Проекты\muhoed-deploy\muhoed.ps1`, публичный `pki/bundle/bundle.json` |

Официальные источники для инструмента прошивки и микроконтроллера:

| Источник | Адрес |
|---|---|
| STM32CubeProgrammer UM2237 | `https://www.st.com/resource/en/user_manual/dm00403500-stm32cubeprogrammer-stmicroelectronics.pdf` |
| STM32CubeProgrammer CLI | `https://dev.st.com/stm32cube-docs/prog/2.23.0/en/docs/markup/CubeProg_Command_Lines.html` |
| STM32U585 datasheet | `https://www.st.com/resource/en/datasheet/stm32u585vi.pdf` |
| Android Debug Bridge | `https://developer.android.com/tools/adb` |

Команды PKI в настоящем документе сверены с `server/pki/cli.py` той же версии, что записана в `release_manifest.json`. Перед использованием более новой версии оператор повторно сверяет `python -m pki.cli --help` и release notes.

## 30. Лист регистрации изменений

| Ревизия | Дата | Изменение | Основание |
|---|---|---|---|
| Rev A | 05.10.2026 | Первый регламент прошивки, настройки, EOL/EVT и evidence | Синхронизация firmware и приложения |
| Rev B | 06.10.2026 | Выпуск 2026100601; добавлены factory identity до первого BLE, полный PKI flow, классификация секретов, BG95 mTLS, SIM registration, ACL и end-to-end проверка `dioneya.ru` | Release `EVT_PRE_20_BENCH_RELEASE_2026100601`; commit в manifest |
| Rev C | 06.10.2026 | Добавлены сквозная операторская последовательность, точное создание P-256 key/CSR, журналы factory identity, карта BG95, повторяемость команд и форма provisioning receipt | Release `EVT_PRE_20_BENCH_RELEASE_2026100601`; firmware без изменения |

## 31. Остаточные проверки и решения

Стендовый программный комплект полностью сформирован и подписан. До признания полевой производственной готовности остаются действия, которые требуют собранного изделия, EOL-оснастки или отдельного решения по защите:

1. SWD read-back, option bytes и cold boot STM32 на B01.
2. nRF SWD, BLE LESC, GATT, UART IPC и MCUboot recovery на B01.
3. Запись `factoryid`, cold reboot, передача pairing secret в nRF, первое LESC, затем запись operational station secrets и проверка engineer role на B01.
4. Загрузка CA, station certificate и private key в фактический BG95 через EOL UART, проверка checksum и mTLS.
5. Attach, DNS, network time, MQTT, heartbeat, event, receipt, command ACK и SIM failover с реальными SIM.
6. A/B power-cut и rollback STM32 и nRF.
7. Замер токов, питания, микрофонов, GNSS/PPS, памяти, RF, температуры и герметичности.
8. Выбор production immutable root of trust, RDP/WRP/PCROP и политики восстановления.
9. Выпуск числовых production limits по результатам golden unit и EVT.

Если один из перечисленных шагов не выполнен, это фиксируется как HARDWARE VALIDATION PENDING или HOLD, а не как программная недоработка без анализа причины. Любое изменение ключей, endpoint, topic schema, BLE ICD, partition map или option bytes требует нового release manifest и регрессионного прогона.
## 32. Повторное выполнение, ротация и восстановление

| Операция | Можно повторить без изменения состояния | Что делать при ошибке или необходимости замены |
|---|---|---|
| `station-add` | Нет необходимости; duplicate должен быть отклонен | Сверить существующую запись, не создавать новый serial |
| `station-keygen` для B01 | Нет, активный сертификат повторно не выпускать | При компрометации выполнить revoke, ACL, затем новый keygen по решению |
| `station-sign` | Нет при активном certificate | Отозвать старый certificate, обновить CRL/ACL, создать новый key/CSR и подписать |
| `station-package` | Да, для текущего сертификата и текущих factory secrets | Защитить новый export и удалить старый после сверки |
| `label-qr` | Да, пока pairing secret не ротирован | После ротации уничтожить старую этикетку |
| `factoryid` | Нет, это однократная операция | Только оформленный full rework с согласованной очисткой |
| `pairsec` | Только после утвержденной server-side ротации | Перепечатать label, cold boot и проверить LESC |
| `station-secrets` export | Да, export аудируется | Старый временный файл удалить; повторная запись станции требует engineer role |
| BG95 `QFUPL` | Да, после `QFDEL` и с начала одного файла | Не продолжать со следующего файла при неизвестном результате |
| `acl` | Да | После любого issue/revoke повторить и проверить broker |
| `station-commission` | Нет, применяется после EOL к статусу provisioned | При rework сохранить историю; не маскировать новый цикл старым PASS |

Ротация station certificate выполняется в следующем порядке: зафиксировать причину, выполнить `station-revoke`, выполнить `acl`, убедиться в отказе старого сертификата, создать новый private key и CSR, выполнить `station-sign`, заново выпустить station package, загрузить новый cert/key в BG95, снова выполнить `acl`, повторить весь сетевой тест и только затем выполнить `station-commission`.

## 33. Форма provisioning receipt

Receipt создается отдельно для каждого изделия и не содержит secret values. Минимальная машинночитаемая форма:

```text
{
  "serial": "DIO-EVT-NNN",
  "station_id": 0,
  "tenant": "pilot1|pilot2|bench",
  "lot": "EVT-LOT-1|EVT-LOT-2|BENCH",
  "firmware_release": "EVT_PRE_20_BENCH_RELEASE_2026100601",
  "source_git_head": "<40 hex>",
  "stm32_sha256": "<64 hex>",
  "nrf52840_sha256": "<64 hex>",
  "apk_certificate_sha256": "<64 hex>",
  "factory_identity": "PASS",
  "pairing_present": true,
  "station_certificate_fingerprint_sha256": "<64 hex>",
  "station_key_generation": "fixture-generated|server-side-bench",
  "iccid1_masked": "***************1234",
  "iccid2_masked": "***************5678",
  "imei_masked": "***********1234",
  "apn_profile": "<profile id>",
  "acl_revision": "<revision or hash>",
  "bg95_files": {"ca": "PASS", "cert": "PASS", "key": "PASS"},
  "network": {"sim": "PASS", "pdp": "PASS", "dns": "PASS", "tls": "PASS", "mqtt": "PASS"},
  "application": {"heartbeat": "PASS", "event_receipt": "PASS", "command_ack": "PASS", "store_forward": "PASS", "sim_failover": "PASS"},
  "eol_record": "<path or id>",
  "temporary_secret_exports_removed": true,
  "operator": "<id>",
  "controller": "<id>",
  "completed_utc": "<ISO 8601>",
  "decision": "PASS|FAIL|HOLD"
}
```

Значение station ID заполняется фактическим числом. Поля с `PASS` должны иметь ссылку на журнал или EOL record в evidence manifest. Полные ICCID, IMSI, pairing secret, engineer key, command private key и station private key в receipt запрещены.

## 34. Передача результата и закрытие рабочего места

Перед окончанием смены оператор:

1. Проверяет, что все журналы относятся к правильному serial и имеют UTC timestamp.
2. Сохраняет release manifest, логи SWD, read-back, EOL, redacted modem log, PKI audit и server evidence.
3. Проверяет receipt вторым сотрудником и подписывает traveller.
4. Удаляет временные station package, label payload, station secrets и незашифрованный private key с телефона, съемного носителя и EOL-каталога после выполнения утвержденной политики хранения.
5. Проверяет корзину, временные каталоги, PowerShell history, clipboard и экспорт терминала на отсутствие secret values.
6. Возвращает телефон в заблокированное состояние, закрывает service window станции и отключает TEST_UART/SWD fixture.
7. Передает на следующий этап только публичные файлы, receipt без секретов и ссылку на контролируемое evidence.

Инструкция считается выполненной только после наличия подписанного traveller, provisioning receipt и EOL record для конкретного serial. Устное подтверждение, наличие MQTT PUBACK или видимость устройства в BLE не заменяют эти документы.
