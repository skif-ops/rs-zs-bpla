# DIONEA-INTEGRATION-v0.12

Дата: 10.09.2026.

Статус: `OPEN / INTEGRATION BASELINE / NOT FOR MANUFACTURE`.

Версия закрывает рабочий блок `MAIN-AUTH-011` в общем интеграционном дереве `develop`
и `main`, не объединяя поставочные области `evt-mb` и `evt-pre-20` между собой.

## Исходные контрольные точки

| Область | Ветка | SHA |
|---|---|---|
| Предыдущий интеграционный baseline v0.11 | `main` / `develop` | `6dea6958f167b910de016d5602753aabd9a95523` |
| Макетный EVT-MB v1.3 | `evt-mb` | `7d0f7f182e342cd3a3c6ba6f28bc6f138c71c4e1` |
| Предсерийный EVT-PRE-20 Rev.A | `evt-pre-20` | `b2fe734fe024d5e80573e85c23de3f0fc86c602a` |

## Изменение v0.12

- закрыт `MAIN-AUTH-011` машинным authority из 70 записей и вторым независимым геометрическим контролем;
- зафиксирована PCB-MAIN 110 x 75 x 1.6 мм, R3, четыре симметричных D3.2 NPTH под M3 и консервативный unmated PCBA envelope 110 x 75 x 12 мм;
- зафиксированы направления J_PWR, J_MIC1..4, J6/J7, J8/J9/J10, USB-C J11, microSD J12 и tamper J13;
- разделены cellular, GNSS, RU868 и BLE зоны; закреплены BLE all-layer keepout 3.8 x 10.5 мм, внешний BLE exclusion и GNSS upper-view exclusion;
- зафиксированы 31 bottom-side production pogo pad на шаге 2.54 мм, три fixture fiducial и компонент-свободное окно оснастки;
- `mechanics/common/OPEN_DIMENSIONS.csv` различает закрытый authority input и ещё не подтверждённый native STEP;
- исправлен отчёт основного PCB-MAIN аудита: он снова выводит фактически проверенные 67 назначений U1, а не длину позднее переиспользованного списка выводов пассивного компонента;
- новый независимый mechanical placement gate включён в CI и PCB Native Gate.

## Зафиксированный статус

- EVT-MB v1.3 остаётся `OPEN`; аппаратные I2S/PPS/BG95/RF/S0-S4 — `NOT RUN`;
- EVT-PRE-20 остаётся `OPEN / NOT RUN`;
- `MAIN-AUTH-001…011` закрыты, `capture_readiness.complete=true`;
- native `PCB-MAIN` отсутствует, `Review A` заблокирован его отсутствием, `Review B` заблокирован;
- PCBA envelope ещё не подтверждён native STEP и полной сборочной моделью корпуса;
- точная геометрия 50 Ohm не задана до получения шестислойного stackup от производителя;
- производственный BOM, Gerber и `FOR_MANUFACTURE` не объявлены;
- SI/PI/RF/ESD, fixture MSA и все физические проверки остаются `NOT RUN`.

## Контроль продвижения

1. Выполнить основной pre-schematic audit и все одиннадцать независимых MAIN authority audit.
2. Выполнить QG-1/QG-2, firmware CTest и server pytest.
3. Продвинуть один проверенный SHA в `develop` и дождаться полного CI.
4. Продвинуть тот же SHA в `main` и повторить CI/Release integrity.

Любое последующее изменение дерева после проверки создаёт новую версию с новым SHA.
