# PCB-MAIN Rev.A human-readable hierarchy review

Status: `CANDIDATE / COMMIT-BOUND KICAD 9 EVIDENCE AND HUMAN REVIEW PENDING`

## 1. Scope

This subgate reviews schematic presentation and exact electrical equivalence only.
It does not reopen the signed PCB-MAIN Review A pin/net decision and cannot
authorize PCB routing, fabrication, assembly, Review B or manufacturing release.

Permitted reviewer decision: `ACCEPT_HIERARCHY_ONLY` or `REJECT_HIERARCHY`.

## 2. Controlled candidate

- Pages: 10 A2 landscape sheets — one system overview and nine functional sheets.
- Symbols: 248 total; 247 have physical PCB footprints and `U12` is the logical card.
- PCB pads: 1,066 logical pad numbers and 1,077 physical pad occurrences; seven
  repeated shell-pad numbers on `J6` through `J12` account for 11 additional
  physical occurrences.
- Authority pins: 1,074 total; 905 connected and 169 explicit NC.
- Explicit child-sheet wire stubs: 905.
- Cross-sheet nets: 75 with 168 hierarchical-label participations.
- Root-sheet connection wires: 168.
- Total controlled wire segments: 1,073.
- Pin/net semantic SHA-256:
  `d320bdd98712a65f9736bd520a8f9197d4f53fedb4be3b798086810e7a8f4bf6`.
- Routing authorized: `false`.
- Manufacturing release: `false`.

## 3. Functional sheets

1. Power entry and rail interface.
2. MCU clocks, reset and straps.
3. PDM audio, AAD and microphone harnesses.
4. GNSS timing, antenna and supervisor.
5. Cellular modem, dual SIM and recovery.
6. LoRa radio control and conducted RF.
7. BLE module, reset, DFU and SWD.
8. Storage, sensors, microSD and tamper.
9. USB service, debug and EOL fixture.

## 4. Machine controls

- [x] Deterministic regeneration of root and all nine child sheets.
- [x] Root-sheet spatial traversal controls KiCad PDF order as pages 1 through 10,
  with short title-block labels bounded inside the printable frame.
- [x] Exact RefDes allocation: every symbol appears once and only once.
- [x] Exact authority pin/net equivalence and explicit NC preservation.
- [x] Exact schematic-to-PCB pad/net comparison for every physical pad, including
  all 11 duplicated shell solder occurrences.
- [x] Release boundary keeps routing and manufacture prohibited.
- [ ] Commit-bound KiCad 9 ERC: zero violations.
- [ ] Commit-bound 10-page schematic PDF archived and visually inspected.
- [ ] Source commit SHA and PDF SHA-256 recorded.
- [ ] Independent human hierarchy decision recorded.

## 5. Human review

Reviewer: `PENDING`

Date: `PENDING`

Source commit SHA: `PENDING`

Reviewed PDF SHA-256: `PENDING`

Decision: `PENDING`

## 6. Retained blockers

Routing, planes, numeric impedance geometry, native board DRC, STEP/enclosure
clearance, CAM comparison, fabricator stackup acceptance, assembler DFM/stencil
acceptance, Review B and physical EVT remain open.
