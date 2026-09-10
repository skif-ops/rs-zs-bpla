# EOL test specification EVT-PRE-20

Статус: `DRAFT / LIMITS PARTLY OPEN / NOT RUN`

EOL выполняется для 20 из 20 изделий после полного provisioning. Один machine-readable bundle содержит `serial`, hardware revisions, firmware hashes, tool versions, калибровки, raw values, limits, итог и ссылки на бинарные evidence.

## Обязательные группы

| ID | Проверка | Минимальный критерий до freeze |
|---|---|---|
| EOL-ID-01 | Серийный номер и состав | Все ID уникальны и совпадают с traveller, QR и register |
| EOL-PWR-01 | Полярность, защиты и rails | Нет защитного события; rail limits будут заморожены после power validation |
| EOL-PWR-02 | S0-S4 токи | Измерены и сохранены во всех режимах; PASS limits OPEN до golden-unit characterization |
| EOL-FW-01 | Boot, signature, rollback counter | Только подписанный образ; версия и anti-rollback совпадают с manifest |
| EOL-STO-01 | QSPI и microSD | ID, read/write/verify, fault recovery и свободный объём проходят |
| EOL-AUD-01 | 4 канала | Все каналы присутствуют, без clipping/dropout; gain/phase limits OPEN до fixture MSA |
| EOL-AUD-02 | Геометрия и calibration | MIC1-MIC3/MIC4 mapping однозначен; calibration hash совпадает |
| EOL-TIM-01 | GNSS и PPS | Получены fix/timepulse и time quality; точностной предел замораживается в ПМИ |
| EOL-CELL-01 | SIM и attach | IMEI и оба ICCID ref читаются, slot mapping однозначен, attach проходит на утверждённой тестовой SIM |
| EOL-CELL-02 | MQTT/TLS | Проверка CA и hostname обязательна; publish, ACK и reconnect проходят |
| EOL-CELL-03 | Store-and-forward | Буфер сохраняется без сети и передаётся один раз после восстановления |
| EOL-CELL-04 | Dual SIM/APN failover | Только один слот активен; штатное переключение публичных APN и восстановление очереди проходят; private APN отклоняется |
| EOL-LORA-01 | Module and region lock | Модуль отвечает; профиль соответствует label; TX только в conducted/shielded setup до RF release |
| EOL-LORA-02 | Packet integrity | Framing, authentication, counter, dedup и retry проходят на test peer |
| EOL-BLE-01 | Service mode | Вход требует физического действия; неавторизованное чтение/запись отклонены |
| EOL-BLE-02 | Android compatibility | Config read/write and signed OTA smoke проходят с утверждённой app build |
| EOL-SEN-01 | Temperature and motion | ID, plausible values and self-test проходят |
| EOL-MECH-01 | Labels, ports, torque, seals | Визуальный контроль и torque records полны |
| EOL-IP-01 | Leak | Кривая соответствует отдельно замороженному limit данного корпуса |
| EOL-REC-01 | Record completeness | Нет пустого обязательного поля; все evidence hashes разрешаются |

## Fail policy

Любой обязательный FAIL блокирует изделие. После ремонта повторяется затронутая проверка и полный регрессионный EOL. Старый FAIL не удаляется, создаётся новая attempt с ссылкой на NCR/rework. Изделие не может получить PASS при неопределённом обязательном лимите.

## Fixture gate

До запуска партии EOL fixture проходит MSA на golden unit и known-fault samples: перепутанный MIC, отсутствующая антенная нагрузка, неверный регион, повреждённый storage, недействительная TLS chain и рассинхронизация serial. CAD, schematic, wiring и software fixture входят в MFG-004.
