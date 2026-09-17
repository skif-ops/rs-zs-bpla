# PCB-MAIN limited mechanical ECO candidate - EVT-PRE-20 Rev.A

Status: `PROPOSED / NOT APPROVED / NOT APPLIED / NOT FOR MANUFACTURE`

Proposal ID: `PCB-MAIN-MECH-ECO-001`
Baseline commit: `989ce217d44795ba2986453d1f37152af5a8e1fc`
PCB SHA-256: `aa35fe622b6a0761b9b25ae488e1a2c6e7160c285ab771b580f63513b83e4a22`
MAIN-AUTH-011 CSV SHA-256: `2ea8da3b8469f616c469eb342127afd2e75b3b0ad04f3ab75154560211f353c9`

This is a calculation-backed proposal for the limited `MAIN-AUTH-011` ECO
required by `PCB_MAIN_PLACEMENT_CLEARANCE_ERRATA_REV_A.md`. It does not change
the signed authority, native PCB or electrical connectivity. The machine input
is `PCB_MAIN_MECHANICAL_ECO_CANDIDATE_REV_A.json`; the independent overlay audit
is `tools/audit_pcb_main_mechanical_eco_candidate_rev_a.py`.

## Proposed authority delta

All X coordinates and all connector/module rotations stay unchanged. The
110.00 x 75.00 mm R3 outline, H1-H4 coordinates, 10.0 mm component exclusions,
stackup allocation, other anchors, other zones, DFT window and pogo coordinates
also stay unchanged.

| Record | Feature | Current | Proposed | Purpose |
|---|---|---:|---:|---|
| `MECH-007` | J_PWR Y | 13.0 mm | 15.0 mm | Clear H1 |
| `MECH-008` | J_MIC1 Y | 30.0 mm | 42.5 mm | Clear J_PWR |
| `MECH-014` | J8 Y | 68.0 mm | 71.5 mm | Clear U8 courtyard and D8 tool cylinder |
| `MECH-016` | J10 Y | 68.0 mm | 71.5 mm | Clear U10 from the D8 tool cylinder |
| `MECH-019` | J13 Y | 13.0 mm | 15.0 mm | Clear H2 |
| `MECH-020` | U8 Y | 53.0 mm | 52.0 mm | Retain positive J8 tool clearance without rotating BG95 |
| `MECH-024` | ZONE_CELL Y | 42.0 mm | 34.0 mm | Reserve a south-side RF matching/bulk strip |
| `MECH-024` | ZONE_CELL height | 30.0 mm | 40.0 mm | Contain moved J8, north edge becomes Y=74.0 mm |
| `MECH-026` | ZONE_LORA height | 26.0 mm | 28.0 mm | Contain moved J10, north edge becomes Y=74.0 mm |
| `MECH-032` | KO_MIC1_HARNESS Y | 25.0 mm | 37.5 mm | Track J_MIC1 |
| `MECH-032` | KO_MIC1_HARNESS width | 12.0 mm | 10.0 mm | Retain the specified 10 mm bend-start allocation and stop at the cellular-zone boundary |

## Independently calculated result

The audit reads the unchanged authority and board, verifies both SHA-256 values,
then translates only the six affected controlled courtyards and overlays the
three affected zone/corridor records. It rejects any extra record or field change.

| Controlled check | Baseline | Proposed result |
|---|---|---|
| Locked component conflicts | J8/U8; J_MIC1/J_PWR | None |
| Locked mounting conflicts | H1/J_PWR; H2/J13 | None |
| Locked U.FL D8 x Z15 tool-cylinder conflicts | J8/U8; J10/U10 | None |
| J_PWR to J_MIC1 edge gap | Collision | 0.940 mm |
| J8 to U8 edge gap | Collision | 2.450 mm |
| J10 to U10 edge gap | 0.500 mm | 4.000 mm |
| H1 exclusion margin at J_PWR | -1.080 mm | +0.920 mm |
| H2 exclusion margin at J13 | -1.091 mm | +0.776 mm |
| J8 D8 tool cylinder to U8 | -3.800 mm | +0.700 mm |
| J9 D8 tool cylinder to U9 | +0.900 mm | +0.900 mm, unchanged |
| J10 D8 tool cylinder to U10 | -1.250 mm | +2.250 mm |
| MIC1 corridor to U8 courtyard | Not applicable | +1.050 mm |
| MIC1 corridor / ZONE_CELL overlap | Not applicable | 0 mm², boundaries touch at X=10.0 mm |
| ZONE_CELL / audio-digital zone gap | 1.000 mm | 1.000 mm |
| U8 south courtyard / ZONE_CELL south edge | Not applicable | 3.200 mm allocation for RF matching/bulk placement |
| J8/J10 courtyard / north board edge | 4.750 mm | 1.250 mm, above the 1.000 mm rule |
| J8/J10 D8 tool north overhang | None | 0.500 mm into the required enclosure service opening |

The D8 x Z15 tool cylinders deliberately open 0.500 mm beyond the north PCB edge while
the component courtyards retain 1.250 mm edge clearance. This is not a release of
coax or enclosure geometry. The selected coax, mating tool and enclosure opening
still require a swept-volume check. U8 remains at rotation 0, so pad 60 remains
on the south side. The expanded cellular allocation creates a 3.200 mm strip
below the controlled U8 courtyard, but final matching topology, 50 Ohm geometry,
return continuity and via fencing remain Review-B work.

## What this proposal does not solve

Applying only these six anchor translations to the current unrouted placement
leaves 15 confirmed component collisions, 67 pad-envelope screening collisions
and one pad-envelope mounting-screening finding. Those are all outside the
locked-authority conflict set and require a new electrically constrained
placement, not blind movement to empty board area.

The proposed 10.0 mm MIC1 inboard corridor is exactly the frozen bend-start
allocation. It may be accepted only as a minimum capture allocation, not as
harness-fit evidence. Before manufacturing release, the selected mating harness
must prove latch pull, cable OD, bend radius and strain relief at that envelope.
No harness has been inferred or silently selected.

After explicit ECO approval, the implementation must:

1. amend the nine listed `MAIN-AUTH-011` records and regenerate its documented hash;
2. move only the corresponding locked board anchors before repacking unlocked parts;
3. preserve cellular RF, return-current, decoupling, quiet-zone, thermal and service-volume constraints during the repack;
4. add controlled body/courtyard evidence for the 169 screened fitted footprints;
5. pass the strict clearance audit, KiCad DRC with zero unrouted items, STEP/enclosure review, PCB-MAIN delta review and independent Review B.

Until the reviewer records an explicit decision against this exact proposal,
the current authority remains controlling and PCB-MAIN remains on `HOLD`.
