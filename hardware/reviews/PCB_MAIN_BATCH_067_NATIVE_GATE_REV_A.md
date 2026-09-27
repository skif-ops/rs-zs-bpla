# PCB-MAIN candidate 067 — ten signal connections (2026-09-27)

Candidate, route manifest, generator and native ERC/DRC evidence:
`hardware/kicad/candidates/PCB-ROUTING-P2-BATCH-067/`. The cumulative
board builds on 066; the authoritative PCB-MAIN 003 remains unchanged.

- KiCad 9.0.9 native Actions run:
  https://github.com/skif-ops/rs-zs-bpla/actions/runs/36310099284 — success.
- Ten connections: `AAD_CFG_1V8_FANOUT`, `CELL_DTR_U16`, `FAULT`,
  `I2C2_SCL_U1`, `I2C2_SDA_U1`, `NRST`, `REV_STRAP0`, `SIM_MUX_EN`,
  `SWDIO` and `USB_VBUS_SENSE`. New trace length is 177.2818 mm at
  0.15 mm width; 26 new through vias are 0.25/0.15 mm under the
  candidate-only process overlay. Individual paths and anchors are
  recorded in `ROUTES.json` and `SUMMARY.json`.
- The generator checks every new segment against all foreign copper on
  its layer, every via against copper on all six layers, drill clearance
  against existing holes, route-to-route conflicts, edge keepout and
  reference zone outlines. Digital/modem and digital/microphone boundary
  crossings are identified for Review B. The `SIM_MUX_EN` path ends at
  the exact endpoint of its existing F.Cu track.
- Native filled-board comparative DRC is **76 → 66** open connections
  across 49 nets, with **zero new errors or warnings**. Nine-sheet ERC
  has **0 violations** and no schematic-parity change. Generator
  `--check` passes. Candidate PCB SHA-256:
  `22391d5e5fda68ec30438406a4497ff96b1b26d6acb75a4cd9738beb8024d16d`.

Complete connectivity, cross-domain return, supply/clock integrity,
small-via DFM, and CAM remain Review B items. This is not a
manufacturing release.
