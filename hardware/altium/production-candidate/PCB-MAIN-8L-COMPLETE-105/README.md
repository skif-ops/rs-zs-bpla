
# PCB-MAIN 8L COMPLETE-105 — primary Altium production candidate

Status: **PRIMARY EVT 8L PRODUCTION CANDIDATE / HOLD FOR DFM**. Manufacturing is not authorized.

This directory contains the Altium Designer 26.10.1 Trial conversion of PCB-MAIN COMPLETE-105 Rev.B. On 2026-10-16 the exact 8-layer candidate was promoted to `hardware/kicad/native/PCB-MAIN`; the former 6-layer source remains preserved under `hardware/kicad/retired`. The accepted KiCad source and this Altium conversion remain in the repository and release archive.

## Verified results

- Altium project compile: 0 errors, 146 unsuppressed warnings (64 missing component models, 43 nets with no driving source, 39 nets with possible connection problems).
- KiCad 10.0.6 ERC: 0 violations.
- KiCad board DRC: 0 errors, 0 unconnected items, 30 warnings (7 dangling vias, 23 silk-over-copper).
- KiCad-to-Altium parity: 5969/5969 routed segments, 5856/5856 physical paths, 251 components, 1143 pads, 853 vias and 185 named nets; no missing/extra route and no wrong copper layer.
- Altium DRC: 0 clearance, short, unrouted, modified-polygon, width or hole-size violations. Three `Net Antennae` via warnings remain at (32.809, 38.010), (47.762, 37.361), and (57.977, 32.251) mm.
- Final PCB SHA-256: `BFA1355CFE70B9794507C58FFD22923FBAEB3234DECDDB595796E8C0441141CF`.

## Generated outputs

`Project Outputs for PCB-MAIN/` contains Gerber X2 for all eight copper layers, mask/paste/legend/profile layers, plated round/slot NC drill files, metric Pick&Place, IPC-D-356A testpoint output, STEP, DRC reports, a 21-page documentation PDF and an Altium-compiled BOM extract.

No separate NPTH drill file was emitted by Altium because the converted board contains no NPTH drill objects in the output job. This must be confirmed during DFM.

## Open release gates

- disposition of the three antenna-via warnings;
- fabricator stackup, copper and controlled-impedance confirmation;
- confirmation that EMS/fabricator quotations reference the reconciled Rev.B 8-layer BOM and JLC08161H-3313 order profile;
- reconciliation of 248 compiled schematic components versus 251 board component objects;
- RF/GNSS/cellular review, DFM, independent Review B, DNP/polarity and first-article checks.

See `validation/PCB-MAIN-validation-summary-2026-10-15.json` and the final `.drc`/HTML reports for machine-readable evidence.
