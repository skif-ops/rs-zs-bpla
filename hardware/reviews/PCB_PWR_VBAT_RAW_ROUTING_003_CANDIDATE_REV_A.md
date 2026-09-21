# PCB-PWR VBAT_RAW routing candidate 003

Creation is authorized by
`ACCEPT_PCB_PWR_ROUTING_CANDIDATE_003_CREATION_SUBGATE`.

## Exact bounded delta

- Add one 4.0 mm `F.Cu` segment from `J1.1` to `F1.1` on `VBAT_RAW`.
- Added length: 5.946428 mm.
- Add no vias or zones.
- Preserve all three accepted predecessor segments and every other object.

## Engineering selection

`VBAT_RAW` is a short two-pad 5 A input connection. The candidate uses the
full 4.0 mm rule width and avoids a layer transition. Complex buck hot-loop,
switch-node, Kelvin and return routing remains outside this candidate.

## Gates retained

The authoritative board is unchanged. Commit-bound KiCad 9 comparative DRC
must preserve the existing violation inventory, reduce unconnected items by
exactly one and introduce no unrelated DRC fingerprint. Exact human acceptance
is required before application. Overall routing, Review B, CAM, DFM, thermal
and manufacturing release remain open.
