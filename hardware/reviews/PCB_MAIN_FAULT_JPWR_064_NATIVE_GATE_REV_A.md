# PCB-MAIN FAULT J_PWR candidate 064 — native gate (2026-09-27)

Candidate PCB, project and native ERC/DRC evidence are in
`hardware/kicad/candidates/PCB-ROUTING-P2-FAULT-JPWR-064/`.
Candidate 064 builds on 063 and retains the corrected MCU sheet from
062 during the native check. The authoritative PCB-MAIN 003 and
schematic remain unchanged.

- KiCad 9.0.9 Actions run:
  https://github.com/skif-ops/rs-zs-bpla/actions/runs/36307648451 — success.
- `FAULT` joins J_PWR.8 at (11.92, 26.5) to R103.1 at
  (26.675, 22.5): four 0.15 mm B.Cu segments, 15.1362 mm total,
  and a 1.5876 mm F.Cu segment. The new 0.25/0.15 mm through via
  at (25.1, 22.7) is outside R103.1. Total new copper length is
  16.7239 mm.
- Geometry screening found at least 0.20 mm other-net copper
  clearance and 0.25 mm drill-to-drill clearance. Both layer legs
  lie within the In1.Cu GND_DIGITAL, In2.Cu GND_MIC and In4.Cu
  GND_DIGITAL zone outlines.
- The copied full nine-sheet hierarchy has native ERC **0 violations**.
  Filled-board comparative DRC is **78 → 77** unconnected items across
  **57 nets**, with **0 new errors** and no schematic-parity differences.
  The separate `FAULT` connection to TP_EOL.8 remains open.
- Generator `--check` passes against the committed candidate and
  `SUMMARY.json`; PCB SHA-256
  `393f131f58c8285026b01f99770362970ad631ede069004e0f6735d02accb827`.

The FAULT signal return, particularly the layer transition near R103,
small-via fabrication, test-pad branch and complete board routing
remain Review B items. This candidate is not a manufacturing release.
