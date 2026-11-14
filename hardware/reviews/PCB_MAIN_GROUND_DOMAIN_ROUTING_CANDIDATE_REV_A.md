# PCB-MAIN ground-domain routing candidate 001 — Rev.A

Status: `PROPOSAL / MACHINE GATE REQUIRED / SIGNATURE REQUIRED / NOT A FABRICATION RELEASE`

This package isolates the first PCB-MAIN copper subgate: fanout and shaped plane
geometry for `GND_DIGITAL`, `GND_MODEM` and `GND_MIC`. The authoritative native
board remains unchanged and unrouted. The candidate is evidence for a human
decision; it is not final routing and it does not close Review B.

## Controlled result

The candidate adds 319 short `0.15 mm` neck segments, 254 through vias of
`0.50/0.30 mm`, three independent domain zones and four all-copper mounting-hole
rule areas. It changes no footprint, pad, net, outline, stackup token or placement.

| Domain | Plane layer | Endpoints | Fanout vias | Direct pads | Segments |
|---|---|---:|---:|---:|---:|
| `GND_DIGITAL` | `In1.Cu` reference | 139 | 138 | 1 | 187 |
| `GND_MODEM` | `In4.Cu` reference | 96 | 95 | 1 | 106 |
| `GND_MIC` | `In2.Cu` power-domain layer | 22 | 21 | 1 | 26 |

`GND_MIC` was deliberately moved from the experimental `B.Cu` pour to `In2.Cu`.
That follows the controlled six-layer function intent (`In2.Cu = POWER_DOMAINS`)
and keeps `B.Cu` available for signals and the production fixture.

The first draft of this candidate was rejected during clean-project preflight:
its experimental `0.10 mm` obstacle raster produced 49 copper-clearance errors
and 21 additional finished-hole-clearance errors. The committed candidate is a
full reroute of all 254 fanouts against the authoritative `0.20 mm` copper and
`0.25 mm` finished-hole rules; it is not the rejected draft.

## Plane boundaries and mechanical authority

The first full-board experimental pours were rejected even though native DRC did
not report an error: they did not encode all constraints that exist only in the
mechanical authority. The reviewed candidate therefore uses shaped zones:

- `GND_DIGITAL` is absent from the exclusive cellular region;
- `GND_MODEM` is absent from GNSS, LoRa, BLE-body and audio/digital regions;
- `GND_MIC` is absent from cellular, GNSS, LoRa and BLE-body regions;
- the Raytac U11 all-layer antenna keepout remains empty of traces, vias and pours;
- H1–H4 each receive a six-layer `NO_COPPER_D8.0` rule area.

Each mounting rule area is a conservative 64-sided polygon with `4.010 mm`
vertex radius and `4.00517 mm` minimum apothem. Tracks, vias and pours are
forbidden. The existing NPTH pad and its mounting footprint remain allowed so
that the rule area does not create a false DRC violation against its own hole.

The committed candidate intentionally stores the three copper zones unfilled.
CI and review tools refill them before connectivity and DRC. This keeps the
review source compact and prevents stale filled polygons from hiding a geometry
change.

## Verification

Local KiCad 7.0.11 preflight after refilling the zones gives:

| Check | Baseline | Candidate |
|---|---:|---:|
| Native unconnected relationships | 718 | 464 |
| DRC unconnected items | 499 | 464 |
| Copper-clearance errors | 0 | 0 |
| Finished-hole-clearance errors | 4 | 4 |
| New clearance, hole, mask or keepout errors | — | 0 |
| Dangling ground vias | — | 0 |
| Foreign ground copper in exclusive regions | — | 0 |

The exact connectivity reduction is 254, one for every added fanout via. Routing
is still incomplete: 464 unconnected relationships remain. The four unchanged
finished-hole violations are inherited from the authoritative baseline around
the J11 footprint; this proposal neither adds nor hides them. KiCad 9 comparative
DRC in CI is mandatory before this proposal is ready for a signature.

An explicit inner-layer plane tree is not included. The experimental tree added
1,158 segments without reducing the unconnected count and would consume routing
area before signal routing. The filled zones already provide the intended plane
connectivity; return-path continuity still requires later whole-board Review B.

Candidate board:
`hardware/kicad/candidates/PCB-MAIN-GROUND-DOMAIN-001/PCB-MAIN_GROUND_DOMAIN_CANDIDATE_REV_A.kicad_pcb`

Candidate SHA-256:
`9c8abfabc18fa22b53c94b6b4d7946dbe1dfab797fbff9d00d7c3408aece1b9e`

Independent audit:
`tools/audit_pcb_main_ground_domain_routing_candidate_rev_a.py`

## Requested decision and boundary

After the machine gate is green, the independent reviewer may record one decision:

- `ACCEPT_GROUND_DOMAIN_ROUTING_SUBGATE`: apply only the exact hash-bound fanout,
  via, D8 rule-area and shaped-plane candidate, then continue signal and power
  routing engineering from it;
- `REJECT_GROUND_DOMAIN_ROUTING_SUBGATE`: retain the authoritative unrouted board
  and revise the domain geometry.

Acceptance does **not** complete PCB-MAIN routing, return-path review, SI/PI,
thermal review, DFM, Review B, CAM release or manufacturing authorization.
