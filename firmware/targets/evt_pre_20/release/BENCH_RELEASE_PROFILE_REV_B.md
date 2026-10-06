# EVT-PRE-20 bench software release profile, Rev.B

## Назначение

Профиль фиксирует комплект `EVT_PRE_20_BENCH_RELEASE_2026100601` для прошивки, фабричной идентификации и аппаратной проверки PCB-MAIN. Комплект содержит подписанный образ STM32U585, подписанный образ MCUboot для nRF52840 и подписанный APK монтажника. Закрытые ключи, пароли и Android keystore в пакет не входят.

Статус: `READY TO FLASH / HARDWARE VALIDATION PENDING`.

## Состав и доверие

| Компонент | Версия | Механизм доверия | Статус до железа |
|---|---:|---|---|
| STM32U585 | 2026100601 | Ed25519, canonical CBOR manifest, public key ID `04b418857c5001b2` | Сборка, подпись, размер, 74 host-теста и stack usage проверены |
| nRF52840 | 0.1.0+2026100501 | MCUboot ECDSA P-256, два слота по 472 KiB | Sysbuild и подпись проверены |
| Android | 0.1.0-bench.20261005, code 2026100501 | APK Signature Scheme v2, отдельный bench certificate | Unit tests, release build и подпись проверены |

STM32 версии 2026100601 добавляет фабричную команду `factoryid <serial> <pairing_secret_hex>`. Команда через изолированный TEST_UART записывает в NOR серийный номер физической станции и pairing secret из защищенного EOL-пакета. После холодного перезапуска STM32 передает pairing secret в nRF52840 до открытия BLE-окна. Один и тот же подписанный STM32 image применяется к B01 и DIO-EVT-001 - DIO-EVT-040, а уникальные данные вводятся на EOL.

## Обязательный порядок EOL

1. Проверить SHA-256 архива и подписей образов.
2. Прошить STM32 и nRF52840 через отдельные SWD.
3. Выпустить station certificate и защищенный station package.
4. Через TEST_UART выполнить `factoryid` с serial и полем `pairing_secret_hex` из `station.json`.
5. Выполнить холодный перезапуск и командой `secrets` проверить только признаки `factory <serial>` и `pairing set`.
6. Отсканировать соответствующую label QR, открыть сервисное окно и выполнить первое LESC-сопряжение.
7. Через BLE 0x0206 записать engineer key, фактические ICCID и public key подписи команд.
8. Загрузить в BG95 CA, station certificate и station private key, проверить size, checksum, список UFS-файлов и mTLS.
9. Записать station config, проверить heartbeat, тестовое событие, application receipt и только затем выполнить `station-commission`.

`station-package` является защищенным EOL-пакетом. Он не содержит station private key, но содержит pairing secret и engineer key. Label QR также содержит pairing secret. Эти файлы не являются публичными и удаляются с промежуточных носителей после подтвержденной загрузки.

## Границы стендового выпуска

STM32 использует прикладную проверку подписанного образа и A/B-переключение банков. Неизменяемый production root of trust, окончательная блокировка отладки и необратимые option bytes вводятся отдельным решением после EVT. До физической проверки остаются SWD, BOOT0, A/B power-cut, BLE, UART IPC, BG95 mTLS, две SIM, GNSS/PPS, LoRa в разрешенном RF-стенде, четыре микрофона, память, питание и EOL-пределы.

## English summary

This profile freezes bench release 2026100601. The STM32 image adds persistent EOL factory identity and label pairing-secret provisioning before the first BLE session. The station package and label are protected because they contain pairing and engineer secrets. Hardware validation remains mandatory for SWD, BLE, BG95 mutual TLS, peripherals, power, RF and EOL limits.
