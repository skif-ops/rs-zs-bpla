# PCB-MAIN fabrication notes - EVT-PRE-20 Rev.B

Status: **EVT BUILD AUTHORIZED / CUSTOMER CHECKOUT REQUIRED.**

- Board: PCB-MAIN COMPLETE-105 Rev.B.
- Copper layers: 8 (`F.Cu; In1.Cu; In2.Cu; In3.Cu; In4.Cu; In5.Cu; In6.Cu; B.Cu`).
- Finished thickness: 1.6 mm.
- Preferred order stack: JLC08161H-3313.
- Copper target: outer 1 oz, inner 0.5 oz.
- Finish: ENIG.
- EVT impedance disposition: manufacture as routed without a controlled-impedance order; validate installed RF, GNSS, cellular and LoRa performance on first articles.
- POFV: epoxy resin fill, planarize and copper cap all 76 controlled sites (74 source-board sites plus 2 documented CAM overrides). Solder-mask tenting alone is prohibited.
- Electrical test: 100 percent against the included IPC-D-356 data.
- DRC: 0 errors, 0 unconnected items. Three Altium Net Antennae warnings are accepted import-rule artifacts; native KiCad DRC and KiCad-to-Altium route/physical-path parity are clean.

The customer must select the stated stack/copper/finish and POFV process, resolve upload-parser/DFM findings without geometry changes, compare the job-specific production files with this package and confirm them in the factory portal.
