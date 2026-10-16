# Реестр выпусков ветки `evt-pre-20`

## Текущий инженерный baseline

- конфигурация: `EVT-PRE-20 Rev.A v0.3`;
- дата среза: 14.09.2026;
- источник синхронизированных authority: `f3411e51938aa1423fdbaeeef9585aeea385c239`;
- `MAIN-AUTH-001…011`: `CLOSED / VERIFIED`;
- native-схемы PCB-MAIN и PCB-PWR, а также их KiCad 9 ERC: `PASS / REVIEW A`;
- PCB-MAIN и PCB-PWR routing, Review B и manufacturing release: `OPEN / BLOCKED`;
- повторный PCB-MIC Review A: `PASS`; copper-return subgate Review B: `ACCEPTED`;
- PCB-MIC manufacturing handoff: `PACKET READY / EXTERNAL DFM ACCEPTANCE PENDING`;
- оставшиеся PCB-MIC panelization/DFM/acoustic/physical-EVT gates: `OPEN`;
- аппаратный EVT: `NOT RUN`;
- общий статус: `OPEN / NOT FOR MANUFACTURE`.

До REV_D7 производственный архив EVT-PRE-20 не был выпущен. Унаследованный
полный EVT v0.7 остаётся справочным источником методик и не является комплектом
производства партии из 20 станций. REV_D7 ниже фиксирует документальную выдачу;
физические Review-B, first article, EOL и EVT остаются отдельными фактическими gates.

## EVT-PRE-20 REV_D7 — 2026-10-16

- Полный производственный комплект: `releases/EVT_PRE_20_REV_D7/Архивы/EVT_PRE_20_REV_D7_FULL.zip`.
- Фабричный комплект плат: `releases/EVT_PRE_20_REV_D7/Архивы/EVT_PRE_20_REV_D7_ALTIUM.zip`.
- Программа, методики, отчёты и Мухоед: `releases/EVT_PRE_20_REV_D7/Архивы/EVT_PRE_20_REV_D7_TESTS.zip`.
- PCB-MAIN Rev.B — 8 слоёв; PCB-PWR — 4; PCB-MIC — 2. Платы выдаются в Altium; KiCad в основном и фабричном архивах отсутствует.
- Документальный пакет готов; physical first article/EOL/EVT остаются NOT RUN до фактического изготовления.

\n