# PCB-MAIN cellular USB modem routing candidate 001

Status: `COMMIT-BOUND KICAD 9 PASS / APPLICATION AUTHORIZATION RECORDED / NOT FOR MANUFACTURE`

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

The machine gate is closed. The user's standing instruction to approve the
most rational decisions and avoid additional questions authorizes recording
the bounded acceptance separately before exact application.

This is an engineering routing candidate only. Final fabricator impedance,
coupon, DFM, Review B, CAM and manufacturing release remain open.
