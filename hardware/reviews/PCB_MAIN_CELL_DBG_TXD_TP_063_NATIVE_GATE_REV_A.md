# PCB-MAIN CELL_DBG_TXD_TP candidate 063 — native gate (2026-09-27)

Candidate PCB, project and native ERC/DRC evidence are in
`hardware/kicad/candidates/PCB-ROUTING-P2-CELL-DBG-TXD-TP-063/`.
Candidate 063 builds on candidate 062, including its corrected MCU sheet;
the authoritative PCB-MAIN 003 and schematic remain unchanged.

- KiCad 9.0.9 Actions run:
  https://github.com/skif-ops/rs-zs-bpla/actions/runs/36306717954 — success.
- The 0.15 mm `CELL_DBG_TXD_TP` route joins the existing through via at
  (46.474, 31.7499) to a new 0.25/0.15 mm through via at (47.9, 31.4)
  over 1.4683 mm of In3.Cu. A 2.1563 mm B.Cu segment connects the new
  via to TP_CELL_DBG.2 at (49.54, 30.0). Total new copper length:
  3.6246 mm. There is no via in the test pad.
- Geometry screening found at least 0.20 mm other-net copper clearance
  and 0.25 mm drill-to-drill clearance. Both segments are within the
  In1.Cu GND_DIGITAL, In2.Cu GND_MIC and In4.Cu GND_DIGITAL zone outlines.
  The nearest GND_DIGITAL stitching via to the new via is 2.997 mm away.
- The copied full nine-sheet hierarchy has native ERC **0 violations**.
  Filled-board comparative DRC is **79 → 78** unconnected items across
  **57 nets**, with **0 new errors** and no schematic-parity differences.
  The `CELL_DBG_TXD_TP` unconnected item is closed.
- Generator `--check` passes against the committed candidate and
  `SUMMARY.json`; PCB SHA-256
  `02147cb8e1af7ef426a69e54dd47da0538160ac2944df346d8e704f97de8a121`.

Test-pad access, signal return around the layer transition, small-via
fabrication and complete board routing remain Review B items. This
candidate is not a manufacturing release.
