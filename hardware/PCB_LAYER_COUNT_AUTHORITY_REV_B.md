# Дионея EVT-PRE-20 Rev.B — authority числа медных слоёв

Статус: `CONTROLLED LAYER COUNT / PCB-MAIN 8L ACCEPTED / NOT FOR MANUFACTURE`

Дата: 2026-10-16

| Плата | Число слоёв | Толщина | Основной базис |
|---|---:|---:|---|
| PCB-MAIN | 8 | 1,6 мм | COMPLETE-105 Rev.B; JLC08161H-3313 preferred order stack |
| PCB-PWR | 4 | 1,6 мм | Rev.A authority без изменения |
| PCB-MIC | 2 | 1,0 мм | Rev.A authority без изменения |

Машинный источник: `hardware/PCB_LAYER_COUNT_AUTHORITY_REV_B.csv`.

PCB-MAIN: `F.Cu`, `In1.Cu`…`In6.Cu`, `B.Cu`, ENIG, наружная медь 1 oz,
внутренняя 0,5 oz. Основной KiCad-источник находится в
`hardware/kicad/native/PCB-MAIN`. Предыдущая 6L-версия сохранена в
`hardware/kicad/retired/PCB-MAIN-6L-REV-A-2026-10-16` и снята с действия.

Принятие 8L не является разрешением производства. До заказа остаются
обязательными checkout DFM, фиксация выбранного стека и диэлектриков,
проверка импеданса/return path, POFV, Review B и first article.
