# Дионея EVT-PRE-20 Rev.A - PCB-PWR provisional placement candidate

Status: `FITTED 2D + EVT MOUNTING CLEARANCE PASS / DIM-003 18/18 EVT ACCEPTED / THREE CONTROLLED ROUTING SEGMENTS APPLIED / ROUTING INCOMPLETE / NOT FOR MANUFACTURE`

This authority creates a reviewable native-board canvas without claiming enclosure or
fabrication approval. The four-copper-layer count is frozen for Rev.A by
`hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv`. The `90 x 60 mm` outline,
`1.60 +/-0.16 mm` thickness, four round M3 mounting holes, assembled envelope,
terminal zones and fixture datum are accepted for the EVT test batch by
`hardware/reviews/PCB_PWR_DIM_003_EVT_AUTHORITY_REV_A.{md,json}`. This is a
mechanical routing input, not a serial-enclosure or manufacturing release; serial
transition requires a repeat mechanical/STEP review.

## Controlled candidate content

- all 62 physical schematic references are present once and carry their exact native
  footprint and net assignment;
- J1 starts the west-side input/protection chain and J2 is provisionally oriented for
  an east-side harness exit;
- the 3V8 and 3V3 buck channels occupy separate upper and lower functional regions;
- the two LMR60440 input/bootstrap/inductor/output groups are kept close enough for
  power-loop review; accepted ECO-001 places C4/C6 at `(54.575,16.40/44.40)`
  with 180° rotation and L1/L2 at `(60.75,14.00/42.00)` with 180° rotation,
  but no copper geometry is inferred from placement alone;
- the INA226 and shunt occupy one Kelvin-review region;
- TP1-TP10 form a top-side `2.54 mm` pitch review row using the controlled no-paste
  `1.70 mm` target. Final side, fixture datum and probe access remain open;
- four board-only round `NPTH 3.4 mm` mounting holes are present at
  H1 `(5,5)`, H2 `(82,5)`, H3 `(68,55)`, H4 `(5,55) mm`; each enforces a
  `D8.0 mm` all-copper exclusion and `D10.0 mm` fitted-body exclusion;
- all 44 simultaneously fitted assembly bodies have controlled courtyards and
  pass the independent `0.20 mm` 2D clearance subgate; the minimum observed
  fitted-courtyard clearance is `0.22 mm`.

The historical exact ECO-001 placement board has SHA-256
`9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37`.
Its fresh commit-bound application gate passed at source commit `878425d2` with
zero new error classes and unchanged `126` unconnected items.

The separately reviewed `PCB-PWR-BUCK-WARNING-REMEDIATION-001` successor is now
applied byte-for-byte as the authoritative board with SHA-256
`b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957`.
It preserves every component pose and all pad copper geometry, normalizes only
C4/C6 rotated child serialization, retains their physical reference centres and
moves only the R10 visible reference. The corrected candidate passed CI #586,
PCB-PWR Schematic #65 and PCB Native #313 with exact `90 -> 86` violation and
`126 -> 126` unconnected-item results; reviewer `Скиф` supplied the exact
acceptance token. Its fresh commit-bound application gate passed at CI #592,
PCB-PWR Schematic #70 and PCB Native #319 with exact `90 -> 86` violations,
unchanged `126 -> 126` unconnected items and no other DRC fingerprint delta.
The four warning-only items are therefore closed; routing, Review B and CAM
remain blocked by their independent gates.

The authoritative successor is SHA-256
`05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3`.
It contains exactly four accepted F.Cu segments: both bootstrap connections,
the LM74700 VCAP connection and the `VBAT_RAW` connection. It has zero vias and
zero copper zones. The separate `PCB-PWR-REV-GATE-ROUTING-004` artifact is
accepted but is not applied to the active board.

## Local input-capacitor placement evidence

TI SNAS877 Table 8-3 requires both local `CIN=4.7 uF` and
`CIN_HF=0.1 uF`. The current provisional coordinates provide the following
center-to-center distances:

| Buck | Local `CIN` | Distance | Local `CIN_HF` | Distance |
|---|---|---:|---|---:|
| `U3` | `C11` | `6.00 mm` | `C20` | `2.60 mm` |
| `U4` | `C12` | `6.00 mm` | `C21` | `2.60 mm` |

These distances prove only that the intended parts occupy the correct local
functional regions. The four accepted partial-routing segments do not implement
or prove the final VIN-PGND loop geometry. C11/C12 effective capacitance at bias and
temperature, direct pad-first routing of C20/C21, and routed hot-loop review
remain mandatory.

`C13` is central 100 uF `VBAT_SYS` damping, not local buck input-capacitor
authority. Its provisional center distances are `19.70 mm` to U3 and `12.81 mm`
to U4, so no release claim may rely on C13 as a substitute for C11/C20 or
C12/C21. Exact TI source binding and the independently recomputed distances are
controlled by
`hardware/reviews/PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.{md,json}` and
`tools/audit_pcb_pwr_design_rev_a.py`.

## Hard interlocks

The active candidate must contain only the four accepted bootstrap/VCAP/VBAT_RAW
segments, zero vias and zero copper zones; any other active copper fails this
gate. Gerber, drill, position and IPC-356 fabrication export remain prohibited. The controlled
EVT envelope STEP is the sole permitted mechanical export in this state. The independent
audit checks the complete reference/net/footprint set, every candidate coordinate,
the frozen layer count, accepted EVT outline/thickness and the closed EVT
`DIM-003` record.

The bounded fitted-body clearance repack and its independent strict audit are
recorded in `hardware/reviews/PCB_PWR_PLACEMENT_CLEARANCE_REV_A.md`. Five DNP
footprints and thirteen PCB features are not assembly bodies; their copper,
fixture and service-access checks remain mandatory. J2's provisional east-edge
overhang is not a mating, cable-bend, enclosure or 3D clearance approval.

All 31 native nets now have controlled pre-route coverage in
`hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv`. That manifest adds current,
return-domain, topology, layer/via and separation inputs without relaxing this
placement interlock. `DIM-003` and the standard `JLC04161H-3313`, 1.6 mm,
outer 2 oz / inner 1 oz EVT ordering profile are accepted as routing input;
the routing candidate itself still requires its own controlled subgate.

The historical stackup/copper request is controlled in
`hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.md`. All `24/24` rows are
closed by the EVT engineering baseline; no fabricator reply is required. Actual
checkout DFM deviations still return as ECOs and this does not authorize fabrication.

Review B still requires preservation of the accepted EVT stackup and mechanics;
high-current and Kelvin routing; hot-loop and switch-node control; physical
thermal/current-density evidence;
TVS/fuse coordination; DRC; DFM; load-step, cold-start, fault, EMI and fixture evidence.
