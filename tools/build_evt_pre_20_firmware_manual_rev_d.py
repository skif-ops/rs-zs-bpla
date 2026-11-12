#!/usr/bin/env python3
"""Build Rev D flashing manual and Rev B physical EOL program."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
MANUAL_SOURCE = ROOT / "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.md"
MANUAL_MD = ROOT / "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.md"
MANUAL_DOCX = ROOT / "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.docx"
EOL_SOURCE = ROOT / "docs/EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_A.md"
EOL_MD = ROOT / "docs/EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_B.md"
EOL_DOCX = ROOT / "docs/EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_B.docx"


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"expected one occurrence, found {text.count(old)}: {old[:80]!r}")
    return text.replace(old, new, 1)


def replace_section(text: str, start: str, end: str, replacement: str) -> str:
    start_at = text.find(start)
    end_at = text.find(end, start_at + len(start))
    if start_at < 0 or end_at < 0:
        raise RuntimeError(f"section boundary not found: {start!r} -> {end!r}")
    return text[:start_at] + replacement.rstrip() + "\n\n" + text[end_at:]


def normalize(text: str) -> str:
    for source in ("\u2014", "\u2013", "\u2011", "\u2212"):
        text = text.replace(source, "-")
    return text.replace("\r\n", "\n")


def build_manual_markdown() -> str:
    text = normalize(MANUAL_SOURCE.read_text(encoding="utf-8"))
    text = replace_once(text, "**Ревизия:** Rev C", "**Ревизия:** Rev D")
    text = replace_once(text, "**Дата:** 06.10.2026", "**Дата:** 12.11.2026")
    text = replace_once(
        text,
        "Документ не разрешает программирование необратимых option bytes, включение RDP Level 2, окончательную блокировку отладки, загрузку закрытых ключей в Git, передачу производственных секретов контрактному сборщику и радиопередачу LoRa вне согласованного стенда до выпуска утвержденного профиля RU868.",
        "Документ не разрешает программирование необратимых option bytes, включение RDP Level 2, окончательную блокировку отладки, загрузку закрытых ключей в Git и передачу производственных секретов контрактному сборщику. Частотный план RU868 утвержден для EVT-PRE-20. До аппаратной проверки мощности, спектра, скважности и установленной антенны передача LoRa разрешается только в проводной или экранированной RF-оснастке по отдельному разрешению испытателя. Полевой TX остается заблокированным.",
    )
    text = replace_once(
        text,
        "| LoRa RU868 | Профиль-кандидат и fail-closed политика | `tx_enabled: false` до RF release |",
        "| LoRa RU868 | Частотный план и список каналов утверждены; изменение региона запрещено | Полевой `tx_enabled: false`; conducted TX только по разрешению испытателя до измерения мощности, спектра, скважности и антенны |",
    )
    text = replace_once(
        text,
        "- ST-LINK/V3 с известным серийным номером, актуальной прошивкой probe и линией NRST.",
        "- ST-LINK/V3 с известным серийным номером, актуальной прошивкой probe и линией NRST для STM32U585.\n- Отдельный коммерческий SEGGER J-Link BASE или J-Link PLUS для nRF52840. J-Link EDU и EDU Mini для производственных работ не применяются.",
    )
    text = replace_once(
        text,
        "- Антенны или согласованные 50-омные нагрузки для LTE, GNSS и LoRa. Передача LoRa до RF release выполняется только через conducted/shielded setup.",
        "- Утвержденные LTE, GNSS и LoRa антенны. Для передающих испытаний LTE и LoRa применяются согласованные нагрузки 50 Ом, аттенюаторы и проводная или экранированная RF-оснастка. GNSS проверяется с антенной или симулятором и не требует нагрузки вместо антенны.",
    )
    text = replace_once(
        text,
        "| STM32CubeProgrammer | Утвержденная на день выпуска версия, версия и ST-LINK firmware пишутся в лог |",
        "| STM32CubeProgrammer | 2.23.0 для Rev D; версия и ST-LINK firmware пишутся в лог |",
    )
    text = replace_once(
        text,
        "| nRF Connect SDK | v2.7.0 |",
        "| nRF Connect SDK | v2.7.0 |\n| Nordic nRF Command Line Tools | 10.24.2, `nrfjprog`; пакет архивирован Nordic и закреплен только для текущего релиза |\n| SEGGER J-Link | BASE или PLUS; версия software pack и серийный номер пишутся в EOL log |\n| mcumgr | Версия из nRF Connect SDK v2.7.0; применяется для MCUboot serial recovery и проверки OTA |",
    )

    operator_matrix = """### 4.3. Матрица применения приборов и инструментов

Эта таблица является обязательным маршрутом оператора. Если строка требует прибор, переход к следующему шагу без указанного результата и evidence запрещен.

