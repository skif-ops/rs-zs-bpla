# PCB-MAIN GNSS RF placement/routeability ECO-001 — Rev.A

Status: `PROPOSAL / KICAD 9 COMPARATIVE DRC PASS / HUMAN ACCEPTANCE PENDING / NOT FOR MANUFACTURE`

`PCB-MAIN-GNSS-RF-ECO-001` is the bounded response to finding `RF-SI-003`.
It keeps locked GNSS anchors `U9` and `J9` fixed, moves only unlocked `FL1`
and `C64` to the RF_IN side of U9, and regenerates only the affected GNSS RF
copper and obsolete FL1 ground fanout.

## Exact placement delta

| Ref | From `(x, y, rot)` mm/deg | To `(x, y, rot)` mm/deg |
|---|---:|---:|
| `FL1` | `(60.50, 68.00, 0)` | `(56.80, 51.60, 270)` |
| `C64` | `(58.75, 68.00, 0)` | `(58.30, 51.60, 180)` |

The strict 2D audit remains `PASS`: all 227 fitted assembly footprints retain
courtyards, with zero component, mounting-exclusion or U.FL tool conflicts.
No other footprint moves.

## RF topology result

| Net | Base segments / length | Candidate segments / length |
|---|---:|---:|
| `GNSS_RF_ANT_BIASED` | 17 / 10.205267 mm | 22 / 34.114752 mm |
| `GNSS_RF_DC_BLOCK` | 1 / 1.000000 mm | 2 / 1.386910 mm |
| `GNSS_RF_FILTERED` | 6 / 25.325357 mm | 2 / 1.326997 mm |
| Total | 24 / 36.530624 mm | 26 / 36.828659 mm |

The overall connector-to-receiver copper length is effectively unchanged, but
the SAW is now adjacent to U9 RF_IN. The post-SAW route is reduced by
23.998360 mm, has a 1.299279 mm pad span and 1.021334 stretch ratio, and exits
the U9 edge without signal copper under its body. The long portion is moved to
the antenna side of the SAW. All three RF nets remain on `F.Cu` at the bounded
`0.1509 mm` L1-over-L2 engineering width with zero signal vias.

The obsolete FL1 ground fanout removes five segments and three vias. The new
fanout uses four short segments, one new via, and the adjacent existing U9.12
ground via at `(55.725, 51.850)` mm. U9 and all its non-RF connections remain
untouched.

## Identity and required gate

- Base SHA-256: `9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040`
- Candidate SHA-256: `d4c0eaa95bb62c7b9ae15b110fb3a76e6a056f462f0a36a734b3fa63730d2aee`
- Generator SHA-256: `da949bfd6acd35876af7cd97837801354c101d351438cc620153cf50884716f0`
- Generator: `tools/generate_pcb_main_gnss_rf_eco_001_candidate_rev_a.py`
- Independent audit: `tools/audit_pcb_main_gnss_rf_eco_001_candidate_rev_a.py`

The commit-bound machine gate regenerated the candidate byte-for-byte, refilled
base and candidate with KiCad 9, proved strict placement clearance, ran
comparative DRC/connectivity, and sampled the filled L2 reference:

- source commit/tree: `67538ba5dfea4cde08c06738cc6b537847a25398` /
  `f45c0923461b299eb3ccfaa97eb9ca2cf069a285`;
- PCB Native Gate `#273` (`35511383587`): `success`, including the GNSS
  comparative DRC and filled-reference step;
- CI `#546` (`35511383579`): `success`;
- DRC: 226 -> 227 total warning-level violations, 0 -> 0 errors and
  429 -> 429 unconnected items;
- filled reference: one connected `GND_DIGITAL` polygon, 372
  `GNSS_RF_ANT_BIASED`, 17 `GNSS_RF_DC_BLOCK` and 17 `GNSS_RF_FILTERED`
  centreline samples at no more than `0.1 mm`, zero uncovered;
- artifact `10605856993`, `evt-pre-20-kicad-native-gate`, digest
  `sha256:3e08973033e263876c833abc220196daf1b6cbfc60d2476924032131c96b9056`.

Even after a green machine gate, this proposal requires the exact independent
decision `ACCEPT_GNSS_RF_PLACEMENT_ROUTEABILITY_SUBGATE` before application.
It does not accept the cellular L2 proposal, close the complete RF/SI review,
finish routing or authorize Review B, CAM, fabrication, assembly or production.
