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

## EVT-PRE-20 REV_D8 - 2026-10-16

- Полный комплект закупки, производства, сборки и программного кандидата: `releases/EVT_PRE_20_REV_D8/Архивы/EVT_PRE_20_REV_D8_FULL.zip`.
- Фабричный комплект Altium/CAM для PCB/PCBA: `releases/EVT_PRE_20_REV_D8/Архивы/EVT_PRE_20_REV_D8_ALTIUM.zip`.
- Программа, методики, отчётные формы и пакет Мухоеда: `releases/EVT_PRE_20_REV_D8/Архивы/EVT_PRE_20_REV_D8_TESTS.zip`.
- Программа EVT: две группы по 20 станций и одна стендовая, 41 серийный номер `DIO-EVT-001...040` и `DIO-EVT-B01`.
- Варианты закупки: 21 станция как первая фаза и 41 станция как полная программа. Варианты не суммируются.
- PCB-MAIN - 8 слоёв; PCB-PWR - 4; PCB-MIC - 2. Основной и фабричный архивы не содержат KiCad.
- Подписанный software release candidate: `2026101601`; firmware lock запрещён до закрытия аппаратной квалификации.
- Число 21 в форме MFG-004 означает количество открытых EOL-критериев, а не количество станций.
- CRC, полная распаковка, отсутствие закрытых ключей и отсутствие KiCad в FULL/ALTIUM: `PASS`.
- Физические first article, числовые EOL-пределы и EVT остаются `NOT RUN / OPEN` до измерений собранных станций.

SHA-256:

- FULL: `A215CC4D579A7E856E651AB0C2C578E03A64525330F1F4CFA34E9BDB9E678423`
- ALTIUM: `FDF68CF277E36D0943473FDA077C372D0307CA9A0ADED400F6259486347F7C2D`
- TESTS: `3B20614280335E1DFB406210BD5137C32AEA7AAF08675B8106661B01A6CE0BB5`
