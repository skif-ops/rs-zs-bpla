# PCB-MAIN Rev.A placement-clearance errata

Status: `OPEN / LIMITED MECHANICAL ECO APPLIED / FULL PLACEMENT REWORK REQUIRED / NOT FOR MANUFACTURE`

Discovery date: 2026-09-15  
Inspected commit: `989ce217d44795ba2986453d1f37152af5a8e1fc`  
PCB SHA-256: `aa35fe622b6a0761b9b25ae488e1a2c6e7160c285ab771b580f63513b83e4a22`  
MAIN-AUTH-011 CSV SHA-256: `2ea8da3b8469f616c469eb342127afd2e75b3b0ad04f3ab75154560211f353c9`

This record controls a defect discovered after the signed PCB-MAIN electrical
Review A. It does not alter the signed schematic conclusion. The limited
mechanical ECO was accepted and applied on 2026-09-15; placement completion and
Review B remain blocked until the remaining candidate placement is reworked and
the strict clearance audit passes.

## Independent method

`tools/audit_pcb_main_placement_clearance_rev_a.py` parses the committed native
board with `kiutils==1.4.8` and evaluates same-side assembly envelopes after the
footprint rotation and translation are applied.

- A controlled `F.CrtYd`/`B.CrtYd` rectangle is a confirmed assembly envelope.
- A footprint without a courtyard is screened with the union of its pad bounds
  expanded by 0.25 mm. These conservative findings are not represented as exact
  body/courtyard geometry.
- Positive overlap must exceed 0.02 mm on both axes to be reported.
- The MAIN-AUTH-011 10.0 mm component-exclusion diameter around H1-H4 is checked
  against the same envelopes.
- Each `TOOL_D8_Z15` U.FL rule is checked as a 4.0 mm-radius, 15.0 mm-high
  top-side service cylinder against every other fitted assembly envelope. The cylinder may open
  beyond a service edge, but it may not intersect a component courtyard/body.
- Bottom production pogo footprints are fixture contacts, not assembled bodies,
  and are excluded from component-collision counts.

The current board uses orthogonal footprint rotations and rectangular courtyard
boundaries, so each reported courtyard/courtyard overlap below is an exact
axis-aligned overlap after transformation. KiCad DRC and a final 3D/service-volume
inspection remain mandatory and are not replaced by this audit.

## Controlled pre-ECO result

| Item | Count | Disposition |
|---|---:|---|
| Fitted assembly footprints | 227 | Audited |
| Footprints with controlled courtyard | 58 | Exact rectangular-envelope check |
| Footprints using pad-envelope screening | 169 | Courtyard/body control still required |
| Confirmed component collisions | 17 | Placement blocker |
| Screening component collisions | 67 | Rework or exact courtyard required |
| Confirmed mounting-exclusion conflicts | 2 | Placement blocker |
| Screening mounting-exclusion conflicts | 1 | Rework or exact courtyard required |
| Confirmed U.FL tool-clearance conflicts | 2 | Locked service-volume blocker |
| Screening U.FL tool-clearance conflicts | 0 | None |

Confirmed courtyard/courtyard collisions:

| Pair | Overlap X, mm | Overlap Y, mm | Overlap area, mm² | Authority disposition |
|---|---:|---:|---:|---|
| C36 / J12 | 7.885 | 5.100 | 40.214 | Move unlocked placement |
| C36 / U24 | 1.900 | 3.000 | 5.700 | Move unlocked placement |
| C44 / J6 | 2.910 | 0.900 | 2.619 | Move unlocked placement |
| C44 / U14 | 3.100 | 2.200 | 6.820 | Move unlocked placement |
| D4 / U15 | 1.530 | 0.150 | 0.230 | Move unlocked placement |
| D4 / U21 | 1.330 | 0.750 | 0.998 | Move unlocked placement |
| D6 / U22 | 1.530 | 0.750 | 1.147 | Move unlocked placement |
| J12 / U23 | 1.900 | 3.000 | 5.700 | Move unlocked placement |
| J12 / U24 | 1.900 | 3.000 | 5.700 | Move unlocked placement |
| J8 / U8 | 4.100 | 2.050 | 8.405 | `MAIN-AUTH-011` conflict, limited ECO required |
| J_MIC1 / J_PWR | 7.620 | 9.560 | 72.847 | `MAIN-AUTH-011` conflict, limited ECO required |
| J_PWR / Q2 | 0.920 | 3.300 | 3.036 | Move unlocked placement |
| Q2 / Q3 | 0.200 | 3.300 | 0.660 | Move unlocked placement |
| U1 / U6 | 4.200 | 3.380 | 14.196 | Move unlocked placement |
| U1 / U7 | 3.500 | 4.750 | 16.625 | Move unlocked placement |
| U16 / U8 | 5.850 | 8.300 | 48.555 | Move unlocked placement |
| U18 / U7 | 2.660 | 0.200 | 0.532 | Move unlocked placement |

