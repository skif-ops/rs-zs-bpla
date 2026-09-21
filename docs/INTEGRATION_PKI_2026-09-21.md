# Поставка: PKI сервера «Мухоед» и реестр станций (v0.1, 2026-09-21)

Ветка `feature/station-config-pki`. Все файлы новые, существующие файлы не менялись:
- server/pki/__init__.py, __main__.py, ca.py, registry.py, mosquitto.py, cli.py
- server/pki/offline_tool.py, pyinstaller_muhoed_pki.spec, pyinstaller_root_offline.spec, build_windows.ps1
- server/tests/test_pki.py
- server/requirements-pki.txt (единственная новая зависимость: cryptography>=42; добавить строку в requirements.txt при следующем обновлении lock-файла)
- .github/workflows/pki-windows-exe.yml (сборка muhoed-pki.exe и dioneya-root-offline.exe под x64/arm64) - добавляется отдельным коммитом, так как требует права Workflows у интеграции

Проверено локально: `pytest tests/test_pki.py` 12/12 PASS, полный набор сервера с новым модулем 180/180 PASS; спеки PyInstaller проверены сборкой и запуском Linux-бинарников, Windows-сборку выполняет workflow или `pki\\build_windows.ps1`.

Схема: корневой CA офлайн (ключ зашифрован, на сервере только сертификат) -> промежуточный CA на сервере -> сертификат сервера с SAN, клиентский сертификат моста (CN=bridge), сертификаты станций по CSR (CN = серийный номер, OU = лот). Реестр SQLite на 41 единицу: лоты EVT-LOT-1 (001-020), EVT-LOT-2 (021-040), BENCH (B01, station_id 901); tenant по лоту pilot1 / pilot2 / bench. ACL и конфигурация mosquitto генерируются из реестра.

Подробная процедура - документ «Инструкция_PKI_ключи_и_сертификаты» (вне репозитория, пакет поставки 2026-09-21).

Что потребуется поменять в существующих файлах (отдельная серия после согласования):
- android/.../StationModels.kt: регулярное выражение серийного номера сейчас допускает только 001-020; для второй группы и стенда нужен диапазон 001-040 и B01;
- deploy/mosquitto/*.conf: заменить статический ACL и `allow_anonymous true` на сгенерированные файлы;
- server/.env.example: ZS_MQTT_CA -> ca-chain.pem, ZS_MQTT_CERT/KEY -> bridge.crt.pem / bridge.key.pem;
- manufacturing/LOT_SERIAL_REGISTER.csv: добавить DIO-EVT-021…040 и DIO-EVT-B01;
- protocols/MQTT_TLS_ICD_v0_1.md: зафиксировать tenant по лотам и CN = serial.
