
# PCB-MAIN 8L COMPLETE-105 — Altium production candidate

Status: **PRODUCTION CANDIDATE / HOLD FOR DFM**. Manufacturing is not authorized.

This directory contains the Altium Designer 26.10.1 Trial conversion of the exact KiCad 8-layer candidate at commit `592f955d88570dcbb5eb41d59848db05aac84f88` and path `hardware/kicad/candidates/PCB-MAIN-8L-COMPLETE-105`. The KiCad source remains preserved in the repository and in the release archive.

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
- reconciliation of the global procurement BOM, which still identifies PCB-MAIN as six-layer;
- reconciliation of 248 compiled schematic components versus 251 board component objects;
- RF/GNSS/cellular review, DFM, independent Review B, DNP/polarity and first-article checks.

See `validation/PCB-MAIN-validation-summary-2026-10-15.json` and the final `.drc`/HTML reports for machine-readable evidence.
