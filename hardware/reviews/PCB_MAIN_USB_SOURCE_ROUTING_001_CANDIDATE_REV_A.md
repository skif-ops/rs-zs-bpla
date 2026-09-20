# PCB-MAIN USB MCU source routing candidate 001 — Rev.A

Status: `STATIC PASS / COMMIT-BOUND KICAD 9 GATE PENDING / HUMAN ACCEPTANCE PENDING / NOT FOR MANUFACTURE`

Candidate `PCB-MAIN-USB-SOURCE-ROUTING-001` is a bounded proposal based on
authoritative PCB SHA-256
`d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e`.
It does not modify authoritative `PCB-MAIN`.

## Exact scope

- connect `U1.71 USB_DP_U1` to `R91.1`;
- connect `U1.70 USB_DM_U1` to `R92.1`;
- add 13 `F.Cu` segments and no signal vias;
- retain every footprint, outline, accepted RF trace, zone and unrelated
  copper item byte-for-byte;
- move only local `GND_DIGITAL` segment
  `fb9ade5d-8496-4617-9d20-390d44c347c4` and via
  `bbd350c1-609d-43b7-9dd0-824ee009466f` from `(62.1, 26.475)` to
  `(62.5, 26.75)`, without changing the via geometry, net or ground-domain
  topology.

The return-fanout move is required because the accepted via occupied the only
clearance-clean differential-pair channel between `C12` and `R3`. It is part
of this proposal and is not independently authorized for application.

## Engineering geometry

The proposal uses the controlled public `JLC06161H-3313` engineering basis:

- `0.1537 mm` trace width;
- `0.2032 mm` minimum pair edge gap;
- `F.Cu` over the unchanged `GND_DIGITAL` zone on `In1.Cu`;
- zero signal-layer transitions;
- both routes are `4.178827774173 mm`; computed mismatch is zero.

This numeric basis is valid only for an engineering candidate. Final
job-specific stackup, production tolerance, solver evidence and coupon plan
still require two attributable fabricator responses and project RF/SI review.

## Gate and boundary

Static regeneration and the independent topology/reference audit pass.
Commit-bound KiCad 9 comparative DRC must still prove zero new errors and an
exact two-connection reduction. Only after that evidence is recorded may the
reviewer consider token `ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE`.

This proposal does not route the main connector segment or either cellular
USB segment. Review B, final SI, DFM, CAM and manufacturing release remain
open. No fabrication or purchase is authorized.
