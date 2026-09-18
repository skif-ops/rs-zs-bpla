# PCB-MAIN mechanical ECO-002 approval

Status: `ACCEPT_LIMITED_MECHANICAL_ECO / IMPLEMENTATION AUTHORIZED / NOT FOR MANUFACTURE`

Proposal: `PCB-MAIN-MECH-ECO-002`

Reviewer: `Скиф`

Decision date: `18.09.2026`

Reviewed candidate: `hardware/reviews/PCB_MAIN_MECH_ECO_002_CANDIDATE.md`

Candidate SHA-256: `5164195ebf6a9a66b6a30197abfcb314655bfe059d0aea5f3782a744069780ff`

Candidate authority SHA-256: `8b3dbcb5b3fffe8ce393850e4fa65b178ea79c03b584c2f8b54e6fdfd93e42f9`

Candidate generated PCB SHA-256: `e81daf6d8cf0220f762c64f1fc637f65d71d6bc99128ab8c4993a540431e461e`

Candidate placement-repack SHA-256: `dbc433cb36b0bec612f55dbb96e6dce34d502728e488810c115207ffbbebc1d1`

Reviewed candidate commit: `b3ab796bcdee727798a121d114605e7ba84d683a`

Decision: `ACCEPT_LIMITED_MECHANICAL_ECO`

The reviewer authorized only two MAIN-AUTH-011 translations: `MECH-007` moves
the J_PWR mating-face centre from `(0.00,15.00)` to `(0.00,22.00)` mm without
rotation change, and `MECH-012` moves the J6 card-opening centre from
`(18.00,2.50)` to `(21.00,2.50)` mm without rotation change. H1 at
`(8.00,5.00)` mm is retained from the accepted ECO-001 baseline and is not a
new ECO-002 change.

No MPN, pinout, connector orientation, edge mating direction, drill, land
pattern, board outline or electrical-connectivity change is authorized by
this decision. The candidate-board hash is clearance evidence for the exact
two translations; it is not a blanket approval of unrelated layout work.

This approval is not PCB-MAIN Review B and does not authorize routing, CAM,
fabrication, assembly or manufacturing release. Stackup and impedance
acceptance, routed-board DRC, STEP/enclosure service-volume review,
fabricator/assembler DFM and independent Review B remain open.
