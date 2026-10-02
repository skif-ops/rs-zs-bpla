# PCB-MAIN SIM_MUX_SEL candidate 066 — native gate (2026-09-27)

Candidate PCB, candidate-only project rules, generator and native ERC/DRC
evidence are in `hardware/kicad/candidates/PCB-ROUTING-P2-SIM-MUX-SEL-066/`.
The cumulative candidate builds on 065 and uses the corrected MCU sheet
from 062 for full-hierarchy ERC. The authoritative PCB-MAIN 003 and
schematic remain unchanged.

- KiCad 9.0.9 Actions run:
  https://github.com/skif-ops/rs-zs-bpla/actions/runs/36309060929 — success.
- `SIM_MUX_SEL` U1.97 (47.5, 22.25) joins the existing F.Cu branch at
  (40.9, 20.825) through F.Cu escapes and a three-segment B.Cu route.
  Total new trace length is 8.7609 mm at 0.15 mm width. Two candidate
  process 0.25/0.15 mm through vias sit at (47.5, 21.4) and
  (41.6, 20.7), 1.2134 and 1.4792 mm from existing GND_DIGITAL
  stitching vias respectively.
- All new traces are screened against existing copper on their layer
  at 0.20 mm clearance, all new via barrels against copper on six
  layers, and all new copper and drills against non-net holes at
  0.25 mm drill clearance. The route is wholly within the In1.Cu
  GND_DIGITAL, In2.Cu GND_MIC and In4.Cu GND_DIGITAL zone outlines.
- Native filled-board comparative DRC is **77 → 76** unconnected items
  with **0 new errors** and no schematic-parity differences. The 76
  remaining connections span 56 nets. Full-hierarchy ERC has
  **0 violations**. Generator `--check` passes; candidate PCB SHA-256
  is `f0d62adb45d766521c1af48bff1e0cb4555f703694d34cc9b668f3a7608d8362`.

SIM switching integrity, complete connectivity, return-path and
0.25/0.15 mm via DFM remain Review B items. This candidate is not a
manufacturing release.
