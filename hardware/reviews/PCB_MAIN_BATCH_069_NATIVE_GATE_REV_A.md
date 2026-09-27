# PCB-MAIN candidate 069 — five signal connections (2026-09-27)

Candidate PCB, manifest, generator and native gate evidence:
`hardware/kicad/candidates/PCB-ROUTING-P2-BATCH-069/`. It builds on
068; authoritative PCB-MAIN 003 is unchanged.

- KiCad 9.0.9 Actions run:
  https://github.com/skif-ops/rs-zs-bpla/actions/runs/36310817626 — success.
- Five connections: `AAD_CFG_1V8_U7`, `LORA_RESET_N`,
  `LORA_SCK_U10`, `SIM1_DET`, `SWCLK`. New trace length is 117.8945 mm
  at 0.15 mm width with twelve 0.25/0.15 mm through vias. `SIM1_DET`
  uses candidate-only via-in-pad transitions; DFM acceptance is open.
- Geometry checks cover foreign copper on all affected layers, holes,
  new route conflicts, edge keepout, endpoint continuity and the
  nearest ground reference for each routed layer. Native filled-board
  comparative DRC is **60 → 55** unconnected items on 39 nets, with
  **zero new errors or warnings**. Nine-sheet ERC has **0 violations**;
  `--check` passes. Candidate PCB SHA-256:
  `1c358e1ef89165c05f9c6987bcfaf34c9848464400fc9f20c9ebe4846339b78d`.

Complete routing, LoRa/SIM signal and return timing, via-in-pad DFM
and CAM remain Review B items. No manufacturing release.
