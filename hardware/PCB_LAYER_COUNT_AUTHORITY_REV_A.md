# Дионея EVT-PRE-20 Rev.A — authority числа медных слоёв

Статус: `CONTROLLED LAYER COUNT / EVT STACKUPS ACCEPTED / NOT FOR MANUFACTURE`

Дата: 2026-09-15

## Решение Rev.A

| Плата | Число слоёв | Толщина платы | Состояние |
|---|---:|---:|---|
| PCB-MAIN | 6 | заказ 1,6 мм; public stack 1,54 мм ±10% | `JLC06161H-3313` принят для EVT; routing/DRC/CAM/Review B открыты |
| PCB-PWR | 4 | 1,60 мм ±10%, EVT-only | `JLC04161H-3313A`, 70/35 мкм и расчётная геометрия приняты; thermal/Review B открыты |
| PCB-MIC | 2 | 1,0 мм ±10% | стандартный FR-4/1 oz/ENIG принят; Review B и first-panel inspection открыты |

Машинным источником является `hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv`.
Он заменяет прежние конфликтующие упоминания четырёх слоёв для PCB-MAIN и двух
слоёв для PCB-PWR.

## Граница решения

Принятые stackup разрешают трассировку, но не производство. Для PCB-MAIN
зафиксированы геометрии 50 Ом/90 Ом и `±10%`; для PCB-PWR — 2 oz/1 oz,
минимальное plating и расчётная токовая геометрия. Ответы конкретных фабрик не
нужны для EVT; checkout DFM, native DRC, CAM и Review B остаются стоп-гейтами.

Четырёхслойная PCB-PWR выбрана для непрерывных возвратных плоскостей и отвода
тепла от двух LMR60440. Это соответствует рекомендации TI использовать несколько
медных слоёв и тепловые переходы к внутренним земляным слоям; окончательная
реализация проверяется расчётом и DFM выбранной фабрики:
`https://www.ti.com/lit/ds/symlink/lmr60440-q1.pdf`.

## Межблокировки выпуска

- PCB-MAIN: routing, RF/SI, DRC, STEP, CAM/checkout DFM и Review B.
- PCB-PWR: силовая/Kelvin/thermal routing, проверка drop/температуры/аварий,
  DRC, STEP, CAM/checkout DFM и Review B.
- PCB-MIC: first-panel acoustic inspection, panelization/depanel, CAM и Review B.

Ни одна строка этого authority не является разрешением на Gerber или заказ плат.
