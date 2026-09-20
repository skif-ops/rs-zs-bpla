# PCB-MAIN USB routeability review — Rev.A

Status: `MCU SOURCE APPLIED / CELL MODEM PROPOSAL READY / MAIN CONNECTOR DFM BLOCKED / REVIEW_B OPEN`

Reviewed source commit: `2c67acaeb93c05b1bb7a6d9267275ff9fc260204`.

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

Historical decision: `ECO_REQUIRED_USB_SOURCE_TERMINATION_CLUSTER`.

## Placement disposition

`PCB-MAIN-USB-PLACEMENT-ECO-001` supplied the bounded proposal requested
above. Its board SHA-256 is
`d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e`.
It supersedes the failed four-footprint candidate from PCB Native Gate #280
and moves only the previously unrouted R91/R92. Reviewer `Скиф` accepted the
exact delta; application commit `1f8c0bad` passed CI #557 and PCB Native #284
with zero new errors and unconnected `429→429`. The placement subgate is
closed, but it does not authorize USB copper.

## MCU source-routing proposal

The accepted placement exposed one additional local copper constraint: the
`GND_DIGITAL` via at `(62.1, 26.475)` occupies the only clearance-clean pair
channel between `C12` and `R3`. Candidate
`PCB-MAIN-USB-SOURCE-ROUTING-001` therefore routes only `USB_DP_U1` and
`USB_DM_U1` and relocates that exact via plus its attached ground segment.
Candidate SHA-256 is
`76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5`.
Static regeneration, exact length matching, `0.1537/0.2032 mm` geometry and
continuous `GND_DIGITAL` L2-reference sampling pass. Proposal commit
`f4ed1a4d` passed CI #559 and PCB Native #286: zero new errors, total
violations `232→232` and unconnected `429→427`. The exact candidate was
accepted and applied as authoritative commit `6c27d3ae`; CI #562 and PCB
Native #289 repeated violations `232→232`, zero new errors and unconnected
`429→427`.

Current decision:
`USB_MCU_SOURCE_ROUTING_APPLICATION_PASS_CELL_MODEM_PROPOSAL_READY_MAIN_CONNECTOR_DFM_BLOCKED`.

## Main-connector escape disposition

The GCT/KiCad single-row J11 contact mapping is retained: the duplicated USB2
contacts alternate D+/D- at 0.50 mm pitch. With the current general 0.20 mm
clearance, a 0.50/0.30 mm through-via cannot make a clearance-clean escape
between adjacent opposite-net pads/traces. No smaller via is introduced before
the job-specific fabricator returns finished-drill and annular-ring acceptance.
The connector segment therefore remains a separate DFM/escape ECO instead of
receiving speculative copper.

## Cellular modem-segment proposal

Candidate `PCB-MAIN-USB-CELL-MODEM-ROUTING-001` routes only
`CELL_USB_DP_U8` / `CELL_USB_DM_U8` between U8.9/U8.10 and R39.1/R40.1.
It adds six F.Cu segments, no vias and no other delta. Both routes are exactly
`4.765484866498 mm`; minimum pair edge gap is `0.2032 mm`; all sampled points
remain over the accepted `GND_MODEM` In1.Cu reference zone. Candidate SHA-256
is `4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5`.
Static regeneration and independent geometry checks pass. Proposal commit
`5c73ffe5` passed CI #564 and PCB Native #291: violations remained `232→232`,
zero new errors were introduced and unconnected items changed `427→425`.
Artifact `10613537447` is bound by digest
`sha256:fa9f1ab6357ad4ad2e356194e05ae999a6a8358641082a860228e0e4cfe04e90`.

The main connector pair and cellular fixture pair remain separate open
subgates. Final stackup/tolerance/coupon acceptance, Review B, CAM, DFM and
manufacturing release remain blocked.
