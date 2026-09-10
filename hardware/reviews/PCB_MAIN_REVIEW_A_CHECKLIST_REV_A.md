# PCB-MAIN Rev.A human Review A checklist

Status: `OPEN / UNSIGNED / NOT FOR MANUFACTURE`

Configuration: `EVT-PRE-20 Rev.A`

This checklist records the mandatory human review of the controlled native
PCB-MAIN schematic. Automated gates provide evidence but do not replace reviewer
judgement. Any failed or unexplained item keeps Review A open.

## 1. Review identity and immutable evidence

- [ ] Review commit SHA recorded: `________________________________________`
- [ ] Reviewer name recorded: `________________________________________`
- [ ] Review date recorded: `________________________________________`
- [ ] GitHub `CI` run URL recorded: `________________________________________`
- [ ] GitHub `PCB Native Gate` run URL recorded: `________________________________________`
- [ ] Both runs belong to the recorded commit and concluded `success`.
- [ ] `PCB-MAIN_schematic.pdf`, `erc.json`, `native_schematic_audit.json` and
      `native_schematic_bom.csv` were downloaded from that exact native-gate run.
- [ ] SHA-256 evidence manifest from the run was verified.

## 2. Source and automated gate review

- [ ] Deterministic generator check passes with no drift.
- [ ] Independent native schematic audit reports 248 components, 233 fitted,
      15 DNP, 1074 pins, 169 explicit NC markers and 186 native nets.
- [ ] KiCad 9 ERC report contains zero errors, warnings and exclusions.
- [ ] QG-1 reports 293 BOM rows and `PASS`.
- [ ] QG-2 remains `BLOCKED` only by declared production/review inputs; it does
      not report a missing native PCB-MAIN schematic.
- [ ] EVT branch isolation passes with no foreign configuration deliverable present.

## 3. MCU, clocks and debug

- [ ] U1 is `STM32U585VIT6Q`, LQFP100, with all 100 positions reviewed.
- [ ] The 67 functional assignments agree with the frozen pin authority and
      generated CubeMX `.ioc` report.
- [ ] PC15 and every unused/reserved pin have the required explicit disposition.
- [ ] No HSE crystal, oscillator, load capacitors or HSE routing is present.
- [ ] SiT1552 32.768 kHz source, NRST, BOOT0 and STM32 SWD agree with authority.
- [ ] STM32 SWD and nRF SWD remain electrically and physically separate.

## 4. Power and return domains

- [ ] `GND_MODEM`, `GND_DIGITAL` and `GND_MIC` remain separate on PCB-MAIN.
- [ ] J_PWR pins 2, 4 and 6 carry those three returns respectively.
- [ ] PCB-MAIN contains no ground-domain net tie.
- [ ] The only joins to `GND_PWR` are PCB-PWR NT1, NT2 and NT3.
- [ ] Entry bulk, local decoupling, SMPS components and rail test points agree
      with MAIN-AUTH-001/010 and the schematic-derived BOM.
- [ ] DC-bias derating, regulator stability and BG95 burst-droop calculations
      are reviewed and any open evidence is recorded below.

## 5. Functional blocks

- [ ] OCTOSPI flash, accelerometer and temperature-sensor pins/straps/addresses agree.
- [ ] PDM translation is bidirectional only where authorized; unused channels are safe.
- [ ] Four active-high AAD wake inputs and the two-stage OR path agree with authority.
- [ ] BG95 power banks, UART/USB/debug, PWRKEY and RESET_N open-collector stages agree.
- [ ] Dual-SIM mux, both protected sockets, detect paths and powered-off policy agree.
- [ ] GNSS UART/PPS, SAFEBOOT and active-antenna bias/supervisor topology agree.
- [ ] RU868 LoRa TXEN/RXEN, TCXO, reset and no-stub RF path agree.
- [ ] BLE UART/reset/DFU, separate SWD and integrated-antenna keepout agree.
- [ ] microSD, USB-C, RF receptacles, tamper, EOL and fixture contacts agree.

## 6. Components, footprints and mechanical inputs

- [ ] All 211 MAIN-AUTH-010 passive/support rows match the rendered schematic and BOM.
- [ ] DNP status is visually checked and no DNP part is treated as fitted.
- [ ] All standard 0402/0603/0805/1206/1210 footprints are appropriate.
- [ ] The 63 blank custom-footprint fields are reviewed as explicit blockers,
      not silently replaced by generic or synthetic land patterns.
- [ ] Exact manufacturer land patterns and paste/mask rules are approved before
      any affected footprint is populated in the schematic/layout.
- [ ] Board outline, four M3 holes, 13 connector anchors, four RF zones,
      keepouts and 31 pogo-pad coordinates agree with MAIN-AUTH-011.
- [ ] Enclosure/STEP and service-sweep evidence remains open until native layout exists.

## 7. Findings and disposition

Open findings or required changes:

| ID | Severity | Finding | Owner | Disposition / evidence |
|---|---|---|---|---|
| RA-001 | Major | Recorded commit `ac10cded` has no commit-matched `PCB Native Gate` run because its only changed path was outside the workflow path filter. | Automation | OPEN: create a traceability commit under `hardware/**`, obtain successful commit-matched CI and Native Gate runs, then verify the evidence ZIP manifest, expected SHA-256 values and `erc.json`. |

## 8. Sign-off

- [ ] All checklist items pass or have an approved, traceable disposition.
- [ ] No schematic/net/BOM difference remains unexplained.
- [ ] Review A status may be changed only in the same commit that records the
      reviewer, date, reviewed commit SHA and signed checklist evidence.

Decision: `PASS / FAIL / REWORK REQUIRED` (select one)

Reviewer signature: `________________________________________`

Date: `________________________________________`

Until this section is completed, PCB-MAIN layout, Review B and production BOM
release remain blocked.
