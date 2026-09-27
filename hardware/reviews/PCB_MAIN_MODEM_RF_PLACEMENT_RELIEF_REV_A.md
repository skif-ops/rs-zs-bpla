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

## Bounded placement trial — rejected at copper preflight

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

Moving all three footprints in a temporary in-memory board and checking the
new pad shapes against existing F.Cu copper (0.20 mm clearance) found:

| Moved pad | Intersecting / clearance-blocking nets |
|---|---|
| C36.1, `3V8_MODEM_BB` | `TEST_UART_RX_U1`, `LORA_MOSI_U10`, `LORA_NSS_U10` |
| C36.2, `GND_MODEM` | `CELL_STATUS_U16`, `CELL_USIM_DATA_1V8` |
| C47.1, `3V8_MODEM_RF` | `CELL_DTR_U16` at 0.198 mm, below the 0.20 mm screening clearance |

The two C47 pads have a nominal 0.20 mm mutual gap in the existing 0402
footprint; their mutual contact with a 0.20 mm screening buffer is not a new
external-net conflict. C47.2 showed no additional external-net conflict in
this scan. R102's moved pads likewise only meet the footprint's nominal
mutual 0.20 mm clearance.

Thus the three-coordinate move is **rejected as a direct candidate 051**.
Courtyard clearance alone concealed multiple signal/power conflicts; the
existing C36 power and ground branches and R102 UART copper would also need
replacement. A larger placement/rip-up proposal must explicitly preserve
those nets and the modem/digital return boundaries before generating a PCB
candidate. KiCad 9 DRC, modem burst PI, assembly and via-process review would
follow that proposal. Candidate 050 and authoritative board 003 remain
unchanged.
