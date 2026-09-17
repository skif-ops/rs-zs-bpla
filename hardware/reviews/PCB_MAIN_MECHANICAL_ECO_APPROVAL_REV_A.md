# PCB-MAIN limited mechanical ECO approval - EVT-PRE-20 Rev.A

Status: `ACCEPT_LIMITED_MECHANICAL_ECO / IMPLEMENTATION AUTHORIZED / NOT FOR MANUFACTURE`

Proposal: `PCB-MAIN-MECH-ECO-001`

Reviewer: `Скиф`

Decision date: `15.09.2026`

Reviewed commit: `61cbe796de2f87560342a44b063ff6283a8ce1e8`

Reviewed candidate: `hardware/reviews/PCB_MAIN_MECHANICAL_ECO_CANDIDATE_REV_A.json`

Candidate SHA-256: `5ef7d0390da97796febbef6a69f0206a06efe00782e238bf7c8f32bf29d08fc1`

Decision: `ACCEPT_LIMITED_MECHANICAL_ECO`

The reviewer accepts only the nine-record `MAIN-AUTH-011` delta contained in
the exact candidate above and authorizes its application to the native
PCB-MAIN placement. The reviewed candidate remains byte-for-byte unchanged;
this sidecar is the commit-bound decision record.

The approval covers `MECH-007`, `MECH-008`, `MECH-014`, `MECH-016`,
`MECH-019`, `MECH-020`, `MECH-024`, `MECH-026` and `MECH-032`. It does not
authorize any X-coordinate, rotation, mounting-hole, board-outline, electrical
connectivity or other authority change.

This is a limited mechanical ECO approval, not PCB-MAIN Review B and not a
manufacturing release. Full unlocked-footprint repacking, controlled
courtyard/body evidence, strict placement clearance, routed-board KiCad DRC,
native STEP and enclosure service-sweep review, independent Review B, and
fabricator/assembler DFM acceptance remain blocking.
