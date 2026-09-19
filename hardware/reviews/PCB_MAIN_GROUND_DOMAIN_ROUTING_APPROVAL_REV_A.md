# PCB-MAIN ground-domain routing subgate approval

Status: `ACCEPT_GROUND_DOMAIN_ROUTING_SUBGATE / EXACT CANDIDATE APPLICATION AUTHORIZED / ROUTING ENGINEERING CONTINUATION AUTHORIZED / NOT FOR MANUFACTURE`

Proposal: `PCB-MAIN-GROUND-DOMAIN-ROUTING-001`

Reviewer: `Скиф`

Decision date: `19.09.2026`

Decision: `ACCEPT_GROUND_DOMAIN_ROUTING_SUBGATE`

The reviewer confirmed the immediately preceding decision request with
`подтверждаю и продолжаем` after both proposal machine gates completed.

Reviewed GitHub commit:
`830139e8875e4e67738cf88b938a8d0ff91e2798`

Reviewed tree:
`7670dea776097a70381792ad4efadc349d6537df`

Reviewed proposal SHA-256:
`6ad0446ea98a44863cef91be137da3e5dcff92303ac9e395e260773e8cebc314`

Reviewed proposal record SHA-256:
`12f5ffafaa90cf3d796e08f17c333ac7701d0b17f286af487c31b8410673cb19`

Reviewed candidate-board SHA-256:
`9c8abfabc18fa22b53c94b6b4d7946dbe1dfab797fbff9d00d7c3408aece1b9e`

Machine gates:

- PCB Native Gate `35439569309`: `success`;
- CI `35439569334`: `success`;
- KiCad 9 comparative ground-domain DRC: `success`.

This approval authorizes application of exactly the reviewed 319-segment,
254-via candidate, its three shaped domain planes and four H1-H4 all-copper
rule areas to the authoritative PCB-MAIN board. The application must preserve
the reviewed board SHA-256 and must be recorded separately.

The accepted scope covers only the `GND_DIGITAL`, `GND_MODEM` and `GND_MIC`
fanout/plane subgate. Signal and power routing engineering may continue from
that exact geometry. Any change to the reviewed ground geometry requires a new
controlled delta and repeat machine/human review.

This approval does not complete routing, return-path review, SI/PI, thermal or
DFM review, does not close PCB-MAIN Review B, and does not authorize CAM
generation, fabrication, assembly, procurement release or manufacture.
