# PCB-MAIN Rev.A Review B checklist

Status: `OPEN / LAYOUT ENGINEERING CANDIDATE / NOT FOR MANUFACTURE`

Review B is independent from the signed Review A. This record is intentionally not
signed and contains no manufacturing release assertion.

## 1. Current controlled baseline

- Review A: `PASS`, signed by Скиф.
- Native schematic: present; commit-matched KiCad 9 ERC evidence is PASS.
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
- [ ] Two attributable fabricator responses are complete, compared and accepted;
  one construction and its 50-ohm/90-ohm numeric geometry are selected through
  project RF/SI review.
- [ ] RF, power, PDM, USB and SIM routing is complete.
- [ ] Return planes, stitching, antenna keepouts and impedance coupons are complete.
- [ ] KiCad 9 DRC passes with zero blocker/critical violations and zero unrouted items.
- [ ] Gerber/Excellon is generated only from that DRC-clean commit.
- [ ] IPC-356, PnP, BOM, assembly/fabrication drawings and STEP are generated and hash-bound.
- [ ] Independent CAM comparison is archived.
- [ ] Factory stackup and DFM response are accepted; blocker/critical comments are closed.
- [ ] RA-003-LAYOUT is closed with routed-board evidence.
- [ ] RA-003-MEAS is closed with physical droop/ripple evidence from assembled hardware.
- [ ] Reviewer, date and reviewed commit SHA are recorded in a separate signing commit.

## 3. Decision

`HOLD`. The candidate is 2D placement-complete and its 186-net pre-route
constraint coverage is controlled, but it is unrouted and has not passed
3D/service, DRC, CAM, DFM or Review B. The exact current clearance result and
release boundary are recorded in
`hardware/reviews/PCB_MAIN_PLACEMENT_CLEARANCE_ERRATA_REV_A.md`; the routing input
is recorded in `hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.md`. Production outputs
are prohibited until every unchecked item passes.
