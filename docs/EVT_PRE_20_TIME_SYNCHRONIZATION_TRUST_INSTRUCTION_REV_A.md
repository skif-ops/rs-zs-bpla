# Синхронизация времени и доверие координат EVT PRE 20

Ревизия A. Дата 16 октября 2026 года. Проект Дионея.

RU: Документ задаёт настройку и проверку GNSS, PPS, holdover, сетевого времени и неизменяемых координат установки станции. Он применяется при сборке, EOL, монтаже и повторном вводе.

EN: This document defines setup and verification of GNSS, PPS, holdover, network time and locked installation coordinates. It applies during assembly, EOL, field installation and recommissioning.

## 1 Архитектура

RU: Координаты установки и текущее GNSS-наблюдение имеют разные роли. После commissioning авторитетной геометрией являются installation coordinates. GNSS продолжает давать PPS, время и диагностическое сравнение, но не заменяет координаты установки автоматически.

EN: Installation coordinates and the current GNSS observation have different roles. After commissioning, installation coordinates are authoritative for geometry. GNSS continues to provide PPS, time and diagnostic comparison but cannot overwrite the installation coordinates automatically.

| Функция Function | Основной источник Primary source | Резерв или ограничение Backup or limit |
|---|---|---|
| Геометрия станции Station geometry | Locked installation coordinates | Изменение только в физическом service mode |
| Точное время Precise time | GNSS time plus PPS | Holdover после ранее доверенной дисциплины |
| Сетевые операции Network operations | BG95 network time where required | Не заменяет PPS для TDOA |
| Контроль позиции Position integrity | GNSS fix против installation coordinates | Spoof jam и distance thresholds |
| TDOA | Только trusted time и установка | Degraded invalid после исчерпания holdover |

## 2 Состояния доверия

RU: Time trust использует GNSS TIME TRUSTED, HOLDOVER, GNSS TIME SUSPECT и UNSYNCED. Position trust использует UNCONFIGURED, CONFIGURED OK, CONFIGURED WARN, CONFIGURED SUSPECT и REVALIDATION REQUIRED.

EN: Time trust uses GNSS TIME TRUSTED, HOLDOVER, GNSS TIME SUSPECT and UNSYNCED. Position trust uses UNCONFIGURED, CONFIGURED OK, CONFIGURED WARN, CONFIGURED SUSPECT and REVALIDATION REQUIRED.

RU: Начальные пороги позиции для EVT равны 25 m warning, 75 m suspect и 250 m gross jump с учётом reported accuracy. Эти значения программные. Окончательные пределы точности PPS и допустимого holdover утверждаются только по измерениям B01 и последующих станций.

EN: Initial EVT position thresholds are 25 m warning, 75 m suspect and 250 m gross jump, adjusted for reported accuracy. These are software settings. Final PPS-accuracy and permitted-holdover limits require measurements from B01 and subsequent stations.

## 3 Подготовка

1. RU: Проверить PCB MAIN 8L, разъём J9 GNSS, тракт активной антенны, питание bias и линию PPS на PA0 TIM2 capture. EN: Verify PCB MAIN 8L, J9 GNSS, the active-antenna path, bias supply and the PPS line at PA0 TIM2 capture.
2. RU: Подключить утверждённую GNSS-антенну с открытым небом или GNSS simulator. Не включать RF тракт с неподходящей нагрузкой. EN: Connect an approved GNSS antenna with sky view or a GNSS simulator. Do not operate the RF path with an unsuitable load.
3. RU: Зафиксировать firmware release, serial, дату UTC, тип антенны, кабель, уровень сигнала и приборы. EN: Record firmware release, serial, UTC date, antenna type, cable, signal level and instruments.
4. RU: Проверить, что команда pps, heartbeat и серверная страница состояния доступны. EN: Confirm that the pps command, heartbeat and server station-status page are available.

## 4 Первичное получение времени

1. RU: Подать питание и дождаться корректного GNSS fix и валидного сообщения времени. EN: Power the unit and wait for a valid GNSS fix and time message.
2. RU: Выполнить pps. Bound count должен расти, jumps не должны увеличиваться, time suspect должен быть false после окна проверки. EN: Run pps. The bound count must increase, jumps must not increase and time suspect must clear after the verification window.
3. RU: Сверить UTC с эталонным прибором или GNSS simulator. Записать measured offset и jitter. EN: Compare UTC against the reference instrument or GNSS simulator. Record measured offset and jitter.
4. RU: Проверить heartbeat. Он должен содержать time trust, PPS state, GNSS fix и диагностические данные без изменения locked position. EN: Check the heartbeat. It must contain time trust, PPS state, GNSS fix and diagnostics without changing the locked position.
5. RU: До утверждения измеренных пределов поле решения остаётся HOLD даже при исправной программной последовательности. EN: Until measured limits are approved, the decision remains HOLD even when the software sequence behaves correctly.

## 5 Установка координат

1. RU: Ввести станцию в физический service mode и установить защищённое BLE соединение по QR и serial. EN: Enter physical service mode and establish a protected BLE connection using the QR and serial.
2. RU: Выбрать manual, phone location, station GNSS snapshot или surveyed. EN: Select manual, phone location, station GNSS snapshot or surveyed.
3. RU: Проверить latitude, longitude, MSL altitude, accuracy, source и delta относительно текущего GNSS. EN: Verify latitude, longitude, MSL altitude, accuracy, source and delta from current GNSS.
4. RU: Подтвердить serial, выполнить atomic write, read back, hash comparison и lock. EN: Confirm the serial, perform atomic write, read back, hash comparison and lock.
5. RU: После power cycle убедиться, что locked coordinates сохранены. EN: After a power cycle confirm that the locked coordinates are retained.
6. RU: Любое повторное изменение требует service mode, авторизованной роли, новой audit записи и полного revalidation. EN: Any later change requires service mode, an authorized role, a new audit record and complete revalidation.

