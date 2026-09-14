# Реестр выпусков ветки `evt-pre-20`

## Текущий инженерный baseline

- конфигурация: `EVT-PRE-20 Rev.A v0.3`;
- дата среза: 14.09.2026;
- источник синхронизированных authority: `f3411e51938aa1423fdbaeeef9585aeea385c239`;
- `MAIN-AUTH-001…011`: `CLOSED / VERIFIED`;
- native-схемы PCB-MAIN и PCB-PWR, а также их KiCad 9 ERC: `PASS / REVIEW A`;
- PCB-MAIN и PCB-PWR routing, Review B и manufacturing release: `OPEN / BLOCKED`;
- повторный PCB-MIC Review A: `PASS`; copper-return subgate Review B: `ACCEPTED`;
- оставшиеся PCB-MIC panelization/DFM/acoustic/physical-EVT gates: `OPEN`;
- аппаратный EVT: `NOT RUN`;
- общий статус: `OPEN / NOT FOR MANUFACTURE`.

Производственный архив EVT-PRE-20 пока не выпущен. Унаследованный полный EVT v0.7
остаётся справочным источником методик и не является комплектом производства партии из
20 станций. Generated BOM, candidate PCB-MIC CAM и audit-отчёты создаются
воспроизводимо в CI и не получают статус производственного выпуска, пока QG-2 и
оставшиеся Review-B gates остаются `BLOCKED/OPEN`.
