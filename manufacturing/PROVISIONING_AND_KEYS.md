# Provisioning и ключи EVT-PRE-20

Статус: `DRAFT / IMPLEMENTATION NOT RELEASED`

## Разделение доверия

Контрактный производитель в Китае получает тестовые образы и открытые ключи проверки, но не получает production root key, OTA signing private key или серверный CA private key. Уникальное доверенное provisioning выполняется после входного контроля на изолированном рабочем месте владельца проекта либо доверенного интегратора.

## Уникальные данные изделия

- serial `DIO-EVT-NNN`;
- device UUID, не производный только от серийного номера;
- hardware revision и PCB serials;
- locked LoRa region profile `RU868`;
- modem IMEI, две ссылки ICCID, slot mapping и preferred slot в контролируемом реестре;
- разрешённые public APN profile IDs и hashes без открытых секретов;
- station client certificate и private key либо эквивалентная уникальная credential;
- BLE service pairing secret или PAKE verifier;
- LoRa device keys, если они требуются выбранным режимом;
- OTA image verification public key и anti-rollback counter baseline;
- calibration set identifier и hash.

## Поток

1. Проверить release manifest, часы, оператора и состояние изолированного ПК.
2. Считать аппаратные идентификаторы и сопоставить serial register.
3. Сгенерировать уникальный device UUID и ключ на устройстве или HSM-backed station. Экспорт private key запрещён, если hardware path поддержан.
4. Выпустить client certificate с ограниченным сроком и назначением.
5. Считать обе SIM, подтвердить `SIM1/SIM2 -> ICCID` и выбрать preferred slot.
6. Записать RU868, APN allowlist, endpoint allowlist, OTA public key и минимальную разрешённую версию.
7. Выполнить challenge-response без чтения секретного материала.
8. Сохранить только receipt: serial, public identifiers, обе redacted ICCID references, certificate fingerprint, key generation mode, tool version, operator, timestamp и результат.
9. Zeroize временные файлы и очистить test credentials до EOL.

## SIM без операторского API

Обычные SIM допускаются. В provisioning хранится ordered public APN profile set без PIN/PUK и открытых секретов. Станция инициирует исходящий MQTT/TLS или HTTPS/TLS сеанс через публичный APN/CGNAT. Private APN запрещён политикой пилота. Управление SIM через API оператора не является условием пилота.

Два физических слота работают как Dual SIM Single Standby. В provisioning обязательны локальный учёт двух ICCID/IMEI, preferred slot, public APN allowlist и безопасный сценарий замены SIM. Тариф и баланс не входят в критерии EVT.

## Release gate

Provisioning tool должен иметь воспроизводимую сборку, журнал событий, режим повторного запуска без создания дубликатов, проверку несовпадения serial/IMEI и тест zeroization. До этого MFG-003 остаётся OPEN.
