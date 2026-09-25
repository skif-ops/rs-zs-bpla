# PCB-MAIN 003 — OctoSPI / SDIO / EN_MODEM off In2/In3 (candidate record, Rev A)

Status: **ACCEPTED and APPLIED** (`ACCEPT_INNER_REROUTE_003`, project owner, 2026-09-25; ci-apply commit `33f20a1b`).
Not a manufacturing release. Application: section 7.

| Item | Value |
|---|---|
| Base (authoritative PCB-MAIN) | `2dd9bdf2…` (same base as 002) |
| Stage 2 (resistor moves + 002 construction with corridor) | `b2d751b0…` |
| Reroute plan `REROUTE_PLAN.json` | `46e70a7d…` |
| Candidate `PCB-MAIN_INNER_REROUTE_003_CANDIDATE_REV_A.kicad_pcb` | `30c6c93e5afbbc0888ed7c7e8693af6c6f0c7df8f5c4525e02c6d5a4c47b8739` |
| Generator | `tools/apply_pcb_main_inner_reroute_003_candidate_rev_a.py` (ci-apply run 3, bot commit `18ecdaae`) |
| Geometry / router | `tools/pcb_main_inner_reroute_003_rev_a.py` |
| KiCad | 9.0.9 (`ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b…`) |

003 answers option (a) of the 002 record, section 6: the 11 OctoSPI / SDIO / EN_MODEM runs left on In2.Cu
(GND_MIC plane layer) and In3.Cu (referenced to In2, not digital) move to F.Cu / B.Cu, each over a GND_DIGITAL
reference. 003 contains the 002 construction (In4 split, stitching vias, modem-island tie) with one change —
the In4 GND_DIGITAL corridor — so **if accepted, 003 supersedes 002**; 002 is not applied separately.

## 1. What changes

| Change | Detail |
|---|---|
| In4 split | 002 construction; the joint pad hull (+1.0 mm) of U1, R9…R12, U2 is kept GND_DIGITAL (OctoSPI corridor). GND_MODEM on In4 stays one piece (2342 mm²) + the 5.2 mm² island with its 12.61 mm In3 tie, as in 002 |
| Re-placed parts | R9, R10, R11 (22 Ω 1 % ERJ-2RKF22R0X, same part as R8, R12) |
| Rerouted nets | 12: NOR_CLK_U1/U2, NOR_IO0…IO2_U1/U2, NOR_IO3_U2, SD_D2_U1, EN_MODEM, NOR_NCS_U2 |
| Removed copper | every In2/In3 segment of these nets, the old fan-out of U1 pins 38/40/41/42 and of the re-placed resistors, the NCS run inside U1, 4 vias left single-layer (144 lines) |
| Added copper | 146 segments, 16 signal vias 0.5/0.3 mm, 4 GND_DIGITAL return vias |
| Silkscreen | R9–R11 reference text above the row, vertical |
| Unchanged | all other nets, parts and footprints; netlist and BOM |

### Resistor row
In the base the resistor row above U1 is ordered IO1 (R10, far left), CLK (R8), IO2 (R11), IO0 (R9), while the U1
bottom pins are CLK (38), IO0 (40), IO1 (41), IO2 (42): on two layers the runs must cross, and every automatic
attempt ended with detours up to 55 mm or 4–7 vias per net. R9–R11 are moved into one row right of R8 in pin order
and rotated 90° (pin 1 towards U1, pin 2 towards U2):

| Ref | Net (pin 1 / pin 2) | Base position | 003 position |
|---|---|---|---|
| R8 | NOR_CLK | 54.5, 16.0, 0° | unchanged (accepted OctoSPI R8 ECO-002) |
| R9 | NOR_IO0 | 58.5, 20.75, 0° | 60.5, 19.75, 90° |
| R10 | NOR_IO1 | 42.25, 24.0, 0° | 62.0, 19.75, 90° |
| R11 | NOR_IO2 | 56.75, 19.5, 0° | 63.5, 19.75, 90° |

