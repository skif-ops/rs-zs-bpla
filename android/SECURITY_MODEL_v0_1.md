# Android commissioning app - security model v0.1

Статус: `DRAFT / SECURITY REVIEW REQUIRED`

| Угроза | Контроль | Проверка |
|---|---|---|
| Подключение к чужой станции | QR-to-BLE identity binding и serial confirmation | подмена advertising и QR |
| Удалённое окно настройки | физическая service button и timeout 10 минут | попытка подключения вне окна |
| Общий заводской пароль | уникальный bootstrap secret на изделие, одноразовое погашение | duplicate/expired secret |
| Перехват BLE | BLE Secure Connections плюс application transcript binding | MITM test |
| Несанкционированная конфигурация | role, authenticated session, schema validation, atomic commit | fuzz и permission test |
| Подмена координат станции | installation coordinates записываются только в физическом service mode, read-back/hash/lock, смена создаёт новую version/audit | remote write, modified app request, replay старой конфигурации |
| GNSS spoofing позиции | configured installation coordinates остаются authoritative, GNSS сравнивается с ними, receiver spoof/jam flags отображаются отдельно | drift/jump/spoof injection matrix |
| GNSS spoofing времени | position trust и time trust разделены; подозрительный PPS переводит систему в TIME_SUSPECT/HOLDOVER | time jump/PPS injection |
| Реальное перемещение станции | accelerometer/tamper переводит station position в REVALIDATION_REQUIRED без автоматической смены координат | physical relocation test |
| Утечка местоположения монтажника | phone location используется только по явному выбору, без GMS dependency и без хранения истории перемещений | permission/storage audit |
| Подмена firmware | SHA-256, цифровая подпись product root, anti-rollback | bad hash/signature/downgrade |
| Кирпич при обрыве | A/B slot, resume, trial boot, watchdog rollback | power cut matrix |
| Кража ключей из APK | firmware signing key отсутствует; station key не экспортируется | static analysis и secret scan |
| Утечка в отчёте | redaction ICCID/IMSI/PIN/password/key/QR secret | golden redaction tests |
| Смена радиорегиона | region read-only, signed manufacturing profile | modified app/protocol request |
| Зависимость от облака | offline workflow, local verification | airplane-mode acceptance |
| Supply-chain dependency | version lock, SBOM, vulnerability scan | clean reproducible build |

Приложение не является корнем доверия firmware. Корень доверия находится в bootloader станции и проверяет подпись независимо от результата Android-проверки.

Координаты установки являются критической конфигурацией геометрии сети. Android не имеет права автоматически заменять их текущим GNSS fix после commissioning. Состояние `GNSS spoof not indicated` также не трактуется приложением как абсолютное доказательство отсутствия spoofing; оно показывается как состояние встроенного детектора.

Production APK запрещён до threat-model review, signing ceremony, dependency scan, permission audit, BLE fuzzing, coordinate-write access-control test и проверки утечки данных.
