# PCB-MAIN USB source-termination placement ECO-001 candidate — Rev.A

Status: `PROPOSAL / KICAD9 AND HUMAN REVIEW PENDING / NOT APPLIED`.

Base authoritative PCB SHA-256:
`f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9`.

Candidate SHA-256:
`d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e`.

The revised candidate moves only two previously unrouted 0402 footprints:

| RefDes | Base pose, mm/deg | Candidate pose, mm/deg | Purpose |
|---|---:|---:|---|
| R91 | 49.00, 18.25, 180 | 64.00, 25.25, 0 | place USB D+ termination near U1.71 |
| R92 | 55.00, 18.25, 180 | 64.00, 26.25, 0 | place USB D- termination near U1.70 |

U1, J11 and U25 remain fixed. No net, pad, footprint definition, trace, via,
zone, keepout, outline or accepted RF-remediation object changes. C12/R3 stay
at their authoritative positions with their accepted fanout intact. Direct
source-side distances are `3.996013639 mm` for D+ and `3.932953725 mm` for D-;
their `0.063059914 mm` difference is reserved for trace matching. Both
resistor pad 1 lands face U1.

The earlier candidate SHA-256 `e92d3a65…c424` is superseded. PCB Native Gate
`#280` proved it invalid: moving C12/R3 increased unconnected items from 429
to 431 and introduced one clearance plus one hole-clearance error at the
existing GND via `(62.725, 24.35)`.

The strict 2D model reports 227/227 fitted assembly footprints with zero
component, mounting-exclusion or U.FL tool-clearance conflicts. This is only a
placement proposal. KiCad 9 zone refill/comparative DRC, human acceptance,
USB pair routing, final fabricator impedance acceptance, Review B, CAM and
manufacturing release remain open.

Requested future decision token after a green commit-bound gate:
`ACCEPT_USB_SOURCE_TERMINATION_PLACEMENT_SUBGATE`.
