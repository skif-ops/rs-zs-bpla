# PCB-PWR autoroute 011 — application record (Rev A)

Status: **APPLIED_EXACT_AUTOROUTE_011_EVT_ROUTING — Review B open, no manufacturing release.**

## Identity

| Item | Value |
|---|---|
| Predecessor (J2 placement ECO-003) | `b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6` |
| Applied board = committed candidate | `cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578` |
| Board semantic SHA-256 (routing authority) | `2694f7cfe20ab3b0f67d6dd00ea32ca83fd92db69137cddeaec58943a784de7e` |
| Candidate | `hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011/` (board, project, rules, `drc.json`, `SUMMARY.json`) |
| Generator | `tools/apply_pcb_pwr_autoroute_candidate_rev_a.py` + `tools/kicad_autoroute_stage_rev_a.py` + `tools/pcb_gapfill_router_rev_a.py` |
| Application | `tools/apply_pcb_pwr_autoroute_011_rev_a.py` (ci-apply, `--check` byte-exact) |
| Tools | KiCad 9.0.9 image `e638b79b…`, Freerouting 2.4.1 linux-x64 `3ad5a956…`, 150 passes |

Placement, footprints, nets and outline are unchanged relative to ECO-003; only copper,
the project net classes and the rule file change.

## What the pipeline does

1. All accepted copper (routing 001–010) is locked; preroutes (103 items) are added locked.
2. In1.Cu and In2.Cu become solid `GND_PWR` planes (layer authority: In1 REFERENCE,
   In2 POWER_RETURN). Tracks are on F.Cu and B.Cu only. Layer types stay `signal`.
3. Freerouting routes the open connections; power classes at 1.0 mm for connectivity.
4. A grid A* gap-fill router closes what Freerouting leaves open, on the actual copper,
   class-aware clearances (SW nodes 0.4 mm), no via in SMD pads, hole keepouts 4 mm.
5. Power routes are thickened by zones to the basis widths (4.0 mm 5 A, 3.0 mm 4 A),
   necking automatically where neighbours are closer; GND pours on F.Cu/B.Cu, a via beside
   every SMD ground pad, 3.5 mm stitching grid.
6. Router leftovers (open-ended router/preroute tracks, vias with fewer than two links) are
   removed; accepted copper is never touched.

Deterministic preroutes cover everything the autorouter must not decide: the input
protection power path (F1 → D1/U1 corridor → under Q1 → source; Q1 drain → 7 vias →
B.Cu 3 mm → 7 vias at RSH1/C10), 3V8 to J2 pin 1 (3 mm east corridor), 3V3 to J2 pin 3,
LMR60440 and U2 fan-outs, net-tie exits, I2C test-point links, ground vias under U1/U2.
Each preroute was checked against every copper item of the board before use.

## KiCad 9 DRC of the applied board (with project and rules)

0 errors, 0 unconnected items. Warnings: 66 `lib_footprint_issues` (library sync open),
41 `silk_over_copper` + 16 `silk_overlap` (silk pass before CAM), 1 `via_dangling`
(unused RT_3V8 escape via at 53.6/11.5; timing-resistor node, negligible).

## Power copper width (measured along every power track ≥ 1 mm)

Screen from the 35 µm basis: 2.77 mm at 5 A, 2.03 mm at 4 A (outer layer, ΔT 10 °C).

| Net | Class | Min | Median | Where narrower than screen |
|---|---|---|---|---|
| VBAT_RAW | 5 A | 3.57 | 4.17 | — |
| VBAT_PROTECTED (B.Cu / F.Cu) | 5 A | 3.98 / 3.12 | 4.00 / 5.10 | — |
| VBAT_FUSED | 5 A | 1.20 | 3.95 | only between the Q1 source pins (package access); 2.4 mm below the pins, 1.9 mm beside the 1206 fuse |
| VBAT_SYS | 5 A | 2.00 | 4.00 | branches to the U3/U4 inputs (current already split) and accepted copper |
| 3V8_MODEM | 4 A | 1.00 | 3.00 | only the J2 → TP4 test-point branch (no load current); main path to J2 ≥ 2.71 |
| 3V3_DIGITAL | 4 A | 1.41 | 3.00 | at the J2 locating peg (1.2 mm, connector pitch) and the branch to LDO U5 / pull-ups |

Sense and escape stubs < 1 mm (U2, U3/U4 pins) carry no load current and are excluded.

## Deviations from the routing basis (accepted for EVT, closed by Review B / EVT tests)

1. Clearance 0.2 mm (basis 0.3 mm) for non-switch classes: fine-pitch pins (0.5 mm pitch,
   0.2 mm gaps) cannot meet 0.3 mm; 0.2 mm is above the JLC 1 oz minimum. SW nodes keep 0.4 mm.
2. VBAT_PROTECTED layer transitions: 7 + 7 vias 0.6/0.3 mm, no via-in-pad, instead of the
   provisional 12 of the basis; covered by the EVT 5 A / +70 °C thermal test.
3. 3V3_DIGITAL 1.2 mm between the J2 pins and the locating peg (connector pitch limit).
4. VBAT_FUSED 1.2 mm inside the Q1 source pin row (package access).
5. Power tracks routed at 1.0 mm and thickened by zones to the basis width.
6. Rule file adds `U2 VSSOP-10 land pattern` (min 0.19 mm between pads of U2), like ECO-004
   for U3/U4. The ECO-004 comparative DRC audit now allows U2 pad-to-pad errors to vanish
   in addition to the four U3/U4 ones, nothing else.

## Audit chain

Autoroute 011 is the accepted successor of ECO-003, recognised by
`tools/pcb_pwr_hot_loop_006_board.py::is_autoroute_011` (SHA-256 and byte identity with the
committed candidate). Historical audits of 001–010 and ECO-003 replay on their archived
boards as before. `hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json`: placement-clearance and
pre-route controls carry the new semantic SHA-256 and copper counts (873 trace items,
33 zones); `routing_complete` stays `false` until Review B.

Local replay of 133 CI commands (ci.yml, pcb-native.yml, pcb-pwr-schematic.yml; PCB-PWR,
layer count, EVT gate): no new failure against the ECO-003 baseline.

## Open

Review B (human), library sync (66 footprint warnings), silk pass, CAM export with 1 oz /
1 oz fab notes, EVT thermal test 5 A at +70 °C.
