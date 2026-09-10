# EVT-PRE-20 - состав PCB и правила выпуска

Статус: `DRAFT / OPEN / NOT RUN`

## PCB-MAIN

- Количество на изделие: 1.
- Целевая технология: 4 слоя, FR-4, 1.6 мм, ENIG, controlled impedance для RF/USB при наличии.
- Целевая зона: ориентировочно до 100 x 80 мм, окончательно после компоновки корпуса.
- Разделение зон: RF cellular, RF GNSS, RF LoRa, quiet digital/audio, modem power, service/debug.
- Антенны внешние, отдельные разъёмы cellular/GNSS/LoRa. Межпортовая развязка проверяется на макете корпуса.
- Обязательные интерфейсы: SWD, USB-C service, два nano-SIM через 2:1 mux, microSD, battery/power, 4 x MIC, cellular antenna, GNSS antenna, LoRa antenna, tamper/service.
- Dual SIM работает только в режиме Single Standby. Оба слота и мультиплексор входят в STEP, schematic, BOM, DFT и EOL coverage.

## PCB-MIC x4

- Количество на изделие: 4 одинаковые платы.
- Технология Rev.A: 2 слоя, FR-4, 1.0 мм, ENIG.
- Габарит Rev.A: 24.0 x 22.0 мм.
- Один T5838 на плату, нижний акустический порт, локальная развязка питания.
- Акустический PCB-порт: NPTH 0.8 мм в X=12.0 мм, Y=16.65 мм.
- Монтаж: H1/H2, два NPTH 2.2 мм под M2, X=4.0 и 20.0 мм, Y=16.65 мм.
- Разъём Rev.A: Molex Pico-Lock 5040500691, 6 контактов: 1.8 V, GND, PDM_CLK, PDM_DATA, MIC_WAKE, AAD_CFG/THSEL.
- Не допускаются разные MPN микрофонов внутри одной станции.
- Платы и жгуты маркируются MIC1...MIC4, но PCB остаётся единой ревизии.
- Оснастка фиксирует треугольник 120 мм и MIC4 +150 мм над центром.
- Авторитетный mechanical freeze: `hardware/kicad/REV_A_CAPTURE_ADDENDUM_003_PCB_MIC_MECH.md`.

## PCB-PWR

- Количество на изделие: 1.
- Технология: 2 слоя, медь 2 oz ориентировочно, толщина и полигоны подтверждаются расчётом.
- Вход только от защищённой батарейной шины после внешнего MPPT/BMS.
- Функции: предохранитель, reverse protection, TVS, current/voltage monitor, load disconnect, 3.8 V modem rail, 3.3 V digital rail, 1.8 V microphone rail.
- Силовые разъёмы должны исключать переполюсовку и иметь запас по току/температуре.

## Закупочное количество

| Объект | На изделие | 20 изделий | Запас | К заказу |
|---|---:|---:|---:|---:|
| PCB-MAIN bare | 1 | 20 | 5 | 25 |
| PCB-MAIN assembled | 1 | 20 | 2 | 22 |
| PCB-MIC bare | 4 | 80 | 20 | 100 |
| PCB-MIC assembled | 4 | 80 | 8 | 88 |
| PCB-PWR bare | 1 | 20 | 5 | 25 |
| PCB-PWR assembled | 1 | 20 | 2 | 22 |

Запасные голые платы не заменяют запас компонентов. Критические IC закупаются с отдельным запасом и из одной подтверждаемой партии, где это влияет на согласование каналов.

## Производственный release gate

Каждая плата должна иметь исходники KiCad, PDF схемы, Gerber, drill, IPC-356, pick-and-place, BOM/AVL, assembly drawing TOP/BOTTOM, fabrication notes, 3D STEP, ERC/DRC отчёты и письменный DFM review фабрики. Gerber сверяется отдельным CAM viewer со схемой и исходной PCB.
