# Дионея EVT-PRE-20 - аппаратная архитектура v0.1

Статус: `DRAFT / OPEN / NOT RUN`  
Дата базы: 2026-09-08  
Партия: 20 предсерийных изделий `DIO-EVT-001` ... `DIO-EVT-020`

Документ фиксирует архитектурную основу для разработки КД. Он не является разрешением на производство: электрическая схема, PCB, ERC/DRC/DFM и образцы компонентов ещё не прошли gate.

## 1. Принятые решения

| Узел | Решение | Статус |
|---|---|---|
| Центральный MCU | STM32U585VIT6Q, LQFP100 | SELECTED_PENDING_SCHEMATIC_AND_SAMPLE |
| Акустика | 4 x T5838, один MPN и предпочтительно одна производственная партия | SELECTED_PENDING_SAMPLE |
| Геометрия | 3 нижних микрофона, равносторонний треугольник 120 мм; MIC4 над центром +150 мм | LOCKED |
| Cellular | BG95-класс, Cat M1/NB2/EGPRS, два nano-SIM через внешний 2:1 mux, исходящее MQTT/TLS или HTTPS | SELECTED_PENDING_OPERATOR_AND_DUAL_SIM_TEST |
| GNSS/PPS | отдельный MAX-M10S-класс | SELECTED_PENDING_SAMPLE |
| LoRa | E22-900M22S/SX1262-класс, RU868 на всех 20 пилотных изделиях; окна 864-865 и 868.7-869.2 МГц | SELECTED_PENDING_RF_AND_REGULATORY_TEST |
| BLE | отдельный BLE-сервисный модуль, кандидат ESP32-C3-MINI-1-N4 | CANDIDATE_PENDING_SAMPLE |
| Локальное хранилище | QSPI NOR не менее 64 MB плюс industrial microSD для EVT-данных | SELECTED_PENDING_MEDIA_TEST |
| Питание | 12.8 V LiFePO4 40-60 Ah, панель 60-80 W | LOCKED |
| Заряд | внешний MPPT 10 A для LiFePO4 плюс собственная защищённая interface PCB | RFQ_REQUIRED |
| Корпуса | 20 изделий вакуумного литья; резерв всей партии через 3D-печать; отдельные исходные данные для всех трёх процессов, включая ТПА без пилотной оснастки | LOCKED |

## 2. Комплект плат одного изделия

1. `PCB-MAIN` - основная контроллерная плата: MCU, cellular, отдельный GNSS/PPS, LoRa, BLE, QSPI, microSD, датчики и сервисные интерфейсы.
2. `PCB-MIC` x4 - четыре одинаковые микрофонные платы T5838. Каналы различаются только жгутом и конфигурацией.
3. `PCB-PWR` - защищённый интерфейс между батареей/MPPT и электроникой станции: предохранитель, защита переполюсовки, TVS, измерение тока/напряжения, управляемое отключение нагрузок и DC/DC.

Силовой MPPT не интегрируется в `PCB-MAIN` и не переносится из схемы EVT-MB с CN3791. Старая схема была рассчитана на другую панель и батарейную архитектуру и для EVT-PRE-20 запрещена.

## 3. Соединение узлов