| Шаг | Прибор или инструмент | Подключение | Настройка до начала | Для чего применяется | Обязательный результат и evidence |
|---|---|---|---|---|---|
| 1. Входной контроль | Увеличение и DMM | Обесточенное изделие | Режим сопротивления или continuity, проверочное напряжение не более 5 В | Осмотр монтажа, полярности, DNP и поиск коротких замыканий | Фото, сопротивления шин, решение GO или HOLD |
| 2. Подготовка питания | Лабораторный источник и регистратор тока | Только J_PWR_IN | 12,8 В как начальная точка B01; аппаратный current limit из traveller; выход выключен до проверки полярности | Безопасное первое включение и запись пускового тока | Профиль напряжения и тока, отсутствие current limit и reset loop |
| 3. Контроль шин | Четырехканальный осциллограф | CH1 TP_EOL.2, CH2 .3, CH3 .4, CH4 .7 или .8, общий TP_EOL.1 | Single acquisition до подачи питания; полоса и частота выборки фиксируются в журнале | 3V3_DIGITAL, 3V8_MODEM, 1V8_MIC, PWR_GOOD и FAULT | Исходные waveform-файлы и скриншоты с масштабами |
| 4. Тепловой контроль | Тепловизор | Вид на PCB-MAIN и PCB-PWR | Запись начинается до подачи питания | Поиск локального перегрева при запуске и modem burst | Термограмма с временем, ambient и максимальной температурой |
| 5. STM32 SWD | ST-LINK/V3 | TP_MCU_SWD: 5 GND, 1 VTREF, 4 NRST, 2 SWDIO, 3 SWCLK | Connect Under Reset, 1000 кГц; при отказе 100 кГц | ID, flash size, option bytes, erase, program, verify и reset | Лог по serial, option bytes до и после, verify PASS |
| 6. nRF52840 SWD | J-Link BASE или PLUS | TP_BLE_SWD: 4 GND, 1 VTREF, 2 SWDIO, 3 SWCLK | nRF Command Line Tools 10.24.2; family NRF52 | Запись merged.hex, verify и reset | Лог программатора и MCUboot startup PASS |
| 7. Заводская идентификация | Изолированный UART 3,3 В | TP_EOL.5 DUT_TX, .6 DUT_RX, .1 GND | 115200, 8N1, no flow control; RX оснастки high-Z до valid VTREF | `factoryid`, `secrets`, self-test и диагностический журнал | Serial и station ID совпадают, `pairing set`, секреты в лог не попали |
| 8. Отладочный журнал BG95 | Изолированный UART 1,8 В | TP_CELL_DBG.2 DUT_TX, .5 GND; .3 обычно не подключать | 115200, 8N1; вход оснастки high-Z до valid VREF_1V8 | Только boot и debug log BG95 | Лог или отметка, что вывод отключен прошивкой модема; AT-команды здесь запрещены |
| 9. TLS в BG95 | Сервисная функция STM32 на основном UART BG95 | TEST_UART управляет сервисной операцией; STM32 USART1 работает с MAIN UART U8 | Только подписанный сервисный выпуск; три файла заранее проверены | Передача CA, station certificate и private key через `QFUPL` | Size, checksum, `QFLST`, read-back `QSSLCFG` и mTLS PASS |
| 10. BG95 recovery | Изолированный USB 2.0 и current-limited VBUS | TP_CELL_USB; при необходимости TP_CELL_DBG.4 USB_BOOT 1,8 В | J11 физически отключен; аварийное снятие питания проверено | USB recovery и идентификация модема | Enumeration log и подтверждение отсутствия связи с J11 |
| 11. Android commissioning | Телефон Android 9 или новее | BLE, затем USB только для установки APK | Проверенный APK, отключенное автосохранение файлов с секретами | LESC, station secrets, config, read-back и локальные координаты | Экспорт без секретов и provisioning receipt |
| 12. LTE и MQTT | Две SIM, LTE-антенна или RF-стенд | J8 и штатные SIM | APN только из утвержденного профиля | Attach, DNS, TLS, MQTT, heartbeat, event, receipt и SIM failover | AT-log без секретов и серверный receipt |
| 13. GNSS и PPS | GNSS-антенна или симулятор, осциллограф или логический анализатор | J9 и PPS capture | Сценарий симулятора или условия видимости неба записаны | Fix, RMC, PPS, loss и holdover | NMEA, PPS waveform и timestamp report |
| 14. LoRa | Нагрузка 50 Ом, аттенюатор, анализатор и test peer | J10, только проводной или экранированный тракт | Частотный план RU868 фиксирован; пределы мощности и скважности берутся из подписанного RF test profile | Частота, мощность, occupied bandwidth, spurious, packet и retry | RF trace и packet log; полевая передача запрещена до итогового RF PASS |
| 15. Акустика | Калиброванный излучатель и опорный микрофон | Геометрия 3+1 в собранной головке | Уровень, расстояние, угол, сигнал и ambient записаны | Каналы, задержки, шум, AAD и влияние корпуса | WAV или PCM, калибровочный файл и отчет по четырем каналам |
| 16. A/B и rollback | Управляемый power interrupter | J_PWR_IN | Сценарии отключения 10, 30, 70 и 99 процентов передачи плюс boot record и confirmation | Устойчивость обновления к пропаданию питания | Лог активного банка, rollback и сохранности данных |
| 17. Выпуск | Сканер QR и принтер этикеток | Реестр serial и защищенный label output | Сверка serial, station ID, tenant и certificate fingerprint | Исключение перепутывания станции и учетных данных | Подписанные traveller, receipt и EOL record |

