# PCB-PWR LM74700 VCAP routing candidate 002

Creation is authorized by
`ACCEPT_PCB_PWR_ROUTING_CANDIDATE_002_CREATION_SUBGATE`.

## Exact bounded delta

- Add one 0.5 mm `F.Cu` segment from `U1.1` to `C1.1` on
  `LM74700_VCAP`.
- Added length: 3.158307 mm.
- Add no vias or zones.
- Preserve the accepted bootstrap routing and every other predecessor object.

## Engineering selection

`LM74700_VCAP` is a short local analog-timing connection with an explicit
0.5 mm rule. The next buck switch-node routes require 2.1 mm copper, while the
current QFN escape is adjacent to BOOT and GND features. A narrow switch-node
substitution is prohibited; those nets remain deferred to a separate bounded
routeability or placement review.

## Gates retained

The authoritative board is unchanged. Commit-bound KiCad 9 comparative DRC
must preserve 86 violations, reduce unconnected items by exactly one and add
or remove no unrelated DRC fingerprint. Exact human acceptance is required
before application. Overall routing, Review B, CAM, DFM, thermal and
manufacturing release remain open.
