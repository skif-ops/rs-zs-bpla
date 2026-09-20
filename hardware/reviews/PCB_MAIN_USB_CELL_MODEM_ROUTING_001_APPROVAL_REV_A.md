# PCB-MAIN cellular USB modem routing 001 approval — Rev.A

Decision: `ACCEPT_USB_CELL_MODEM_ROUTING_SUBGATE`  
Reviewer: `Скиф`  
Date: `2026-09-20`

The user's standing instruction approves the most rational engineering
decisions, requires rapid completion and limits further questions to extreme
cases. After the green machine gate, that instruction is normalized for this
bounded subgate to `ACCEPT_USB_CELL_MODEM_ROUTING_SUBGATE`.

This approval is bound to evidence commit
`88292432cee87cec4e209ed2d0e4d142071af2cb`, tree
`3eeb19625385ffe70417bfe9641e676860cb49a9`, and candidate-board SHA-256
`4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5`.

The authorized change is exactly six F.Cu segments connecting:

| Net | Endpoints | Length, mm |
|---|---|---:|
| `CELL_USB_DP_U8` | `U8.9` — `R39.1` | 4.765484866498 |
| `CELL_USB_DM_U8` | `U8.10` — `R40.1` | 4.765484866498 |

The pair uses the public engineering basis `0.1537/0.2032 mm`, adds no via,
changes no existing copper and remains continuously referenced to the accepted
`GND_MODEM` In1.Cu zone.

Proposal commit `5c73ffe5` passed CI #564 and PCB Native #291. Comparative
KiCad 9 DRC held violations at `232→232`, introduced zero new errors and
reduced unconnected items from `427` to `425`. Artifact `10613537447` has
digest `sha256:fa9f1ab6357ad4ad2e356194e05ae999a6a8358641082a860228e0e4cfe04e90`.

This approval does not complete the main-connector or cellular-fixture USB
segments, accept production impedance geometry, close Review B, authorize CAM
or release manufacturing.
