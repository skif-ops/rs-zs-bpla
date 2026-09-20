# PCB-MAIN GNSS RF placement/routeability ECO-001 — Rev.A

Status: `PROPOSAL / STATIC CLEARANCE PASS / KICAD 9 GATE REQUIRED / NOT FOR MANUFACTURE`

`PCB-MAIN-GNSS-RF-ECO-001` is the bounded response to finding `RF-SI-003`.
It keeps locked GNSS anchors `U9` and `J9` fixed, moves only unlocked `FL1`
and `C64` to the RF_IN side of U9, and regenerates only the affected GNSS RF
copper and obsolete FL1 ground fanout.

## Exact placement delta

| Ref | From `(x, y, rot)` mm/deg | To `(x, y, rot)` mm/deg |
|---|---:|---:|
| `FL1` | `(60.50, 68.00, 0)` | `(56.80, 51.80, 270)` |
| `C64` | `(58.75, 68.00, 0)` | `(58.30, 51.60, 180)` |

The strict 2D audit remains `PASS`: all 227 fitted assembly footprints retain
courtyards, with zero component, mounting-exclusion or U.FL tool conflicts.
No other footprint moves.

## RF topology result

| Net | Base segments / length | Candidate segments / length |
|---|---:|---:|
| `GNSS_RF_ANT_BIASED` | 17 / 10.205267 mm | 22 / 34.114752 mm |
| `GNSS_RF_DC_BLOCK` | 1 / 1.000000 mm | 2 / 1.304117 mm |
| `GNSS_RF_FILTERED` | 6 / 25.325357 mm | 2 / 1.150694 mm |
| Total | 24 / 36.530624 mm | 26 / 36.569563 mm |

The overall connector-to-receiver copper length is effectively unchanged, but
the SAW is now adjacent to U9 RF_IN. The post-SAW route is reduced by
24.174663 mm, has a 1.103687 mm pad span and 1.042591 stretch ratio, and exits
the U9 edge without signal copper under its body. The long portion is moved to
the antenna side of the SAW. All three RF nets remain on `F.Cu` at the bounded
`0.1509 mm` L1-over-L2 engineering width with zero signal vias.

The obsolete FL1 ground fanout removes five segments and three vias. The new
fanout uses four short segments, one new via, and the adjacent existing U9.12
ground via at `(55.725, 51.850)` mm. U9 and all its non-RF connections remain
untouched.

## Identity and required gate

- Base SHA-256: `9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040`
- Candidate SHA-256: `40c67cf8f32a46fb7de16c0267079c546002349ce3ffb6a8096782af025fd5ea`
- Generator SHA-256: `9362439d733b46732aebc1b8833faddfe91edd7469b979d2d397bb9fee17d8b4`
- Generator: `tools/generate_pcb_main_gnss_rf_eco_001_candidate_rev_a.py`
- Independent audit: `tools/audit_pcb_main_gnss_rf_eco_001_candidate_rev_a.py`

CI must regenerate the candidate byte-for-byte, refill base and candidate with
KiCad 9, prove strict placement clearance, run comparative DRC/connectivity,
and find connected `GND_DIGITAL` L2 copper below every sampled centreline point
of all three GNSS RF nets at a maximum `0.1 mm` pitch.

Even after a green machine gate, this proposal requires the exact independent
decision `ACCEPT_GNSS_RF_PLACEMENT_ROUTEABILITY_SUBGATE` before application.
It does not accept the cellular L2 proposal, close the complete RF/SI review,
finish routing or authorize Review B, CAM, fabrication, assembly or production.
