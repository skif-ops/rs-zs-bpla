# PCB-MAIN USB source-termination placement ECO-001 candidate — Rev.A

Status: `PROPOSAL / KICAD9 AND HUMAN REVIEW PENDING / NOT APPLIED`.

Base authoritative PCB SHA-256:
`f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9`.

Candidate SHA-256:
`e92d3a65a9b716d4940d5ebf91fc516240afb62974a666e040594cc78a8dc424`.

The candidate moves only four unlocked 0402 footprints:

| RefDes | Base pose, mm/deg | Candidate pose, mm/deg | Purpose |
|---|---:|---:|---|
| R91 | 49.00, 18.25, 180 | 61.75, 25.75, 0 | place USB D+ termination beside U1.71 |
| R92 | 55.00, 18.25, 180 | 61.75, 26.75, 0 | place USB D- termination beside U1.70 |
| C12 | 61.75, 25.25, 0 | 63.50, 24.00, 0 | clear the paired termination escape |
| R3 | 61.75, 27.25, 0 | 63.50, 25.25, 0 | clear the paired termination escape |

U1, J11 and U25 remain fixed. No net, pad, footprint definition, trace, via,
zone, keepout, outline or accepted RF-remediation object changes. Direct
source-side distances U1.71→R91.1 and U1.70→R92.1 are both
`1.693553955 mm`; the direct-length mismatch is zero. Both resistor pad 1
lands face U1.

The strict 2D model reports 227/227 fitted assembly footprints with zero
component, mounting-exclusion or U.FL tool-clearance conflicts. This is only a
placement proposal. KiCad 9 zone refill/comparative DRC, human acceptance,
USB pair routing, final fabricator impedance acceptance, Review B, CAM and
manufacturing release remain open.

Requested future decision token after a green commit-bound gate:
`ACCEPT_USB_SOURCE_TERMINATION_PLACEMENT_SUBGATE`.

