# PCB-MAIN candidate 070 — microphone rail and FB1 output (2026-09-27)

Candidate board, route manifest, generator and native gate evidence:
`hardware/kicad/candidates/PCB-ROUTING-P2-POWER-070/`. It builds on
069; authoritative PCB-MAIN 003 is unchanged.

- KiCad 9.0.9 Actions run:
  https://github.com/skif-ops/rs-zs-bpla/actions/runs/36311257488 — success.
- Four `1V8_MIC` supply branches use 0.25 mm traces and nine
  0.50/0.30 mm through vias. A 3.61 mm, 0.8 mm F.Cu branch connects
  FB1.2 to the existing `3V8_MODEM_BB` through via. Total new trace
  length is 100.7369 mm.
- The generator checks copper and drill clearances, conflicts among
  routes, edge keepout, and the nearby reference outlines. The FB1
  F.Cu branch is above the In1.Cu GND_DIGITAL outline, which makes
  modem current return at that boundary a specific Review B item.
- Native filled-board comparative DRC is **55 → 50** unconnected
  items on 38 nets, with **zero new errors or warnings**. Nine-sheet
  ERC has **0 violations**; `--check` passes. Candidate PCB SHA-256:
  `0d96887854926d95f486313d23655898dbeb34269577d1494d95413578e36546`.

Microphone rail drop and noise, modem burst-current return, via DFM,
complete connectivity and CAM remain Review B items. No manufacturing
release.
