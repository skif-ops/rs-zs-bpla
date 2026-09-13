# ЗС-БПЛА firmware, EVT-PRE-20

Текущий каталог содержит переносимое C11-ядро: типы событий, compact CBOR, DSP, архивирование, state machines BG95/LoRa, GNSS parsing и host-тесты.

Целевой контроллер предсерии: `STM32U585VIT6Q`, LQFP100. Упоминания STM32U585ZI и платы WeAct относятся к предыдущим этапам и не являются target EVT-PRE-20.

## Что уже проверяется

```sh
cmake -S firmware -B firmware/build -DCMAKE_BUILD_TYPE=Release
cmake --build firmware/build --parallel
ctest --test-dir firmware/build --output-on-failure
```

Host PASS не означает готовую прошивку изделия.

## Что отсутствует до target build

- открытие, проверка и регенерация подготовленного STM32CubeMX `.ioc` версией 6.12.0;
- production linker с secure boot/A/B и HAL/LL bindings;
- драйвер PDM/MDF для четырёх T5838 на фактической плате;
- аппаратное и end-to-end подтверждение BG95 TLS/MQTT, защищённый downstream и provisioning;
- два валидированных региональных LoRa-профиля;
- secure boot, A/B OTA, rollback и подписанный release;
- измерение памяти, CPU, тока и времени на target.

До закрытия этих пунктов статус firmware: `TARGET_PORT_REQUIRED / OPEN / NOT RUN`. BIN/HEX из host-сборки запрещено маркировать как прошивку станции.

Host-контракт BG95 теперь покрывает автоматическое чтение SIM/оператора,
выбор APN через ответ сети или разрешённый PLMN-каталог, обязательное чтение
APN/IP/шлюза/DNS активного PDP и последовательность TLS/MQTT с fail-closed
обработкой ошибок. Полные IMSI/ICCID удерживаются только в оперативном состоянии
и включаются в отдельный heartbeat, разрешённый только через взаимный TLS;
общий server API маскирует их. Границы и отложенные до сборки станций
аппаратные доказательства зафиксированы в `BG95_MQTT_TLS_CONTRACT_REV_A.md`;
это не снимает общий `TARGET_PORT_REQUIRED` и не является сетевым EVT PASS.

Portable dual-SIM controller теперь отделяет проверяемую host-политику от
будущего target GPIO binding. Он принимает слот только после 20 ms DET debounce,
ограничивает профиль тремя попытками и 900-second hold, требует authenticated
manual assertion и audit intent/commit. При активном переключении новый слот не
может быть выбран до остановки трафика, сохранения очереди, штатного выключения
BG95, подтверждения mux High-Z и отключения modem rail. После включения
обязательны стабильный `PWR_GOOD` не менее 30 ms, 700 ms PWRKEY, полное совпадение
provisioned ICCID и attach/DNS/TLS до resume прежних event IDs. Любая ошибка,
brownout или debounced removal переводит controller в safe-off request. Это
host QG-1/QG-2, а не доказательство GPIO, реальных SIM, 100 циклов, операторов
или 24-часовой работы станции.

Portable store-and-forward теперь дополнен серверным application receipt:
сервер после durable processing публикует canonical CBOR с SHA-256 точного
detection payload, а fixed-memory firmware parser проверяет topic, QoS/retain и
полную identity события до маркировки outbox slot доставленным. Portable uplink
adapter сохраняет retry marker до выдачи exact `up` topic/payload и не считает
PUBACK разрешением на удаление. BG95 uplink binding использует fixed-length
`QMTPUB`: после `>` пишет ровно заявленное число binary CBOR bytes и оставляет
event pending даже после `+QMTPUB` success. Базовая BG95 state machine до
`QMTOPEN` включает direct `QMTRECV` с обязательной длиной; receipt binding после
connect проверяет этот флаг, подписывается на exact receipt topic с QoS 1 и
разбирает полный URC по byte count, сохраняя NUL/quote/CRLF/`0x1a`. Сам URC не
содержит retain-флаг, поэтому путь разрешается только явным внешним контрактом
station credential + server-only ACL + запрет retained receipt. Host QG не
заменяет target USART/DMA/ISR wiring, проверку broker policy/версии BG95 и аппаратный
recovery test.

