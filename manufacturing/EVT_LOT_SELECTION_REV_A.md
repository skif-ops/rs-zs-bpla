# EVT lot selection control — Rev.A

`EVT-PRE-20` reserves traceable serial capacity through `DIO-EVT-020`; it no
longer means that twenty stations must be purchased or assembled. Exactly one
procurement scenario from `EVT_LOT_SELECTION_REV_A.csv` must be selected before
an RFQ becomes a purchase release: 4, 10 or 20 stations.

The selected scenario controls the corresponding `Qty_N`, `Spares_N` and
`Procure_qty_N` columns in `hardware/EVT_PRE_20_BOM_REV_A.csv` and the matching
`Required_qty_N` column in `hardware/CHINA_PROCUREMENT_RFQ.csv`. Mixing columns
from different scenarios is prohibited.

Only the leading serial range for the selected scenario is activated. The
remaining serials stay reserved and unbuilt. Every assembled station receives
100 percent EOL and every applicable all-unit EVT test; acceptance denominators
therefore follow the selected lot rather than the 20-serial capacity.

Vacuum casting is the primary housing process for every selected-lot station.
The equal-quantity 3D-print fallback remains zero in procurement until its
separate approval. Injection molding remains source-data and DFM only, with no
pilot tooling or molded-part quantity.

Selection is currently `NOT_YET_SELECTED`. This state permits comparable RFQs
for all three quantities but blocks purchase release and physical EVT population
assignment.
