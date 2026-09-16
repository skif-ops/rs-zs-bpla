# PCB-PWR Rev.A Review B checklist

Status: `OPEN / FITTED 2D CLEARANCE, PRE-ROUTE CONSTRAINT, DIM-003 REQUEST AND STACKUP/COPPER REQUEST PASS / NOT FOR MANUFACTURE`

Review B is independent from the completed pin/net Review A. This checklist is
not signed and contains no routing, CAM or manufacturing-release assertion.

## 1. Current controlled baseline

- Review A pin/net audit: `PASS`.
- Native KiCad 9 schematic and zero-violation ERC evidence: present.
- Native PCB: provisional 90 x 60 x 1.6 mm, four copper layers, 60 footprints,
  zero mounting holes, zero traces/vias/zones.
- Fitted-body 2D clearance: `PASS`; 42/42 fitted footprints have courtyards,
  minimum required/observed separation is 0.20/0.22 mm and conflicts are zero.
- Mechanical authority: `DIM-003 OPEN`; the outline, mounting pattern, terminal
  zones, tool access and assembled STEP are not frozen.
- DIM-003 request packet: internally complete; the response register is `0/18`
  accepted, so no provisional dimension or service volume is authorized.
- Pre-route constraint coverage: `PASS` for all 31 native nets. Numeric widths,
  copper weights, via arrays and thermal geometry remain open.
- Stackup/copper request: internally complete for `FAB-A` and `FAB-B`; the
  24-row response register is `0/24` accepted, `0/2` fabricator sets are
  accepted and no construction is selected. The controlled template is
  `PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv`.
- Manufacturing release: `HOLD`.

## 2. Review-B gate

- [x] Native PCB parses independently and its component/net set matches the
  reviewed schematic and placement authority.
- [x] All 42 fitted assembly courtyards pass the bounded 0.20 mm 2D clearance
  subgate; DNP/PCB-feature service and fixture checks remain open.
- [x] Four-layer count is frozen for Rev.A and agrees with the native board.
- [x] All 31 native/capture nets have one explicit route class, return domain,
  topology, current basis and source authority.
- [x] Switch-node, bootstrap, Kelvin, feedback and net-tie constraints are
  explicit without invented final geometry.
- [x] I²C remains 100 kHz initially with authoritative pull-ups on PCB-MAIN and
  PCB-PWR pull-up footprints DNP.
- [ ] `DIM-003` has all 18 attributable response rows accepted and freezes the
  board outline, mounting holes, terminal/tool zones, assembled envelope and
  PCB STEP in `PCB_PWR_DIM_003_RESPONSE_REV_A.csv`.
- [ ] Both independent fabricators return all 24 attributable stackup/copper
  rows, the project accepts both complete response sets, compares them and
  selects one four-layer dielectric construction.
- [ ] The selected fabricator construction freezes finished thickness, base and
  finished copper, hole-wall plating, via construction, minimum rules, mask and
  finish without silently changing the PCB source.
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

`HOLD`. Fitted-body 2D clearance, constraint coverage and the internal DIM-003
and two-fabricator stackup/copper requests are complete, but the response
registers remain `0/18` and `0/24` with `0/2` accepted fabricator sets. Accepted
mechanics/service volumes, DNP/PCB-feature access, selected construction,
numeric copper geometry, routing, physical evidence, DRC, CAM, DFM and
independent Review B are open. Production outputs remain prohibited.
