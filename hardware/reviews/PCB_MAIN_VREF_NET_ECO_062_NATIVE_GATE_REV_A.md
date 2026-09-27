# PCB-MAIN VREF bypass candidate 062 — native gate (2026-09-27)

Candidate PCB and corrected MCU sheet remain in
`hardware/kicad/candidates/PCB-ROUTING-P2-VREF-3V3-062/`; the authoritative
PCB-MAIN 003 and native schematic are unchanged.

- KiCad 9.0.9 Actions run:
  https://github.com/skif-ops/rs-zs-bpla/actions/runs/36305521530 — success.
- ERC of the copied full nine-sheet hierarchy with the two corrected C10/C11
  labels: **0 violations**.
- Filled-board comparative DRC: **80 → 79** unconnected items across **58
  nets**; **0 new errors** and empty schematic-parity list. `VREF+` no longer
  appears among open nets. The `3V3_DIGITAL` net retains six open items.
- The generator passes `--check` against committed PCB, MCU sheet, ERC/DRC
  JSON and `SUMMARY.json`; PCB SHA-256
  `ae099f301e6dff1d93cb67141d0b28c416d8cad86b6f46eb120c9e2d0553be43`.
- `AUTHORITY_DELTA_062.patch` is the exact, unapplied correction for the
  C10/C11 passive-support rows and removal of the obsolete separate
  `VREF+` routing row; `git apply --check` passes on this branch.

This resolves the disconnected bypass nets in the **candidate** only. The
analog-reference decoupling loop, 3V3 current/return, complete routing,
Review B, DFM/CAM and manufacturing approval remain open. Apply the
schematic, PCB and authority delta together when the authoritative board
is promoted; do not cherry-pick only the F.Cu traces.
