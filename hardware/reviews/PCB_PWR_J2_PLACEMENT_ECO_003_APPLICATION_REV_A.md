# PCB-PWR J2 placement ECO-003 — application, Rev.A

Status: `APPLIED / NOT FOR MANUFACTURE`

- Decision: candidate SHA-256
  `b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6` accepted by the
  customer in chat on 2026-09-24 (together with the separate decision "PCB-PWR outer
  layers 1 oz", handled as ECO-004).
- Predecessor board: routing 010,
  `e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469`.
- Applied by `tools/apply_pcb_pwr_j2_placement_eco_003_rev_a.py` through the
  `ci-apply` workflow, bot commit `d222ee5d` on `feature/pcb-pwr-j2-eco-003`;
  `--check` passes on the result.

## What changed

- Native board: exactly the nine accepted placement lines (J2, U5, C7, C8, NT1–NT3,
  DNP R13/R14); copper, nets, rotations and outline unchanged.
- `tools/audit_pcb_pwr_placement_clearance_rev_a.py`: `rotate()` follows KiCad's
  y-down convention; ECO-003 poses are an exact override bound to the ECO-003 board
  SHA (same pattern as ECO-002). `tools/audit_pcb_pwr_layout_candidate_rev_a.py`
  carries the same override.
- Predecessor interlocks 006–010 (`pcb_pwr_hot_loop_006_board.py`, application
  generators/audits, historical runners) accept the ECO-003 successor, verified by
  regeneration from the committed routing-010 candidate; routing 010 replays on its
  committed candidate.
- `hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json`: placement-clearance and pre-route
  controls recomputed by their audits.

The placement authority CSV, the DIM-003 authority record and all historical
contracts are byte-identical: historical packets bind their SHA-256. The corrected
J2 reference (pin-1 origin `[81.08, 40.0]`, housing flush with the east edge x = 90,
body inside the accepted DIM-003 box x 80..130, y 35..60) is recorded here and in
`J2_PLACEMENT_ECO_003_POSES`.

## Verification before commit

- All `ci.yml` python steps (single- and multi-line PCB-PWR interlocks) pass on the
  applied tree; branch isolation passes.
- EVT build release audit: `pcb-pwr_pads_within_outline` passes; blockers 12 -> 11.
- KiCad 9.0.9 comparative DRC of the exact candidate (CI job
  `pcb-pwr-j2-placement-eco-003-drc`): J2 `copper_edge_clearance` x3 and H3/R13
  `courtyards_overlap` removed, no new error fingerprint, unconnected not grown.

## Open

- `.github/workflows/pcb-native.yml` step "KiCad 9 comparative DRC for PCB-PWR 3V8
  output bulk routing 010" compares the native board byte-for-byte with the 010
  candidate (`cmp`); that line must be removed by the owner (the following
  `generate_..._010_application_rev_a.py --check` accepts the ECO-003 successor).
- U3/U4 clearance and outer copper: ECO-004.
- Remaining routing, DRC closure, CAM, DFM and Review B.
