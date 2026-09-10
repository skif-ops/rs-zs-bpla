# DIONEA-INTEGRATION-v0.9

Дата: 10.09.2026.

Статус: `OPEN / INTEGRATION BASELINE / NOT FOR MANUFACTURE`.

Версия закрывает рабочий блок `MAIN-AUTH-008` в общем интеграционном дереве `develop`
и `main`, не объединяя поставочные области `evt-mb` и `evt-pre-20` между собой.

## Исходные контрольные точки

| Область | Ветка | SHA |
|---|---|---|
| Предыдущий интеграционный baseline v0.8 | `main` / `develop` | `b9943a6a50968d1fa2e1b939dfb0dd41f2ffa748` |
| Макетный EVT-MB v1.3 | `evt-mb` | `7d0f7f182e342cd3a3c6ba6f28bc6f138c71c4e1` |
| Предсерийный EVT-PRE-20 Rev.A | `evt-pre-20` | `b2fe734fe024d5e80573e85c23de3f0fc86c602a` |

## Изменение v0.9

- закрыт `MAIN-AUTH-008` полным 61-площадочным authority для Raytac `MDBT50Q-P1MV2`;
- UART закреплён на nRF `P0.06/P0.08`, DFU-запрос на `P0.15`, reset на `P0.18/nRESET`;
- закреплён fail-closed reset от STM32 `BLE_EN` и активный LOW open-drain `BLE_DFU_REQ`;
- закреплён отдельный четырёхконтактный nRF SWD `VTREF/NRF_SWDIO/NRF_SWCLK/GND`;
- закреплены 3,3 В normal-voltage mode, внутренний LFRC и явные NC для nRF USB/неиспользуемых GPIO;
- закреплён all-layer no-ground/copper keepout встроенной антенны не менее 10,5 x 3,8 мм;
- добавлен второй независимый BLE authority gate в CI и PCB Native Gate.

## Зафиксированный статус

- EVT-MB v1.3 остаётся `OPEN`; аппаратные I2S/PPS/BG95/RF/S0–S4 - `NOT RUN`;
- EVT-PRE-20 остаётся `OPEN / NOT RUN`;
- `MAIN-AUTH-001…008` закрыты, `MAIN-AUTH-009…011` открыты;
- native `PCB-MAIN` отсутствует, `Review A` не начат, `Review B` заблокирован;
- производственный BOM и `FOR_MANUFACTURE` не объявлены;
- BLE SWD/DFU/reset, ток, дальность и совместная работа в корпусе физически не испытаны.

## Контроль продвижения

1. Выполнить основной pre-schematic audit и отдельный независимый BLE authority audit.
2. Выполнить остальные QG-1/QG-2, firmware CTest и server pytest.
3. Продвинуть один проверенный SHA в `develop` и дождаться полного CI.
4. Продвинуть тот же SHA в `main` и повторить CI/Release integrity.

Любое последующее изменение дерева после проверки создаёт новую версию с новым SHA.
