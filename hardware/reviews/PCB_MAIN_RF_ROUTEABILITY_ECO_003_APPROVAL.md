# PCB-MAIN RF routeability ECO-003 approval

Status: `ACCEPT_LIMITED_RF_ROUTEABILITY_ECO / PLACEMENT IMPLEMENTATION AUTHORIZED / ROUTING ENGINEERING CONTINUATION AUTHORIZED / NOT FOR MANUFACTURE`

Proposal: `PCB-MAIN-RF-ROUTEABILITY-ECO-003`

Reviewer: `Скиф`

Decision date: `19.09.2026`

Reviewed proposal: `hardware/reviews/PCB_MAIN_RF_ROUTEABILITY_ECO_003_CANDIDATE_REV_A.json`

Proposal SHA-256: `81c71958796e816fd28360562c1034a96c67d1c314bc645210ebc249065dc831`

Reviewed proposal record SHA-256: `72904af934e7ee41050a660d47fd59916ed798a9ee1183c5df0b828e509303ae`

Reviewed candidate-board SHA-256: `3561f334476259f4e2aa6143a49dcc945da7eb1a292400449b60d204ac421c5d`

Reviewed GitHub commit: `23d4195c15a380f4e12337094be0d09d022be065`

Decision: `ACCEPT_LIMITED_RF_ROUTEABILITY_ECO`

The reviewer authorizes exactly three unlocked placement changes:

- `FL1`: `(61.00, 69.50, 0°)` to `(60.50, 68.00, 0°)`;
- `D4`: `(61.00, 68.00, 0°)` to `(58.25, 70.00, 90°)`;
- `L2`: `(59.25, 69.50, 0°)` to `(59.75, 70.25, 90°)`.

These coordinates may be applied to the controlled placement manifest and the
unrouted authoritative PCB-MAIN layout source. RF routing engineering may
continue from this geometry.

The reviewed 89-segment, seven-net, F.Cu route is feasibility evidence only.
It is not approved as final production copper and must not be copied wholesale
into the authoritative board. Signal return-path design, ground stitching,
complete routing, SI review and routed-board DRC remain open.

This approval is not PCB-MAIN Review B and does not authorize CAM generation,
fabrication, assembly or manufacturing release. Final job-specific fabricator
impedance acceptance and assembler DFM also remain open.
