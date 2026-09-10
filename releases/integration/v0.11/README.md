# DIONEA-INTEGRATION-v0.11

Дата: 10.09.2026.

Статус: `OPEN / INTEGRATION BASELINE / NOT FOR MANUFACTURE`.

Версия закрывает рабочий блок `MAIN-AUTH-010` в общем интеграционном дереве `develop`
и `main`, не объединяя поставочные области `evt-mb` и `evt-pre-20` между собой.

## Исходные контрольные точки

| Область | Ветка | SHA |
|---|---|---|
| Предыдущий интеграционный baseline v0.10 | `main` / `develop` | `74202193eec62a30ba72bd1ef2f2ef72cb8f25dc` |
| Макетный EVT-MB v1.3 | `evt-mb` | `7d0f7f182e342cd3a3c6ba6f28bc6f138c71c4e1` |
| Предсерийный EVT-PRE-20 Rev.A | `evt-pre-20` | `b2fe734fe024d5e80573e85c23de3f0fc86c602a` |

## Изменение v0.11

- закрыт `MAIN-AUTH-010` машинным authority из 211 уникальных физических компонентов: 196 fitted и 15 DNP;
- зафиксированы точные RefDes, производители, MPN, корпуса, номиналы, population, температурные диапазоны, физические выводы и электрические пути для `C1-C80`, `R1-R103`, L1/L2, FB1, FL1, U5/U6, Q4, U19-U27, D1-D11 и X1;
- закреплена полная реализация active-antenna supervisor GNSS по Figure 38, fail-closed BLE reset, ESD-защита разъёмов и fixture, ревизионные straps `HW_REV[1:0]=00` и мост `FAULT` к `PWR_FAULT`;
- SiT1552 X1 закреплён без внешних load/bypass-конденсаторов согласно разрешённой производителем схеме применения;
- контролируемый Rev.A BOM расширен до 293 строк и машинно сверяется с authority для всех 211 позиций;
- добавлен второй независимый passive/support authority gate в CI и PCB Native Gate.

## Зафиксированный статус

- EVT-MB v1.3 остаётся `OPEN`; аппаратные I2S/PPS/BG95/RF/S0-S4 — `NOT RUN`;
- EVT-PRE-20 остаётся `OPEN / NOT RUN`;
- `MAIN-AUTH-001…010` закрыты, `MAIN-AUTH-011` открыт;
- native `PCB-MAIN` отсутствует, `Review A` заблокирован его отсутствием, `Review B` заблокирован;
- механика, ориентация и координаты размещения принадлежат `MAIN-AUTH-011`;
- производственный BOM и `FOR_MANUFACTURE` не объявлены;
- частотная характеристика FB1, SI/PI/RF/ESD и все физические цепи остаются непроверенными до native capture, Review A/B и стендовых испытаний.

## Контроль продвижения

1. Выполнить основной pre-schematic audit и все десять независимых MAIN authority audit.
2. Выполнить остальные QG-1/QG-2, firmware CTest и server pytest.
3. Продвинуть один проверенный SHA в `develop` и дождаться полного CI.
4. Продвинуть тот же SHA в `main` и повторить CI/Release integrity.

Любое последующее изменение дерева после проверки создаёт новую версию с новым SHA.
