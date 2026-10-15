# EVT-PRE-20 full production candidate — 2026-10-16

Status: **HOLD FOR ENGINEERING CLOSURE**. Manufacturing and assembly are not authorized.

The external archive `EVT-PRE-20_FULL_PRODUCTION_CANDIDATE_2026-10-16.zip` was built from clean commit `ba16d9968064b95e9b657c5245129443496234bf` and contains Altium and preserved KiCad sources for PCB-MAIN, PCB-PWR and PCB-MIC, current Gerber/drill/IPC-D-356/BOM/Pick&Place/STEP outputs, review evidence, and program manufacturing documents.

- Archive bytes: `24438596`
- Archive SHA-256: `DCFB935C96FDBAF156F449658976D024986703DEC3459ACC1EB1C16881475802`
- Payload files: `1069`
- ZIP members: `1070`
- Manifest, CRC, payload hashes and path confinement: `PASS`

The active six-layer PCB-MAIN remains incomplete with 203 DRC errors and 499 unconnected items. The included routed eight-layer Altium candidate conflicts with the active six-layer authority and cannot replace it without a controlled design decision. PCB-PWR and PCB-MIC also retain the Review gates recorded in `STATUS.json` and the final audit reports.