Версии приборов, программ, probe serial, COM-порты, диапазоны, точность, калибровка и имена исходных файлов записываются до начала измерений. Скриншот без исходного waveform, журнала или экспортированного результата не считается достаточным evidence.
"""
    text = replace_once(text, "\n## 5. Входные данные перед началом работ", "\n" + operator_matrix + "\n## 5. Входные данные перед началом работ")

    fixture_sections = """### 7.3. TP_BLE_SWD

| Контакт | Сигнал | Подключение | Правило |
|---:|---|---|---|
| 1 | VTREF | J-Link VTREF sense | Только измерение, probe не питает DUT |
| 2 | NRF_SWDIO | J-Link SWDIO | Не соединять со SWDIO STM32 |
| 3 | NRF_SWCLK | J-Link SWCLK | Не соединять со SWCLK STM32 |
| 4 | GND | J-Link GND | Соединяется первым, снимается последним |

### 7.4. TP_CELL_DBG

`TP_CELL_DBG` подключен к DEBUG UART BG95 на выводах U8. Это не основной AT UART. Площадки служат для контролируемого boot или debug log и USB_BOOT recovery. Команды `AT`, `QFUPL`, `QFLST` и `QSSLCFG` через эти площадки не выполняются.

| Контакт | Сигнал | Подключение | Правило |
|---:|---|---|---|
| 1 | VREF_1V8 | Высокоомный sense и reference level shifter | Никогда не питать |
| 2 | DUT_TX | Вход изолированного UART 1,8 В | 115200, 8N1; подключать после valid VREF |
| 3 | DUT_RX | Обычно не подключен; выход оснастки 1,8 В только по отдельной процедуре | High-Z по умолчанию, AT-команды запрещены |
| 4 | USB_BOOT | Current-limited 1,8 В control | Только recovery sequence, затем high-Z |
| 5 | GND_MODEM | Земля modem fixture | Соединяется первой |

Основной AT UART BG95 находится на U8 MAIN_RXD и MAIN_TXD и соединен со STM32 USART1 через штатный level translator. Прямая внешняя перемычка к этим цепям не предусмотрена. Загрузка TLS-файлов выполняется сервисной функцией STM32 через основной UART. До выпуска образа, в котором эта функция привязана к target и испытана на B01, шаг имеет статус SOFTWARE INTEGRATION PENDING и не может получить PASS.

### 7.5. TP_CELL_USB

| Контакт | Сигнал | Подключение | Правило |
|---:|---|---|---|
| 1 | HOST_VBUS | Изолированный current-limited USB VBUS | Подавать последним, отключать первым |
| 2 | D- | Изолированный USB D- | Не соединять с J11 |
| 3 | D+ | Изолированный USB D+ | Не соединять с J11 |
| 4 | GND_MODEM | Земля modem fixture | Соединяется первой |

До подключения на обесточенной плате проверяют отсутствие непрерывности между TP_CELL_USB.1-.3 и J11 VBUS, D- и D+. Обычный USB-кабель без изолированного current limiter запрещен.

"""
    text = replace_once(text, "\n## 8. Получение исходников и фиксация версии", "\n" + fixture_sections + "## 8. Получение исходников и фиксация версии")

    text = replace_once(
        text,
        "Для первой записи используется `02_NRF52840/merged.hex`, включающий MCUboot и приложение. SHA-256 merged HEX должен быть `7528e8a474283776162c9ac49d3de5082aa86a9a0d0f98d66603fdb2132a0f7f`. Пример команды Nordic:",
        "Для первой записи используется `02_NRF52840/merged.hex`, включающий MCUboot и приложение. SHA-256 merged HEX должен быть `7528e8a474283776162c9ac49d3de5082aa86a9a0d0f98d66603fdb2132a0f7f`. Для текущего выпуска закреплен `nrfjprog` 10.24.2 с коммерческим J-Link BASE или PLUS. Nordic архивировала этот пакет и рекомендует переход на nRF Util, поэтому миграция выполняется только отдельным релизом после повторной квалификации команды. Пример команды текущего выпуска:",
    )
    text = replace_once(
        text,
        "Если производственная оснастка использует J-Link или другое утвержденное средство, команда меняется, но последовательность erase, program, verify, reset и сохранение лога остается обязательной. Не стирать STM32 при работе с nRF SWD.",
        "Перед записью выполнить `nrfjprog --version`, `nrfjprog --ids` и сверить серийный номер J-Link. Последовательность erase, program, verify, reset и сохранение полного лога обязательна. Не использовать `--recover` вместо штатной записи и не стирать STM32 при работе с nRF SWD.",
    )

    bg95_section = """### 16.7. Загрузка mTLS-материала в BG95

