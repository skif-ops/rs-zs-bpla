# EVT lot selection control — Rev.A

`EVT-PRE-20` reserves traceable serial capacity through `DIO-EVT-020`. The
customer-selected procurement scenario is `EVT-20`: 20 stations using serials
`DIO-EVT-001` through `DIO-EVT-020`. The 4- and 10-station columns remain
controlled comparison and contingency calculations only.

The wider program demand is two EVT-20 production sets plus one bench station
(`20 + 20 + 1 = 41`). This does not rename the controlled per-set configuration or
mix scenario columns. Its aggregate quantities are controlled separately in
`hardware/EVT_PROGRAM_2X20_PLUS_1_PROCUREMENT_REV_A.csv`: two EVT-20 spare pools
are included and the bench station adds no third pool. Serial identities for the
second set (`DIO-EVT-021` through `DIO-EVT-040`) and bench (`DIO-EVT-B01`) are
reserved in `manufacturing/LOT_SERIAL_REGISTER_LOT2_AND_BENCH.csv`; individual
build travellers remain required before assembly starts.

The selected scenario controls the corresponding `Qty_N`, `Spares_N` and
`Procure_qty_N` columns in `hardware/EVT_PRE_20_BOM_REV_A.csv` and the matching
`Required_qty_N` column in `hardware/CHINA_PROCUREMENT_RFQ.csv`. Mixing columns
from different scenarios is prohibited.

All 20 reserved serials are assigned to the selected EVT lot and remain in
`AWAITING_BUILD` state until the hardware manufacturing gate passes. Every assembled
station receives 100 percent EOL and every applicable all-unit EVT test.

Vacuum casting is the primary housing process for every selected-lot station.
The equal-quantity 3D-print fallback remains zero in procurement until its
separate approval. Injection molding remains source-data and DFM only, with no
pilot tooling or molded-part quantity.

Selection is `SELECTED: EVT-20`. Comparable RFQs may still be collected for 4,
10 and 20 stations, but only `Procure_qty_20` and `Required_qty_20` are eligible
for the selected-lot purchase package. The customer owns supplier selection,
stock, price, MOQ, payment and delivery confirmation and the project does not
wait for those commercial fields. Selection does not authorize fabrication or
assembly: strict BOM QG-2, released PCB/mechanical data, checkout DFM,
first-article evidence and applicable physical EVT qualification remain
blocking. Named-site technical reply letters are not required for this test lot.
