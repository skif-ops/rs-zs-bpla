# PCB-MAIN cellular USB fixture-routing candidate 001

Status: `ACCEPTED / EXACT CANDIDATE APPLIED / APPLICATION GATE PENDING / NOT FOR MANUFACTURE`

This bounded proposal connects the already-routed BG95 USB series links to the
dedicated recovery fixture. The exact candidate is now the authoritative board.

## Exact delta

- route only `CELL_USB_DP_TP` and `CELL_USB_DM_TP` from R39/R40 pad 2 through
  the existing U26 ESD pads to TP_CELL_USB contacts 2/3;
- add six local F.Cu segments, 21 B.Cu segments and two 0.50/0.30 mm signal
  vias; modify no existing copper, footprint, zone, outline or keepout;
- use the public engineering geometry `0.1537 mm` width and `0.2032 mm`
  minimum pair edge gap;
- keep the complete primary paths exactly `76.293814073931 mm` and the two
  ESD shunts exactly `1.007782218537 mm`;
- keep the B.Cu trunk over the accepted `GND_MODEM` In4.Cu reference polygon;
- reuse the adjacent existing `GND_MODEM` return vias at 1.044330 mm and
  0.865975 mm from the respective signal transitions.

The conservative static copper check finds `0.23625 mm` minimum clearance to
pre-existing obstacles. The candidate board SHA-256 is
`2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273`.
Deterministic regeneration, exact topology, endpoint, length, pair-gap,
reference-plane, return-via and non-mutation checks pass.

Proposal commit `11af5c9df9ac8e4fd68ba78dbbd5c067bd3fe23f`
passed CI #568 and PCB Native #295. Comparative KiCad 9 DRC retained
`232→232` violations, introduced zero new errors and reduced unconnected items
from `425` to `421`. Artifact `10614043819` has digest
`sha256:0a2bd9269a99a517716182f84fa280f3807c1f56045731a6a2253f4f434b7680`.

The user's standing authorization accepts this exact hash-bound delta. It is
applied to the authoritative board; the commit-bound application gate is
pending.

This remains engineering geometry. The main-connector escape still requires
job-specific via/drill/annular/clearance evidence or a separate local ECO.
Final fabricator impedance, coupon, DFM, Review B, CAM and manufacturing
release remain open.
