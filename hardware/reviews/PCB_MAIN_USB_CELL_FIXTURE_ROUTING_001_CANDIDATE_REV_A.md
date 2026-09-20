# PCB-MAIN cellular USB fixture-routing candidate 001

Status: `STATIC PASS / COMMIT-BOUND KICAD 9 GATE PENDING / NOT APPLIED / NOT FOR MANUFACTURE`

This bounded proposal connects the already-routed BG95 USB series links to the
dedicated recovery fixture. The authoritative board remains unchanged.

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

The next gate is commit-bound CI plus comparative KiCad 9 DRC. The expected
ratsnest reduction is four connections because each fixture net joins its
series resistor, ESD pad and pogo pad. The exact candidate may be applied only
after that gate is green under the user's standing authorization.

This remains engineering geometry. The main-connector escape still requires
job-specific via/drill/annular/clearance evidence or a separate local ECO.
Final fabricator impedance, coupon, DFM, Review B, CAM and manufacturing
release remain open.
