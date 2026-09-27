# PCB-MAIN FAULT return stitch candidate 065 — native gate (2026-09-27)

Candidate PCB, project and native ERC/DRC evidence are in
`hardware/kicad/candidates/PCB-ROUTING-P2-FAULT-RETURN-065/`.
Candidate 065 builds on 064 and retains the corrected MCU sheet from
062 during the native check. The authoritative PCB-MAIN 003 and
schematic remain unchanged.

- KiCad 9.0.9 Actions run:
  https://github.com/skif-ops/rs-zs-bpla/actions/runs/36308501262 — success.
- One `GND_DIGITAL` 0.50/0.30 mm through via at (25.1, 23.9)
  is 1.20 mm from the `FAULT` signal transition at (25.1, 22.7).
  It is inside the In1.Cu and In4.Cu GND_DIGITAL zone outlines.
- Minimum screened clearance to another net's copper is 0.3671 mm;
  minimum drill-to-drill clearance is 0.975 mm. Native filled-board
  comparative DRC remains **77 → 77** unconnected items, with
  **0 new errors** and no schematic-parity differences. Full-hierarchy
  ERC has **0 violations**.
- Generator `--check` passes against the committed candidate and
  `SUMMARY.json`; PCB SHA-256
  `12130d529609fc1c907f3b6a28508f8ad3e8933c1cc0b2ff380904e06dd4d9cb`.

The nearby stitch shortens the local return transition, but the
complete FAULT current path, TP_EOL.8 branch, ground-domain review,
small-via process and full board routing remain Review B items.
This candidate is not a manufacturing release.
