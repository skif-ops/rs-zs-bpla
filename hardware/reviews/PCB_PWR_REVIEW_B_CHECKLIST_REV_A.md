# PCB-PWR Rev.A Review B checklist

Status: `OPEN / PROVISIONAL PRE-ROUTE CANDIDATE / NOT FOR MANUFACTURE`

Review B is independent from the completed pin/net Review A. This checklist is
not signed and contains no routing, CAM or manufacturing-release assertion.

## 1. Current controlled baseline

- Review A pin/net audit: `PASS`.
- Native KiCad 9 schematic and zero-violation ERC evidence: present.
- Native PCB: provisional 90 x 60 x 1.6 mm, four copper layers, 60 footprints,
  zero mounting holes, zero traces/vias/zones.
- Mechanical authority: `DIM-003 OPEN`; the outline, mounting pattern, terminal
  zones, tool access and assembled STEP are not frozen.
- Pre-route constraint coverage: `PASS` for all 31 native nets. Numeric widths,
  copper weights, via arrays and thermal geometry remain open.
- Manufacturing release: `HOLD`.

## 2. Review-B gate

- [x] Native PCB parses independently and its component/net set matches the
  reviewed schematic and placement authority.
- [x] Four-layer count is frozen for Rev.A and agrees with the native board.
- [x] All 31 native/capture nets have one explicit route class, return domain,
  topology, current basis and source authority.
- [x] Switch-node, bootstrap, Kelvin, feedback and net-tie constraints are
  explicit without invented final geometry.
- [x] I²C remains 100 kHz initially with authoritative pull-ups on PCB-MAIN and
  PCB-PWR pull-up footprints DNP.
- [ ] `DIM-003` freezes the board outline, mounting holes, terminal/tool zones,
  assembled envelope and PCB STEP.
- [ ] A selected fabricator accepts the four-layer dielectric construction,
  finished thickness, copper weights and manufacturing minimums.
- [ ] Input fault/transient envelope, fuse/TVS coordination and MOSFET SOA are
  closed against battery/BMS/MPPT evidence.
- [ ] Numeric high-current widths, plane geometry and via arrays pass DC-drop,
  current-density, fault-energy and +70 °C thermal calculation.
- [ ] Both buck hot loops and switch nodes are routed compactly and isolated
  from Kelvin, feedback, I²C, connector and edge regions.
- [ ] Shunt sense is true Kelvin with no load current in either sense route and
  only high-impedance test-point branches.
- [ ] The 3V8 and fixed 3V3 feedback pickups are routed from the post-inductor
  output-capacitor nodes through quiet corridors.
- [ ] `GND_MODEM`, `GND_DIGITAL` and `GND_MIC` remain separate and join
  `GND_PWR` only at `NT1`, `NT2` and `NT3`.
- [ ] All power, control, status and I²C routing plus return/thermal copper is
  complete with zero unrouted items.
- [ ] KiCad 9 DRC passes with zero blocker/critical violations.
- [ ] Native STEP proves terminal mating, tool access, harness bend/service
  volumes, enclosure clearance and thermal interface.
- [ ] Load-step, BG95 burst, -40 °C cold-start, +70 °C thermal, standby,
  INA226 calibration, fault/transient and EMC/EMI evidence passes.
- [ ] Gerber/Excellon, IPC-356, PnP, production BOM and fabrication/assembly
  drawings are generated and hash-bound to the reviewed source commit.
- [ ] Independent CAM comparison and selected-factory DFM are archived with all
  blocker/critical findings closed.
- [ ] Reviewer, date and reviewed commit SHA are recorded in a separate signing
  commit.

## 3. Decision

`HOLD`. Constraint coverage is complete, but mechanics, stackup, numeric copper
geometry, routing, physical evidence, DRC, CAM, DFM and independent Review B are
open. Production outputs remain prohibited.
