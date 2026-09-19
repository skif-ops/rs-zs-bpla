# EVT-PRE-20 critical MPN market snapshot — 2026-09-18

Status: `HISTORICAL COMMERCIAL SNAPSHOT / NON-BLOCKING CUSTOMER INPUT`

## Scope

This is a public-market planning snapshot for the exact EVT-PRE-20 MPNs below.
Supplier choice is advisory and may change; the MPN and required quantity remain
locked.  Displayed stock, cart availability, and published delivery estimates are
not a delivery guarantee.  Procurement must confirm the final quantity, ship-to
address, freight, export restrictions, and delivery date in a cart or written
quotation.

## Public listings

| Exact MPN | Required | Public supplier/listing | Displayed stock or lead | Public price reference | Quantity status |
|---|---:|---|---|---:|---|
| `RB40` | 21 | [RELiON product page](https://www.relionbattery.com/products/lithium/rb40) / [Inverter Supply listing](https://www.invertersupply.com/index.php?main_page=product_info&products_id=185528) | No usable quantity is exposed on the public product pages | Budget source snapshot: USD 479.95 manufacturer catalog; alternate distributor listing observed at USD 379.95 | `QTY_UNCONFIRMED` |
| `SLP080S-12M` | 21 | [Mr. Solar exact-MPN listing](https://www.mrsolar.com/solarland-slp080s-12m-80-watt-solar-panel/) | Listing explicitly says discontinued and/or not available | USD 177.63 retained for reference only | `BLOCKED_NO_PUBLIC_STOCK` |
| `SCC075010060R` | 21 | [Inverter Supply exact-MPN listing](https://www.invertersupply.com/index.php?main_page=product_info&products_id=31070) | Estimated delivery 6–8 days; lead time to ship may vary; quantity is not exposed | USD 65.45 | `QTY_UNCONFIRMED` |
| `SBS050150200` | 21 | [Inverter Supply exact-MPN listing](https://www.invertersupply.com/index.php?main_page=product_info&products_id=194069) | Estimated delivery 6–8 days; lead time to ship may vary; quantity is not exposed | USD 39.10 | `QTY_UNCONFIRMED` |
| `G30.B.108111` | 22 | [RS exact-MPN listing](https://uk.rs-online.com/web/p/multi-band-antennas/2884458) | 164 units ready to ship | GBP 23.88 each, excluding VAT | `COVERED_BY_DISPLAYED_STOCK` |
| `AA.166.A.301111` | 22 | [Mouser exact-MPN listing](https://www.mouser.lu/en/ProductDetail/Taoglas/AA.166.A.301111?qs=MLItCLRbWsy9cGP7TTjqEA%3D%3D) | 281 units can dispatch immediately; 500 on order with published expected date 2026-10-05; factory lead time 16 weeks beyond displayed stock | EUR 23.80 each at quantity 10 | `COVERED_BY_DISPLAYED_STOCK` |
| `TI.89.B.2111W` | 22 | [DigiKey exact-MPN listing](https://www.digikey.ee/en/products/detail/taoglas-limited/TI-89-B-2111W/29407998) | 49 units in stock; listing states average ship time 1–3 days; manufacturer standard lead time 13 weeks | EUR 9.673 each at quantity 10 | `COVERED_BY_DISPLAYED_STOCK` |
| `CAB.0243` | 66 | [DigiKey exact-MPN listing](https://www.digikey.com/en/products/detail/taoglas-limited/CAB-0243/24770240) | 1,504 units in stock; listing states average ship time 1–3 days; manufacturer standard lead time 16 weeks | USD 5.2068 each at quantity 50 | `COVERED_BY_DISPLAYED_STOCK` |

## Historical set-closure observation

- Four of the eight monitored exact-MPN lines have a public listing whose
  displayed stock covers the complete EVT-20 quantity: `G30.B.108111`,
  `AA.166.A.301111`, `TI.89.B.2111W`, and `CAB.0243`.
- `RB40`, `SCC075010060R`, and `SBS050150200` have usable public price references,
  but the complete required quantity is not confirmed by the public pages.
- The observed `SLP080S-12M` listing was explicitly discontinued/unavailable.
  Its displayed USD 177.63 is a historical budget reference, not an orderable
  offer and not an engineering release blocker.
- A complete procurement set is therefore **not yet confirmed** from public
  listings. Customer procurement must resolve any order-time alternative through
  the controlled no-substitution/ECO process; the engineering project does not
  wait for availability replies.

## Budget linkage

The controlled cost model is in `EVT_PRE_20_BOM_PRICE_ESTIMATE_REV_A.csv` and the
`Cost estimate` worksheet of `EVT_PRE_20_BOM_REV_A.xlsx`.

- EVT-20 all-in planning total: **RUB 4,250,780**.
- Eight public-price rows: **RUB 2,235,600**.
- Remaining 116 low-confidence engineering-estimate rows: **RUB 2,015,180**.
- Planning total per station: **RUB 212,539**.

These RUB values are rounded landed-cost planning allowances.  They are not a
quotation and exclude the effect of the final ship-to address, payment terms,
currency conversion date, and supplier-specific freight or hazardous-goods fees.
