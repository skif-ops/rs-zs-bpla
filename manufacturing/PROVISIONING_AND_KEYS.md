# Provisioning и ключи EVT-PRE-20

Статус: `DRAFT / IMPLEMENTATION NOT RELEASED`

## Разделение доверия

Контрактный производитель в Китае получает тестовые образы и открытые ключи проверки, но не получает production root key, OTA signing private key или серверный CA private key. Уникальное доверенное provisioning выполняется после входного контроля на изолированном рабочем месте владельца проекта либо доверенного интегратора.

## Уникальные данные изделия

- serial `DIO-EVT-NNN`;
- device UUID, не производный только от серийного номера;
- hardware revision и PCB serials;
- locked LoRa region profile;
- modem IMEI и ссылка на ICCID в контролируемом реестре;
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
5. Записать регион, endpoint allowlist, OTA public key и минимальную разрешённую версию.
6. Выполнить challenge-response без чтения секретного материала.
7. Сохранить только receipt: serial, public identifiers, certificate fingerprint, key generation mode, tool version, operator, timestamp и результат.
8. Zeroize временные файлы и очистить test credentials до EOL.

## SIM без операторского API

Обычная SIM допускается. В provisioning хранится APN profile без PIN/PUK и секретов. Станция инициирует исходящий MQTT/TLS или HTTPS/TLS сеанс через публичный APN/CGNAT. Управление SIM через API оператора не является условием пилота. Обязательны локальный учёт ICCID/IMEI, контроль баланса/тарифа организационным способом и сценарий замены SIM.

## Release gate

Provisioning tool должен иметь воспроизводимую сборку, журнал событий, режим повторного запуска без создания дубликатов, проверку несовпадения serial/IMEI и тест zeroization. До этого MFG-003 остаётся OPEN.

