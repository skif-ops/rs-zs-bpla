# EVT-PRE-20 full production release - 2026-10-16

Status: **EVT BUILD RELEASED / CUSTOMER CHECKOUT REQUIRED**.

The external archive `EVT-PRE-20_FULL_PRODUCTION_RELEASE_2026-10-16.zip` was built from clean commit `e208d91ddc251b72c7643881955fb94bc309f17f`. PCB-MAIN Rev.B with eight copper layers is the primary EVT baseline. The selected stack is `JLC08161H-3313`, nominal thickness 1.6 mm. The former six-layer Rev.A source and CAM are retained under `PCB-MAIN/History/`.

The archive contains Altium projects and preserved KiCad sources for PCB-MAIN, PCB-PWR and PCB-MIC; Gerber, drill, IPC-D-356, BOM, Pick&Place and STEP outputs; DRC/ERC evidence; exact PCBA supply mapping; harness documents; and a validated 3D-print housing package.

- Archive bytes: `28084491`
- Archive SHA-256: `034313156E6E104DE730D17EBAFB27AE0158EC46B9071D7AFF1D40DCFC24571D`
- Payload files: `1181`
- ZIP members: `1182`
- Manifest, CRC, payload hashes and path confinement: `PASS`
- Strict EVT build release audit: `PASS`, 61/61 checks

Customer order placement remains outside the repository. At checkout the customer confirms the controlled stack and POFV options, resolves job-specific parser/DFM findings without geometry changes, compares the generated production files and confirms them in the factory portal.

Physical first-article PCB/PCBA, PWR, RF, MIC acoustic, harness and housing checks remain mandatory before releasing the held remainder of the EVT lot and before serial transfer.

`PAYLOAD_SHA256SUMS.json` records every archived payload file.
