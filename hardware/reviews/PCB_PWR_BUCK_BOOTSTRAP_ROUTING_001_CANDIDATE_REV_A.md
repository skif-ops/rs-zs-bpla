# PCB-PWR buck bootstrap routing candidate 001 — Rev.A

Status: `STATIC CANDIDATE / COMMIT-BOUND KICAD 9 GATE PENDING / NOT APPLIED / NOT FOR MANUFACTURE`

Creation was authorized by
`ACCEPT_PCB_PWR_ROUTING_CANDIDATE_001_CREATION_SUBGATE`.

This proposal adds only two short `F.Cu`, `0.5 mm`, zero-via connections:

- `BOOT_3V8`: `U3.4` to `C4.1`;
- `BOOT_3V3`: `U4.4` to `C6.1`.

The two routes total `2.563221 mm`. They implement the shortest-practical
bootstrap-loop priority using the selected EVT `JLC04161H-3313`, 1.6 mm,
outer 2 oz / inner 1 oz ordering profile and the conservative 35 µm numeric
rule set.

Base SHA-256:
`b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957`

Candidate SHA-256:
`a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236`

The candidate preserves every footprint pose, pad, net, outline and layer. It
adds no switch-node, VIN/PGND, rail, return, feedback, Kelvin, net-tie or control
copper and does not modify the authoritative board.

Before human acceptance it must pass fresh commit-bound CI and PCB Native
comparative KiCad 9 DRC with zero new errors, exactly two fewer unconnected
items and no unrelated DRC fingerprint delta. After that evidence exists, the
only valid acceptance value is
`ACCEPT_PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_SUBGATE`.

Acceptance would authorize only a separate exact-candidate application step.
Routing completion, Review B, CAM and manufacturing release remain false.