До первого MQTT-подключения в файловое хранилище BG95 должны быть загружены `dioneya-root`, `station.crt` и `station.key`. Endpoint равен `dioneya.ru:8883`, SSL context равен 1.

Электрический путь фиксирован: TEST_UART используется только для управления сервисной операцией STM32; фактические команды BG95 идут от STM32 USART1 через штатный translator на MAIN UART U8. `TP_CELL_DBG` подключен к DEBUG UART и не используется для AT-команд или передачи PEM. Прямое соединение внешнего UART с цепями MAIN_RXD и MAIN_TXD не предусмотрено.

Сервисная функция должна выполнить для каждого файла удаление прежней записи, `QFUPL` с точным размером, передачу точного числа байтов, проверку `+QFUPL` size и checksum, `QFLST`, затем read-back `QSSLCFG`. Private key не выводится в TEST_UART, debug log или evidence. Оператор передает данные из защищенного EOL-каталога, а firmware возвращает только имя, размер, checksum и итог.

Portable state machine `zs_bg95_provision` и host-тесты готовы. Ее target binding, безопасный источник трех файлов, сервисная команда, очистка буферов и полный обмен с реальным BG95 должны войти в новый подписанный firmware release. Текущий `EVT_PRE_20_BENCH_RELEASE_2026100601` не получает PASS по этому шагу только на основании наличия portable-кода. До нового релиза действует статус SOFTWARE INTEGRATION PENDING; после релиза до проверки на B01 действует HARDWARE VALIDATION PENDING.

#### 16.7.1. Карта файлов BG95 и критерии приемки
"""
    text = replace_section(text, "### 16.7. Загрузка mTLS-материала в BG95", "#### 16.7.1. Карта файлов BG95 и критерии приемки", bg95_section)

    lora_section = """### 20.7. LoRa

Частотный план `DIONEA-RU868-v0.1` и регион RU868 утверждены для EVT-PRE-20. Пользователь, приложение и удаленная команда не могут менять регион или список каналов. Разрешенные центры каналов: 864,1; 864,3; 864,5; 864,7; 864,9; 868,9 и 869,1 МГц при полосе 125 кГц.

Утверждение частот не заменяет аппаратную проверку выходной мощности, occupied bandwidth, spurious emissions, скважности, согласования кабеля и VSWR установленной антенны. Поэтому полевой `tx_enabled` остается false. Для B01 допускается отдельный подписанный RF test profile, который включает TX только при подтвержденной проводной или экранированной оснастке и не используется в полевой конфигурации.

Порядок проверки:

1. До подачи питания подключить J10 к нагрузке 50 Ом через утвержденный аттенюатор и анализатор либо к экранированному test peer.
2. Сверить profile ID, region, channel mask, bandwidth, spreading factor, coding rate, output power и duty-cycle с подписанным RF test profile.
3. Проверить отклонение всех частот вне списка и отдельное отклонение старых 868,1; 868,3; 868,5 и 868,7 МГц.
4. Для каждого разрешенного канала сохранить center frequency, power, occupied bandwidth, spurious trace и packet result.
5. Проверить authenticated frame, counter, dedup, retry и возврат на cellular после восстановления связи.
6. После испытания вернуть полевой профиль с `tx_enabled: false` и проверить read-back.

Без подписанного RF test profile, подключенной нагрузки или экранированного стенда передача запрещена. Отсутствие аппаратного RF evidence дает HOLD для полевого TX, но не означает, что частотный план не выбран.

