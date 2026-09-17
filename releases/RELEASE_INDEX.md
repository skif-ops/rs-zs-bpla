# Интеграционный реестр актуальных материалов

Версия контрольного среза: `DIONEA-INTEGRATION-v0.14`.
Дата: 17.09.2026.
Статус: `OPEN / NOT FOR MANUFACTURE`.

Описание интеграционного среза: [`releases/integration/v0.14/README.md`](integration/v0.14/README.md).

`main` и `develop` содержат согласованный интеграционный срез. Поставочные материалы
`evt-mb` и `evt-pre-20` сохраняются в раздельных пространствах и не являются взаимозаменяемыми.

## Выпущенные и контрольные комплекты

| Линия | Комплект | SHA-256 | Статус |
|---|---|---|---|
| Полный EVT | `РС_ЗС-БПЛА_EVT_gate_3plus1_v0_7.zip` | `37eaee4e85e8f12f26da3fbd3a7c40d4cda19c9192dca2e5bb30963435747e6c` | OPEN |
| EVT-MB | `РС_Дионея_EVT_MB_v1_3_ПОЛНЫЙ_КОМПЛЕКТ_OPEN.zip` | `df7275e4915da534fee284e78c6eef6419b1672223d2c823707140cee6dfb446` | OPEN |
| EVT-MB | `РС_Дионея_EVT_MB_v1_3_ПМИ_И_ОТЧЕТНЫЕ_МАТЕРИАЛЫ_OPEN.zip` | `0e997293fdceb396dfc5c8fb9b0e482bbb413d6af4fd47e00cfb42090e3f5ecb` | OPEN |
| Презентация | `Дионея_презентация_проекта_v0_3.pptx` | `3ea0a8ba33eaf17208678dfb94ae4d975d44d4b129452b48a7bdacb0eda19c38` | RELEASED |
| Аудиопроверка | `Результаты_прогона_звуков_Мухоед_2026-09-07.zip` | `84b9ad6cead103ce19abc94ca49f222ac863133113549e228708a70ab1364466` | 3/3 TRUE_POSITIVE; диагностический прогон |

## Текущий инженерный baseline EVT-PRE-20

- исходная ветка: `evt-pre-20`;
- зафиксированный SHA: `7ed5b021b1e7eddfda616b54fbc79e1bf0221702`;
- аппаратная конфигурация: `EVT-PRE-20 Rev.A`, 20 станций, собственные PCB;
- `PCB-MAIN`: десятистраничная hierarchy и pad/net equivalence приняты только как `ACCEPT_HIERARCHY_ONLY`; routing и Review B открыты;
- `PCB-PWR`: F1 `0451008.MRL` применён bounded value-only ECO; commit-bound KiCad 9 ERC/PDF evidence прошли, независимый post-ECO hierarchy review открыт, qualification 1/20;
- `PCB-MIC`: copper-return subgate принят, но общий Review B и manufacturing handoff открыты;
- контролируемый BOM: 295 engineering-строк и 124 procurement-строки; QG-1 `PASS`, QG-2 `BLOCKED`;
- системные кандидаты: RB40, SLP080S-12M, SCC075010060R, SBS050150200,
  Taoglas G30.B.108111, AA.166.A.301111, TI.89.B.2111W и `CAB.0243`;
- производственный BOM, routing, Gerber/CAM/DFM и выпуск в изготовление заблокированы;
- аппаратный EVT: `NOT RUN`.

Инженерные пакеты EVT-PRE-20 формируются CI как воспроизводимые артефакты. Они не
получают статус производственного выпуска до завершения обоих контролей и закрытия
аппаратных evidence.

## Правило применения

Перед использованием архива восстановить его штатным `reassemble.sh` или
`reassemble.ps1`, проверить SHA-256 и выполнить входной gate соответствующей линии.
