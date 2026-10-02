# PCB-MAIN candidate 061 — local preflight (Rev A, 2026-09-27)

Status: **geometry probe only; native KiCad 9 comparative DRC pending**. This is a
continuation of candidate 060 in draft PR #93 and does not modify the
authoritative PCB-MAIN 003 board.

## Proposed connection

The `SIM1_RST_CONN` C54/J6 front-side island remains separate from R50.2 in
candidate 060. A 0.25/0.15 mm through via at (18.175, 16.0) lands on the
existing C54.1 F.Cu trace outside the capacitor pad. A 0.15 mm In3.Cu segment
joins it to the existing R50.2 through via at (24.075, 16.7). Segment length:
5.9414 mm; one new via. No component moves or removal of earlier copper.

## Local checks

- SHA-256 of input 060: `397917294ca238fa72fd17548a77518b56887b77af361606bb4062fbf96afacd`.
- SHA-256 of generated 061 PCB: `b733b350b14dcbad0c62e91f7b58a715a891b418bdeac28d17f88277e724b4d0`.
- Geometry parser accepts the board; trace/via item count increases 3668 → 3670.
- The new via overlaps the existing same-net F.Cu trace; it is outside C54.1's
  copper pad. Minimum calculated clearance to other-net copper at that via is
  0.2925 mm (In3.Cu); on F.Cu it is 0.3681 mm. Minimum clearance of the new
  In3.Cu trace to other-net copper is 0.3425 mm. The new drill-to-existing-hole
  clearance is at least 0.8503 mm. These are shape-screening results, not DRC.
- The line is entirely within the In4.Cu `GND_MODEM` zone **outline**. Copper
  fill and the actual SIM reset return path still need native KiCad DRC and
  Review B. In2.Cu is `GND_MIC` here, so mixed-domain coupling requires review.

## Gates

The 060 baseline has **81** unconnected DRC items. Do not record 80 until the
061 workflow completes and its filled-board comparative DRC shows one fewer
unconnected item with no new errors. The generator and pinned KiCad 9.0.9
workflow are `tools/apply_pcb_main_sim1_rst_c54_061_rev_a.py` and
`.github/workflows/pcb-main-candidate-061.yml`.

The 0.25/0.15 mm via remains subject to fabrication approval. SIM return,
complete connectivity, Review B, DFM/CAM and manufacturing release remain
open. Do not apply this PCB to `hardware/kicad/native/PCB-MAIN`.
