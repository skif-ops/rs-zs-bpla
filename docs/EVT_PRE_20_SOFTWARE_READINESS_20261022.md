# Готовность ПО станции «Дионея» EVT-PRE-20

Дата проверки: 22.10.2026.

## Решение

Программный комплект готов к прошивке и аппаратной квалификации стендового образца `DIO-EVT-B01`.

Статус подписанного комплекта: `READY_TO_FLASH_HARDWARE_VALIDATION_PENDING`.

Блокировка прошивки станции запрещена до полного испытания таргета на реальном изделии, успешной регрессии, утверждения протокола EOL и индивидуального EOL PASS станции.

Синхронизация валидатора подтверждена успешным прогоном. SHA-256 `target_status.yaml`: `dc757b951ac4fa5508f9bace1dbee162ddef82a57f2f00bf3bed1152a75faed1`. SHA-256 `validate_mqtt_command_transport.py`: `ef74dfc93823eec39c5bf7ea765f3dde023a084d8efca71ea84f86e8f8f7895b`.

## Проверенный состав

| Объект | Результат |
|---|---|
| Host-сборка прошивки, MSVC Release | PASS |
| Тесты прошивки | 74 из 74 PASS |
| Сквозной CBOR `прошивка -> сервер` | PASS, detection schema 4, heartbeat schema 2 |
| Сервер «Мухоед» | 493 теста PASS, пропущенных тестов нет |
| Android, `testDebugUnitTest` и `assembleDebug` | PASS |
| Подпись стендового release APK | PASS, APK Signature Scheme v2, один подписант |
| Target contract и CubeMX IOC | QG-1 и QG-2 PASS |
| MQTT-команды, квитанции и outbox | QG-1 и QG-2 PASS |
| Dual SIM | QG-1 и QG-2 PASS для программной модели и host-runtime |
| STM32 vendor lock и scaffold | PASS |
| Server SBOM и supply chain | PASS |
| Канонический ZIP стендового выпуска | PASS |
| Поиск закрытых ключей в стендовом ZIP | PASS, закрытые материалы отсутствуют |
| Межблокировка производственной защиты | PASS, блокировка запрещена |

## Канонические артефакты

Архив: `releases/evt-pre-20/2026-10-06-rev-e/EVT_PRE_20_BENCH_RELEASE_2026100601.zip`.

SHA-256 архива: `e574bde3895d0e0c02ed6094d3861e2ab52723e223c0101c859451f3efc05d43`.

| Артефакт | SHA-256 |
|---|---|
| STM32U585, подписанный образ `2026100601` | `27a4e2ba3de7f3e6b9720cb1d1a1b25da62a5164cd6362349a99e3d48f884ef5` |
| nRF52840, подписанное приложение | `27a9e76b969ba6197de9b77874786a304dc0c04efe2f8994307fdc35560dd89b` |
| nRF52840, объединённый HEX | `7528e8a474283776162c9ac49d3de5082aa86a9a0d0f98d66603fdb2132a0f7f` |
| Android release APK | `39f45d4cd24cb2ce318d6e748cb9a581857e98ceeee0a4f2ddfcec9d6e7519fe` |

Сертификат Android release APK имеет SHA-256 `64b9b31cc6e64bdbc09457254501812634872a8e05de1a95e7d8c638dbfed90a` и совпадает с контрактом выпуска.

Повторная упаковка под тем же release ID не используется. Основанием остаётся канонический архив с закреплённым SHA-256.

## Что остаётся только на реальном изделии

1. Прошивка и read-back STM32U585 и nRF52840 через отдельные интерфейсы.
2. Проверка SWD, BOOT0, system memory recovery и фактического профиля option bytes.
3. Проверка A/B swap, trial confirmation и rollback STM32, включая потерю питания.
4. Проверка MCUboot, serial recovery, BLE advertising, LESC pairing, GATT и UART IPC nRF52840.
5. Проверка BG95 с реальными SIM и APN: mutual TLS, MQTT, application receipt и 100 циклов dual SIM.
6. Проверка W25Q512JV на целевом OCTOSPI: JEDEC, SFDP, QE, разметка, число слотов и ресурс записи.
7. Проверка GNSS/PPS, LoRa, датчиков, четырёх микрофонных каналов, DSP и передачи тревоги.
8. Измерения EOL по утверждённым пределам, cold boot, heartbeat и тестовое событие.
9. Полная регрессия на `DIO-EVT-B01` с оформленным протоколом и подписями ответственных лиц.

До выполнения этих пунктов `do_not_release: true` сохраняется. Secure boot и необратимые option bytes не включаются.

## Формальный общий аудит EVT-PRE-20

Исходные материалы полного комплекта найдены полностью. Общий формальный выпуск остаётся в состоянии `CUSTOMER_PROCUREMENT_HANDOFF_SENT_OPEN_FOLLOWUP`: заказной комплект уже передан заказчику, а старый корневой профиль аудита продолжает требовать разложенные производственные выходы, закрытие BOM QG-2 и снятие `do_not_release` после аппаратных испытаний.

Это состояние не отменяет готовность программного комплекта к стендовому образцу. Оно запрещает считать аппаратную квалификацию и окончательный производственный допуск выполненными заранее.
