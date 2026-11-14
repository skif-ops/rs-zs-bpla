# PCB-MAIN mechanical ECO-002 candidate

Status: `CANDIDATE / SIGNATURE REQUIRED / NOT A FABRICATION RELEASE`

## Proposed controlled delta

| Authority record | Existing approved ECO-001 geometry | Proposed geometry | Reason |
| --- | --- | --- | --- |
| `MECH-007` / `J_PWR` | mating-face centre `(0.00, 15.00)`, 90 deg | `(0.00, 22.00)`, 90 deg | clears the SIM1 card-service envelope and H1 exclusion field |
| `MECH-012` / `J6` | card-opening centre `(18.00, 2.50)`, 180 deg | `(21.00, 2.50)`, 180 deg | clears the `J_PWR` body and the H1 exclusion field |

No MPN, pinout, connector orientation, edge mating direction, drill, land pattern or
board outline changes are proposed. `H1=(8.00,5.00)` remains the already accepted
ECO-001 datum and is not part of ECO-002.

## Independent geometry evidence

The regenerated six-layer native candidate using the proposed rows passes strict
placement clearance: 227 assembly envelopes, 227 controlled courtyards, zero
component/component, component/mounting and component/tool conflicts.

The same candidate with ECO-001 retained but the two ECO-002 rows restored to their
previous coordinates fails strict clearance with a `J6`/`J_PWR` collision and both
connectors entering the H1 exclusion field. Therefore the delta is necessary for a
manufacturable placement; it is not a routing convenience.

Candidate authority CSV SHA-256:
`8b3dbcb5b3fffe8ce393850e4fa65b178ea79c03b584c2f8b54e6fdfd93e42f9`

Candidate generated PCB SHA-256:
`e81daf6d8cf0220f762c64f1fc637f65d71d6bc99128ab8c4993a540431e461e`

## Approval boundary

Until a named approver accepts this candidate against a committed source state, the
native PCB remains `LAYOUT_ENGINEERING_CANDIDATE / NOT FOR MANUFACTURE`. Routing and
BOM work may proceed against it as engineering work; CAM, fabrication files and a
production-release claim remain blocked.
