# PCB-MAIN cellular USB modem routing candidate 001

Status: `STATIC PASS / COMMIT-BOUND KICAD 9 GATE PENDING / NOT FOR MANUFACTURE`

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
pass. Application is allowed only after commit-bound KiCad 9 comparative DRC
shows zero new errors and exactly two fewer unconnected items.

This is an engineering routing candidate only. Final fabricator impedance,
coupon, DFM, Review B, CAM and manufacturing release remain open.
