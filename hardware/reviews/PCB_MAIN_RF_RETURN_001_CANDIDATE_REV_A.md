# PCB-MAIN cellular L2 return-plane candidate 001 — Rev.A

Status: `PROPOSAL / KICAD 9 COMPARATIVE DRC PASS / HUMAN ACCEPTANCE PENDING / NOT FOR MANUFACTURE`

`PCB-MAIN-RF-RETURN-001` is the bounded response to finding `RF-RP-002` in the
RF/SI return-path review. The accepted RF P0 routes use the public
`JLC06161H-3313` L1-over-L2 width, but `GND_MODEM` currently exists only on
`In4.Cu` and `GND_DIGITAL` is deliberately cut out below the cellular region.

## Exact candidate delta

The candidate preserves all 976 accepted track/via objects, all footprints,
existing zones/rule areas, nets, outline and stackup. It adds exactly one
unfilled zone:

| Field | Value |
|---|---|
| Net | `GND_MODEM` (47) |
| Layer | `In1.Cu` / L2 |
| Name | `PCB_MAIN_GND_MODEM_CELL_In1_Cu` |
| Polygon | `(10,34) – (36,34) – (36,74) – (10,74)` mm |
| Clearance / min thickness | `0.10 / 0.15 mm` |
| Existing GND_MODEM vias inside | 50 |
| Minimum cellular RF centreline margin to polygon edge | `2.525 mm` |

The polygon follows the locked `ZONE_CELL` rectangle and stays inside the
existing `GND_DIGITAL` L2 cut-out, whose boundary is offset by 0.2 mm. It
therefore supplies the missing local L2 reference without joining
`GND_MODEM` and `GND_DIGITAL`.

## Identity

- Base SHA-256: `9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040`
- Candidate SHA-256: `22ddd8c56ceabf397ed033a44235b439625d3104fa2cf798bb57b782d24b1352`
- Generator: `tools/generate_pcb_main_rf_return_001_candidate_rev_a.py`
- Independent audit: `tools/audit_pcb_main_rf_return_001_candidate_rev_a.py`

The zone is intentionally stored unfilled. The commit-bound machine gate has
regenerated the candidate, refilled base and candidate with KiCad 9, run
comparative DRC/connectivity, and sampled the filled L2 reference:

- source commit/tree: `239016fdd295426766cc88209822be39610297db` /
  `7a6e0c226318bd85e6456d17bae119b489d2aff1`;
- PCB Native Gate `#267` (`35508574131`): `success`, including the cellular
  L2-return comparative step;
- CI `#540` (`35508574124`): `success`;
- DRC: 226 -> 226 total violations, 0 -> 0 errors and 429 -> 429 unconnected
  items;
- filled reference: one connected `GND_MODEM` polygon, 385 `CELL_RF` plus 238
  `CELL_RF_ANT` centreline samples at no more than `0.1 mm`, zero uncovered;
- artifact `10603873750`, `evt-pre-20-kicad-native-gate`, digest
  `sha256:65adbdc2a6f9b2803645fe6df17cd8ee2b6eb6d4ab0b03be76322626ec814ded`.

The exact candidate is now eligible for the requested independent decision
`ACCEPT_CELLULAR_L2_RETURN_PLANE_SUBGATE` or rejection. It remains a proposal
until that decision is recorded and applied in a separate controlled commit.

Acceptance may close only the cellular L2 return-plane subgate. The separate
`GNSS_RF_FILTERED` placement/routeability defect, complete RF/SI review, final
fabricator stackup/tolerance/coupon, remaining routing, Review B, CAM and
manufacture stay open.
