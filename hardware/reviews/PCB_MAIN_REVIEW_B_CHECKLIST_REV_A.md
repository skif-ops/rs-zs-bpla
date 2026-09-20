# PCB-MAIN Rev.A Review B checklist

Status: `HIERARCHY ACCEPTED / PARTIAL ROUTING / RF REMEDIATION REPEAT REVIEW PASS / REVIEW B OPEN / NOT FOR MANUFACTURE`

Review B is independent from the signed Review A. This record is intentionally not
signed for Review B. The hierarchy, placement and several bounded routing subgates
are accepted independently; none asserts complete routing, Review B or
manufacturing release.

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
- Native PCB: partially routed, 2D placement-complete engineering candidate
  present. The authoritative board contains 692 segments and 283 vias (975
  track/via objects), four copper zones and four rule areas. KiCad 9 comparative
  gates accepted bounded ground-domain, hard-signal, OctoSPI and seven-net RF P0
  subgates; 429 unconnected items remain after deterministic zone refill.
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
- MAIN-AUTH-011 limited ECO-002: reviewer `Скиф` accepted the exact hash-bound
  two-record J_PWR/J6 translation on `18.09.2026` with decision
  `ACCEPT_LIMITED_MECHANICAL_ECO`. H1 at `(8.00,5.00)` mm is retained from
  ECO-001. The applied authority, PCB and repack hashes pass the dedicated
  ECO-002 audit; routing, 3D/service review and Review B remain open.
- Board: 110 x 75 x 1.6 mm, six copper layers, rounded R3 outline, four M3 NPTH holes.
- Population represented: 247 on-board components plus four mounting holes; 186 native nets.
- Routing/copper zones: partial and explicitly not final. The accepted RF P0
  inventory is 138 `F.Cu` segments at `0.1509 mm` with zero RF signal vias.
- Pre-route constraint coverage: `PASS` for all 186 native nets. The controlled
  manifest assigns one explicit class, return domain, topology, priority and
  source authority to every net. The official JLCPCB public
  `JLC06161H-3313` calculator result now controls candidate RF/USB geometry at
  `0.1509 mm` for 50 ohm and `0.1537/0.2032 mm` width/gap for 90 ohm on L1/L2.
  Final production geometry remains blocked on job-specific fabricator
  acceptance and RF/SI review.
- RF/SI return-path remediation: both bounded subgates are independently
  accepted and applied. `PCB-MAIN-RF-RETURN-001` contributes exactly one local
  `GND_MODEM` L2 zone; `PCB-MAIN-GNSS-RF-ECO-001` keeps U9/J9 fixed, moves only
  FL1/C64 and reduces the post-SAW route to `1.326997 mm`. The composed board is
  SHA-256 `f8797a1055…f4f9`; deterministic regeneration and strict placement
  clearance pass. Commit-bound source `7ee9cfc9` passed CI `#550` and PCB
  Native `#277`: errors remain zero, unconnected items remain `429`, and all
  `623` cellular plus `406` GNSS filled-L2 samples are covered. The bounded
  repeat return-path review passes; final SI and Review B remain open.
- Stackup/impedance request: controlled packet and blank 22-row response
  register are ready, with 0/2 accepted fabricator responses. No final job
  construction, production tolerance, coupon plan or manufacturing route rule
  has been accepted; the public numeric basis does not populate a response row.
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
- [x] The accepted limited mechanical ECO chain, including the bounded ECO-002
  J_PWR/J6 translation, supersedes the internally conflicting MAIN-AUTH-011
  geometry and passes its independent application audits.
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
  templates for `FAB-A` and `FAB-B` are ready.
- [x] The official public `JLC06161H-3313` calculator result is recorded as a
  bounded engineering-candidate input with exact 50-ohm and 90-ohm geometry;
  all 22 job-specific response rows remain pending.
- [x] A machine-audited bounded assembler DFM/stencil request and blank
  14-question response template for `U2/U25/U26/U9` are ready without guessed
  paste, stencil, reflow, inspection or first-article process parameters.
- [x] The exact seven-net RF P0 candidate was accepted and applied as a bounded
  engineering subgate; its comparative KiCad 9 DRC introduced no new errors and
  reduced unconnected items from 444 to 429.
- [x] `PCB-MAIN-RF-RETURN-001` passed its independent comparative gate, was
  accepted and applied as the exact local `GND_MODEM` L2-zone candidate.
- [x] `PCB-MAIN-GNSS-RF-ECO-001` was independently accepted and its exact
  FL1/C64 plus GNSS-copper delta was composed without changing U9/J9 or the
  accepted cellular zone.
- [x] The final composed board passes commit-bound combined KiCad 9 refill/DRC,
  both filled-reference coverage audits and repeat RF/SI return-path review.
- [ ] Two attributable fabricator responses are complete, compared and accepted;
  one final construction, its production 50-ohm/90-ohm geometry and tolerance,
  and its coupon plan are selected through project RF/SI review.
- [ ] All 14 attributable assembler responses are accepted for a named legal
  entity and manufacturing site; the process baseline, U2/U25/U26 land/mask/
  stencil decisions, U9 stencil adaptation, PnP polarity, first-article plan and
  blocker/critical DFM closure are approved through controlled review.
- [ ] RF, power, PDM, USB and SIM routing is complete.
- [ ] USB source-termination placement ECO is closed. Routeability review
  `PCB_MAIN_USB_ROUTEABILITY_REVIEW_REV_A.md` records that R91/R92 are 6.00 mm
  apart while U1 D-/D+ pads are on 0.50 mm pitch; routing is prohibited until
  the bounded local U1 cluster passes clearance and pair-geometry review.
  Revised candidate `PCB-MAIN-USB-PLACEMENT-ECO-001` moves only R91/R92 and
  passes static regeneration plus strict clearance. The superseded
  four-footprint candidate failed PCB Native #280 because C12/R3 already own
  accepted fanout; repeat KiCad 9 and human review remain pending, and the
  authoritative board is unchanged.
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
The candidate is 2D placement-complete and partially routed. Its 186-net
pre-route constraint coverage, public numeric routing basis and accepted RF P0
subgate are controlled. Both bounded RF/SI remediations are independently
accepted and applied in the exact deterministic composition. The commit-bound
combined KiCad 9 gate and bounded repeat return-path review pass on source
commit `7ee9cfc9`; final SI remains open. Remaining routing, pair-geometry
audit, 3D/service review, final DRC, CAM, DFM and Review B are open.
The exact current clearance result and
release boundary are recorded in
`hardware/reviews/PCB_MAIN_PLACEMENT_CLEARANCE_ERRATA_REV_A.md`; the routing
inputs are recorded in `hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.md` and
`hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.md`. Production
outputs are prohibited until every unchecked item passes.
