# Production BOM correction — Rev B

Date: 2026-09-29. Rev B supersedes the previously supplied `EVT_PRE_20_PRODUCTION_BOM_NO_PRICES_REV_A.csv` for PCB-PWR fabrication description.

**Corrected field:** procurement line `PR-003`, column `Package`. The prior `outer 2 oz target` wording was obsolete after ECO-004. The correct nominal fabrication specification is **four layers, outer 1 oz, inner 1 oz, ENIG**, board 90 × 60 × 1.6 mm. Factory stack ID and DFM checkout are to be confirmed by the customer with the selected PCB supplier at order placement; any supplier changes require documented review/ECO.

All 111 BOM data rows, item identities, population status, and quantities are unchanged from Rev A. The delivered DNP schedule remains applicable. There are no prices or unitemized totals in Rev B. D1 remains a controlled candidate pending surge-profile selection; the corrected fabrication field does not resolve that component decision.

**Files to forward together:** `EVT_PRE_20_PRODUCTION_BOM_NO_PRICES_REV_B.xlsx` and `EVT_PRE_20_PRODUCTION_BOM_NO_PRICES_REV_B.csv`. Cite Rev B in the order package and withdraw the Rev A fabrication wording from order instructions.

