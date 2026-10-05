# Реестр выпусков ветки `evt-pre-20`

## Текущий инженерный baseline

- конфигурация: `EVT-PRE-20 Rev.A v0.3`;
- дата среза: 14.09.2026;
- источник синхронизированных authority: `f3411e51938aa1423fdbaeeef9585aeea385c239`;
- `MAIN-AUTH-001…011`: `CLOSED / VERIFIED`;
- native-схемы PCB-MAIN и PCB-PWR, а также их KiCad 9 ERC: `PASS / REVIEW A`;
- procurement handoff заказчику: `SENT / EVT-PRE-20 Rev_D / FULL PROGRAM 2x20+1`;
- заказ размещается целиком, без паузы после первых изделий;
- PCB-MAIN и PCB-PWR routing, Review B и manufacturing-release evidence: `OPEN FOLLOW-UP / ECO AFTER FACTORY FEEDBACK`;
- повторный PCB-MIC Review A: `PASS`; copper-return subgate Review B: `ACCEPTED`;
- PCB-MIC manufacturing handoff: `PACKET READY / EXTERNAL DFM ACCEPTANCE PENDING`;
- оставшиеся PCB-MIC panelization/DFM/acoustic/physical-EVT gates: `OPEN`;
- аппаратный EVT: `NOT RUN`;
- прошивка STM32U585: `ENGINEERING ARM BUILD PASS / UNSIGNED / HARDWARE VALIDATION PENDING`;
- приложение монтажника: `UNIT TESTS AND DEBUG APK BUILD PASS / RELEASE SIGNING AND STATION GATT VALIDATION PENDING`;
- общий статус: `CUSTOMER PROCUREMENT HANDOFF SENT / TECHNICAL FOLLOW-UP OPEN`.

Производственный пакет EVT-PRE-20 Rev_D передан заказчику для закупки. Формальные
engineering-release хвосты больше не трактуются как стоп закупки; они ведутся как
follow-up/ECO после DFM, stackup, via, assembly и housing feedback фабрики. Унаследованный
полный EVT v0.7 остаётся справочным источником методик.
