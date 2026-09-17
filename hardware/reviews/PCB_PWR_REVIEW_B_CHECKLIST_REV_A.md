# PCB-PWR Rev.A Review B checklist

Status: `F1 VALUE ECO APPLIED / HIERARCHY LEGIBILITY REMEDIATION COMMITTED / COMMIT-BOUND ERC AND PDF EVIDENCE PASS / HUMAN HIERARCHY REVIEW PENDING / REVIEW B OPEN / FITTED 2D CLEARANCE, PRE-ROUTE CONSTRAINT, DIM-003 REQUEST AND STACKUP/COPPER REQUEST PASS / NOT FOR MANUFACTURE`

Review B is independent from the completed pin/net Review A. This checklist is
signed only for the bounded hierarchy subgate and contains no routing, CAM or
manufacturing-release assertion.

## 1. Current controlled baseline

- Review A pin/net authority: `PASS`; the exact 60-position pad/net comparison
  retains this electrical decision across the hierarchy-only representation change.
- Human-readable schematic hierarchy: internally `PASS`; one system overview and
  four functional child sheets contain 63 symbols, 185 explicit wire segments,
  9 cross-sheet nets and 26 hierarchical labels. The independently calculated
  pin/net semantic SHA-256 is
  `fb31a1880037c2d15873ef7a003b74967e0427ed767bc16de256a790b5320b5a`.
- Historical commit-bound native KiCad 9.0.9 evidence for source commit
  `2a973f6856aa115aa59323d619be985578780682` is `PASS`: Schematic Gate
  [#35122481138](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35122481138)
  reports zero violations across all five sheets, and its A3 landscape PDF has
  five unclipped pages with no visible duplicate root labels. The evidence ZIP,
  ERC JSON and PDF are SHA-256 bound in `PCB_PWR_CAPTURE_STATUS_REV_A.json`.
  Reviewer `Скиф` accepted that bounded hierarchy subgate on `2026-09-16` with
  decision `ACCEPT_HIERARCHY_ONLY`. The F1 value ECO supersedes that evidence
  for the active source. Post-ECO Schematic Gate
  [#35197150159](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35197150159)
  passed KiCad 9.0.9 ERC with zero violations on five sheets; PDF SHA-256
  `9733a1df0026a53ecfc56355cf185e04fb372242a9dcdcb13ef214cced81c744`
  covers five A3 landscape pages. During independent review, the reviewer found
  that text overlaps symbols and connection marks, so this PDF is superseded as
  active review evidence despite its earlier automated clipping preflight. The
  source and artifact
  evidence are bound to commit `091a2eb223161cb4396fc6838921eeb79150c38d`.
  The presentation-only remediation increases text/stub spacing, rotates
  two-terminal symbols for horizontal labels and expands functional bodies while
  retaining the exact pin/net semantic hash. For source commit
  `6ba3ba5d219b95cb7de12f37c4eb646f7f18cfa8`, Schematic Gate
  [#35209892756](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35209892756)
  passes KiCad 9.0.9 ERC with zero violations on five sheets. PDF SHA-256
  `16afef6ecb337109f2a61318c9459167c6d06f4b74534b656c97884c1fed57dd`
  covers five A3 landscape pages; visual preflight found no text/symbol/
  connection overlap or clipping. Independent review of the remediated drawing
  is pending.
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
- Input protection: active native F1 is Littelfuse `0451008.MRL` and target D1
  remains `SMBJ18A`. The bounded value-only ECO is applied with footprint,
  placement, topology and nets retained. The earlier post-ECO PDF is superseded
  by the legibility remediation; fresh ERC/PDF evidence passes, while independent
  hierarchy review and 19 of 20 qualification rows remain open.
  PCBA procurement is prohibited.

## 2. Review-B gate

- [x] Native PCB parses independently and its component/net set matches the
  reviewed schematic and placement authority.
- [x] The five-page hierarchy has one explicit wire stub per connected pin, no
  cross-net wire collisions and exact electrical equivalence to all 60 PCB
  footprints/pads.
- [x] All 42 fitted assembly courtyards pass the bounded 0.20 mm 2D clearance
  subgate; DNP/PCB-feature service and fixture checks remain open.
- [x] Four-layer count is frozen for Rev.A and agrees with the native board.
- [x] All 31 native/capture nets have one explicit route class, return domain,
  topology, current basis and source authority.
- [x] Switch-node, bootstrap, Kelvin, feedback and net-tie constraints are
  explicit without invented final geometry.
- [x] I²C remains 100 kHz initially with authoritative pull-ups on PCB-MAIN and
  PCB-PWR pull-up footprints DNP.
- [x] Historical KiCad 9 evidence for the superseded F1 value has zero ERC
  violations and is commit/SHA-256 bound to source commit
  `2a973f6856aa115aa59323d619be985578780682`.
- [x] Independent reviewer `Скиф` accepted that historical five-page drawing on
  `2026-09-16` with decision `ACCEPT_HIERARCHY_ONLY`; it is not acceptance of
  the active post-ECO source.
- [ ] `DIM-003` has all 18 attributable response rows accepted and freezes the
  board outline, mounting holes, terminal/tool zones, assembled envelope and
  PCB STEP in `PCB_PWR_DIM_003_RESPONSE_REV_A.csv`.
- [ ] Both independent fabricators return all 24 attributable stackup/copper
  rows, the project accepts both complete response sets, compares them and
  selects one four-layer dielectric construction.
- [ ] The selected fabricator construction freezes finished thickness, base and
  finished copper, hole-wall plating, via construction, minimum rules, mask and
  finish without silently changing the PCB source.
- [ ] The bounded F1 value-only ECO has changed historical `0451005.MRL` to
  active target `0451008.MRL` without changing topology, footprint, placement
  or nets; the legibility-remediated five-page source retains that electrical
  mapping and fresh KiCad 9 ERC/PDF evidence passes, but this combined gate
  remains unchecked until independent hierarchy review passes.
- [ ] All 20 rows in `PCB_PWR_INPUT_PROTECTION_TEST_MATRIX_REV_A.csv` pass,
  including +70 C 5 A connector/harness/fuse thermal, battery/MPPT transient,
  SMBJ18A clamp, prospective-current, primary-fuse and fail-short coordination.
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

`HOLD`. Reviewer `Скиф` accepted the historical hierarchy-only subgate on
`2026-09-16` for source commit `2a973f6856aa115aa59323d619be985578780682`
and PDF SHA-256 `7a1eee774d6a0dd03e6cb72935824f5a7d2af4bebe0e37ad739f61eb8d32a1f4`.
The active source retains exact electrical equivalence after the F1 value-only
ECO and presentation-only legibility remediation. Fresh commit-bound KiCad 9
ERC/PDF evidence passes; independent human review is pending. Fitted-body 2D
clearance, constraint coverage and the
internal DIM-003 and two-fabricator stackup/copper requests remain valid. The
response registers remain `0/18` and `0/24` with `0/2` accepted fabricator sets.
Accepted mechanics/service volumes, DNP/PCB-feature access, selected construction,
numeric copper geometry, routing, physical evidence, DRC, CAM, DFM and independent
Review B are open. Production outputs remain prohibited.