| Источник | Приёмник | Интерфейс | Обязательная проверка |
|---|---|---|---|
| 60-80 W solar panel | внешний MPPT | PV+/PV-, съёмный поляризованный разъём | Voc при минимальной температуре, Isc, полярность, IP |
| внешний MPPT | 12.8 V LiFePO4 40-60 Ah | BAT+/BAT-, предохранитель у батареи | профиль LiFePO4, ток 10 A, запрет заряда ниже 0 °C |
| батарея/MPPT | PCB-PWR | защищённая 12.8 V шина | reverse, surge, fuse, провод и нагрев |
| PCB-PWR | PCB-MAIN | 3.8 V modem, 3.3 V digital, 1.8 V microphone | ripple, startup, brownout, LTE burst |
| PCB-MAIN | PCB-MIC x4 | 1.8 V, GND, PDM_CLK, PDM_DATA[n] | задержка, EMI, channel mapping, одинаковая длина |
| MCU | BG95 | UART + PWRKEY + RESET + STATUS + DTR | уровни 1.8/3.3 V, attach/recovery |
| BG95 | SIM mux | 1.8 V USIM_VDD/RST/CLK/DATA | signal integrity, ESD, high-Z, safe switch |
| SIM mux | nano-SIM 1/2 | один активный слот, два отдельных DET | ICCID mapping, 100 switch cycles |
| MCU | MAX-M10S | UART/I2C + TIMEPULSE | PPS capture, holdover, antenna fault |
| MCU | LoRa | SPI + NSS + DIO1 + BUSY + RESET | RF region, conducted output, sleep current |
| MCU | BLE module | UART + enable/reset | pairing, access control, signed OTA |
| MCU | QSPI NOR | OCTOSPI | power-loss, endurance, integrity |
| MCU | microSD | SDMMC preferred, SPI fallback | industrial card, removal, filesystem recovery |
| PCB-MAIN | сервер «Мухоед» | MQTT/TLS 1.2+; HTTPS fallback | CGNAT, reconnect, dedup, store-and-forward |

## 4. Почему отдельный GNSS обязателен

BG95 поддерживает GNSS, но его WWAN и GNSS используют общий аппаратный тракт и не предназначены для одновременной работы. Станции нужна непрерывная временная метка/PPS во время передачи событий, поэтому GNSS модема используется только как диагностический резерв. Основной источник времени - отдельный GNSS-модуль с выводом TIMEPULSE.

## 5. SIM без API оператора

Обычная SIM с публичным APN допустима для пилота. Станция сама инициирует MQTT/TLS или HTTPS-сессию, работает за CGNAT и получает команды через уже установленное защищённое соединение. Не требуются статический публичный IP, входящие порты и API оператора. До закупки 20 SIM обязательны тест одной SIM каждого оператора, 24-часовая сессия, reconnect и восстановление очереди.

На PCB устанавливаются два физических nano-SIM слота. BG95 имеет один внешний 1.8 В USIM-интерфейс, поэтому применяется внешний 2:1 мультиплексор и режим Dual SIM Single Standby. Переключение выполняется только после штатного выключения BG95. Для пилота разрешены только public APN; private APN отклоняется политикой конфигурации.

## 6. Неподтверждённые позиции

- pin assignment MCU до проверки в STM32CubeMX и review alternate functions;
- точный вариант BG95 по диапазонам и сертификации страны пилота;
- точный MPPT, BMS, панель, батарея, антенны и гермовводы после RFQ;
- BLE-модуль после проверки OTA, энергопотребления и поставки;
- PCB размеры, разъёмы и жгуты до механической компоновки;
- фактическая автономность 30 суток без солнца до профилирования S0-S4.

## 7. Gate производства

Заказ PCB/PCBA запрещён до одновременного выполнения: schematic freeze, CubeMX pin check, ERC PASS, DRC PASS, RF/power/layout review, BOM/AVL review, CAM review, DFM от фабрики и сборки минимум двух инженерных образцов.

## 8. Первичные источники

- ST STM32U585VIT6Q: https://estore.st.com/en/stm32u585vit6q-cpn.html
- Quectel BG95: https://www.quectel.com/product/lpwa-bg95-cat-m1-cat-nb2-egprs-series/
- u-blox MAX-M10: https://www.u-blox.com/en/product/max-m10-series
- TDK T5838: https://www.invensense.tdk.com/en-us/products/microphone/t5838
- Ebyte E22-900M22S: https://www.ebyte.com/product/435.html
- LoRaWAN Regional Parameters RP002-1.0.5: https://resources.lora-alliance.org/document/rp002-1-0-5-lorawan-regional-parameters