The five resistors are identical parts, each stays on its own nets: function and BOM do not change. On
application, three rows of `hardware/PCB_MAIN_PLACEMENT_REPACK_REV_A.csv` (status `UNLOCKED_LAYOUT_CANDIDATE`)
change to these values (`PLACEMENT_ROWS.json`); nothing else in the placement authority.

### Topology on the U1 side
The F.Cu area under U1 is closed by the pad ring (0.5 mm pitch) except at the corners, and the BOOT0 B.Cu track
crosses the body diagonally. Each U1-side run: F.Cu from the pin under the body → via in the triangle above
BOOT0 → B.Cu through its own gap of the TP_EOL test-pad row (B.Cu pads 1.7 mm, pitch 2.54 mm; IO2 passes TP_EOL.13
on its right) → via under its resistor → F.Cu to pin 1. 2 vias per net. NOR_NCS_U2 (pin 39, between CLK and IO0)
now drops to B.Cu at its pin and passes under the IO lanes; its short stubs to R7.2 and U2.7 are unchanged.
NOR_CLK_U1 reaches R8 from the right, so EN_MODEM keeps the only way out to the left (top-left U1 corner).

## 2. Checks

| Check | Result |
|---|---|
| Stage 2 reproducible, SHA pinned in the plan | PASS |
| Plan exact geometry (0.20 mm copper, 0.25 mm holes, keep-outs, reference boundary 0.3 mm, 0.5 mm edge) | PASS: 28 runs, 16 vias, 4 return vias |
| Textual delta proof (candidate − added + removed = stage 2) | PASS |
| Connectivity of the 12 nets | each one component, pad to pad; nothing left on In2/In3 |
| KiCad DRC, candidate vs base | new errors **0**, new warnings **0**; unconnected 421 = base 421; 2 base warnings gone (silk over copper R4, R5) |
| In4 fill | GND_MODEM 2342.36 + 5.21 mm²; GND_DIGITAL 5230.28 mm² + 5 via rings 0.19 mm² (002 had 7 such rings) |

## 3. Reference (filled copper under the track, KiCad fill)

| Layer / domain | Base | 003 |
|---|---|---|
| B.Cu over In4, GND_DIGITAL | 0 % | **94.4 %** |
| F.Cu over In1, GND_DIGITAL | 93.8 % | **96.1 %** |
| In2.Cu / In3.Cu digital runs | 157.4 / 112.7 mm, 0 % | none |

Per rerouted net and layer: 64–100 %, gaps at via antipads and pad clearances. Lowest: NOR_IO3_U2 F.Cu 64 %
(2.5 mm of its unchanged stub at U2), NCS F.Cu 79 % (the stub inside the U1 pad ring), NOR_CLK_U1 B.Cu 82 %.
Full table: `REFERENCE_MAP.json` → `rerouted_nets`.

## 4. Return vias
Every F.Cu↔B.Cu transition of a rerouted net has a GND_DIGITAL via within 2.0 mm: 21 transitions, 17 served
by existing vias (0.7–1.93 mm), 4 vias added (EN_MODEM, NOR_IO2_U2, NOR_CLK_U1, NOR_IO0_U2). Rows: plan `return_rows`.

## 5. OctoSPI length matching
End to end U1 pin → series resistor → U2 pin, track length + 1.6 mm per F.Cu↔B.Cu transition:

| Signal | Base | Routed | Matched |
|---|---|---|---|
| CLK | 55.51 | 59.73 | 61.01 |
| IO0 | 65.36 | 51.23 | 61.01 |
| IO1 | 56.07 | 49.81 | 61.01 |
| IO2 | 71.21 | 60.49 | 61.01 |
| IO3 | 52.57 | 61.01 | 61.01 |
| Spread | 18.64 | 11.20 | **0.00** (tolerance 1.0) |

Serpentines (pitch 0.6 mm, gap 0.45 mm = 3 × track width): NOR_CLK_U2 +1.28 (B.Cu), NOR_IO0_U1 +1.50 (B.Cu) and
+8.28 (F.Cu, 6 bumps under the U1 body), NOR_IO1_U2 +11.20 (B.Cu, 3 bumps), NOR_IO2_U2 +0.52. NCS is a chip
select and is not matched; SD_D2_U1 and EN_MODEM are not in the OctoSPI group.

