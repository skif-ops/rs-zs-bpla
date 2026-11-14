# PCB-MAIN EVT-PRE-20 8-layer adoption — Rev.B

Status: **ACCEPTED AS PRIMARY EVT SOURCE / RELEASE GATES REMAIN OPEN**

Date: 2026-10-16

PCB-MAIN COMPLETE-105 Rev.B is the primary EVT-PRE-20 board. The controlled
native KiCad location is `hardware/kicad/native/PCB-MAIN` and its board SHA-256
is `47b1c8dd391aabd6339c878ac4baff4f8fdf4f82d6ab588c13f7437552ea1f77`.

The accepted structure is eight copper layers: `F.Cu`, `In1.Cu` through
`In6.Cu`, and `B.Cu`; finished thickness 1.6 mm, ENIG, 1 oz outer copper and
0.5 oz inner copper. `JLC08161H-3313` is the preferred published stack example.
The selected order stack and dielectric values must still be confirmed in the
fabricator checkout and recorded before panel release.

The exact same board was present in
`EVT_PRE_20_ПЛАТЫ_ЗАКАЗ_И_МОНТАЖ_20261013_REV_D6`: board SHA-256
`f828fc6b30afbd64ed67afbee9ed7a5f5cdb9c47c1112722c5a0fe315268665f` before Git line-ending normalization and
`47b1c8dd391aabd6339c878ac4baff4f8fdf4f82d6ab588c13f7437552ea1f77` in the repository, KiCad DRC errors 0, unconnected
items 0 and ERC errors 0.

The former six-layer native source is preserved at
`hardware/kicad/retired/PCB-MAIN-6L-REV-A-2026-10-16` and is superseded.
It must not be used for current CAM generation.

This adoption does not waive fabricator DFM, selected-stack impedance review,
POFV confirmation, Altium warning disposition, Review B or first article checks.
