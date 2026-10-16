# Инструкция по монтажу, подключению и вводу станции Дионея EVT-PRE-20

**Документ:** EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_B  
**Ревизия:** Rev B  
**Дата:** 16.10.2026  
**Комплект:** EVT-PRE-20 REV_D10  
**Статус:** RELEASED FOR SITE PREPARATION; SITE-SPECIFIC PARAMETERS AND PHYSICAL EXECUTION OPEN  
**Назначение:** пошаговый монтаж, подключение, настройка, проверка и передача станции в эксплуатацию

## 1. Условия допуска Acceptance prerequisites

RU: К монтажу допускается станция с подписанным traveller, unit passport, complete EOL record, resolved NCR list and Overall PASS. Серийный номер должен входить в `DIO-EVT-001…040`; B01 устанавливается на объект только по отдельному решению. Candidate firmware 2026101601 применяется для EVT и не обозначается final production release.

EN: Installation requires a signed traveller, unit passport, complete EOL record, resolved NCR list and Overall PASS. The serial shall be within `DIO-EVT-001…040`; B01 is field-installed only by separate approval. Candidate firmware 2026101601 is for EVT and shall not be represented as final production release.

## 2. Документы на объект Site documents

1. RU: Site drawing with coordinates, elevation, orientation, foundation and service access. EN: Site drawing with coordinates, elevation, orientation, foundation and service access.
2. RU: Approved anchor and torque plan PAR-I01. EN: Approved anchor and torque plan PAR-I01.
3. RU: Grounding and lightning protection design with acceptance limit PAR-I02. EN: Grounding and lightning protection design with acceptance limit PAR-I02.
4. RU: Cable route, protective device, fuse and disconnection plan. EN: Cable route, protective device, fuse and disconnection plan.
5. RU: RF survey or confirmed coverage for both SIMs and LoRa profile. EN: RF survey or confirmed coverage for both SIMs and the LoRa profile.

## 3. Приемка площадки Site readiness

1. RU: Сверить координаты и физический site ID с заданием. EN: Match coordinates and physical site ID to the assignment.
2. RU: Проверить несущую способность, вертикальность, drainage, flood level, snow/ice and service clearance. EN: Verify load capacity, verticality, drainage, flood level, snow/ice and service clearance.
3. RU: Проверить охранную зону, доступ персонала и отсутствие постоянного препятствия микрофонам и антеннам. EN: Verify access controls and absence of permanent microphone or antenna obstructions.
4. RU: Проверить lightning protection, bonding point and power isolation. EN: Verify lightning protection, bonding point and power isolation.
5. RU: При несоответствии чертежу присвоить SITE HOLD; не адаптировать крепление на месте без approved deviation. EN: Assign SITE HOLD for drawing mismatch and do not improvise mounting without an approved deviation.

## 4. Приемка станции и распаковка Unit receipt and unpacking

1. RU: Сверить serial/QR, tamper indicators, packing list and shock/water indicators. EN: Verify serial/QR, tamper indicators, packing list and shock/water indicators.
2. RU: Осмотреть enclosure, membranes, acoustic ports, glands, antenna connectors and solar/battery interfaces. EN: Inspect enclosure, membranes, acoustic ports, glands, antenna connectors and solar/battery interfaces.
3. RU: До подъема подтвердить транспортное состояние батареи и снять только разрешенные caps. EN: Confirm battery transport state before lifting and remove only authorized caps.
4. RU: Повреждения фотографировать до распаковки и оформлять NCR. EN: Photograph damage before unpacking and open an NCR.

## 5. Механический монтаж Mechanical installation

