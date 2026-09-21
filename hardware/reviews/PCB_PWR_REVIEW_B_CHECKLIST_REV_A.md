# PCB-PWR Rev.A Review B checklist

Status: `C20/C21 CIN_HF ECO APPLIED / COMMIT-BOUND ERC, PDF AND HUMAN HIERARCHY EVIDENCE PASS / REVIEW B OPEN / FITTED + EVT MOUNTING CLEARANCE, PRE-ROUTE CONSTRAINT AND DIM-003 ACCEPTANCE PASS / STACKUP/COPPER REQUEST PASS / NOT FOR MANUFACTURE`

Review B is independent from the completed pin/net Review A. The active C20/C21
hierarchy subgate is signed, but this checklist contains no routing, CAM or
manufacturing-release assertion.

## 1. Current controlled baseline

- Review A pin/net authority: `PASS`; the exact 62-position pad/net comparison
  retains this electrical decision across the hierarchy-only representation change.
- Human-readable schematic hierarchy: internally `PASS`; one system overview and
  four functional child sheets contain 65 symbols, 189 explicit wire segments,
  9 cross-sheet nets and 26 hierarchical labels. The independently calculated
  pin/net semantic SHA-256 is
  `84a35aa607bac3ee65b5d8f60684e958277b2fa5a7ed01f810af32f0b52b73f7`.
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
  is pending. The subsequent electrical ECO adds C20/C21 local 100 nF/50 V
  input capacitors at U3/U4 and therefore supersedes the 6ba3ba5 evidence too.
  For active source commit
  `e32c0aa9e510e8321e24ebb3ee2056100c5f3a1a`, Schematic Gate
  [#35217048575](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35217048575)
  passes KiCad 9.0.9 ERC with zero violations on all five sheets. PDF SHA-256
  `7abb5e83e5d8cc72178c37fbf559bd77ca0d915b1c92f94e12ed278ce83bf130`
  covers five A3 landscape pages; independent visual preflight found no
  text/symbol/connection overlap or clipping. Reviewer `Скиф` accepted this
  exact active source/PDF pair on `2026-09-17` with decision
  `ACCEPT_HIERARCHY_ONLY`.
- Native PCB: EVT-frozen 90 x 60 x 1.6 mm, four copper layers, 62 electrical
  footprints plus four board-only mounting holes, zero traces/vias/zones.
- TI primary-source binding: `PASS`. The machine-audited record
  `PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.{md,json}` binds exact
  `LMR604403SRAKR` to SNAS877 pages 3/6/13/22 and the 2025-11-08 TI
  package-option addendum, and binds C1 to LM74700-Q1 SNOSD17G pages 5/6.
  This closes the part-mode and VCAP document questions without changing the
  native schematic or any physical-release state.
- Fitted-body 2D clearance: `PASS`; 44/44 fitted footprints have courtyards,
  minimum required/observed separation is 0.20/0.22 mm and conflicts are zero.
- Mechanical authority: `DIM-003 18/18 EVT ACCEPTED`; the outline, round H1-H4
  pattern, terminal zones, tool access, fixture datum and conservative assembled
  STEP envelope are frozen for EVT. Serial revalidation remains mandatory.
- Pre-route constraint coverage: `PASS` for all 31 native nets. Numeric widths,
  copper weights, via arrays and thermal geometry remain open.
- Stackup/copper request: internally complete for `FAB-A` and `FAB-B`; the
  24-row response register is `0/24` accepted, `0/2` fabricator sets are
  accepted and no construction is selected. The controlled template is
  `PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv`.
- Manufacturing release: `HOLD`.
- Input protection: active native F1 is Littelfuse `0451008.MRL` and target D1
  remains `SMBJ18A`. The bounded value-only ECO is applied with footprint,
  placement, topology and nets retained. The later C20/C21 electrical ECO leaves
  F1 unchanged. Exact Littelfuse/Molex source payloads and order codes are
  hash-bound in the controlled primary-source record. Its active-source
  ERC/PDF/human hierarchy gate passes; 17 of 20
  input-protection qualification rows remain open.
  PCBA procurement is prohibited.

## 2. Review-B gate

- [x] Native PCB parses independently and its component/net set matches the
  reviewed schematic and placement authority.
- [x] The five-page hierarchy has one explicit wire stub per connected pin, no
  cross-net wire collisions and exact electrical equivalence to all 62 PCB
  footprints/pads.
- [x] All 44 fitted assembly courtyards pass the bounded 0.20 mm 2D clearance
  subgate; H1-H4 D10 fitted-body and D8 existing-pad checks also pass with zero
  conflicts and `0.53 mm` minimum fitted-body margin.
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
- [x] `DIM-003` has all 18 attributable response rows accepted and freezes the
  board outline, mounting holes, terminal/tool zones, assembled envelope and
  EVT PCB STEP in `PCB_PWR_DIM_003_RESPONSE_REV_A.csv`; serial mechanics require
  repeat validation.
- [ ] Both independent fabricators return all 24 attributable stackup/copper
  rows, the project accepts both complete response sets, compares them and
  selects one four-layer dielectric construction.
- [ ] The selected fabricator construction freezes finished thickness, base and
  finished copper, hole-wall plating, via construction, minimum rules, mask and
  finish without silently changing the PCB source.
- [x] The machine-audited TI primary-source record confirms exact
  `LMR604403SRAKR` is an Active Production `3.3V fixed / adjustable`
  orderable; U3's 26.308 kOhm parallel divider selects adjustable 3.801120 V
  and U4's direct FB-VOUT connection selects fixed 3.3 V.
- [x] TI SNOSD17G Rev.G specifies C1's VCAP-to-ANODE value as 0.1 uF; no
  LM74700 VCAP ECO is required.
- [x] `PWR-IPQ-001` source control binds exact `0451008.MRL`, `SMBJ18A`,
  `43045-0213` and `43030-0038` to current official Littelfuse/Molex payloads,
  retrieval date, byte sizes and SHA-256 values without accepting a family
  substitute.
- [x] `PWR-IPQ-002` binds manufacturer documents and exact-MPN supplier
  catalogue records for the four orderables before purchase. No sample-only
  PO, receiving quarantine, mandatory photos, five-piece body sample, lot/date
  record or CoC is required; normal PO/packing-slip discrepancy handling is not
  a qualification gate.
- [x] C20/C21 local 100 nF/50 V CIN_HF are present at U3/U4, and the new
  five-page source passes commit-bound KiCad 9 ERC plus PDF visual preflight.
- [ ] Routed C11/C20/U3 and C12/C21/U4 VIN-PGND hot loops prove direct
  pad-first geometry; C11/C12 effective capacitance at bias and temperature is
  accepted. C13 remains central damping and is not a local-CIN substitute.
- [x] Independent reviewer `Скиф` accepted exact source commit
  `e32c0aa9e510e8321e24ebb3ee2056100c5f3a1a` and PDF SHA-256
  `7abb5e83e5d8cc72178c37fbf559bd77ca0d915b1c92f94e12ed278ce83bf130`
  on `2026-09-17` with decision `ACCEPT_HIERARCHY_ONLY`.
- [ ] Conducted-emissions, RF coexistence and signed input-filter/no-filter
  decision rows `EVT-PWR-02/03/04` pass before routing.
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
- [x] The frozen EVT STEP binds the board, mounting pattern, conservative Z
  envelope and J1/J2 service volumes without fitted-body/mounting conflicts.
- [ ] Post-route native component STEP and final serial enclosure prove exact
  terminal mating, tool access, harness bend/service, enclosure and thermal fit.
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
The active source includes the later C20/C21 electrical ECO and has a new exact
pin/net semantic digest. Commit-bound KiCad 9 ERC/PDF evidence and independent
human hierarchy acceptance pass. Fitted-body and H1-H4 mounting clearance,
constraint coverage and `DIM-003` EVT acceptance remain valid. The mechanical
register is `18/18`; the stackup register remains `0/24` with `0/2` accepted
fabricator sets. Selected construction, numeric copper geometry, routing, physical
evidence, DRC, CAM, DFM, final serial mechanics and independent Review B are open.
Production outputs remain prohibited.
