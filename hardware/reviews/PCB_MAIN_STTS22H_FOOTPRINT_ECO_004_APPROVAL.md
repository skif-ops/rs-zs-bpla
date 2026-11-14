# PCB-MAIN STTS22H footprint ECO-004 approval

Status: `ACCEPT_STTS22H_FOOTPRINT_ECO_004 / IMPLEMENTATION AUTHORIZED / ROUTING ENGINEERING CONTINUATION AUTHORIZED / NOT FOR MANUFACTURE`

Proposal: `PCB-MAIN-STTS22H-FOOTPRINT-ECO-004`

Reviewer: `Скиф`

Decision date: `19.09.2026`

Decision: `ACCEPT_STTS22H_FOOTPRINT_ECO_004`

The reviewer confirmed the immediately preceding ECO decision request with
`подтверждаю и продолжаем`.

Reviewed GitHub commit:
`059ecd0e2e35fc56a56f48d62cce4f72a93755c0`

Reviewed tree:
`d6805c8f15ce319410a996f143132c6f8f58f35e`

Reviewed proposal SHA-256:
`4b7da50ef11415385317f4811a26301c189988e349d3fcef0b0107692a443df8`

Reviewed proposal record SHA-256:
`35b7c9455fad54013959b2f589fa3068830b8d2dbb812ce924fb42ebd6d4e772`

Reviewed candidate footprint SHA-256:
`e06136e5f2ebd67798141ff1ef99db94d895d139d20b3c98a671e34bbbfa277f`

Reviewed materialized board SHA-256:
`a50aa153d1dad2ccc9f0759213932767c9950c441a887aaf5ab2d3d9fb59a2d8`

Machine gates:

- PCB Native Gate `35435603064`: `success`;
- CI `35435603054`: `success`.

This approval authorizes only the bounded U4 correction described by ECO-004:
signal-pad rows move from `Y = +/-0.540 mm` to `Y = +/-0.865 mm`, the U4
courtyard expands to `Y = +/-1.500 mm`, and the U4 reference text moves to
`Y = -1.800 mm`. U4 placement, EP geometry, pad sizes, shapes, layers, nets and
local clearance remain unchanged.

The correction may be applied to the controlled footprint library, deterministic
generator, footprint review register, independent audits and unrouted authoritative
PCB-MAIN board. Routing engineering may continue from the corrected geometry.

This approval does not authorize candidate or future routing as final production
copper, does not complete PCB-MAIN Review B, and does not authorize CAM generation,
fabrication, assembly or manufacturing release.
