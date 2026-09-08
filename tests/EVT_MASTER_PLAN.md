# EVT master plan - партия 20 изделий

Статус: `DRAFT / NOT RUN`

## Цель

Подтвердить предсерийную конфигурацию `EVT-PRE-20` на фактически собранных изделиях. EVT не заменяет 100% EOL. Серверный replay, host build и тест макета EVT-MB не являются hardware evidence этой партии.

## Популяция

- все 20 изделий: идентификация, визуальный контроль, EOL, питание S0-S4, четыре аудиоканала, GNSS/PPS, BLE, LTE attach/TLS/store-and-forward и базовый LoRa test;
- все 20 изделий испытываются с заблокированным профилем RU868; EU868 в пилот не прошивается и остаётся будущим TX-disabled шаблоном;
- корпусные технологии имеют раздельные отчёты и не объединяются в один PASS;
- разрушительные и длительные тесты назначаются после freeze корпуса и customer usage profile;
- образец, использованный в разрушительном тесте, не возвращается в обычный полевой пул без disposition.

## Последовательность

1. Freeze requirements, schematic, PCB, BOM/AVL, firmware, protocols, mechanics and test limits.
2. QG-1 complete release bundle and independent hash verification.
3. Incoming inspection and build of golden/instrumented units.
4. Fixture MSA and pilot build review.
5. Build remaining units with 100% traveller and EOL.
6. Baseline functional EVT for all 20.
7. Environmental, ingress, RF, energy and field tests by approved allocation.
8. Repeat critical functional checks after every stress.
9. Close deviations, publish raw evidence manifest and review configuration consistency.

## Решения о результате

- `PASS`: все P0 requirements verified, no open blocker/critical deviation, primary evidence available and hashes match.
- `CONDITIONAL`: only customer-accepted non-safety deviations with owner and closure date.
- `FAIL`: any safety, power, sealing, secure update, identity, protocol integrity or required performance criterion fails.
- `NOT RUN`: no primary evidence or test not started.

## Открытые входы

Exact site, public APN and RAT values for the selected SIMs, station deployment spacing, acoustic target set and negative set, environmental ranges, mast/wind conditions, transport route and acceptance thresholds must be frozen before QG-2. Tariff is not an EVT input. RU868 and the primary allocation of 20 vacuum-cast housings are locked; full-lot 3D printing is the controlled fallback and injection molding is source-data-only for the pilot.
