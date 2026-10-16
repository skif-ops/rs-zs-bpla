# Инструкция по монтажу и вводу станции Дионея EVT PRE 20

**Ревизия:** Rev A  
**Дата:** 16.10.2026  
**Комплект:** EVT-PRE-20 REV_D8  
**Назначение:** подготовка площадки, механический монтаж, подключение, настройка, функциональная проверка и передача станции в эксплуатацию

## 1. Условия допуска Acceptance prerequisites

RU: Монтаж разрешен только для станции с подписанным traveller, EOL record и Overall PASS. Кандидат 2026101601 используется для EVT; окончательный production release оформляется после аппаратной квалификации и фиксации численных EOL-пределов.

EN: Installation is allowed only for a station with a signed traveller, EOL record and Overall PASS. Candidate 2026101601 is used for EVT; the final production release follows hardware qualification and numeric EOL limit freeze.

## 2. Подготовка площадки Site preparation

1. RU: Подтвердить координаты, высоту, ориентацию, зону обслуживания и радиовидимость. EN: Confirm coordinates, height, orientation, service area and radio visibility.
2. RU: Проверить несущую способность основания и защиту от несанкционированного доступа. EN: Verify foundation capacity and protection against unauthorized access.
3. RU: Проверить молниезащиту, заземление и разделение силовых и сигнальных трасс по проекту площадки. EN: Verify lightning protection, grounding and separation of power and signal routes under the site design.
4. RU: До подъема проверить корпус, уплотнения, кабельные вводы и акустические порты. EN: Before lifting, inspect the enclosure, seals, cable glands and acoustic ports.

## 3. Механический монтаж Mechanical installation

1. RU: Использовать утвержденные крепеж, момент затяжки и схему опоры. EN: Use the approved fasteners, tightening torque and support arrangement.
2. RU: Не деформировать корпус и микрофонную геометрию. EN: Do not deform the enclosure or microphone geometry.
3. RU: Сформировать капельники и сервисные петли без малого радиуса изгиба. EN: Form drip and service loops without tight bend radius.
4. RU: Не размещать металл, силовые кабели и экраны в запрещенных зонах антенн. EN: Keep metal, power cables and shields out of antenna keepout zones.

## 4. Электрическое подключение Electrical connection

1. RU: Выполнять подключение при снятом питании. EN: Make connections with power removed.
2. RU: Проверить полярность, защитный аппарат, номинал предохранителя и сопротивление изоляции. EN: Verify polarity, protective device, fuse rating and insulation resistance.
3. RU: Подключить землю первой, питание последним. Отключать в обратном порядке. EN: Connect ground first and power last. Disconnect in reverse order.
4. RU: Не питать станцию через USB-C и не включать RF тракт без антенны или 50 ohm нагрузки. EN: Do not power the station through USB-C and do not enable RF without an antenna or 50 ohm load.

## 5. Настройка Commissioning

1. RU: Сверить QR и serial с traveller. EN: Match the QR and serial to the traveller.
2. RU: Открыть сервисное окно, выполнить BLE LESC pairing и проверить identity. EN: Open the service window, complete BLE LESC pairing and verify identity.
3. RU: Записать station secrets и конфигурацию только в предусмотренные поля; секретные значения не сохранять на телефоне. EN: Write station secrets and configuration only to defined fields; do not retain secret values on the phone.
4. RU: Записать фактические координаты и проверить read-back hash. EN: Enter the actual coordinates and verify the read-back hash.
5. RU: Проверить обе SIM, APN, LTE attach, DNS, время, TLS и MQTT. EN: Test both SIM cards, APN, LTE attach, DNS, time, TLS and MQTT.
6. RU: Проверить heartbeat, тестовое событие, application receipt, command ACK и store-and-forward. EN: Verify heartbeat, test event, application receipt, command ACK and store-and-forward.

## 6. Приемка монтажа Installation acceptance

| Проверка Check | Требование Requirement |
|---|---|
| Механика Mechanical | Нет деформации, люфта, натяга кабелей и перекрытия акустических портов / No deformation, looseness, cable strain or blocked acoustic ports |
| Герметичность Sealing | Уплотнения и вводы установлены, результат испытания записан / Seals and glands installed and test result recorded |
| Питание Power | Полярность, ток и шины соответствуют утвержденным пределам / Polarity, current and rails meet approved limits |
| Связь Communications | Обе SIM, TLS, MQTT, heartbeat and receipt PASS |
| GNSS | Fix, PPS and location record PASS по утвержденным пределам / Fix, PPS and location record PASS under approved limits |
| Акустика Acoustics | Четыре канала, фаза, шум и геометрия PASS / Four channels, phase, noise and geometry PASS |

## 7. Передача в эксплуатацию Operational handoff

RU: В паспорт станции включают serial, ревизии HW и FW, координаты, фото монтажа, EOL record, журнал commissioning, masked SIM identifiers, certificate fingerprint, номера NCR и подписи монтажника и контролера. При отсутствии обязательного доказательства решение остается HOLD.

EN: The unit passport includes serial, HW and FW revisions, coordinates, installation photographs, EOL record, commissioning log, masked SIM identifiers, certificate fingerprint, NCR references and installer and inspector approvals. Missing mandatory evidence keeps the decision at HOLD.
