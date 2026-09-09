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

- STM32CubeMX `.ioc` для STM32U585VIT6Q;
- подтверждённая карта выводов собственной PCB;
- startup, linker script и HAL/LL bindings;
- драйвер PDM/MDF для четырёх T5838 на фактической плате;
- production TLS/MQTT, защищённый downstream и provisioning;
- два валидированных региональных LoRa-профиля;
- secure boot, A/B OTA, rollback и подписанный release;
- измерение памяти, CPU, тока и времени на target.

До закрытия этих пунктов статус firmware: `TARGET_PORT_REQUIRED / OPEN / NOT RUN`. BIN/HEX из host-сборки запрещено маркировать как прошивку станции.

Первый target-инкремент уже фиксирует точный исходный контракт
`STM32U585VIT6Q/LQFP100`: 65 назначений из Rev.A pin map и AAD addendum,
запрет внешнего HSE, 32.768 kHz reference и пять ещё не измеренных runtime
profiles. Контракт генерируется воспроизводимо и проходит два независимых
контроля, но не снимает ни один из перечисленных выше release blockers.