1. RU: Использовать только крепеж, washers, isolators and anchor pattern из site drawing. EN: Use only the fasteners, washers, isolators and anchor pattern in the site drawing.
2. RU: Поднимать за предусмотренные точки; не использовать microphone arms, cable glands or antennas. EN: Lift only from designated points and never by microphone arms, cable glands or antennas.
3. RU: Установить ориентацию по drawing; записать azimuth, tilt and height. EN: Set orientation per drawing and record azimuth, tilt and height.
4. RU: Затягивать крепеж утвержденной sequence; записывать actual torque, tool ID and calibration. EN: Tighten in the approved sequence and record actual torque, tool ID and calibration.
5. RU: PASS разрешен только при APPROVED PAR-I01 и отсутствии deformation or looseness. EN: PASS requires PAR-I01 APPROVED and no deformation or looseness.

## 6. Кабели, антенны и акустика Cables, antennas and acoustics

1. RU: Сформировать drip loops ниже вводов; обеспечить service loops and strain relief. EN: Form drip loops below glands and provide service loops and strain relief.
2. RU: Соблюдать минимальные bend radii and separation от силовых трасс по утвержденному проекту. EN: Maintain approved bend radii and separation from power routes.
3. RU: Держать metalwork and cables вне antenna keepout; RF порт подключать до включения передатчика. EN: Keep metalwork and cables outside antenna keepout and connect the RF path before enabling transmission.
4. RU: Не закрывать acoustic ports, vents and membranes; проверить одинаковую ориентацию микрофонных узлов. EN: Do not obstruct acoustic ports, vents or membranes and verify microphone assembly orientation.
5. RU: Сделать обзорные и close-up photos после укладки. EN: Take overview and close-up photographs after routing.

## 7. Заземление и защита Grounding and protection

1. RU: Подключить protective bonding первым и отключать последним. EN: Connect protective bonding first and disconnect it last.
2. RU: Очистить контактную поверхность и применить approved corrosion protection. EN: Clean the bonding surface and apply approved corrosion protection.
3. RU: Измерить continuity and grounding resistance approved method; записать instrument and calibration. EN: Measure continuity and grounding resistance using the approved method and record instrument and calibration.
4. RU: До утверждения PAR-I02 результат остается HOLD. EN: Keep the result at HOLD until PAR-I02 is approved.

## 8. Подключение питания Power connection

1. RU: Убедиться, что disconnect device открыт, battery isolated and solar input covered or disconnected. EN: Verify that the disconnect device is open, the battery isolated and solar input covered or disconnected.
2. RU: Проверить polarity, open-circuit voltage, fuse rating and protective-device setting. EN: Verify polarity, open-circuit voltage, fuse rating and protective-device setting.
3. RU: Подключить ground first, then low-voltage power; активировать источник последним. EN: Connect ground first, then low-voltage power and energize the source last.
4. RU: Записать input voltage and current during start-up; compare with approved limits. EN: Record input voltage and current during start-up and compare with approved limits.
5. RU: При overcurrent, unstable rails, odor, smoke or abnormal heating отключить питание и открыть NCR. EN: De-energize and open an NCR on overcurrent, unstable rails, odor, smoke or abnormal heating.

## 9. Идентичность, сертификаты и конфигурация Identity and certificates

1. RU: Сверить QR, serial, device ID and unit passport. EN: Match QR, serial, device ID and unit passport.
2. RU: Выполнить BLE LESC pairing в контролируемом сервисном окне. EN: Perform BLE LESC pairing in the controlled service window.
3. RU: Установить site configuration без хранения секретов на телефоне. EN: Apply site configuration without retaining secrets on the phone.
4. RU: Проверить certificate fingerprint, chain, validity, CRL behavior and server identity по PKI instruction. EN: Verify certificate fingerprint, chain, validity, CRL behavior and server identity under the PKI instruction.
5. RU: Сохранить только masked identifiers and hashes в открытом отчете. EN: Store only masked identifiers and hashes in the open report.

## 10. Координаты и синхронизация Coordinates and synchronization

1. RU: Записать фактические latitude, longitude, altitude, method and accuracy evidence. EN: Record actual latitude, longitude, altitude, method and accuracy evidence.
2. RU: Выполнить configuration read-back and hash check. EN: Perform configuration read-back and hash verification.
3. RU: Проверить GNSS fix, PPS, trusted-time state, holdover transition and recovery. EN: Verify GNSS fix, PPS, trusted-time state, holdover transition and recovery.
4. RU: Численные пределы принимаются только из утвержденного EOL limit set; undefined limit gives HOLD. EN: Numeric limits come only from the approved EOL limit set; an undefined limit gives HOLD.