Confirmed mounting-hole conflicts:

| Hole / component | Required radius, mm | Nearest courtyard distance, mm | Deficit, mm | Authority disposition |
|---|---:|---:|---:|---|
| H1 / J_PWR | 5.000 | 3.920 | 1.080 | `MAIN-AUTH-011` conflict, limited ECO required |
| H2 / J13 | 5.000 | 3.909 | 1.091 | `MAIN-AUTH-011` conflict, limited ECO required |

The pad-envelope screening also finds H1/C1 with a 0.112 mm apparent deficit.
That finding is controlled as placement rework or courtyard completion, not as a
new authority conflict.

Confirmed U.FL D8 tool-cylinder conflicts:

| Tool / component | Required radius, mm | Nearest courtyard distance, mm | Deficit, mm | Authority disposition |
|---|---:|---:|---:|---|
| J8 / U8 | 4.000 | 0.200 | 3.800 | `MAIN-AUTH-011` conflict, limited ECO required |
| J10 / U10 | 4.000 | 2.750 | 1.250 | `MAIN-AUTH-011` conflict, limited ECO required |

## ECO and release boundary

Reviewer `Скиф` accepted proposal `PCB-MAIN-MECH-ECO-001` on 2026-09-15 with
decision `ACCEPT_LIMITED_MECHANICAL_ECO`, bound to commit
`61cbe796de2f87560342a44b063ff6283a8ce1e8` and candidate SHA-256
`5ef7d0390da97796febbef6a69f0206a06efe00782e238bf7c8f32bf29d08fc1`.
The candidate remains immutable and its separate approval record is
`PCB_MAIN_MECHANICAL_ECO_APPROVAL_REV_A.json`.

The nine accepted MAIN-AUTH-011 record changes and six corresponding native-PCB
anchor translations are applied. Current controlled hashes are:

- PCB SHA-256: `8de8ac2eedc00775853a26641931ded8873cf5c1d9f61e7358d0546fea9dc379`
- MAIN-AUTH-011 CSV SHA-256: `6a28821413fb631d299574e0a86fd87be4fa2b20606b60947700fc6e37ab3e44`

The machine-readable application record is
`PCB_MAIN_MECHANICAL_ECO_APPLICATION_REV_A.json`.

GitHub App transport reproduced the reviewed local commit tree exactly as
remote commit `e265d1f1a0a74f94b9c887e12794a9b59fc2bfa0`. Both commits have tree
SHA `f1fd423bbcfedefa830677ce2d8b3c54b2294caa` and candidate blob SHA
`b3dede3b466676bbab4e3bd737160cacfc57ad28`. The machine-audited mapping is
`PCB_MAIN_MECHANICAL_ECO_REVIEW_COMMIT_MAPPING_REV_A.json`.

The post-ECO audit reports no locked component, mounting or U.FL tool-cylinder
conflicts. It leaves 15 confirmed component collisions, 67 pad-envelope
screening collisions and one pad-envelope mounting-screening finding, all in
the unlocked placement/repack scope. The 10.0 mm MIC1 corridor and north-side
coax/tool openings remain minimum capture allocations; named harness and
enclosure evidence remain manufacturing-release blockers.

All unlocked footprints must now be repacked, the 169 screened
footprints must receive controlled courtyard/body disposition, and the following
must pass on one commit:

1. `python tools/audit_pcb_main_layout_candidate_rev_a.py`
2. `python tools/audit_pcb_main_placement_clearance_rev_a.py --strict`
3. KiCad 9 DRC with zero blocker/critical violations and zero unrouted items
4. Native STEP plus enclosure, connector-mate, card, coax-tool and harness-sweep review
5. Independent PCB-MAIN Review B and factory/assembler DFM

Until then the disposition is `HOLD`; Gerber, placement release, production BOM
release and any `FOR_MANUFACTURE` claim remain prohibited.
