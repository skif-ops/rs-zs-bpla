# Scope ветки `evt-pre-20`

## Включается

- конфигурационная база предсерийного EVT на 20 изделий;
- исходники и производственные файлы собственных PCB;
- BOM, AVL, закупка в Китае и входной контроль;
- firmware STM32, modem/LoRa/BLE profiles и воспроизводимая сборка;
- крайний совместимый релиз сервера «Мухоед»;
- протоколы GSM/LTE, LoRa, BLE, GNSS/PPS и station-server;
- механика для 3D-печати, вакуумного литья и ТПА;
- производственный маршрут, EOL, паспорта и ПМИ партии;
- отдельный каталог Android-приложения настройки и OTA;
- доказательства двухступенчатой проверки.

## Не включается

- презентация проекта;
- макетная плата 70×90 мм как производственная основа;
- заявления о выполненном аппаратном EVT без первичных данных;
- секретные ключи, PIN-коды SIM, production credentials и закрытые сертификаты;
- бинарники без манифеста версии, исходного commit и SHA-256;
- Gerber без SCH/PCB source, BOM/AVL, ERC/DRC и DFM gate;
- корпусные файлы без чертежа, материала, допуска и обозначения технологии.

## Правила интеграции

- полный или частичный merge, cherry-pick и копирование поставочных материалов между
  `evt-pre-20` и `evt-mb` запрещены;
- техническая идея из другой EVT-линии может быть реализована заново только по общим
  требованиям, без переноса её релизных файлов, отчётов и evidence;
- в `develop` и `main` попадают только отдельно принятые и проверенные общие изменения;
- продвижение изменения в `develop/main` не даёт права переносить содержимое одной
  EVT-линии в другую;
- региональные варианты LoRa различаются BOM/profile/label, но используют общую PCB;
- Android-релиз имеет независимую версию и журнал совместимости с firmware/protocol schema.

## Текущий контрольный срез

- версия ветки: `EVT-PRE-20 Rev.A v0.3` от 14.09.2026;
- `MAIN-AUTH-001…011` закрыты и проходят основной и независимые authority-аудиты;
- все девять native `.kicad_sch/.kicad_pcb/.kicad_pro` файлов PCB-MAIN,
  PCB-MIC и PCB-PWR присутствуют и контролируются CI;
- native-схемы PCB-MAIN и PCB-PWR прошли Review A; PCB-MAIN имеет
  частично разведённый engineering-кандидат, а PCB-PWR — неразведённый
  placement-кандидат с принятым для EVT `DIM-003`: `18/18`, контур 90 x 60 mm,
  четыре круглых NPTH M3 H1-H4 и hash-bound STEP. Серийная механика требует
  повторной проверки. Консервативная 35 µm числовая база разрешает только
  bounded EVT engineering routing candidate; плата пока не разведена и
  производство не разрешено;
- внутренний PCB-PWR stackup/copper-запрос двум фабрикам готов, но все 24 строки
  остаются пустыми (`0/24`), принято `0/2` комплектов, конструкция не выбрана;
- PCB-MAIN placement-кандидат после принятого ограниченного ECO и полного
  репака проходит строгий 2D clearance: 227/227 fitted footprint имеют
  courtyard, component/mounting/U.FL-tool конфликты равны нулю; приняты
  bounded ground-domain, hard-signal, OctoSPI и seven-net RF P0 routing
  subgates (691 segment, 285 via, 3 copper zones, 4 rule areas);
- независимый PCB-MAIN RF/SI return-path review имеет статус
  `ECO_REQUIRED`: cellular L2-return candidate `PCB-MAIN-RF-RETURN-001` не
  применён; commit-bound KiCad 9 comparative DRC в gate `#267` пройден,
  623/623 RF-centreline samples покрыты связной L2-зоной, но независимая
  приёмка ещё не дана; отдельный GNSS proposal
  `PCB-MAIN-GNSS-RF-ECO-001` переставляет только FL1/C64 и прошёл commit-bound
  KiCad 9 comparative DRC в gate `#273`: новых ошибок и unconnected-регрессии
  нет, 406/406 RF-centreline samples покрыты связной L2-зоной; независимая
  приёмка и применение ещё открыты, как и remaining routing, STEP, CAM/DFM и
  Review B;
- повторный PCB-MIC Review A после copper ECO подписан `PASS` по commit `e17a86bc`;
  copper-return subgate Review B принят по commit `7aeec13a`, но panelization,
  DFM, acoustic-stack, physical-EVT, общий Review B и manufacturing release открыты;
- PCB-MIC manufacturing-handoff packet подготовлен; все fabricator/assembler
  response rows остаются `PENDING_EXTERNAL_ACCEPTANCE`;
- производственный BOM, Gerber и статус `FOR_MANUFACTURE` заблокированы;
- firmware имеет статус `TARGET_PORT_REQUIRED`;
- аппаратный EVT имеет статус `NOT RUN`.
