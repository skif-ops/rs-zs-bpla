# PCB-MAIN Rev.A Review B checklist

Status: `OPEN / LAYOUT ENGINEERING CANDIDATE / NOT FOR MANUFACTURE`

Review B is independent from the signed Review A. This record is intentionally not
signed and contains no manufacturing release assertion.

## 1. Current controlled baseline

- Review A: `PASS`, signed by Скиф.
- Native schematic: present; commit-matched KiCad 9 ERC evidence is PASS.
- Native PCB: placement-stage candidate present.
- Placement clearance: `BLOCKED`; the independent controlled audit records 17
  confirmed courtyard collisions, 67 pad-envelope screening collisions, two
  confirmed mounting-exclusion conflicts and one screening mounting conflict.
- MAIN-AUTH-011 limited ECO: required for locked `J8/U8`, `J_MIC1/J_PWR`,
  `H1/J_PWR` and `H2/J13` conflicts; no revised coordinate is approved yet.
- Board: 110 x 75 x 1.6 mm, six copper layers, rounded R3 outline, four M3 NPTH holes.
- Population represented: 247 on-board components plus four mounting holes; 186 native nets.
- Routing/copper zones: absent.
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
- [x] Placement/courtyard and mounting-exclusion blockers are independently
  inventoried and hash-bound by `tools/audit_pcb_main_placement_clearance_rev_a.py`.
- [ ] U9 paste stencil is adapted and approved for the selected assembly process.
- [ ] The selected assembler approves copper, mask and stencil rules for the `U2/U25/U26` project IPC candidates.
- [ ] A limited mechanical ECO supersedes the four internally conflicting
  MAIN-AUTH-011 placements/exclusions and receives independent mechanical review.
- [ ] All 169 pad-envelope screening footprints receive controlled courtyard/body
  disposition or are placed with equivalent independently reviewed evidence.
- [ ] Placement is collision-free and every courtyard/height/service zone passes.
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

`HOLD`. The candidate is a controlled starting point for placement and footprint
qualification, but it is not placement-complete. The exact current blocker inventory
and release boundary are recorded in
`hardware/reviews/PCB_MAIN_PLACEMENT_CLEARANCE_ERRATA_REV_A.md`. Production outputs
are prohibited until every unchecked item passes.
