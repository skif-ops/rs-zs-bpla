# PCB-PWR J2 placement ECO-003 — candidate, Rev.A

Status: `CANDIDATE / HUMAN ACCEPTANCE REQUIRED / NOT APPLIED / NOT FOR MANUFACTURE`

## Finding

The authoritative PCB-PWR board (routing 010, SHA-256 `e46097f8…`) places J2
(Molex 43045-1202, Micro-Fit 3.0 2x6 right angle) at `(90, 56, -90)`. In KiCad
geometry 12 of its 14 pads and NPTH pegs lie on or outside the 90 x 60 mm
outline: the pin field runs from y = 56 to y = 71, the pegs sit at x = 94.32 and
the housing spans x 89.0..98.9, y 52.4..74.6. The engineering snapshot DRC of
2026-09-24 reports only three `copper_edge_clearance` errors because KiCad DRC
does not flag footprints lying outside a rectangular outline.

Root cause: the placement audits transform footprint geometry with
`x' = x cos a - y sin a, y' = x sin a + y cos a` (y-up convention). KiCad boards
are y-down: `x' = x cos a + y sin a, y' = -x sin a + y cos a`. For ±90° the two
differ by a mirror. The audit envelope of J2 therefore fell inside the DIM-003
service box and the clearance gate passed. The same `rotate()` exists in the
PCB-PWR and PCB-MAIN placement audits and in several candidate audits. A full
comparison of every ±90° footprint on all three boards shows that J2 on PCB-PWR is
the only footprint whose real placement is wrong; the two rotated PCB-MAIN
connectors are correctly placed in KiCad geometry. Correcting `rotate()` in the
historical audits is part of the ECO-003 application step.

## Proposed change (placement only)

| Ref | Base | Candidate | Reason |
|---|---|---|---|
| J2 | (90, 56, -90) | (81.08, 40.00, -90) | body flush with east edge x = 90.00; body x 80.09..90.00, y 36.43..58.58 inside the accepted DIM-003 box x 80..130, y 35..60 |
| U5 | (76, 46) | (74.4, 46) | clear J2 rear pin row |
| C7 | (76, 50) | (74.4, 50) | clear J2 rear pin row |
| C8 | (76, 54) | (74.9, 54) | clear J2 rear pin row and the H3 D10 exclusion |
| NT1 | (79, 38) | (75.6, 40.12) | GND_MODEM join moved out of the J2 pin field |
| NT2 | (79, 41) | (75.6, 48.52) | GND_DIGITAL join moved out of the J2 pin field |
| NT3 | (79, 44) | (75.6, 52.00) | GND_MIC join moved out of the J2 pin field |
| R13 (DNP) | (71, 51) | (74.6, 56.5) | clears the pre-existing H3/R13 courtyard overlap |
| R14 (DNP) | (73.5, 51) | (74.6, 58) | clears C7 after its move |

Rotations, footprints, nets, values, outline, the 53 accepted trace items and
both `GND_PWR` zones are unchanged. The textual delta is exactly these nine
`(at …)` lines.

DIM-003 box, mating direction (+X east), cable exit and all 18 accepted rows are
unchanged. Only `reference_xy_mm` of J2 in
`hardware/reviews/PCB_PWR_DIM_003_EVT_AUTHORITY_REV_A.json` changes at
application from `[90.0, 56.0]` to the pin-1 origin `[81.08, 40.0]`. The harness
datum (mating-face centreline at the east exit plane) moves from y = 56 to
y = 47.5; the 8.5 mm shift is inside the accepted 10 % service allowance.

## Evidence

- Generator: `tools/generate_pcb_pwr_j2_placement_eco_003_candidate_rev_a.py`
  materialises BASE and CANDIDATE from the authoritative board; base SHA-256
  `e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469`, candidate
  SHA-256 `b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6`
  (pinned in the generator; board files are not committed at candidate stage).
- Independent audit: `tools/audit_pcb_pwr_j2_placement_eco_003_candidate_rev_a.py`
  (KiCad y-down geometry). Candidate: pads outside outline 0; J2 body inside the
  DIM-003 box and flush with the east edge; courtyard overlaps 0 (DNP, PCB
  features and D10 circles included); fitted minimum clearance 0.20 mm; mounting
  exclusion conflicts 0; accepted copper within 0.20 mm of a moved footprint 0.
  Base: 12 pads outside outline, H3/R13 overlap.
- KiCad 9.0.9 comparative DRC: CI job `pcb-pwr-j2-placement-eco-003-drc`
  (`ci/pcb_pwr_eco_003_drc.sh`, pinned official image). Expected: the three J2
  `copper_edge_clearance` errors and the H3/R13 `courtyards_overlap` error
  disappear, no new error fingerprint, unconnected items do not grow.

## Out of scope

- U3/U4 (LMR60440) pad-to-pad clearance 0.125 mm against 2 oz outer copper:
  requires the stackup decision (1 oz outer proposed) and a local clearance rule;
  the four `clearance` errors stay until then.
- Library copies of H1–H4 and L1/L2 (text/silk only, copper identical).
- Remaining routing, DRC closure, CAM, DFM and Review B.

Application requires human acceptance of this exact candidate SHA-256.
