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
- Provisional project-local footprints: 52 instances; manufacturer land-pattern approval open.

## 2. Review-B gate

- [x] Native PCB file exists and parses independently.
- [x] Component and net sets match the reviewed schematic authority.
- [x] Locked connector/module anchors and rotations match MAIN-AUTH-011.
- [x] Six-layer count, thickness, outline and mounting pattern are represented.
- [ ] All 35 unique custom land patterns are approved against manufacturer drawings.
- [ ] Placement is collision-free and every courtyard/height/service zone passes.
- [ ] RF, power, PDM, USB and SIM routing is complete.
- [ ] Return planes, stitching, antenna keepouts and impedance coupons are complete.
- [ ] KiCad 9 DRC passes with zero blocker/critical violations and zero unrouted items.
- [ ] Gerber/Excellon is generated only from that DRC-clean commit.
- [ ] IPC-356, PnP, BOM, assembly/fabrication drawings and STEP are generated and hash-bound.
- [ ] Independent CAM comparison is archived.
- [ ] Factory stackup and DFM response are accepted; blocker/critical comments are closed.
- [ ] RA-003-LAYOUT and RA-003-MEAS are closed with calculation and physical evidence.
- [ ] Reviewer, date and reviewed commit SHA are recorded in a separate signing commit.

## 3. Decision

`HOLD`. The candidate is a controlled starting point for placement and footprint
qualification. Production outputs are prohibited until every unchecked item passes.
