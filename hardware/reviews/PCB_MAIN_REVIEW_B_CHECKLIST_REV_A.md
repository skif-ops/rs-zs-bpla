# PCB-MAIN Rev.A Review B checklist

Status: `HIERARCHY ACCEPTED / REVIEW B OPEN / LAYOUT ENGINEERING CANDIDATE / NOT FOR MANUFACTURE`

Review B is independent from the signed Review A. This record is intentionally not
signed for Review B; only its bounded hierarchy subgate is signed, and it contains
no routing or manufacturing-release assertion.

## 1. Current controlled baseline

- Review A: `PASS`, signed by Скиф.
- Signed Review-A electrical baseline: commit-matched KiCad 9 ERC evidence is PASS.
- Human-readable schematic hierarchy: deterministic 10-page A2 candidate present
  (root plus nine functional sheets). Exact 248-symbol, 1,074-pin Review-A
  semantics are retained; 905 connected pins have explicit wire stubs and all
  169 NC pins remain explicit. Commit-bound KiCad 9.0.9 ERC reports zero
  violations across all ten sheets; the ordered ten-page PDF and source hashes
  are bound to commit `9aceca9531f0b9c18679bee1a8050ae7cd94308a`.
  Reviewer `Скиф` accepted this bounded subgate on `2026-09-16` with decision
  `ACCEPT_HIERARCHY_ONLY` against PDF SHA-256
  `7e6ef20a989ec66c55b3e1a32de0a914b9e37a6e70cc5835d36f3260b65ff8d9`.
- Native PCB: unrouted, 2D placement-complete engineering candidate present.
- Placement clearance: `PASS` for the bounded 2D subgate. The deterministic
  225-reference repack and controlled passive courtyards give 227/227 fitted
  assembly footprints explicit courtyards; the strict audit records zero
  component, mounting-exclusion and U.FL tool-cylinder conflicts. The independent
  layout audit also reports no non-owner movable footprint in a locked RF/audio
  allocation or the BLE all-layer antenna keepout.
- MAIN-AUTH-011 limited ECO: proposal `PCB-MAIN-MECH-ECO-001` was accepted by
  reviewer `Скиф` on `15.09.2026` against commit
  `61cbe796de2f87560342a44b063ff6283a8ce1e8` and candidate SHA-256
  `5ef7d0390da97796febbef6a69f0206a06efe00782e238bf7c8f32bf29d08fc1`,
  then applied exactly. The previously locked component, mounting and U.FL
  tool-cylinder conflict sets are empty.
- Board: 110 x 75 x 1.6 mm, six copper layers, rounded R3 outline, four M3 NPTH holes.
- Population represented: 247 on-board components plus four mounting holes; 186 native nets.
- Routing/copper zones: absent.
- Pre-route constraint coverage: `PASS` for all 186 native nets. The controlled
  manifest assigns one explicit class, return domain, topology, priority and
  source authority to every net; numeric RF/USB geometry remains blocked on the
  selected fabricator stackup.
- Stackup/impedance request: controlled packet and blank 22-row response
  register are ready, with 0/2 accepted fabricator responses. No construction,
  numeric RF/USB geometry or route rule has been accepted.
- Assembler DFM/stencil request: the bounded `U2/U25/U26/U9` packet and blank
  14-row response register are ready, with 0/14 accepted assembler responses.
  No assembler legal entity, manufacturing site, paste/stencil/reflow process,
  footprint acceptance or U9 paste aperture has been selected or approved.
- Provisional manufacturer-specific footprints: 0 instances (reduced from 52).
- Manufacturer-drawing controlled project-local footprints: 50 instances.
- Drawing-verified KiCad library patterns: 5 instances (`J11`, `J_MIC1..J_MIC4`).
- KiCad library patterns pending drawing review: 0 instances.
- Project-controlled package-derived IPC candidates: 3 instances (`U2`, `U25`, `U26`); assembler DFM is mandatory.
- Production pogo groups: 5 controlled footprints, 31 bottom pads verified from MAIN-AUTH-011.
- Footprint disposition register: `hardware/reviews/PCB_MAIN_FOOTPRINT_DISPOSITION_REV_A.md`.

## 2. Review-B gate

- [x] Native PCB file exists and parses independently.
- [x] Component and net sets match the reviewed schematic authority.
- [x] Human-readable hierarchy allocates every one of 248 symbols exactly once
  across nine functional child sheets and preserves the signed Review-A pin/net
  semantic SHA-256.
- [x] Every physical pad sharing one logical pad number carries the same
  authority net; this includes all `J11.SHIELD`, `J6.SHIELD` and `J7.SHIELD`
  solder features.