## 6 Проверка holdover

1. RU: Сначала получить GNSS TIME TRUSTED не менее установленного окна проверки. EN: First establish GNSS TIME TRUSTED for at least the configured verification window.
2. RU: Отключить PPS контролируемо и отметить UTC. EN: Disconnect PPS in a controlled manner and record UTC.
3. RU: Проверить немедленный переход в HOLDOVER без скачка event timestamp. EN: Verify immediate transition to HOLDOVER without a jump in event timestamps.
4. RU: Записывать predicted error, offset и длительность. EN: Record predicted error, offset and duration.
5. RU: Текущий программный предел перехода в UNSYNCED равен 120 s. Он не является окончательным метрологическим пределом TDOA до измерений B01. EN: The current software transition to UNSYNCED is 120 s. It is not the final metrological TDOA limit until B01 measurements are completed.
6. RU: Восстановить PPS и проверить возврат без недопустимого скачка. После подозрительного скачка требуется окно последовательных согласованных PPS. EN: Restore PPS and verify recovery without an unacceptable jump. After a suspicious jump, a window of consecutive consistent PPS pulses is required.
7. RU: Сохранить waveform, GNSS log и console output. EN: Retain the waveform, GNSS log and console output.

## 7 Spoof jam и скачки

RU: PPS вне допустимого окна отвергается. Станция остаётся на собственной шкале в HOLDOVER, помечает time suspect и увеличивает jump counter. При длительной потере доверия TDOA становится degraded или invalid, но акустическое обнаружение может продолжаться.

EN: A PPS edge outside the allowed window is rejected. The station stays on its own holdover scale, marks time suspect and increments the jump counter. After prolonged loss of trust, TDOA becomes degraded or invalid while acoustic detection may continue.

RU: GNSS spoof or jam не изменяет installation coordinates. Устойчивая дистанция выше warning или suspect thresholds меняет только состояние доверия. Gross jump и receiver spoof дают немедленный suspect.

EN: GNSS spoof or jam does not change installation coordinates. A persistent distance above warning or suspect thresholds changes only the trust state. A gross jump or receiver-spoof indication causes immediate suspect.

## 8 Роль сетевого времени

RU: Сетевое время BG95 используется для установления соединения, проверки TLS и разрешённых операций, когда это предусмотрено прошивкой. Оно не подтверждает фазу PPS и не заменяет GNSS PPS для TDOA. Расхождение сетевого и GNSS времени фиксируется как диагностическое событие.

EN: BG95 network time supports connection establishment, TLS validation and permitted operations where implemented. It does not establish PPS phase and does not replace GNSS PPS for TDOA. A network-versus-GNSS time mismatch is recorded as a diagnostic event.

## 9 Сервер и мониторинг

1. RU: Сервер хранит authoritative installation coordinates независимо от наблюдаемого GNSS. EN: The server stores authoritative installation coordinates independently from observed GNSS.
2. RU: Экран станции показывает installed position, GNSS now, delta, satellites, accuracy, spoof jam, time trust, PPS и holdover. EN: The station page shows installed position, GNSS now, delta, satellites, accuracy, spoof jam, time trust, PPS and holdover.
3. RU: Сервер не принимает удалённую команду автоматической замены координат для EVT. EN: The server rejects remote automatic coordinate replacement for EVT.
4. RU: Fusion и TDOA используют только разрешённые состояния time trust и installation coordinates. EN: Fusion and TDOA use only permitted time-trust states and installation coordinates.

## 10 EOL и монтажный контроль

| Проверка Test | Evidence | Решение Decision |
|---|---|---|
| GNSS cold warm start | GNSS log и время фикса GNSS log and fix time | PASS по утверждённому пределу |
| PPS bind | Console pps и oscilloscope | HOLD до числового предела B01 |
| Holdover | Offset versus time и waveform | HOLD до числового предела B01 |
| Time jump | Injected jump log | PASS при reject и time suspect |
| PPS loss recovery | Console heartbeat event timestamps | PASS без недопустимого скачка |
| Position lock | Commissioning receipt и power cycle | PASS при hash read back |
| GNSS drift spoof jam | Matrix и server evidence | PASS если geometry не изменена |

RU: Все результаты привязывают к serial и release. Undefined mandatory limit или отсутствующее evidence дают HOLD. EN: Bind every result to the serial and release. An undefined mandatory limit or missing evidence produces HOLD.

## 11 Восстановление

RU: Если PPS не привязывается, проверить fix, timepulse configuration, J9, PA0, TIM2 clock, антенну и bias. Если TLS не устанавливается, проверить GNSS or network time, certificate chain, hostname, APN и redacted modem state. Если coordinates не совпадают, не перезаписывать их автоматически. Перевести станцию в REVALIDATION REQUIRED и выполнить оформленное recommissioning.

EN: If PPS does not bind, check fix, timepulse configuration, J9, PA0, the TIM2 clock, antenna and bias. If TLS fails, check GNSS or network time, certificate chain, hostname, APN and redacted modem state. If coordinates differ, do not overwrite them automatically. Move the station to REVALIDATION REQUIRED and perform controlled recommissioning.

## 12 Критерий завершения

RU: Синхронизация закрыта только при наличии GNSS log, PPS waveform, console pps, heartbeat, holdover record, position commissioning receipt и server screenshot or export для правильного serial. Окончательный FIELD READY требует утверждённых измеренных пределов B01.

EN: Synchronization is complete only when the correct serial has a GNSS log, PPS waveform, pps console output, heartbeat, holdover record, position commissioning receipt and server screenshot or export. Final FIELD READY requires approved measured limits from B01.
