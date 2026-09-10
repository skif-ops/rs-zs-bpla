# ICD LoRa backup transport v0.1

Статус: `DRAFT / TX_DISABLED / OPEN`

## 1. Назначение

LoRa является резервным транспортом событий P0 при недоступности cellular. Текущий проект использует собственный P2P/relay протокол и не должен маркироваться как LoRaWAN без отдельной реализации и сертификации.

## 2. Региональные варианты

Одна hardware PCB поддерживает варианты `RU868` и `EU868`. Регион задаётся подписанным manufacturing profile и дублируется на физической этикетке. Переключение региона пользователем запрещено.

Файл `config/lora/RU868.yaml` содержит контролируемый список кандидатных частот только внутри окон 864-865 и 868,7-869,2 МГц. Мощность и duty-cycle не утверждены, поэтому `tx_enabled: false`. Передача может быть включена только после проверки LoRa Alliance RP002-1.0.5, местных требований, conducted RF и антенны.

Старый символ firmware `zs_ru868_channels_hz={868.1,868.3,868.5,868.7 MHz}` удалён. Firmware принимает только семь кандидатных частот из `RU868.yaml`; 868,1/868,3/868,5/868,7 МГц и любые иные значения отклоняются. Передатчик остаётся заблокирован до загрузки подписанного регионального профиля и закрытия RF gate.

## 3. Предлагаемый frame

| Поле | Размер | Назначение |
|---|---:|---|
| magic/version/type | 3 B | идентификация кадра |
| region/profile id | 2 B | защита от неверного профиля |
| source station_id | 4 B | источник |
| boot_id + seq_no | 8 B | replay/dedup |
| event_id | 8 B | сквозной идентификатор |
| fragment index/count | 2 B | фрагментация |
| hop_count/ttl | 2 B | максимум 5 hop |
| payload length | 2 B | длина фрагмента |
| encrypted payload | variable | compact CBOR P0 |
| authentication tag | 8-16 B | AEAD tag |

Криптографический алгоритм и nonce construction замораживаются после security review. Уникальный ключ станции и ключ relay-группы не хранятся в GitHub. CRC радио не заменяет authentication tag.

## 4. Алгоритм

1. Cellular недоступен и есть P0 event.
2. Станция проверяет region profile и `tx_enabled`.
3. Если профиль не подписан или RF gate не закрыт, событие только сохраняется локально.
4. Иначе discovery ограничен региональным scheduler.
5. Relay проверяет AEAD, replay window, TTL и dedup, затем передаёт только разрешённый приоритет.
6. Gateway отправляет событие в «Мухоед» с исходным `event_id`.
7. End-to-end ACK возвращается источнику; до ACK запись остаётся в store-and-forward.

## 5. Текущий разрыв реализации

В репозитории есть state machine `zs_mesh` и низкоуровневая настройка SX1262, но отсутствуют TX framing, AEAD, ACK, fragmentation, signed profile loader, региональный scheduler и end-to-end тест. Статус: `MISSING_BLOCKER`, аппаратный PASS отсутствует.

## 6. Gate

Оба профиля проверяются отдельно: частота, EIRP, occupied bandwidth, spurious emissions, duty cycle/LBT при применимости, чувствительность, packet error rate, sleep current, работа relay, replay rejection, dedup, потеря фрагмента и восстановление после перезапуска.

Источник региональных параметров: https://resources.lora-alliance.org/document/rp002-1-0-5-lorawan-regional-parameters
