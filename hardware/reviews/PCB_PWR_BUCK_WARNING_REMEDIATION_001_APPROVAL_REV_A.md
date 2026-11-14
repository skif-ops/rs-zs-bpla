# PCB-PWR buck warning remediation 001 approval — Rev.A

Decision: `ACCEPT_PCB_PWR_BUCK_WARNING_REMEDIATION_001_SUBGATE`
Reviewer: Скиф
Date: 2026-09-21

The exact pending subgate token was received verbatim. This approval is bound to
corrected proposal commit `63d87153e441d956117323ed8d9887568c5033ac`, tree
`87b2c7ab4d8fbc1b5d0d3c88c703994abef773bf`, gate-evidence commit
`036787a5674242de94d6dd455acf8ec6bf741952`, and candidate-board SHA-256
`b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957`.

The authorized bounded delta is exactly:

- canonical KiCad 9 child orientation for the rotated `C4` and `C6` instances,
  with their physical reference centres retained at `(54.575, 17.8) mm` and
  `(54.575, 45.8) mm`;
- the visible `R10` reference moved from global `(58.0, 45.6) mm` to
  `(58.0, 48.4) mm`;
- no component pose, pad centre, pad size, layer, net, outline or copper change.

CI `#586`, PCB-PWR Schematic Gate `#65`, and PCB Native Gate `#313` passed for
the reviewed candidate. Comparative KiCad 9 DRC proved exact `90 -> 86`
violations and `126 -> 126` unconnected items, with no new warning or error and
all non-target DRC fingerprints identical. The four authorized closures are two
`C4/C6 lib_footprint_mismatch` findings, one `L2/R10 silk_overlap`, and one
`R10 silk_over_copper`. Minimum fitted clearance remains `0.22 mm`. Artifact
`10636550793` has digest
`sha256:77a1d81b3e03e896c248992ae607c89b2158d7e8692331e45635abcb3f3a84a1`.

Evidence commit `036787a5` independently passed CI `#587`, PCB-PWR Schematic
Gate `#66`, and PCB Native Gate `#314`. Its artifact `10636582687` has digest
`sha256:074b71d9dc5135cecd1c2942cea5471921f35700ae5bbb86d72088f303ce3de5`.

This approval authorizes only byte-exact application of the reviewed candidate
to authoritative PCB-PWR. Routing, final stackup acceptance, Review B, CAM,
fabrication, assembly and manufacturing release remain prohibited.
