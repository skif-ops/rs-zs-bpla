# Регламент развёртывания резервного копирования и эксплуатации сервера Мухоед EVT PRE 20

Ревизия A. Дата 16 октября 2026 года. Проект Дионея.

RU: Документ задаёт операторский порядок подготовки, запуска, проверки, резервного копирования, восстановления и обновления сервера Мухоед для EVT PRE 20. Закрытые ключи, пароли и токены в комплект не включаются.

EN: This document defines the operator procedure for preparation, startup, verification, backup, restore and update of the Muhoed server for EVT PRE 20. Private keys, passwords and tokens are excluded from the package.

## 1 Статус

RU: Исходный код, lock files, контейнерные конфигурации и scripts входят в отдельный архив испытаний и дообучения Мухоеда. Production deployment требует отдельного защищённого хоста, действующих TLS и PKI материалов, DNS, reverse proxy и operator accounts.

EN: Source code, lock files, container definitions and scripts are included in the separate test and Muhoed-training archive. Production deployment requires a dedicated protected host, active TLS and PKI material, DNS, a reverse proxy and operator accounts.

## 2 Подготовка

1. RU: Зафиксировать Git commit, release ID, operating system, container runtime и ответственного администратора. EN: Record the Git commit, release ID, operating system, container runtime and responsible administrator.
2. RU: Проверить свободное место, UTC, DNS dioneya.ru, ports 443 и 8883 и исходящие соединения. EN: Check free space, UTC, DNS for dioneya.ru, ports 443 and 8883 and outbound connectivity.
3. RU: Установить packages только из requirements lock с проверкой hashes. EN: Install packages only from the locked requirements with hash verification.
4. RU: Разместить secrets вне Git с правами только deployment account. EN: Store secrets outside Git with access limited to the deployment account.
5. RU: Development compose с insecure bench flags запрещён в production. EN: Development compose files with insecure bench flags are prohibited in production.

## 3 Запуск и проверка

RU: На Ubuntu использовать штатные start and check scripts. На Windows использовать соответствующие PowerShell scripts. EN: Use the released start and check scripts on Ubuntu and the matching PowerShell scripts on Windows.

    deploy/scripts/start_ubuntu.sh
    deploy/scripts/check_ubuntu.sh
    deploy/scripts/start_windows.ps1
    deploy/scripts/check_windows.ps1

RU: После запуска проверить health endpoint, build identity, database, MQTT TLS, CRL validity, bridge connection, operator login, station status page and audit. EN: After startup verify the health endpoint, build identity, database, MQTT TLS, CRL validity, bridge connection, operator login, station-status page and audit.

## 4 TLS PKI и ACL

1. RU: Серверный сертификат должен содержать публичное имя и compose service name mqtt. EN: The server certificate must contain the public name and the compose service name mqtt.
2. RU: Mosquitto принимает station clients только по mutual TLS 1.2 or newer. EN: Mosquitto accepts station clients only through mutual TLS 1.2 or newer.
3. RU: После issue or revoke повторно выпустить CRL и ACL и перезапустить broker по change record. EN: After any issue or revoke regenerate the CRL and ACL and restart the broker under a change record.
4. RU: CRL действует 30 дней. Настроить weekly refresh and alert before expiry. EN: The CRL is valid for thirty days. Configure weekly refresh and an alert before expiry.
5. RU: Выпуск station and consumer certificates выполняется по отдельному регламенту PKI. EN: Station and consumer certificates are issued under the separate PKI lifecycle instruction.

## 5 Учётные записи операторов

RU: До публикации сервера войти локально как skif root, сменить initial password и подключить TOTP. Создать named accounts с минимальными roles and scopes. Общие учётные записи не использовать.

EN: Before exposing the server, log in locally as skif root, replace the initial password and enroll TOTP. Create named accounts with minimum roles and scopes. Do not use shared accounts.

RU: Viewer reads data, operator also handles audio and analyses, engineer changes datasets and sends station commands, admin manages accounts and audit. Session and token scopes must not exceed the assigned role.

EN: Viewer reads data, operator also handles audio and analyses, engineer changes datasets and sends station commands, and admin manages accounts and audit. Session and token scopes must not exceed the assigned role.

