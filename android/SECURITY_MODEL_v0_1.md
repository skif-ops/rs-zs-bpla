# Android commissioning app - security model v0.1

Статус: `DRAFT / SECURITY REVIEW REQUIRED`

| Угроза | Контроль | Проверка |
|---|---|---|
| Подключение к чужой станции | QR-to-BLE identity binding и serial confirmation | подмена advertising и QR |
| Удалённое окно настройки | физическая service button и timeout 10 минут | попытка подключения вне окна |
| Общий заводской пароль | уникальный bootstrap secret на изделие, одноразовое погашение | duplicate/expired secret |
| Перехват BLE | BLE Secure Connections плюс application transcript binding | MITM test |
| Несанкционированная конфигурация | role, authenticated session, schema validation, atomic commit | fuzz и permission test |
| Подмена firmware | SHA-256, цифровая подпись product root, anti-rollback | bad hash/signature/downgrade |
| Кирпич при обрыве | A/B slot, resume, trial boot, watchdog rollback | power cut matrix |
| Кража ключей из APK | firmware signing key отсутствует; station key не экспортируется | static analysis и secret scan |
| Утечка в отчёте | redaction ICCID/IMSI/PIN/password/key/QR secret | golden redaction tests |
| Смена радиорегиона | region read-only, signed manufacturing profile | modified app/protocol request |
| Зависимость от облака | offline workflow, local verification | airplane-mode acceptance |
| Supply-chain dependency | version lock, SBOM, vulnerability scan | clean reproducible build |

Приложение не является корнем доверия firmware. Корень доверия находится в bootloader станции и проверяет подпись независимо от результата Android-проверки.

Production APK запрещён до threat-model review, signing ceremony, dependency scan, permission audit, BLE fuzzing и проверки утечки данных.

