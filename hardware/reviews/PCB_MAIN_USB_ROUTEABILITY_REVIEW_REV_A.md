# PCB-MAIN USB routeability review — Rev.A

Status: `ECO_REQUIRED / ROUTING_NOT_AUTHORIZED / REVIEW_B_OPEN`

Reviewed source commit: `fd2cfb324be9ef4a97acc538adee681e9770b2eb`.

The authoritative PCB retains the accepted combined RF remediation and is not
modified by this review.  The next controlled routing class was evaluated as
the four 90-ohm USB differential segments before adding copper.

## Finding

The connector-side pair is locally coherent: J11 D+/D- reaches the fixed U25
protection device with adjacent contacts.  The MCU-side source-termination
placement is not routeable as a bounded differential pair without a placement
ECO:

- U1 pads 70/71 (`USB_DM_U1` / `USB_DP_U1`) are at `(59.75, 26.50)` and
  `(59.75, 26.00)` mm, with 0.50 mm pitch;
- series resistors R92/R91 are at `(55.00, 18.25)` and `(49.00, 18.25)` mm;
- the resistor centres are separated by 6.00 mm and their U1-side pads are not
  presented as an adjacent pair;
- the local escape area beside U1 is already occupied by C4, C12 and R3, so a
  two-footprint translation cannot be asserted collision-free without a
  bounded local-cluster placement review.

Routing the present placement would require a long pair split before the
source terminations and would contradict the controlled
`DIFFERENTIAL_SERIES_SEGMENT` topology.  A green generic DRC would not prove
USB pair integrity.

## Required bounded ECO

Create a proposal limited to `R91`, `R92` and only those local U1 support
passives proven necessary for courtyard/escape clearance.  U1, J11 and U25,
the board outline, mounting exclusions, accepted RF traces, the cellular L2
zone and the GNSS remediation must remain unchanged.

The proposal must prove strict 2D clearance, adjacent source-side presentation,
pair topology, `0.1537/0.2032 mm` candidate width/gap on L1 over L2, matched
length for each controlled segment, continuous `GND_DIGITAL` reference, and
comparative KiCad 9 DRC.  Final geometry remains subject to the selected
fabricator's job-specific stackup/impedance response.

Decision: `ECO_REQUIRED_USB_SOURCE_TERMINATION_CLUSTER`.

## Candidate disposition

`PCB-MAIN-USB-PLACEMENT-ECO-001` now supplies the bounded four-footprint
proposal requested above.  Its board SHA-256 is
`d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e`.
It supersedes the failed four-footprint candidate from PCB Native Gate #280
and now moves only the previously unrouted R91/R92. Static regeneration,
strict clearance and commit-bound KiCad 9 comparative DRC pass on commit
`ad3745e7` / PCB Native Gate #281, with errors `0→0` and unconnected
`429→429`. Human acceptance remains pending. The routeability decision remains
open and the candidate is not applied to authoritative PCB-MAIN.
