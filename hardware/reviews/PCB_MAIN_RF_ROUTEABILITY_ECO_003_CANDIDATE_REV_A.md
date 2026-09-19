# PCB-MAIN RF routeability ECO-003 candidate — Rev.A

Status: `PROPOSAL / MACHINE GATE REQUIRED / SIGNATURE REQUIRED / NOT A FABRICATION RELEASE`

This package isolates the smallest placement change found during the first controlled
RF routeability pass. The authoritative board remains unchanged and unrouted. The
candidate is evidence for an ECO decision, not production copper.

## Proposed bounded placement delta

Only three footprints marked `UNLOCKED_LAYOUT_CANDIDATE` move:

| RefDes | Existing pose `(x, y, deg)` | Candidate pose `(x, y, deg)` | Purpose |
|---|---:|---:|---|
| `FL1` | `(61.00, 69.50, 0)` | `(60.50, 68.00, 0)` | place the GNSS SAW ports on the direct module/matching corridor |
| `D4` | `(61.00, 68.00, 0)` | `(58.25, 70.00, 90)` | retain shunt protection without forcing a long DC-block detour |
| `L2` | `(59.25, 69.50, 0)` | `(59.75, 70.25, 90)` | keep the biased-antenna matching branch compact |

No locked connector/module position, footprint, pad, net, board outline, mounting
feature or BOM identity changes. Strict 2D placement clearance passes with all 227
assembly envelopes controlled and zero component, mounting or tool-clearance conflict.

## RF route evidence

The candidate uses the committed public `JLC06161H-3313` engineering basis:
single-ended 50-ohm, non-coplanar traces on L1/`F.Cu`, referenced to L2/`In1.Cu`,
width `0.1509 mm`. It contains no signal via and no copper zone.

| Net | Segments | Routed length, mm |
|---|---:|---:|
| `CELL_RF` | 15 | 31.713834 |
| `CELL_RF_ANT` | 23 | 17.631728 |
| `GNSS_RF_ANT_BIASED` | 13 | 10.340990 |
| `GNSS_RF_DC_BLOCK` | 1 | 1.000000 |
| `GNSS_RF_FILTERED` | 12 | 18.644291 |
| `LORA_RF_ANT` | 15 | 13.088837 |
| `LORA_RF_MODULE` | 10 | 11.062185 |
| **Total** | **89** | **103.481866** |

The original placement forced the experimental `GNSS_RF_DC_BLOCK` path to
`21.516 mm`; this bounded delta makes it a direct `1.000 mm` segment.

Native KiCad connectivity changes from 718 to 703 unconnected relationships. The
reduction of 15 is exactly the sum of `(pad count - 1)` for the seven RF nets, so the
pass closes every proposed RF net without hiding a connectivity regression elsewhere.
The local comparative DRC retains the same six pre-existing clearance errors and six
pre-existing solder-mask-bridge errors; it introduces no new error. KiCad 9 comparative
DRC is required in CI before the proposal is ready for a human decision.

Candidate board:
`hardware/kicad/candidates/PCB-MAIN-RF-ECO-003/PCB-MAIN_RF_ECO_003.kicad_pcb`

Candidate SHA-256:
`3561f334476259f4e2aa6143a49dcc945da7eb1a292400449b60d204ac421c5d`

Baseline SHA-256:
`e81daf6d8cf0220f762c64f1fc637f65d71d6bc99128ab8c4993a540431e461e`

Machine record:
`hardware/reviews/PCB_MAIN_RF_ROUTEABILITY_ECO_003_CANDIDATE_REV_A.json`

Independent audit:
`tools/audit_pcb_main_rf_routeability_eco_003_rev_a.py`

## Requested decision and boundary

After the machine gate is green, the independent reviewer may record one decision:

- `ACCEPT_LIMITED_RF_ROUTEABILITY_ECO`: authorize only the three placement changes
  above in controlled placement sources and continued RF routing engineering.
- `REJECT_RF_ROUTEABILITY_ECO`: retain the current placement and rework the GNSS
  routeability approach.

Acceptance does **not** approve these 89 segments as final RF copper. Return-path and
ground-via design, RF topology cleanup, native 3D/mechanical inspection, final KiCad
DRC, SI review, job-specific fabricator impedance acceptance, assembler DFM, full
Review B and manufacturing release all remain open.
