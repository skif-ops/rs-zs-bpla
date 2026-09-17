# PCB-PWR Rev.A human-readable hierarchy review

Status: `ACCEPTED HIERARCHY ONLY / NOT FOR ROUTING OR MANUFACTURE`

## 1. Scope

This subgate reviews the active five-sheet schematic presentation and its exact
electrical equivalence only. It does not authorize PCB routing, procurement,
fabrication, assembly, Review B or manufacturing release.

Permitted reviewer decision: `ACCEPT_HIERARCHY_ONLY` or `REJECT_HIERARCHY`.

## 2. Controlled candidate

- Pages: 5 A3 landscape sheets — one system overview and four functional sheets.
- Symbols: 65 total; 62 have physical PCB footprints.
- Explicit wire segments: 189.
- Cross-sheet nets: 9 with 26 hierarchical-label participations.
- Pin/net semantic SHA-256:
  `84a35aa607bac3ee65b5d8f60684e958277b2fa5a7ed01f810af32f0b52b73f7`.
- Reviewed source commit:
  `e32c0aa9e510e8321e24ebb3ee2056100c5f3a1a` (tree
  `0d5f87c81bbda962b53088d69cd433c810ef2fc4`).
- PCB-PWR Schematic Gate
  [#35217048575](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35217048575):
  KiCad `9.0.9`, zero ERC violations on all five sheets. Evidence artifact
  [10495663427](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35217048575/artifacts/10495663427),
  ZIP SHA-256
  `f29dfa4e0be9c25f8023e7d5218a97a28db70b0a1059eaca0141f699f46e64d3`.
- ERC JSON SHA-256:
  `68c18cb8e910ed05774766fa68fb2ed502cf425fc550cda0b4385ad2fb52e1ce`.
- Five-page A3 landscape PDF SHA-256:
  `7abb5e83e5d8cc72178c37fbf559bd77ca0d915b1c92f94e12ed278ce83bf130`;
  all pages were checked with no text, symbol or connection overlap and no
  clipping.
- CI [#35218795600](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35218795600)
  and PCB Native Gate
  [#35218795606](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35218795606):
  `PASS` for the reviewed active source.
- Routing authorized: `false`.
- Procurement authorized: `false`.
- Manufacturing release: `false`.

## 3. Machine controls

- [x] Deterministic regeneration of the root and all four child sheets.
- [x] Exact RefDes allocation and pin/net equivalence to all 62 PCB footprints.
- [x] C20/C21 local CIN_HF electrical ECO included in the controlled source.
- [x] Commit-bound KiCad 9 ERC: zero violations on all five sheets.
- [x] Commit-bound five-page A3 PDF archived and visually inspected.
- [x] Source commit, tree, artifact, ERC and PDF digests recorded.
- [x] TI primary evidence closes the LMR604403 mode and LM74700 VCAP questions.
- [x] Independent human hierarchy decision recorded.
- [x] Routing, procurement and manufacture remain prohibited.

## 4. Human review

Reviewer: `Скиф`

Date: `2026-09-17`

Source commit SHA: `e32c0aa9e510e8321e24ebb3ee2056100c5f3a1a`

Reviewed PDF SHA-256: `7abb5e83e5d8cc72178c37fbf559bd77ca0d915b1c92f94e12ed278ce83bf130`

Decision: `ACCEPT_HIERARCHY_ONLY`

The decision accepts only the human-readable hierarchy and its exact electrical
equivalence. It does not authorize routing, procurement, fabrication, assembly,
Review B or manufacturing release.

## 5. Retained blockers

DIM-003, two-fabricator stackup/copper responses, effective C11/C12 capacitance,
routed buck hot loops, input filter/no-filter evidence, F1/TVS/harness physical
qualification, modem-burst evidence, numeric copper geometry, routing, DRC,
STEP/service clearance, CAM, DFM, Review B and physical EVT remain open.