## 6. For the reviewer
1. Accepting 003 replaces 002 (same construction, corridor added). PR #81 then closes without application.
2. The IO0 serpentine under the U1 body is on F.Cu between the pin ring and the vias; the area has no other copper.
3. The row R8–R11 sits over the corridor (In4 GND_DIGITAL); the GND_MODEM arm of In4 above it is not cut.
4. The IO3 U1 side (R12) is unchanged; IO3 sets the matched length.

Decision: `ACCEPT_INNER_REROUTE_003`.

## 7. Application

Tool `tools/apply_pcb_main_inner_reroute_003_application_rev_a.py` (ci-apply, bot commit `33f20a1b`); record
`hardware/reviews/PCB_MAIN_INNER_REROUTE_003_APPLICATION_REV_A.json`.

| Item | Before | After |
|---|---|---|
| `hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb` | `2dd9bdf2…` (USB cell fixture 001 candidate) | `30c6c93e…` (byte copy of the 003 candidate) |
| `hardware/PCB_MAIN_PLACEMENT_REPACK_REV_A.csv` | `df7cdbfc…` | `d97bdf31…` (rows R9, R10, R11 only) |
| Pre-003 manifest snapshot | — | `hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/PCB_MAIN_PLACEMENT_REPACK_PRE_003_REV_A.csv` |

### Audit chain
About 30 audits and generators of the earlier sub-gates (RF P0/remediation/return, GNSS, OctoSPI R8, signal hard
nets, ground domain 001, USB placement/source/cell modem/cell fixture, mechanical ECO-002, the stackup and
assembler/stencil requests, the frozen placement repack) pinned the authoritative board and manifest hashes and
compared the board with their own predecessors. Instead of teaching each of them the 003 delta:

- `tools/pcb_main_lineage_rev_a.py`: `historical_board()` / `historical_placement()` return the exact 003
  predecessor (the USB cell fixture 001 candidate and the pre-003 manifest snapshot) **only** when the authoritative
  board is byte-identical to the accepted 003 candidate, the application record carries the decision, both
  predecessors have their pinned hashes and the manifest differs from the snapshot in the R9–R11 rows only, set to
  the accepted poses. Otherwise they return the authoritative files, so any other change keeps failing every
  earlier audit. The path names itself by the authoritative path (`relative_to`), so path bindings and
  `git show <commit>:<path>` in those audits keep their meaning.
- 24 files read the predecessor board, 6 the predecessor manifest (edits of one line each).
- Current-state audits: the layout audit accepts the applied 003 copper inventory (1069 track items, 10 zones);
  the footprint materialization binds the 003 board hash; the new
  `tools/audit_pcb_main_inner_reroute_003_application_rev_a.py` checks the 003 state (lineage predicate, record,
  candidate DRC evidence, R9–R11 poses, 251 footprints equal to the predecessor set, no rerouted net on In2/In3,
  strict placement clearance of the authoritative board: 227 assembly footprints, 0 collisions).
- Unchanged: `PCB_MAIN_CAPTURE_STATUS_REV_A.json`, the capture manifest, schematic sources.

The tool ran the whole Python part of the PCB-MAIN CI chain (55 commands,
`hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/CI_CHAIN_COMMANDS.txt`) after the application and again in
`--check`: PASS.

### Open after the application
1. `pcb-native.yml` should run `tools/audit_pcb_main_inner_reroute_003_application_rev_a.py` (workflow change,
   owner only).
2. The stackup/impedance and assembler DFM/stencil requests stay bound to the pre-003 manifest (valid as issued);
   the assembly request must be re-issued with the new R9–R11 poses before a quote is used.
3. `PCB_MAIN_ROUTING_AUTHORITY_REV_A` does not yet describe the OctoSPI/SDIO/EN_MODEM runs on the outer layers;
   its audit checks the predecessor. Updating the routing authority is a separate step.
4. PR #81 (candidate 002) closes without application.
