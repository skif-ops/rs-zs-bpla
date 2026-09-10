# Реестр выпусков ветки `evt-pre-20`

## Текущий инженерный baseline

- конфигурация: `EVT-PRE-20 Rev.A v0.2`;
- дата среза: 10.09.2026;
- источник синхронизированных authority: `f3411e51938aa1423fdbaeeef9585aeea385c239`;
- `MAIN-AUTH-001…011`: `CLOSED / VERIFIED`;
- native PCB-MAIN schematic и KiCad 9 ERC: `PASS / REVIEW INPUT`;
- human Review A, PCB-MAIN layout, Review B и производственный BOM: `BLOCKED`;
- аппаратный EVT: `NOT RUN`;
- общий статус: `OPEN / NOT FOR MANUFACTURE`.

Производственный архив EVT-PRE-20 пока не выпущен. Унаследованный полный EVT v0.7
остаётся справочным источником методик и не является комплектом производства партии из
20 станций. Generated BOM и audit-отчёты создаются воспроизводимо в CI и не получают
статус производственного выпуска, пока QG-2 остаётся `BLOCKED`.
