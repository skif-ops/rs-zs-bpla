# PCB-MAIN Rev.A Review B checklist

Status: `OPEN / LAYOUT ENGINEERING CANDIDATE / NOT FOR MANUFACTURE`

Review B is independent from the signed Review A. This record is intentionally not
signed and contains no manufacturing release assertion.

## 1. Current controlled baseline

- Review A: `PASS`, signed by Скиф.
- Native schematic: present; commit-matched KiCad 9 ERC evidence is PASS.
- Native PCB: placement-stage candidate present.
- Board: 110 x 75 x 1.6 mm, six copper layers, rounded R3 outline, four M3 NPTH holes.
- Population represented: 247 on-board components plus four mounting holes; 186 native nets.
- Routing/copper zones: absent.
- Provisional manufacturer-specific footprints: 7 instances (reduced from 52).
- Manufacturer-drawing controlled project-local footprints: 7 instances (`D3`, `D5`, `U4`, `U5`, `U9`, `U10`, `X1`).
- KiCad library patterns pending drawing review: 44 instances.
- Production pogo groups: 5 controlled footprints, 31 bottom pads verified from MAIN-AUTH-011.
- Footprint disposition register: `hardware/reviews/PCB_MAIN_FOOTPRINT_DISPOSITION_REV_A.md`.

## 2. Review-B gate

- [x] Native PCB file exists and parses independently.
- [x] Component and net sets match the reviewed schematic authority.
- [x] Locked connector/module anchors and rotations match MAIN-AUTH-011.
- [x] Six-layer count, thickness, outline and mounting pattern are represented.
- [ ] All 7 provisional instances are replaced from controlled manufacturer drawings.
- [ ] U9 paste stencil is adapted and approved for the selected assembly process.
- [ ] All 44 KiCad-derived instances are approved against the applicable component drawings.
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
qualification. Production outputs are prohibited until every unchecked item passes.
