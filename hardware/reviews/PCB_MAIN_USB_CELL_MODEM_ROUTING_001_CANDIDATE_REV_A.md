# PCB-MAIN cellular USB modem routing candidate 001

Status: `ACCEPTED / EXACT CANDIDATE APPLIED / APPLICATION GATE PASS / NOT FOR MANUFACTURE`

This bounded proposal closes only the BG95-side differential segment between
U8 pads 9/10 and R39/R40 pad 1. The authoritative board remains unchanged.

## Exact delta

- add six F.Cu segments on `CELL_USB_DP_U8` and `CELL_USB_DM_U8`;
- use the public engineering geometry `0.1537 mm` width and `0.2032 mm`
  minimum pair gap on L1 over the accepted `GND_MODEM` L2 zone;
- connect `U8.9 → R39.1` and `U8.10 → R40.1` with both routes exactly
  `4.765484866498 mm` long;
- add no vias and change no footprint, zone, outline or accepted copper.

The candidate board SHA-256 is
`4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5`.
Deterministic regeneration and independent static topology/reference checks
pass. Proposal commit `5c73ffe5b9eae3f623f7336c705f939a2a5af2fd`
passed CI #564 and PCB Native #291. Comparative KiCad 9 DRC retained
`232→232` violations, introduced zero new errors and reduced unconnected items
from `427` to `425`. Artifact `10613537447` has digest
`sha256:fa9f1ab6357ad4ad2e356194e05ae999a6a8358641082a860228e0e4cfe04e90`.

The proposal gate is closed. The user's standing instruction authorized this
bounded acceptance, and the exact candidate is now the authoritative board.
Application commit `4c9a2a85` passed CI #566 and PCB Native #293 with the same
`232→232` violations, zero new errors and `427→425` unconnected result.
Application artifact `10612868581` has digest
`sha256:6f37e792d7f0f7e09c22e5746743976e3953f6b12a5ccfa8f86e1ccd16f5b615`.

This is an engineering routing candidate only. Final fabricator impedance,
coupon, DFM, Review B, CAM and manufacturing release remain open.
