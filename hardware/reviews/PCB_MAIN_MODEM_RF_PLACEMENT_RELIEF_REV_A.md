# PCB-MAIN modem RF power placement relief — measured trial, Rev A (2026-09-27)

Scope: candidate 050 (`07904a6f469e1820218323e56d1cf13f992098f4098ba109bb3201fcb5594beb`),
still a draft with 91 open KiCad DRC connections. This note records a placement trial;
it is not an applied PCB change or a manufacturing approval.

## Observed blockage

`C47.1` (`3V8_MODEM_RF`, 10 pF, 0402) is at (9.675, 47.000) mm. The nearest
U8 RF supply pad is U8.53 at (27.850, 41.000) mm, 19.140 mm away in a straight
line. The DRC endpoint of the existing 0.8 mm F.Cu RF supply run is at
(5.1911, 53.7704), 8.121 mm from C47.1. A local F.Cu geometry search found a
9.23 mm path at only 0.15 mm width; this is not accepted as a modem RF supply
branch. Supply impedance and placement need review before copper is added.

The following F.CrtYd rectangles bound the available space near the 0.8 mm
In3.Cu RF supply run at x≈28.27 mm:

| Part | X bounds (mm) | Y bounds (mm) |
|---|---:|---:|
| U16 | 20.10–27.90 | 28.60–36.90 |
| C36 (`3V8_MODEM_BB` / `GND_MODEM`) | 28.19–37.31 | 31.95–37.05 |
| U8 | 11.05–36.95 | 37.20–66.80 |

The U16–C36 courtyard gap is **0.29 mm**. C47's courtyard is 1.60 × 1.00 mm,
so it cannot occupy that gap in the present placement. The U8 courtyard also
prevents placing it immediately below the supply pads.

## Bounded placement trial for candidate 051

An X-only move of C36 by +2.00 mm changes its courtyard to
(30.19–39.31, 31.95–37.05) mm and opens a 2.29 mm U16–C36 channel.
C47 at centre (29.045, 35.750) mm would then have courtyard
(28.245–29.845, 35.250–36.250) mm: 0.345 mm to each adjacent courtyard
in X and 0.950 mm to U8 in Y. This is a **geometric trial only**.

That C36 move overlaps R102's present courtyard
(37.70–39.30, 32.50–33.50) mm by 1.60 mm². A 0.25 mm-grid courtyard
search with 0.20 mm separation found R102 centre (38.50, 29.75) mm as the
nearest clear trial location, 3.25 mm from its present centre. Neither the
electrical connectivity nor service/assembly clearance of this three-part
move has been validated.

C36 remains only 0.15 mm from C44 above and U8 below, as in the current
placement. This trial preserves those two narrow courtyard gaps; it does
not establish assembly clearance there. The 0.20 mm search separation
applies to the proposed R102 location and C47's new side clearances.

Next operation: create an isolated 051 placement candidate with those three
coordinates; reroute C36's `3V8_MODEM_BB`/ground and R102's UART legs, then
connect both C47 pads with a short RF-supply and local `GND_MODEM` return.
Run KiCad 9 zone fill and comparative DRC, followed by modem burst PI,
return-path, courtyard, assembly and via-process review. Keep candidate 050
and authoritative board 003 unchanged until the trial passes.
