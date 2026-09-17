# PCB-MAIN Rev.A human Review A checklist

Status: `REVIEWED / PASS RECOMMENDED / NOT FOR MANUFACTURE`

Configuration: `EVT-PRE-20 Rev.A`

This checklist records the mandatory human review of the controlled native
PCB-MAIN schematic. Automated gates provide evidence but do not replace reviewer
judgement. Any failed or unexplained item keeps Review A open.

Review method: read-only clone of `skif-ops/rs-zs-bpla`, branch `evt-pre-20`.
Design content was reviewed at `ac10cded959c58e57097bd220737ed380dc2bea9`; the
recorded review commit is `5c68a2da43c834c9a1e1eaac31ccbc07d8a7be80`
("ci(pcb-main): include Review A evidence in native gate paths"). The delta
`ac10cded..5c68a2da` touches only `.github/workflows/pcb-native.yml` (path filter
`hardware/reviews/**`) and this checklist; `hardware/kicad/**`, all authorities,
generator and auditors are byte-identical. All Python gates of `pcb-native.yml` and
`ci.yml` were re-executed locally (Python 3.12, kiutils 1.4.8). KiCad 9.0.9 ERC and PDF
are taken from the commit-matched `PCB Native Gate` run #99 artifact, verified by hash.

## 1. Review identity and immutable evidence