## 11. Связь и сервер Communications and server

1. RU: Проверить SIM1 and SIM2, APN, LTE attach, DNS and signal evidence. EN: Verify SIM1 and SIM2, APN, LTE attach, DNS and signal evidence.
2. RU: Проверить TLS, MQTT connect, heartbeat, test event, application receipt and command ACK. EN: Verify TLS, MQTT connect, heartbeat, test event, application receipt and command ACK.
3. RU: Проверить store-and-forward отключением backhaul и последующей доставкой без дублирования. EN: Verify store-and-forward by interrupting backhaul and confirming later delivery without duplication.
4. RU: Проверить LoRa profile and permitted regional configuration without radiated test outside legal limits. EN: Verify the LoRa profile and permitted regional configuration without radiated testing outside legal limits.

## 12. Акустика и функциональная проверка Acoustic and functional checks

1. RU: Проверить четыре канала, channel identity, gain, phase, noise and wake. EN: Verify four channels, channel identity, gain, phase, noise and wake.
2. RU: Осмотреть пространство вокруг microphones на отражающие или шумящие предметы и записать условия. EN: Inspect the microphone surroundings for reflective or noise-generating objects and record conditions.
3. RU: Выполнить controlled test event и подтвердить receipt в приложении. EN: Run a controlled test event and confirm receipt in the application.
4. RU: Физический site test не заменяет лабораторный EOL; оба результата сохраняются. EN: The physical site test does not replace laboratory EOL; retain both records.

## 13. Герметичность и финальный осмотр Sealing and final inspection

1. RU: Проверить glands, seals, covers, vents and fastener witness marks. EN: Inspect glands, seals, covers, vents and fastener witness marks.
2. RU: Выполнить leak test only by approved method PAR-I03; до утверждения limit результат HOLD. EN: Perform leak testing only under approved method PAR-I03; keep HOLD until the limit is approved.
3. RU: Убедиться, что service access остается возможным без разрушения трассы. EN: Verify service access remains possible without destroying routing.

## 14. Доказательства и приемка Evidence and acceptance

| Область Area | Обязательное evidence Mandatory evidence | Gate |
|---|---|---|
| Механика Mechanical | site overview, anchors, orientation, actual torques | APPROVED parameters plus reviewer |
| Электрика Electrical | polarity, ground, startup voltage/current, instrument IDs | PASS and source log |
| Связь Communications | SIM1/SIM2, TLS/MQTT, heartbeat, receipt, ACK | PASS |
| Время и GNSS Time/GNSS | fix, PPS, trust state, coordinates and hash | PASS or HOLD on open limit |
| Акустика Acoustic | four channels, identity, gain/phase/noise record | PASS or HOLD on open limit |
| Записи Records | checklist, unit passport, NCR disposition, SHA-256 | no blank mandatory field |

RU: Итоговый FIELD READY разрешен только при закрытых обязательных шагах, APPROVED site parameters, Overall PASS and installer/reviewer signatures. Любое отсутствующее evidence дает HOLD.

EN: FIELD READY requires all mandatory steps closed, APPROVED site parameters, Overall PASS and installer/reviewer signatures. Any missing evidence produces HOLD.

## 15. Отключение и демонтаж Shutdown and removal

1. RU: Остановить передачу, открыть disconnect, отключить power, then battery/solar, and remove protective bonding last. EN: Stop transmission, open the disconnect, remove power, then battery/solar, and remove protective bonding last.
2. RU: Закрыть RF and electrical connectors approved caps. EN: Cap RF and electrical connectors with approved covers.
3. RU: Зафиксировать состояние, причину демонтажа, coordinates and returned accessories. EN: Record condition, removal reason, coordinates and returned accessories.
