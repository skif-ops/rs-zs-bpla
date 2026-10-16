# EVT-PRE-20 bench software release profile, Rev.A

## Назначение

Профиль фиксирует стендовый комплект `EVT_PRE_20_BENCH_RELEASE_2026100501` для первой прошивки и аппаратной проверки PCB-MAIN. Комплект содержит подписанный образ STM32U585, подписанный образ MCUboot для nRF52840 и подписанный APK монтажника. Закрытый ключ, пароль и файл хранилища Android в пакет не входят.

Статус: `READY_TO_FLASH / HARDWARE VALIDATION PENDING`.

## Состав и доверие

| Компонент | Версия | Механизм доверия | Статус до железа |
|---|---:|---|---|
| STM32U585 | 2026100501 | Ed25519, canonical CBOR manifest, встроенный public key ID `04b418857c5001b2` | Сборка, подпись, размер и стек проверены |
| nRF52840 | 0.1.0+2026100501 | MCUboot ECDSA P-256, два слота по 472 KiB | Чистая sysbuild сборка и проверка подписи пройдены |
| Android | 0.1.0-bench.20261005, code 2026100501 | APK Signature Scheme v2, отдельный bench certificate | Unit tests, release build и подпись пройдены |

STM32 использует прикладную проверку подписанного образа и A/B переключение банков. Это пригодно для стендового образца и испытания отката. Неизменяемый production root of trust для STM32 будет отдельным решением после проверки железа и выбора production protection profile.

## Что разрешено на стенде

1. Прошить STM32 через SWD с профилем `option_bytes_bench_rev_a.json`.
2. Прошить nRF52840 объединённым `merged.hex` через отдельный SWD разъём.
3. Установить подписанный APK на выделенный телефон монтажника.
4. Выполнить первичную настройку, проверку BLE, UART IPC, A/B и восстановления.
5. Сохранить снимки option bytes, версии инструментов, серийные номера отладчиков и журналы испытаний в паспорт стендового изделия.

## Что требует физического образца

- подтверждение назначений GPIO и полярностей на PCB-MAIN;
- проверка SWD, BOOT0, системного загрузчика и обоих банков STM32;
- проверка BLE pairing, GATT, UART IPC и serial recovery MCUboot;
- испытание A/B с отключением питания на каждой стадии обновления;
- проверка QSPI, microSD, GNSS/PPS, BG95, двух SIM, LoRa, четырёх микрофонов и датчиков;
- измерение токов, уровней питания, акустических, временных, RF и климатических пределов.

## English summary

This profile freezes the signed bench software set for the first EVT-PRE-20 hardware bring-up. All three deliverables build and verify before hardware. The remaining gates require a physical assembled unit, fixture measurements or production security decisions. Private keys and passwords are excluded from the release archive.
