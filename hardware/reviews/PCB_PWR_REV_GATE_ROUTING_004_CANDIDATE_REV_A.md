# PCB-PWR REV_GATE routing candidate 004

Creation is authorized by
`ACCEPT_PCB_PWR_ROUTING_CANDIDATE_004_CREATION_SUBGATE`.

## Exact bounded delta

- Complete only `REV_GATE` from `U1.5` to `Q1.4` with four connected 0.5 mm
  `F.Cu` segments and zero vias.
- Route points are `(21.300,30.000)`, `(22.600,30.000)`,
  `(22.600,27.000)`, `(29.770,27.000)` and `(29.770,28.095)` mm.
- Added length is 12.565 mm.
- Add no zones and preserve all four accepted predecessor segments and every
  other board object.

## Engineering selection

`REV_GATE` is a complete two-pad local gate-drive net for the reverse-input
MOSFET. The screened top-layer corridor exits between the U1 and Q1 copper,
passes above the Q1 load pads and approaches gate pad `Q1.4` from above. The
minimum screened centerline distance to a foreign pad envelope is 0.650 mm;
commit-bound KiCad 9 DRC remains authoritative.

High-current `VBAT_FUSED`, `VBAT_PROTECTED` and `VBAT_SYS` copper, buck
hot-loop/switch-node routing, Kelvin sense, feedback and return planes remain
outside this candidate.

## Gates retained

The authoritative board is unchanged. Commit-bound KiCad 9 comparative DRC
must preserve the existing violation inventory, reduce unconnected items by
exactly one and introduce no unrelated DRC fingerprint. Exact human acceptance
`ACCEPT_PCB_PWR_REV_GATE_ROUTING_004_SUBGATE` is required before application.
Overall routing, Review B, CAM, DFM, thermal and manufacturing release remain
open.