- [x] Review commit SHA recorded: `5c68a2da43c834c9a1e1eaac31ccbc07d8a7be80`
- [x] Reviewer name recorded: `Скиф`
- [x] Review date recorded: `10.09.2026`
- [x] GitHub `CI` run URL recorded: `https://github.com/skif-ops/rs-zs-bpla/actions/runs/34515812070` (run #366)
- [x] GitHub `PCB Native Gate` run URL recorded: `https://github.com/skif-ops/rs-zs-bpla/actions/runs/34515812116` (run #99)
- [x] Both runs belong to the recorded commit and concluded `success` (`5c68a2da`, both `completed successfully` on the Actions page).
- [x] `PCB-MAIN_schematic.pdf`, `erc.json`, `native_schematic_audit.json` and
      `native_schematic_bom.csv` were downloaded from that exact native-gate run
      (artifact `evt-pre-20-kicad-native-gate`, ZIP sha256
      `3838621057cde04e2c10ae1c5260c44b76db0aedafc4580ac0ffc92da0303dca`;
      `PCB-MAIN.kicad_sch` `053297c6…` = tree, `native_schematic_bom.csv` `278c87ca…` = local
      regeneration, `erc.json` `6a7693b7…`, PDF `3569d10c…`, audit `362b9e2c…`).
- [x] SHA-256 evidence manifest from the run was verified — run-side
      `artifacts/kicad-native/sha256_manifest.json`: 40/40 entries match the artifact
      contents; committed `PCB-MAIN_capture_manifest.json`: 17/17 input hashes, generator
      `b5fe0c7c…`, schematic `053297c6…`, symbol library `565d255c…` match the tree;
      MAIN-AUTH-011 CSV `2ea8da3b…` matches.

## 2. Source and automated gate review

- [x] Deterministic generator check passes with no drift
      (`generate_pcb_main_schematic_rev_a.py --check`: PASS).
- [x] Independent native schematic audit reports 248 components, 233 fitted,
      15 DNP, 1074 pins, 169 explicit NC markers and 186 native nets
      (`audit_pcb_main_native_schematic_rev_a.py`: PASS, exact counts; 0 singleton nets).
- [x] KiCad 9 ERC report contains zero errors, warnings and exclusions
      (run #99 `erc.json`: KiCad 9.0.9, 2026-09-10T18:42:13Z, severities error/warning/exclusion
      included, 0 violations; `native_gate.json`: PCB-MAIN `CLI_ERC_PDF_PASS_REVIEW_A_PENDING`,
      no CLI failures for any board).
- [x] QG-1 reports 293 BOM rows and `PASS` (`validate_evt_pre_20_bom_qg1.py`).
- [x] QG-2 remains `BLOCKED` only by declared production/review inputs; it does
      not report a missing native PCB-MAIN schematic (blockers: unreleased system SKUs
      BAT1/PV1/MPPT1/ANT-*/HARNESS/HSG-VC, supplier releases, Review A sign-off itself).
- [x] EVT branch isolation passes with no foreign configuration deliverable present
      (442 tracked paths, foreign configuration deliverables absent).

## 3. MCU, clocks and debug

- [x] U1 is `STM32U585VIT6Q`, LQFP100, with all 100 positions reviewed
      (`verify_pcb_main_mcu_pin_authority_rev_a.py`: 67 functional, 12 unused I/O, NRST, 20 supply/ref/gnd).
- [x] The 67 functional assignments agree with the frozen pin authority and
      generated CubeMX `.ioc` report (target contract PASS 67; IOC QG-1 67/67, QG-2 PASS;
      formal `cubemx_pin_report` evidence field is still `null` — RA-002).
- [x] PC15 and every unused/reserved pin have the required explicit disposition.
- [x] No HSE crystal, oscillator, load capacitors or HSE routing is present
      (`external_hse_allowed: false`; verifier and IOC QG-2 confirm no HSE).
- [x] SiT1552 32.768 kHz source, NRST, BOOT0 and STM32 SWD agree with authority.
- [x] STM32 SWD and nRF SWD remain electrically and physically separate
      (connector/fixture verifier: both SWD domains isolated; TP_MCU_SWD Y=23 X=69…79.16,
      TP_BLE_SWD Y=23 X=84…91.62).

## 4. Power and return domains

- [x] `GND_MODEM`, `GND_DIGITAL` and `GND_MIC` remain separate on PCB-MAIN
      (native endpoints 93 / 137 / 22; no generic `GND` net remains).
- [x] J_PWR pins 2, 4 and 6 carry those three returns respectively.
- [x] PCB-MAIN contains no ground-domain net tie (`pcb_main_ground_net_ties = 0`).
- [x] The only joins to `GND_PWR` are PCB-PWR NT1, NT2 and NT3.
- [x] Entry bulk, local decoupling, SMPS components and rail test points agree
      with MAIN-AUTH-001/010 and the schematic-derived BOM (passive/support verifier: 211 unique,
      196 fitted, 15 DNP; native audit matches MPN/package/population per component).
- [ ] DC-bias derating, regulator stability and BG95 burst-droop calculations
      are reviewed and any open evidence is recorded below (RA-003).

## 5. Functional blocks

- [x] OCTOSPI flash, accelerometer and temperature-sensor pins/straps/addresses agree
      (35 pins; I2C2 addresses 0x18/0x3F/0x40 unique).
- [x] PDM translation is bidirectional only where authorized; unused channels are safe
      (six used U7 channels, two defined unused channels).
- [x] Four active-high AAD wake inputs and the two-stage OR path agree with authority.
- [x] BG95 power banks, UART/USB/debug, PWRKEY and RESET_N open-collector stages agree
      (two MMBT3904 stages, pulse windows, 1.8 V margins verified).
- [x] Dual-SIM mux, both protected sockets, detect paths and powered-off policy agree.
- [x] GNSS UART/PPS, SAFEBOOT and active-antenna bias/supervisor topology agree.
- [x] RU868 LoRa TXEN/RXEN, TCXO, reset and no-stub RF path agree (fail-closed TXEN/RXEN).
- [x] BLE UART/reset/DFU, separate SWD and integrated-antenna keepout agree
      (10.5 x 3.8 mm all-layer keepout; +15 mm enclosure exclusion in MAIN-AUTH-011).
- [x] microSD, USB-C, RF receptacles, tamper, EOL and fixture contacts agree (70 contacts).

## 6. Components, footprints and mechanical inputs

- [x] All 211 MAIN-AUTH-010 passive/support rows match the rendered schematic and BOM.
- [x] DNP status is visually checked and no DNP part is treated as fitted
      (native `dnp` flag matches authority population for all 248 symbols; 15 DNP, all `in_bom`).
- [x] All standard 0402/0603/0805/1206/1210 footprints are appropriate
      (184 symbols carry KiCad standard patterns: R_0402 x102, C_0402 x69, C_0603 x8,
      C_0805, L_0402, L_1206, L_1210, R_1206).
- [x] The 63 blank custom-footprint fields are reviewed as explicit blockers,
      not silently replaced by generic or synthetic land patterns (64 blank fields in the
      schematic = 63 custom parts + U12 microSD card, which has no land pattern by design:
      U1–U11, U13–U27, D1–D11, Q1–Q4, FL1, X1, C36/C44 (T520 polymer 7343), J6–J13,
      J_PWR, J_MIC1–4, five TP groups).
- [x] Exact manufacturer land patterns and paste/mask rules are approved before
      any affected footprint is populated in the schematic/layout (none populated; remains a
      Review B / layout gate).
- [x] Board outline, four M3 holes, 13 connector anchors, four RF zones,
      keepouts and 31 pogo-pad coordinates agree with MAIN-AUTH-011
      (`verify_pcb_main_mechanical_placement_authority_rev_a.py`: PASS; capture-authority audit:
      70/70 records).
- [x] Enclosure/STEP and service-sweep evidence remains open until native layout exists
      (`OPEN_DIMENSIONS.csv` = `CONTROLLED_PENDING_NATIVE_STEP`; `PCB-MAIN.kicad_pcb` absent).

## 7. Findings and disposition

Open findings or required changes:

| ID | Severity | Finding | Owner | Disposition / evidence |
|---|---|---|---|---|
| RA-001 | Major (evidence) | Original review commit `ac10cded` had no commit-matched `PCB Native Gate` run: its only changed path was outside the workflow path filter, and the older run #66 artifact predated the native schematic (PCB-MAIN `MISSING`, PCB-PWR ERC fail). | Скиф | **CLOSED 10.09.2026.** Traceability commits `47dc332` + `5c68a2da` added `hardware/reviews/**` to the Native Gate path filter; commit-matched runs CI #366 and Native Gate #99 concluded `success`. Run #99 artifact independently verified: ZIP `38386210…`, `.kicad_sch` `053297c6…` identical to reviewed tree, BOM `278c87ca…`, `erc.json` `6a7693b7…` with 0 violations (KiCad 9.0.9), run manifest 40/40, audit counts 248/233/15/1074/169/186 unchanged. No schematic change occurred between `ac10cded` and `5c68a2da`. |
| RA-002 | Minor (evidence) | `PCB_MAIN_CAPTURE_STATUS_REV_A.json` → `review_a.evidence.cubemx_pin_report` is `null`, while item 3.2 requires the generated CubeMX report as evidence. IOC QG-1/QG-2 pass (67/67 pins, CubeMX 6.12.0 DB.6.0.120 hash-bound) and are re-run in CI #366. | Скиф | Traceable disposition available: point the field at the CI #366 IOC QG-1/QG-2 artifacts (or the `.ioc` itself, hash-bound) in the signing commit. Does not block PASS once recorded. |
| RA-003 | Open evidence (allowed by §4) | DC-bias derating of MLCC decoupling, U1 SMPS stability and BG95 burst droop have no calculation record for PCB-MAIN. MAIN-AUTH-004 sets requirements (`VBAT_BB`/`VBAT_RF` ≥ 3.3 V at all four U8 VBAT pads under 2G/LTE burst; `GND_MODEM`–`GND_DIGITAL` offset < 75 mV at U16) but defers them to measurement; `POWER_DESIGN_CALC_REV_A.md` covers PCB-PWR only. C36/C44 (100 µF 6.3 V T520 polymer) are locked with "verify droop and ripple current". | Скиф | Recorded as open evidence per §4. Carried forward as a mandatory Review B / EVT bring-up measurement item (VBAT ≥ 3.3 V at four U8 pads under burst; GND offset < 75 mV at U16; MLCC effective capacitance at 3.8 V / 1.8 V; SMPS COUT ESR window). A PCB-MAIN calculation note before layout is recommended but not required for Review A. Not a schematic defect. |
| RA-004 | Minor (process) | The copy of `PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.md` supplied for this review is stale: its §"Review and release boundary" still states the native schematic is absent, while the repository version at `ac10cded` states it is present, net-audited and ERC-clean. The CSV hash `2ea8da3b…` is identical in both. | Скиф | **CLOSED** — repository version at the reviewed commit used; stale copy discarded. No repository change required. |

Automated re-execution summary at `ac10cded` (identical PCB content to `5c68a2da`; local,
read-only): preflight PASS (release gate correctly BLOCKED, 6 native source files still
absent — PWR/MIC/PCB);
capture-authority audit PASS (70/70 records, 20 MPNs, 41 harness pins, 11/11 authorities
closed); all 11 second-independent verifiers PASS; generator drift PASS; native audit PASS;
QG-1 PASS; QG-2 BLOCKED as expected; branch isolation PASS; component/connector freeze
PASS; target contract, IOC QG-1/QG-2 PASS; release audit correctly incomplete.

## 8. Sign-off

- [x] All checklist items pass or have a traceable disposition (RA-001, RA-004 closed;
      RA-002 dispositioned to the signing commit; RA-003 carried to Review B as open evidence).
- [x] No schematic/net/BOM difference remains unexplained.
- [x] Review A status may be changed only in the same commit that records the
      reviewer, date, reviewed commit SHA and signed checklist evidence.

Decision: `PASS` — native PCB-MAIN schematic at `5c68a2da` (content unchanged since
`ac10cded`) with RA-002 to be recorded and RA-003 carried as open evidence into Review B.
Layout, Review B, DFM and all physical EVT tests remain pending; nothing here is a
manufacturing release.

Reviewer signature: `Скиф`

Date: `10.09.2026`

Until this section is completed, PCB-MAIN layout, Review B and production BOM
release remain blocked.
