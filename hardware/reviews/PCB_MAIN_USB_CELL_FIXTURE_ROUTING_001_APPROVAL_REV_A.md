# PCB-MAIN cellular USB fixture-routing approval 001

Status: `ACCEPTED FOR EXACT APPLICATION / NOT REVIEW B / NOT FOR MANUFACTURE`

Reviewer `Скиф` authorized the most rational next engineering actions and
requested additional questions only in an extreme case. The commit-bound
proposal gate for exact source commit
`11af5c9df9ac8e4fd68ba78dbbd5c067bd3fe23f` passed CI #568 and PCB Native
#295. Comparative KiCad 9 DRC held violations at `232→232`, introduced zero
new errors and reduced unconnected items `425→421`.

Decision: `ACCEPT_USB_CELL_FIXTURE_ROUTING_SUBGATE`.

This approval authorizes only candidate board SHA-256
`2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273`:
27 segments and two 0.50/0.30 mm signal vias on `CELL_USB_DP_TP` and
`CELL_USB_DM_TP`. It authorizes no other footprint, copper, zone, keepout or
outline change.

The main-connector segment, returned job stackup, production impedance
tolerance, coupon, final SI/PI, Review B, CAM, DFM and manufacturing release
remain open.
