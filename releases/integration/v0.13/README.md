# DIONEA-INTEGRATION-v0.13

Дата: 17.09.2026.

Статус: `OPEN / INTEGRATION BASELINE / NOT FOR MANUFACTURE`.

Версия синхронизирует общий интеграционный baseline `develop` и `main` с проверенным
срезом `evt-pre-20`. Поставочные области `evt-mb` и `evt-pre-20` не объединялись и
не копировались друг в друга.

## Исходные контрольные точки

| Область | Ветка | SHA |
|---|---|---|
| Предыдущий интеграционный baseline v0.12 | `main` / `develop` | `f3411e51938aa1423fdbaeeef9585aeea385c239` |
| Макетный EVT-MB v1.3, без изменений | `evt-mb` | `7d0f7f182e342cd3a3c6ba6f28bc6f138c71c4e1` |
| Предсерийный EVT-PRE-20 Rev.A | `evt-pre-20` | `0ef02fd7805b19802bc5027bd9a2fe8b1ed514f2` |

## Зафиксированная конфигурация

- партия: 20 станций, аккумулятор-кандидат RB40 40 А·ч;
- солнечная панель `SLP080S-12M`, MPPT `SCC075010060R`, датчик `SBS050150200`;
- антенны Taoglas `G30.B.108111`, `AA.166.A.301111`, `TI.89.B.2111W`;
- внешний разъём SMA bulkhead и внутренний U.FL–SMA пигтейл Taoglas `CAB.0243`;
- на данном этапе зафиксирована одна модель каждого системного компонента по балансу
  цены и качества; решение о продолжении или замене принимается по результатам EVT.

## Контролируемый статус

- `PCB-MAIN`: commit `9aceca9531f0b9c18679bee1a8050ae7cd94308a` и hierarchy PDF
  SHA-256 `7e6ef20a989ec66c55b3e1a32de0a914b9e37a6e70cc5835d36f3260b65ff8d9`
  приняты решением `ACCEPT_HIERARCHY_ONLY`; routing, Review B, CAM/DFM и manufacture
  этим решением не разрешены;
- `PCB-PWR`: hierarchy принята только на уровне hierarchy; target F1 —
  `0451008.MRL`, native F1 остаётся `0451005`, bounded ECO не применён,
  квалификационные результаты — 0/20;
- `PCB-MIC`: copper-return subgate принят; общий Review B, CAM/DFM и manufacturing
  release остаются открыты;
- BOM: 295 engineering-строк, 124 procurement-строки, QG-1 `PASS`, QG-2 `BLOCKED`;
- supplier/physical evidence по системным компонентам, жгутам и корпусу не закрыты;
- аппаратный EVT: `NOT RUN`;
- purchase release и manufacturing release: `BLOCKED`.

## Контроль продвижения

1. Выполнить воспроизводимые BOM, firmware, server и native PCB проверки.
2. Зафиксировать интеграционный commit в `develop` и дождаться полного CI.
3. Продвинуть в `main` ровно тот же SHA без изменения дерева.
4. Не повышать статус hierarchy acceptance до routing/Review B/manufacture без
   отдельного attributable review и первичных evidence.

Любое последующее изменение дерева после проверки создаёт новую интеграционную версию.
