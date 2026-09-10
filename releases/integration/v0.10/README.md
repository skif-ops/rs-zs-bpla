# DIONEA-INTEGRATION-v0.10

Дата: 10.09.2026.

Статус: `OPEN / INTEGRATION BASELINE / NOT FOR MANUFACTURE`.

Версия закрывает рабочий блок `MAIN-AUTH-009` в общем интеграционном дереве `develop`
и `main`, не объединяя поставочные области `evt-mb` и `evt-pre-20` между собой.

## Исходные контрольные точки

| Область | Ветка | SHA |
|---|---|---|
| Предыдущий интеграционный baseline v0.9 | `main` / `develop` | `fe52c5f21ecc4d25a953e8c0596e94ed3060e910` |
| Макетный EVT-MB v1.3 | `evt-mb` | `7d0f7f182e342cd3a3c6ba6f28bc6f138c71c4e1` |
| Предсерийный EVT-PRE-20 Rev.A | `evt-pre-20` | `b2fe734fe024d5e80573e85c23de3f0fc86c602a` |

## Изменение v0.10

- закрыт `MAIN-AUTH-009` машинным authority из 70 физических контактов;
- выбраны Kingston `SDCIT2/32GB` и GCT `MEM2052-00-195-00-A`, закреплён полный microSD-контракт 4-bit SDMMC1 и active-LOW card detect;
- `J11` закреплён как GCT `USB4105-GF-A-120`, USB2 device-only для STM32, с sense-only VBUS, раздельными CC Rd и изолированным shield;
- `J8/J9/J10` закреплены как Hirose `U.FL-R-SMT-1(60)`, а J9/J10 машинно сверяются с закрытыми GNSS/LoRa authority;
- `J13` закреплён как двухконтактный Molex Pico-Lock normally-closed tamper loop;
- закреплены отдельные `TP_MCU_SWD`, `TP_EOL`, `TP_CELL_USB` и `TP_CELL_DBG`; STM32 USB, BG95 USB, nRF USB и обе SWD-области не смешиваются;
- добавлен второй независимый connector/fixture authority gate в CI и PCB Native Gate.

## Зафиксированный статус

- EVT-MB v1.3 остаётся `OPEN`; аппаратные I2S/PPS/BG95/RF/S0–S4 - `NOT RUN`;
- EVT-PRE-20 остаётся `OPEN / NOT RUN`;
- `MAIN-AUTH-001…009` закрыты, `MAIN-AUTH-010…011` открыты;
- native `PCB-MAIN` отсутствует, `Review A` не начат, `Review B` заблокирован;
- точные пассивы/защита принадлежат `MAIN-AUTH-010`, механика/ориентация/размещение - `MAIN-AUTH-011`;
- производственный BOM и `FOR_MANUFACTURE` не объявлены;
- card, USB, tamper, fixture и RF физически не испытаны.

## Контроль продвижения

1. Выполнить основной pre-schematic audit и все девять независимых MAIN authority audit.
2. Выполнить остальные QG-1/QG-2, firmware CTest и server pytest.
3. Продвинуть один проверенный SHA в `develop` и дождаться полного CI.
4. Продвинуть тот же SHA в `main` и повторить CI/Release integrity.

Любое последующее изменение дерева после проверки создаёт новую версию с новым SHA.
