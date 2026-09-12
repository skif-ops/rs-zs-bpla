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

Host-контракт BG95 теперь покрывает public-APN policy и последовательность
PDP/TLS/MQTT с fail-closed обработкой ошибок. Его границы и открытые аппаратные
доказательства зафиксированы в `BG95_MQTT_TLS_CONTRACT_REV_A.md`; это не снимает
общий `TARGET_PORT_REQUIRED` и не является сетевым EVT PASS.

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
