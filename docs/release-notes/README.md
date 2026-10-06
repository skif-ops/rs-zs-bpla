# Журналы выпусков ПО «Дионея»

Этот каталог задаёт единый порядок ведения release notes для сервера «Мухоед» и прошивок станции EVT-PRE-20.

## Основные журналы

- [`server/RELEASE_NOTES.md`](../../server/RELEASE_NOTES.md) — сервер, интерфейс оператора, API, развёртывание и серверная часть обновления станций.
- [`firmware/RELEASE_NOTES.md`](../../firmware/RELEASE_NOTES.md) — совместный выпуск STM32U585 и nRF52840.
- [`RELEASE_INDEX.json`](RELEASE_INDEX.json) — машинно-читаемый указатель текущих выпусков и развёрнутых сборок.
- [`DEPLOYMENT_STATUS.md`](DEPLOYMENT_STATUS.md) — состояние production и bench.

Ранее выпущенные подробные заметки сервера сохранены как первичные источники:

- [`server/RELEASE_NOTES_v0_8_1.md`](../../server/RELEASE_NOTES_v0_8_1.md);
- [`server/RELEASE_NOTES_v0_9_evt_rc1.md`](../../server/RELEASE_NOTES_v0_9_evt_rc1.md);
- [`server/RELEASE_NOTES_EVT_PRE_20_0_1.md`](../../server/RELEASE_NOTES_EVT_PRE_20_0_1.md).

## Обязательный порядок

1. Любое изменение поведения, протокола, безопасности, сборки, конфигурации или развёртывания сервера добавляется в раздел `Unreleased` файла `server/RELEASE_NOTES.md`.
2. Любое изменение STM32, nRF52840, загрузчика, option bytes, формата образа, процедуры прошивки или аппаратного контракта добавляется в раздел `Unreleased` файла `firmware/RELEASE_NOTES.md`.
3. При выпуске записи из `Unreleased` переносятся в раздел с точной версией и датой. Для выпуска указываются исходный commit, хеши артефактов, совместимость, миграции, испытания, известные ограничения и порядок отката.
4. `RELEASE_INDEX.json` обновляется в том же commit. После фактического развёртывания обновляется `DEPLOYMENT_STATUS.md` и поле `deployments` в индексе.
5. Локальная рабочая копия считается синхронизированной только когда commit с журналами отправлен в Git и локальный `HEAD` совпадает с удалённой веткой.
6. Закрытые ключи, пароли, pairing secret, station private key и Android keystore в журналы и репозиторий не помещаются.

## Проверка

```powershell
python tools/check_release_notes.py --validate-only
```

Для проверки конкретного изменения относительно базового commit:

```powershell
python tools/check_release_notes.py --base <BASE_SHA> --head HEAD
```

Отдельная GitHub Actions проверка не допускает изменение `server/` или `firmware/` без синхронного обновления соответствующего журнала.
