# PCB-MAIN candidate 068 — six signal connections (2026-09-27)

Candidate, route manifest, generator and native ERC/DRC evidence:
`hardware/kicad/candidates/PCB-ROUTING-P2-BATCH-068/`. It builds on
the comparative-DRC-clean 067 candidate. PCB-MAIN 003 is unchanged.

- KiCad 9.0.9 Actions run:
  https://github.com/skif-ops/rs-zs-bpla/actions/runs/36310559015 — success.
- Six connections: `HW_REV1`, `I2C2_SCL_BUS`, `LORA_NSS_U1`,
  `PDM_DATA3`, `SD_D2_CARD`, `TAMPER_IN_U1`. New trace length is
  140.6642 mm at 0.15 mm width, with 19 new 0.25/0.15 mm through
  vias under candidate-only process rules. The `SD_D2_CARD` route
  terminates at the existing (90.325, 23.0) mm via centre.
- The generator checks copper, hole and inter-route clearance, edge
  keepout and GND_DIGITAL/GND_MIC reference zone outlines. Native
  filled-board comparative DRC is **66 → 60** unconnected items on
  44 nets, with **zero new errors or warnings**. Nine-sheet ERC is
  **0 violations**; generator `--check` passes. Candidate PCB SHA-256:
  `d78d34cf477825f4b15ac1e68294b1cb22be83184ed53c899022f95bcd5025d8`.

SD/PDM timing, return path, small-via DFM, complete connectivity and
CAM remain Review B items. No manufacturing release.
