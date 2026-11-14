# PCB-PWR Rev.A DIM-003 mechanical freeze

Status: `18 OF 18 RESPONSES ACCEPTED FOR EVT / MECHANICAL ROUTING INPUT AUTHORIZED / SERIAL REVALIDATION REQUIRED / NOT FOR MANUFACTURE`

The original 18-row request has been answered under the project owner's
authorization to use rational engineering defaults for the EVT test batch. The
accepted authority is bounded to EVT-PRE-20 Rev.A; it is not a serial enclosure,
fabricator stackup, Review-B or manufacturing release.

Machine contract:
`hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.json`

Accepted engineering authority:
`hardware/reviews/PCB_PWR_DIM_003_EVT_AUTHORITY_REV_A.{md,json}`

Response register:
`hardware/reviews/PCB_PWR_DIM_003_RESPONSE_REV_A.csv`

Frozen EVT STEP envelope:
`mechanics/pcb_pwr/PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_A.step`

Independent audit:
`tools/audit_pcb_pwr_dim_003_request_rev_a.py`

## Accepted EVT basis

| Item | Accepted value | Boundary |
|---|---|---|
| PCB outline | `90.00 x 60.00 mm`, four straight Edge.Cuts, no cut-outs | `+/-0.15 mm`; serial revalidation required |
| PCB thickness | `1.60 +/-0.16 mm` | exact construction and copper remain fabricator inputs |
| Copper layers | `4` | count frozen; dielectric construction and copper weights open |
| Mounting | H1 `(5,5)`, H2 `(82,5)`, H3 `(68,55)`, H4 `(5,55) mm` | round NPTH `3.40 +/-0.10 mm`; no PCB slots |
| Mounting keep-outs | all-copper `D8.0 mm`; fitted-body `D10.0 mm` | enforced by footprint clearance and independent geometry audit |
| J1 | `(6.00,28.00) mm`, top entry | `+Z` mating and west cable exit; `20 mm` minimum bend radius |
| J2 | `(90.00,56.00) mm`, east exit | `+X` mating; bundle `<=9 mm`; `45 mm` minimum bend radius |
| DFT | TP1–TP10 top row, `2.54 mm` pitch | H1 primary datum; H2 diamond-pin fixture datum; top pogo access |
| Assembled Z | `-3.0 ... +18.0 mm` from PCB bottom | EVT conservative envelope, not exact serial component CAD |
| Routed copper | `0` tracks, `0` vias, `0` zones | remains blocked by stackup/copper and numeric power geometry |

All four mounting features are native board-only footprints excluded from BOM and
pick-and-place. The closest fitted-body margin outside the `D10` exclusion is
positive (`0.53 mm`); existing-pad conflicts with the `D8` copper exclusions are
zero. Board slots were rejected because round holes plus a diamond locator in the
fixture provide a more repeatable datum without weakening the PCB edge.

## Acceptance and serial-transition rule

All 18 response rows are attributable and `ACCEPTED_EVT_ENGINEERING`. The accepted
STEP records the board, mounting holes, conservative assembled envelope and J1/J2
service volumes. The serial enclosure must repeat the interference, connector,
thermal and harness-route checks using final component and enclosure CAD.

Any change to outline, holes, J1/J2 positions, DFT row or service volumes requires
a controlled PCB ECO and repeat placement/mounting clearance. Final harness cut
lengths remain separately blocked by `DIM-001`, `DIM-012` and the enclosure route.

## Release interlock

DIM-003 no longer blocks PCB-PWR routing input: outline/mounting, connector service,
DFT access and the EVT STEP are accepted. Routing itself remains prohibited until
the two-fabricator stackup/copper gate and numeric current-density, voltage-drop,
fault-energy and thermal geometry are accepted. DRC, CAM, DFM, Review B and
manufacturing release remain false.
