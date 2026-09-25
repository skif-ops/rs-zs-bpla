# PCB-PWR — круги Review B

Указатель для ревьюера: какой пакет к какой плате и какому кругу замечаний относится. Пакеты не
перезаписываются: каждый следующий ссылается на манифест предыдущего.

| Пакет | Плата (SHA-256) | Отвечает на | Запись |
|---|---|---|---|
| `PCB_PWR_REVIEW_B_PACKAGE_REV_A` | autoroute 011, `cc2c3c9f…` | первая подача | — |
| `PCB_PWR_REVIEW_B_PACKAGE_REV_B` | ECO-005, `81f44a70…` | R1 (REQUEST_CHANGES) | `PCB_PWR_ECO_005_REV_A.md` |
| `PCB_PWR_REVIEW_B_PACKAGE_REV_C` | ECO-005, `81f44a70…` | R2 (REQUEST_CHANGES_R2): R2.001, R2.002 | `PCB_PWR_REVIEW_B_R2_RESPONSE_REV_A.md` |
| `PCB_PWR_REVIEW_B_PACKAGE_REV_D` | ECO-006, `b8c1da6c…` | решения по R2: исправлены DFM-PWR-02 и DFM-PWR-03 | `PCB_PWR_ECO_006_REV_A.md` |

Актуальный пакет для подписи — **Rev D**. Открытые решения ревьюера: DFM-PWR-01 (U3/U4, зазор меди
0,125 мм) и DFM-PWR-04 (J1.2 и via `GND_PWR`, край отверстий 0,29 мм) — предложения в ответе на R2.
Физические испытания и проверка заказа JLC/JLCDFM — отдельные этапы.