## 6 Мониторинг

1. RU: Проверять health, database size, audio size, free disk, last cleanup and build identity. EN: Monitor health, database size, audio size, free disk, last cleanup and build identity.
2. RU: Контролировать late, lost, never, battery low, GNSS, time trust and firmware version. EN: Monitor late, lost, never, battery low, GNSS, time trust and firmware version.
3. RU: Проверять целостность audit chain. EN: Verify audit-chain integrity.
4. RU: Отдельно контролировать срок CRL, server certificate and issuing certificate. EN: Monitor CRL, server-certificate and issuing-certificate expiry separately.
5. RU: Bench services and data must remain isolated from pilot data and production backups. EN: Bench services and data must remain isolated from pilot data and production backups.

## 7 Резервное копирование

RU: Backup содержит consistent SQLite copies, configuration, PKI registry, operator state, audit, release identity and required evidence. Live SQLite files with WAL нельзя архивировать обычным файловым копированием.

EN: The backup contains consistent SQLite copies, configuration, the PKI registry, operator state, audit, release identity and required evidence. Do not archive live SQLite files with WAL by ordinary file copy.

    deploy/scripts/backup_ubuntu.sh <ARCHIVE>
    deploy/scripts/backup_windows.ps1 -Destination <PATH>

RU: Для каждого backup сохранить SHA-256, UTC, release, host, operator and restore-test result. Хранить минимум две зашифрованные копии на разных носителях. EN: For each backup retain SHA-256, UTC, release, host, operator and restore-test result. Keep at least two encrypted copies on separate media.

## 8 Восстановление

1. RU: Изолировать целевой host и проверить hash архива. EN: Isolate the target host and verify the archive hash.
2. RU: Выполнить штатный restore. Scripts останавливают services, проверяют архив, сохраняют before restore backup и запускают services. EN: Run the released restore script. The scripts stop services, validate the archive, preserve a before-restore backup and restart services.

    deploy/scripts/restore_ubuntu.sh <ARCHIVE>
    deploy/scripts/restore_windows.ps1 -Archive <ARCHIVE>

3. RU: Проверить database integrity, health, operator login, audit, PKI list, CRL, ACL, MQTT TLS, one bench heartbeat and one test alert. EN: Verify database integrity, health, operator login, audit, PKI list, CRL, ACL, MQTT TLS, one bench heartbeat and one test alert.
4. RU: До полного PASS не подключать pilot stations. EN: Do not reconnect pilot stations until all checks pass.

## 9 Обновление

RU: Собрать server package из зафиксированного commit, проверить BUILD ID, SBOM, requirements lock and tests. Создать backup. Обновить один bench environment, выполнить smoke and regression, затем production. При ошибке выполнить rollback к previous image and data backup.

EN: Build the server package from the fixed commit and verify BUILD ID, SBOM, the requirements lock and tests. Create a backup. Update one bench environment, run smoke and regression tests, and then update production. On failure roll back to the previous image and data backup.

## 10 Аварийные случаи

| Событие Event | Действие Action | Gate |
|---|---|---|
| Истекает CRL CRL near expiry | Выпустить CRL, проверить и reload broker | STOP new deployment until PASS |
| Нарушена audit chain Audit chain failure | Freeze changes, copy evidence, investigate | Security HOLD |
| Недостаточно места Low disk | Stop ingest if required, backup, expand storage, verify retention | HOLD |
| Повреждена база Database corruption | Restore verified backup and run integrity check | HOLD until full check |
| Скомпрометирован operator account | Disable sessions tokens, reset password TOTP, review audit | Security incident |
| Не совпадает BUILD ID Build ID mismatch | Stop rollout and reinstall fixed release | FAIL |

## 11 Передача и завершение

RU: Передача включает release manifest, health export, account and scope register without secrets, PKI fingerprints, backup hash, restore-test record, monitoring thresholds and signed change record. Production operation начинается только после независимой проверки.

EN: The handoff includes the release manifest, health export, account and scope register without secrets, PKI fingerprints, backup hash, restore-test record, monitoring thresholds and signed change record. Production operation starts only after independent review.