- [x] Commit-bound KiCad 9 ERC has zero violations, and the ordered 10-page A2
  PDF, source tree and artifact are SHA-256 bound to the reviewed commit.
- [x] Independent reviewer `Скиф` recorded `ACCEPT_HIERARCHY_ONLY` on
  `2026-09-16` against the exact source commit and PDF SHA-256; routing remains
  unauthorized.
- [x] Locked connector/module anchors and rotations match MAIN-AUTH-011.
- [x] Six-layer count, thickness, outline and mounting pattern are represented.
- [x] All registered manufacturer-source footprint reviews are complete; provisional and library-review-pending counts are zero.
- [x] Placement/courtyard, mounting-exclusion and U.FL tool/service blockers are
  independently inventoried and hash-bound by
  `tools/audit_pcb_main_placement_clearance_rev_a.py`.
- [x] A bounded mechanical ECO candidate is machine-readable, baseline-hash-bound
  and independently confirms no locked conflict after the proposed overlay.
- [ ] U9 paste stencil is adapted and approved for the selected assembly process.
- [ ] The selected assembler approves copper, mask and stencil rules for the `U2/U25/U26` project IPC candidates.
- [x] The accepted limited mechanical ECO supersedes the six internally
  conflicting MAIN-AUTH-011 component placements, mounting exclusions and
  U.FL service cylinders and passes its independent geometry/application audit.
- [x] All 169 pad-envelope screening footprints receive controlled courtyard/body
  disposition or are placed with equivalent independently reviewed evidence.
- [x] The 2D placement is collision-free and all controlled courtyard,
  mounting-exclusion and U.FL tool-zone checks pass the strict independent audit.
- [x] Movable footprints respect the MAIN-AUTH-011 exclusive CELL, GNSS, LoRa,
  BLE-body and audio allocations plus the BLE all-layer antenna keepout.
- [ ] Component heights, connector mates, cards, coax and harness service volumes
  pass native STEP/enclosure review.
- [x] All 186 native nets have an explicit pre-route class, reference domain and
  topology; the generator and independent audit fail on missing, extra,
  overlapping or reclassified nets.
- [x] A machine-audited stackup/impedance request and identical 11-question
  templates for `FAB-A` and `FAB-B` are ready without guessed numeric geometry.
- [x] A machine-audited bounded assembler DFM/stencil request and blank
  14-question response template for `U2/U25/U26/U9` are ready without guessed
  paste, stencil, reflow, inspection or first-article process parameters.
- [ ] Two attributable fabricator responses are complete, compared and accepted;
  one construction and its 50-ohm/90-ohm numeric geometry are selected through
  project RF/SI review.
- [ ] All 14 attributable assembler responses are accepted for a named legal
  entity and manufacturing site; the process baseline, U2/U25/U26 land/mask/
  stencil decisions, U9 stencil adaptation, PnP polarity, first-article plan and
  blocker/critical DFM closure are approved through controlled review.
- [ ] RF, power, PDM, USB and SIM routing is complete.
- [ ] Return planes, stitching, antenna keepouts and impedance coupons are complete.
- [ ] KiCad 9 DRC passes with zero blocker/critical violations and zero unrouted items.
- [ ] Gerber/Excellon is generated only from that DRC-clean commit.
- [ ] IPC-356, PnP, BOM, assembly/fabrication drawings and STEP are generated and hash-bound.
- [ ] Independent CAM comparison is archived.
- [ ] Factory stackup and DFM response are accepted; blocker/critical comments are closed.
- [ ] RA-003-LAYOUT is closed with routed-board evidence.
- [ ] RA-003-MEAS is closed with physical droop/ripple evidence from assembled hardware.
- [ ] Final Review-B reviewer, date and reviewed routed-board commit SHA are
  recorded in a separate signing commit.

## 3. Decision

`HOLD`. Reviewer `Скиф` accepted the hierarchy-only subgate on `2026-09-16`
for source commit `9aceca9531f0b9c18679bee1a8050ae7cd94308a` and PDF SHA-256
`7e6ef20a989ec66c55b3e1a32de0a914b9e37a6e70cc5835d36f3260b65ff8d9`.
The candidate is 2D placement-complete and its 186-net pre-route constraint
coverage is controlled, but the board is unrouted and has not passed 3D/service,
DRC, CAM, DFM or Review B.
The exact current clearance result and
release boundary are recorded in
`hardware/reviews/PCB_MAIN_PLACEMENT_CLEARANCE_ERRATA_REV_A.md`; the routing input
is recorded in `hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.md`. Production outputs
are prohibited until every unchecked item passes.