"""
    text = replace_section(text, "### 20.7. LoRa", "### 20.8. Серверная связка", lora_section)
    text = text.replace(
        "| LoRa не передает | `tx_enabled: false` | Не обходить блокировку, ждать signed RU868 release |",
        "| LoRa не передает | Полевой `tx_enabled: false` или нет подписанного RF test profile | Не обходить блокировку; для B01 использовать только разрешенный conducted или shielded профиль |",
    )
    text = text.replace(
        "17. **RU868 заблокирован.** Candidate channel list не является разрешением на передачу.",
        "17. **Частотный план RU868 утвержден, полевой TX еще не выпущен.** Передача на B01 допускается только с подписанным RF test profile в проводной или экранированной оснастке; окончательное включение требует аппаратного RF PASS.",
    )
    text = text.replace(
        "- [ ] RU868 не изменяем.",
        "- [ ] RU868 profile ID, регион и channel mask прочитаны обратно и не изменяемы пользователем.",
    )
    text = replace_once(
        text,
        "| STM32CubeProgrammer CLI | `https://dev.st.com/stm32cube-docs/prog/2.23.0/en/docs/markup/CubeProg_Command_Lines.html` |",
        "| STM32CubeProgrammer CLI 2.23.0 | `https://dev.st.com/stm32cube-docs/prog/2.23.0/en/docs/markup/CubeProg_Command_Lines.html` |\n| Nordic nRF Command Line Tools 10.24.2 | `https://www.nordicsemi.com/Products/Development-tools/nrf-command-line-tools/download` |\n| SEGGER J-Link models | `https://www.segger.com/products/debug-probes/j-link/` |\n| Quectel BG95 AT commands | `https://www.quectel.com/content/uploads/2021/03/Quectel_BG95BG77BG600L_Series_AT_Commands_Manual_V2.0-2.pdf` |",
    )
    text = replace_once(
        text,
        "| Rev C | 06.10.2026 | Добавлены сквозная операторская последовательность, точное создание P-256 key/CSR, журналы factory identity, карта BG95, повторяемость команд и форма provisioning receipt | Release `EVT_PRE_20_BENCH_RELEASE_2026100601`; firmware без изменения |",
        "| Rev C | 06.10.2026 | Добавлены сквозная операторская последовательность, точное создание P-256 key/CSR, журналы factory identity, карта BG95, повторяемость команд и форма provisioning receipt | Release `EVT_PRE_20_BENCH_RELEASE_2026100601`; firmware без изменения |\n| Rev D | 12.11.2026 | Добавлена матрица применения приборов, закреплены версии инструментов, распиновки nRF и BG95, исправлено назначение DEBUG UART BG95, уточнены границы RU868 и порядок замораживания аппаратных пределов | Анализ схемы, target-кода, официальной документации ST, Nordic, SEGGER и Quectel; firmware release без изменения |",
    )

    text = replace_once(
        text,
        "4. Загрузка CA, station certificate и private key в фактический BG95 через EOL UART, проверка checksum и mTLS.",
        "4. Выпуск нового подписанного firmware с target binding `zs_bg95_provision`, затем загрузка CA, station certificate и private key через STM32 и основной UART BG95, проверка checksum и mTLS на B01.",
    )
    text = text.replace(
        "Конкретная последовательность USB DFU должна быть подтверждена на первой собранной PCB-MAIN и закреплена после сверки с AN2606 для STM32U585. До подтверждения USB recovery не считается закрытым EOL-путем.",
        "Последовательность USB DFU для STM32U585 задается AN2606 и проверяется в отдельном recovery-сеансе B01. До аппаратного подтверждения J11, BOOT0 и enumeration USB recovery остается HARDWARE VALIDATION PENDING и не считается закрытым EOL-путем.",
    )
    if any(ch in text for ch in ("\u2014", "\u2013", "\u2011", "\u2212")):
        raise RuntimeError("manual contains forbidden dash")
    MANUAL_MD.write_text(text, encoding="utf-8", newline="\n")
    return text


def build_eol_markdown() -> str:
    text = normalize(EOL_SOURCE.read_text(encoding="utf-8"))
    text = replace_once(text, "**Ревизия:** Rev A", "**Ревизия:** Rev B")
    text = replace_once(text, "**Дата:** 09.10.2026", "**Дата:** 12.11.2026")
    text = replace_once(
        text,
        "| `docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.docx` | Полная инструкция по прошивке, provisioning и испытаниям / Full flashing, provisioning and test manual |",
        "| `docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.docx` | Полная инструкция и обязательная матрица применения приборов / Full manual and mandatory instrument-use matrix |",
    )
    text = replace_once(
        text,
        "| `manufacturing/MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_A.json` | Машиночитаемая последовательность / Machine-readable sequence |",
        "| `manufacturing/MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_B.json` | Машиночитаемая последовательность / Machine-readable sequence |",
    )
    text = replace_once(
        text,
        "| `manufacturing/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.xlsx` | Основной реестр измерений / Primary measurement register |",
        "| `manufacturing/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_B.xlsx` | Основной реестр измерений / Primary measurement register |",
    )
    text = replace_once(
        text,
        "| `manufacturing/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.csv` | Машиночитаемый исходный реестр / Machine-readable source register |",
        "| `manufacturing/MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_B.csv` | Машиночитаемый исходный реестр / Machine-readable source register |",
    )
    text = replace_once(
        text,
        "Нужны лабораторный источник с программируемым ограничением тока и журналом, DMM с действующей калибровкой, осциллограф не менее четырех каналов, логический анализатор, ST-LINK, отдельный nRF probe, изолированные UART 3,3 В и 1,8 В, open-drain I2C adapter, USB 2.0 recovery interface, тепловизор, управляемый power interrupter, RF нагрузки 50 ohm, экранированный или conducted LoRa стенд, утвержденная GNSS антенна или simulator, акустическая оснастка и компьютер EOL.",
        "Нужны лабораторный источник с программируемым ограничением тока и журналом, DMM с действующей калибровкой, осциллограф не менее четырех каналов, логический анализатор, ST-LINK/V3, отдельный коммерческий J-Link BASE или PLUS, изолированные UART 3,3 В и 1,8 В, open-drain I2C adapter, изолированный USB 2.0 recovery interface, тепловизор, управляемый power interrupter, RF нагрузки 50 Ом, аттенюаторы, экранированный или проводной LoRa стенд, утвержденная GNSS антенна или simulator, акустическая оснастка и компьютер EOL. Назначение, подключение и обязательный результат каждого прибора приведены в разделе 4.3 инструкции Rev D.",
    )
    text = replace_once(
        text,
        "В обычном режиме TP_CELL_DBG.4 должен быть LOW, а выход оснастки high-Z. После штатного включения BG95 измеряют TP_CELL_DBG.1 относительно .5. Только при valid VREF_1V8 подключают 1,8 В UART: DUT_TX .2 к входу оснастки, DUT_RX .3 к выходу оснастки.",
        "В обычном режиме TP_CELL_DBG.4 должен быть LOW, а выходы оснастки high-Z. После штатного включения BG95 измеряют TP_CELL_DBG.1 относительно .5. Только при valid VREF_1V8 подключают вход изолированного UART 1,8 В к DUT_TX .2 и GND к .5 для приема boot или debug log на 115200, 8N1. TP_CELL_DBG подключен к DEBUG UART, а не к MAIN UART. Выполнять через .2 и .3 команды AT, QFUPL, QFLST или QSSLCFG запрещено. DUT_RX .3 остается high-Z, если отдельная процедура диагностики явно не требует иного.\n\nСохраняют boot или debug log, если его вывод включен в установленной версии BG95. Отсутствие debug log само по себе не является FAIL, поскольку загрузочный вывод может быть отключен. Modem identity, firmware version и TLS-файлы проверяются через MAIN UART BG95 под управлением STM32. До выпуска target binding этот шаг имеет SOFTWARE INTEGRATION PENDING. Далее отдельно проверяют USB recovery.",
    )
    text = text.replace(
        "После valid TP_EOL.2 подключить UART и STM32 SWD. После valid TP_BLE_SWD.1 подключить nRF SWD. После valid TP_CELL_DBG.1 подключить BG95 debug.",
        "После valid TP_EOL.2 подключить TEST_UART и STM32 SWD. После valid TP_BLE_SWD.1 подключить nRF SWD. После valid TP_CELL_DBG.1 подключить только прием debug log BG95; основной AT-трафик идет через STM32 USART1.",
    )
    text = text.replace(
        "LoRa TX выполняется только в conducted или экранированной оснастке с утвержденным RU868 profile.",
        "Частотный план RU868 утвержден. LoRa TX выполняется только в проводной или экранированной оснастке с отдельным подписанным RF test profile. Полевой TX остается выключенным до аппаратного RF PASS.",
    )
    text += """