Portable BG95 command binding использует тот же общий length-delimited parser:
после exact QoS-1 `down` subscription он передаёт только полный binary payload в
signature/journal/executor channel. Fixed-length `ack` `QMTPUB` начинается лишь
после durable `COMPLETED`; при reconnect повторная server command восстанавливает
ACK из journal без повторного side effect. Partial UART, timeout и mismatched
URC инвалидируют modem transport. Общая portable MQTT session принимает
произвольно фрагментированный raw UART, собирает line/prompt/length-delimited
URC в лимите 2304 bytes, сериализует command/receipt subscriptions, event
publish и command ACK единым TX owner. Один command frame буферизуется во время
занятого TX, следующие учитываются как требующие server retry; disconnect
очищает RAM queue и запускает ordered resubscribe. Retain в `QMTRECV` не виден и покрывается только явно подтверждённым
server-only/non-retained ACL contract. Target crypto, exact slot counts/OCTOSPI/endurance, USART/DMA/ISR,
broker policy и hardware evidence остаются открыты.

Command journal теперь имеет отдельный portable NOR adapter: каждый 88-byte
accepted/completed record занимает собственный physical erase block, callbacks
не могут выйти за логический slot, а torn commit повторно используется без
стирания соседнего record. Host QG проверяет restart roundtrip, commit-write
failure, alignment/range и erase isolation. Общий layout/bind ниже также
доказывает непересечение journal с archive и outbox. Production slot count,
OCTOSPI binding и endurance всё ещё не определены.

Portable NOR adapter выделяет каждому outbox slot отдельный erase block и
проверяет alignment/range partition, поэтому reclaim не стирает соседнее pending
event. Перед выдачей любого storage interface общий bind fail-closed проверяет
точный W25Q512JV JEDEC ID `EF 40 20`, SFDP/BFPT ёмкость 64 MiB, 4-byte geometry
и Status Register-2 QE; сброшенный QE восстанавливается с read-back. Portable
layout planner вычисляет непересекающиеся разделы: audio archive
занимает выровненный префикс NOR, за ним расположен erase-isolated command
journal, а outbox занимает хвост. Для контрольной геометрии 64 MiB / 4 KiB / 16
command slots / 256 event slots host QG проверяет 62.9375 MiB archive + 64 KiB
journal + 1 MiB outbox. Единый bind API создаёт все три adapter-а из одного
layout и ограничивает видимую archive storage точно началом journal, поэтому
независимая ошибочная инициализация диапазонов fail-closed. Точные числа слотов,
OCTOSPI HAL и endurance ещё должны быть утверждены в target memory map и
измерены на плате; host probe не заменяет проверку реального sample.

Первый target-инкремент уже фиксирует точный исходный контракт
`STM32U585VIT6Q/LQFP100`: 67 назначений из Rev.A pin map и AAD addendum,
запрет внешнего HSE, 32.768 kHz reference и пять ещё не измеренных runtime
profiles. Контракт генерируется воспроизводимо и проходит два независимых
контроля.

Второй target-инкремент закрепляет STM32CubeU5 v1.9.0 и его CMSIS-U5 commit,
добавляет официальный GCC startup/system и инженерный linker для 2 MiB flash,
768 KiB SRAM1-3 и 16 KiB SRAM4. Этот linker предназначен только для первичного
запуска без TrustZone; он не заменяет production-разметку secure boot/A/B и не
снимает общий `TARGET_PORT_REQUIRED`.

Третий target-инкремент формирует воспроизводимый pinout `.ioc` для
STM32CubeMX 6.12.0 / DB.6.0.120. В нём сохранены 67 назначений, включая
отдельные fail-closed `LORA_TXEN`/`LORA_RXEN`, и устранён
конфликт EXTI8: `LORA_DIO1` перенесён на `PC2/EXTI2`, а `MIC_WAKE` оставлен на
`PA8/EXTI8`. До открытия и регенерации в зафиксированной версии CubeMX файл не
считается подтверждённым target build.

Portable слой хранения installation position реализует атомарное чередование
двух слотов, CRC32, commit-marker, read-back, monotonic version и обязательные
physical-service/authenticated-role gates. Host QG не закрывает привязку этих
слотов к страницам STM32 Flash, ресурс перезаписи и power-loss fault injection
на фактической плате.

Portable слой commissioning принимает изменение installation position только
из локального BLE-origin после BLE Secure Connections, проверки peer identity
и физического сервисного окна не более 10 минут. Обычная installer-роль может
использовать только locked policy defaults; нестандартная trust policy требует
engineer-роли. Станция сама вычисляет канонический SHA-256, требует audit intent
до записи и audit committed после read-back. Это ещё не nRF52840/GATT binding:
UUID, pairing transport, сервисный таймер и durable audit backend проверяются на
целевой связке STM32+nRF и остаются release blocker.