## 16. Изменения Rev B

1. Добавлена обязательная ссылка на матрицу применения приборов инструкции Rev D.
2. Закреплен коммерческий J-Link BASE или PLUS и Nordic nRF Command Line Tools 10.24.2 для текущего выпуска.
3. Исправлено назначение `TP_CELL_DBG`: это DEBUG UART BG95 для логов, а не MAIN UART для AT-команд.
4. Загрузка TLS-материала назначена сервисной функции STM32 через основной UART BG95 и оставлена в состоянии SOFTWARE INTEGRATION PENDING до нового подписанного firmware release.
5. Зафиксировано, что частотный план RU868 принят, но полевой TX требует аппаратного RF PASS.
6. Численные токовые, тепловые, акустические, RF и герметические пределы не придуманы. Их замораживание выполняется только после измерений B01, расчетной проверки и двух подписей.
"""
    text = normalize(text)
    EOL_MD.write_text(text, encoding="utf-8", newline="\n")
    return text


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_borders(cell, color: str = "D9D9D9", size: str = "4") -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = borders.find(qn("w:" + edge))
        if element is None:
            element = OxmlElement("w:" + edge)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:color"), color)


def set_run_font(run, size: float, bold: bool | None = None) -> None:
    run.font.name = "Times New Roman"
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    for key in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(key), "Times New Roman")
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0, 0, 0)
    if bold is not None:
        run.bold = bold


def add_inline(paragraph, text: str, size: float = 14) -> None:
    parts = re.split(r"(`[^`]+`|\*\*[^*]+\*\*)", text)
    for part in parts:
        if not part:
            continue
        bold = part.startswith("**") and part.endswith("**")
        code = part.startswith("`") and part.endswith("`")
        value = part[2:-2] if bold else part[1:-1] if code else part
        set_run_font(paragraph.add_run(value), size, True if bold else None)


def format_paragraph(paragraph, *, indent: bool, alignment, before: float = 0, after: float = 0) -> None:
    fmt = paragraph.paragraph_format
    fmt.line_spacing = 1.0
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.first_line_indent = Cm(1.25) if indent else Cm(0)
    paragraph.alignment = alignment


def add_table(document: Document, rows: list[list[str]]) -> None:
    if not rows:
        return
    columns = max(len(row) for row in rows)
    table = document.add_table(rows=0, cols=columns)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    for row_index, values in enumerate(rows):
        cells = table.add_row().cells
        for column_index, cell in enumerate(cells):
            value = values[column_index].strip() if column_index < len(values) else ""
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_borders(cell)
            if row_index == 0:
                set_cell_shading(cell, "D9EAF7")
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.line_spacing = 1.0
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.first_line_indent = Cm(0)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if row_index == 0 or column_index == 0 else WD_ALIGN_PARAGRAPH.LEFT
            add_inline(paragraph, value, 12)
            if row_index == 0:
                for run in paragraph.runs:
                    run.bold = True
    document.add_paragraph()


def build_docx(markdown: str, output: Path, footer_text: str, title: str, subject: str) -> None:
    document = Document()
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(1.5)
    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(14)
    for key in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        normal._element.rPr.rFonts.set(qn(key), "Times New Roman")

    lines = markdown.splitlines()
    index = 0
    in_code = False
    table_rows: list[list[str]] = []
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            if table_rows:
                add_table(document, table_rows)
                table_rows = []
            in_code = not in_code
            index += 1
            continue
        if in_code:
            paragraph = document.add_paragraph()
            format_paragraph(paragraph, indent=True, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY)
            add_inline(paragraph, line, 14)
            index += 1
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
                index += 1
                continue
            table_rows.append(cells)
            index += 1
            continue
        if table_rows:
            add_table(document, table_rows)
            table_rows = []
        if not line.strip():
            index += 1
            continue
        if line.startswith("# "):
            paragraph = document.add_paragraph(style="Title")
            format_paragraph(paragraph, indent=False, alignment=WD_ALIGN_PARAGRAPH.CENTER)
            add_inline(paragraph, line[2:].strip(), 14)
            for run in paragraph.runs:
                run.bold = True
        elif re.match(r"^#{2,4} ", line):
            level = len(line) - len(line.lstrip("#"))
            paragraph = document.add_paragraph(style=f"Heading {min(level - 1, 3)}")
            format_paragraph(paragraph, indent=True, alignment=WD_ALIGN_PARAGRAPH.LEFT)
            paragraph.paragraph_format.keep_with_next = True
            add_inline(paragraph, line[level + 1 :].strip(), 14)
            for run in paragraph.runs:
                run.bold = True
        elif re.match(r"^[-*] \[[ xX]\] ", line):
            paragraph = document.add_paragraph()
            format_paragraph(paragraph, indent=False, alignment=WD_ALIGN_PARAGRAPH.LEFT)
            paragraph.paragraph_format.left_indent = Cm(1.25)
            paragraph.paragraph_format.first_line_indent = Cm(-0.63)
            add_inline(paragraph, "☐ " + re.sub(r"^[-*] \[[ xX]\] ", "", line), 14)
        elif re.match(r"^[-*] ", line):
            paragraph = document.add_paragraph()
            format_paragraph(paragraph, indent=False, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY)
            paragraph.paragraph_format.left_indent = Cm(1.25)
            paragraph.paragraph_format.first_line_indent = Cm(-0.63)
            add_inline(paragraph, "• " + line[2:].strip(), 14)
        elif re.match(r"^\d+\. ", line):
            paragraph = document.add_paragraph()
            format_paragraph(paragraph, indent=False, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY)
            paragraph.paragraph_format.left_indent = Cm(1.25)
            paragraph.paragraph_format.first_line_indent = Cm(-0.63)
            add_inline(paragraph, line, 14)
        else:
            paragraph = document.add_paragraph()
            format_paragraph(paragraph, indent=True, alignment=WD_ALIGN_PARAGRAPH.JUSTIFY)
            add_inline(paragraph, line.replace("  ", " "), 14)
        index += 1
    if table_rows:
        add_table(document, table_rows)

    footer = section.footer.paragraphs[0]
    footer.clear()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.paragraph_format.line_spacing = 1.0
    footer.paragraph_format.first_line_indent = Cm(0)
    set_run_font(footer.add_run(footer_text), 12)
    document.core_properties.title = title
    document.core_properties.subject = subject
    document.core_properties.author = "Проект Дионея"
    document.save(output)


def audit_docx(path: Path, expected_revision: str) -> None:
    document = Document(path)
    errors: list[str] = []
    all_text: list[str] = []
    for paragraph_index, paragraph in enumerate(document.paragraphs, 1):
        all_text.append(paragraph.text)
        if not paragraph.text:
            continue
        style = paragraph.style.name if paragraph.style else ""
        if paragraph.paragraph_format.line_spacing != 1.0:
            errors.append(f"spacing:{paragraph_index}")
        if style == "Title" or style.startswith("Heading"):
            if any(run.text and not run.bold for run in paragraph.runs):
                errors.append(f"heading-bold:{paragraph_index}")
            if style.startswith("Heading"):
                indent = paragraph.paragraph_format.first_line_indent
                if indent is None or abs(indent.cm - 1.25) > 0.01:
                    errors.append(f"heading-indent:{paragraph_index}")
        elif not re.match(r"^(?:\d+\. |• |☐ )", paragraph.text):
            indent = paragraph.paragraph_format.first_line_indent
            if indent is None or abs(indent.cm - 1.25) > 0.01:
                errors.append(f"indent:{paragraph_index}")
            if paragraph.alignment != WD_ALIGN_PARAGRAPH.JUSTIFY:
                errors.append(f"alignment:{paragraph_index}")
        for run in paragraph.runs:
            if run.text and (run.font.name != "Times New Roman" or run.font.size is None or round(run.font.size.pt, 1) != 14):
                errors.append(f"font:{paragraph_index}")
    for table_index, table in enumerate(document.tables, 1):
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    all_text.append(paragraph.text)
                    if paragraph.paragraph_format.line_spacing != 1.0:
                        errors.append(f"table-spacing:{table_index}")
                    if paragraph.paragraph_format.first_line_indent and abs(paragraph.paragraph_format.first_line_indent.cm) > 0.01:
                        errors.append(f"table-indent:{table_index}")
                    for run in paragraph.runs:
                        if run.text and (run.font.name != "Times New Roman" or run.font.size is None or round(run.font.size.pt, 1) != 12):
                            errors.append(f"table-font:{table_index}")
    combined = "\n".join(all_text)
    if expected_revision not in combined:
        errors.append("revision")
    if any(ch in combined for ch in ("\u2014", "\u2013", "\u2011", "\u2212")):
        errors.append("forbidden-dash")
    if errors:
        raise RuntimeError(f"{path.name} format audit failed: " + ", ".join(errors[:80]))


def audit_content(manual: str, eol: str) -> None:
    required_manual = (
        "Матрица применения приборов и инструментов",
        "Nordic nRF Command Line Tools | 10.24.2",
        "J-Link EDU и EDU Mini для производственных работ не применяются",
        "подключен к DEBUG UART",
        "AT-команды здесь запрещены",
        "SOFTWARE INTEGRATION PENDING",
        "Частотный план RU868 утвержден",
        "полевой `tx_enabled` остается false",
        "Rev D | 12.11.2026",
    )
    for token in required_manual:
        if token not in manual:
            raise RuntimeError(f"manual missing token: {token}")
    required_eol = (
        "инструкции Rev D",
        "подключен к DEBUG UART",
        "Выполнять через .2 и .3 команды AT",
        "SOFTWARE INTEGRATION PENDING",
        "Частотный план RU868 утвержден",
    )
    for token in required_eol:
        if token not in eol:
            raise RuntimeError(f"EOL program missing token: {token}")


def main() -> None:
    manual = build_manual_markdown()
    eol = build_eol_markdown()
    audit_content(manual, eol)
    build_docx(
        manual,
        MANUAL_DOCX,
        "Дионея EVT-PRE-20. Инструкция Rev D",
        "Инструкция по прошивке, настройке и испытаниям станции Дионея EVT-PRE-20 Rev D",
        "Прошивка, инструменты, PKI, commissioning, mTLS, EOL и EVT",
    )
    build_docx(
        eol,
        EOL_DOCX,
        "Дионея EVT-PRE-20. DIO-EVT-B01 и EOL MFG-004 Rev B",
        "Программа физической квалификации DIO-EVT-B01 и приемки EOL оснастки Rev B",
        "Физические испытания стендовой станции и приемка оснастки MFG-004",
    )
    audit_docx(MANUAL_DOCX, "Rev D")
    audit_docx(EOL_DOCX, "Rev B")
    print(f"wrote {MANUAL_MD}")
    print(f"wrote {MANUAL_DOCX}")
    print(f"wrote {EOL_MD}")
    print(f"wrote {EOL_DOCX}")
    print("content and DOCX format audits: PASS")


if __name__ == "__main__":
    main()
