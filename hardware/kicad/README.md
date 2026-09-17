# ZS-BPLA EVT-PRE-20 KiCad package

Status: `NATIVE SOURCE CONTROLLED / NOT FOR MANUFACTURE`
Configuration: `EVT-PRE-20 Rev.A`
Authoritative branch: `evt-pre-20`

This directory is the authoritative electrical-CAD source package for the EVT-PRE-20 custom-PCB build. The three native projects and their required hierarchical child sheets are present. It remains blocked from manufacturing until each provisional board is completed and the required ERC/DRC, CAM, DFM and independent reviews are complete.

## Frozen baseline used for capture

- MCU: `STM32U585VIT6Q`, LQFP100 14x14 mm. The earlier `STM32U585CIU6`/48-pin and `STM32U585ZIT6Q` references are superseded for EVT-PRE-20.
- Microphones: 4 x TDK/InvenSense `T5838`, identical MPN; same lot preferred.
- Acoustic geometry: 3+1, equilateral base 120 mm, upper microphone +150 mm over center.
- Cellular: Quectel `BG95-M3` candidate, two physical nano-SIM slots through external 2:1 SIM mux, Dual-SIM Single-Standby only.
- GNSS/PPS: independent u-blox `MAX-M10S` class receiver.
- LoRa: Ebyte `E22-900M22S` / SX1262 class, RU868 pilot profile on every station in the selected 4, 10 or 20-unit EVT lot.
- BLE commissioning/diagnostics/OTA coprocessor: Raytac `MDBT50Q-P1MV2` based on Nordic `nRF52840`, integrated PCB antenna. `ESP32-C3-MINI-1-N4` is superseded and forbidden in active Rev.A BOM/capture.
- BLE requirements: BLE 2M/1M/Coded Long Range, authenticated commissioning, signed OTA, local diagnostics; Wi-Fi is not required.
- Local storage: W25Q512-class 64 MB NOR plus industrial microSD.
- Power source: 12.8 V LiFePO4 40-60 Ah, external 10 A LiFePO4 MPPT, 60-80 W solar panel.
- MPPT function is external. Do not reintroduce the older BQ24650/CN3791 charger topology into EVT-PRE-20 PCB-MAIN or PCB-PWR.

## PCB set

1. `PCB-MAIN`: MCU, BG95, dual SIM, MAX-M10S, LoRa module, nRF52840 BLE module, NOR, microSD, sensors, USB service, SWD and test points.
2. `PCB-MIC`: one T5838 microphone leaf; four identical boards per station.
3. `PCB-PWR`: protected battery interface and DC/DC rails for 3.8 V modem, 3.3 V digital/AON and 1.8 V microphone domains. External MPPT remains a separate assembly.

PCB-PWR `C1-C19`, `R1-R15`, `NT1-NT3` and `TP1-TP10` are bound from
`hardware/PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv`. This is a capture/placement input,
not a manufacturing release; its electrical, package, fixture and environmental
blockers remain explicit in the authority.

PCB-PWR now uses a human-readable five-page native hierarchy: one system overview
plus four functional child sheets for input protection/current monitoring, 3V8,
3V3 and 1V8/harness interfaces. The controlled materializer gives every connected
pin an explicit wire stub and the independent audit proves exact pad/net
equivalence to the native PCB. Post-ECO KiCad 9 ERC/PDF evidence passes and is
commit/SHA-256 bound; independent human acceptance of the active drawing remains
open. The earlier acceptance for the superseded F1 value does not release it.

PCB-PWR currently contains a native, unrouted 60-footprint electrical placement
canvas. Its `90 x 60 mm`, four-layer and `1.6 mm` assumptions are provisional;
mounting holes, routing and copper zones are deliberately absent while `DIM-003`
remains open. `hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json` is the machine-readable
release interlock for this state.

The bounded `DIM-003` request is now controlled by
`hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.json`; its 18-row response
register remains `0/18` accepted. It requests outline, mounting, J1/J2, DFT,
assembled-height, enclosure/thermal, harness-datum and frozen-STEP evidence but
does not release any of those values.

The bounded fitted-body clearance repack passes a strict independent subgate:
all 42 simultaneously fitted footprints have controlled courtyards, the required
minimum gap is `0.20 mm`, the observed minimum is `0.22 mm`, and conflicts are
zero. This result excludes DNP/PCB-feature service checks and does not approve
the provisional J2 edge overhang, connector mating/bend volumes, mounting, DFT
fixture access, assembled STEP, routing or Review B.

`hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv` classifies all 31 native nets as a
pre-route input, including high-current paths, three controlled net-tie returns,
switch/bootstrap loops, Kelvin sense, feedback and I2C. Its PASS does not permit
routing: numeric width, via-array and plane geometry remain open until `DIM-003`,
final current/fault envelopes, stackup/copper weights and thermal review close.

## Logical sheet plan

1. `01_POWER` - protected input and regulated rails; no integrated solar MPPT.
2. `02_MCU` - STM32U585VIT6Q, clocks, reset, SWD, decoupling, boot straps.
3. `03_AUDIO` - four PDM channels, common clock fanout/interface, microphone connectors.
4. `04_GNSS` - MAX-M10S, TIMEPULSE/PPS, RF connector/bias, backup supply.
5. `05_CELLULAR` - BG95-M3, 3.8 V transient decoupling, 1.8 V logic translation, dual nano-SIM mux and ESD.
6. `06_LORA` - E22-900M22S/SX1262 interface, RF connector/matching/ESD.
7. `07_BLE` - Raytac MDBT50Q-P1MV2 / nRF52840 service, commissioning and OTA coprocessor with SWD/UART recovery access and antenna keepout.
8. `08_STORAGE_SENSORS` - W25Q512, industrial microSD, LIS2DW12, temperature and current/voltage monitoring.
9. `09_CONNECTORS_TEST` - PCB-PWR, MIC1..MIC4, USB-C service, SWD, production test fixture and revision straps.

## Required CAD gates before Gerber release

- Pre-schematic PCB-MAIN authorities `MAIN-AUTH-001…011` are closed; the 110 x 75 mm outline, connector/module anchors, RF/keepout regions and 31 production pogo-pad coordinates are frozen by `hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv`.
- Treat that frozen PCB-MAIN placement as a capture baseline, not a released
  placement: the accepted limited mechanical ECO clears the six conflicts that
  were inside MAIN-AUTH-011. The controlled 225-reference functional repack and
  explicit generic-passive courtyards now pass the independent strict 2D audit:
  227/227 fitted assembly footprints have courtyards and all component,
  mounting-exclusion and U.FL tool-zone conflict sets are empty. Routing,
  KiCad DRC, 3D/service review and Review B remain required.
- Use `hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv` as the controlled pre-route
  input. It explicitly classifies all 186 native nets and preserves separate
  `GND_MODEM`, `GND_DIGITAL` and `GND_MIC` references. Its PASS is constraint
  coverage only: final stackup-dependent RF/USB geometry, routed copper, pours,
  DRC and manufacturing evidence remain open.
- Use `hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.json` and its
  blank response register only to obtain comparable construction data from
  `FAB-A` and `FAB-B`. The current `0/2` accepted response state does not select
  a stackup, authorize numeric 50-ohm/90-ohm rules or permit routing.
- Use `hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.json` and
  its blank 14-row register only for the bounded `U2/U25/U26/U9` process review.
  The current `0/14` accepted state does not select an assembler or process,
  create U9 paste apertures, close USB SI/whole-board DFM or permit manufacture.
- Use `hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv` as the 31-net PCB-PWR
  pre-route input. Freeze `DIM-003`, current/fault envelopes, stackup/copper
  weights and numeric thermal/current-density geometry before routing any copper.
- Use `hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.json` and its blank
  24-row register only to collect comparable stackup/copper inputs from two
  fabricators. The current `0/24` and `0/2` state selects no construction and
  authorizes no numeric power geometry, routing or fabrication.
- Preserve the strict PCB-PWR fitted-body clearance PASS and its six-reference
  coordinate delta; repeat the audit after any placement or footprint change.
- Freeze CubeMX pin/peripheral assignment for STM32U585VIT6Q; no unresolved AF conflicts.
- Replace provisional MAIN/PWR placement candidates with mechanically frozen,
  reviewed and routed boards; keep all native `.kicad_sch/.kicad_pcb/.kicad_pro`
  sources under CI control.
- Datasheet/reference-design review for STM32U585, T5838, BG95, MAX-M10S, E22/SX1262, nRF52840/Raytac module and all power ICs.
- ERC: zero unexplained errors.
- DRC: zero blocker/critical violations.
- Review modem burst current, brownout and decoupling at 3.8 V.
- Review PDM 1.8 V level compatibility, clock fanout and channel-to-channel skew.
- Review dual-SIM powered-off isolation, signal integrity and low-capacitance ESD.
- RF review for cellular/GNSS/LoRa 50-ohm paths, BLE 2.4 GHz antenna keepout, grounding and coexistence.
- Validate BLE range/RSSI/OTA throughput in the final vacuum-cast housing and the full-lot 3D fallback housing.
- USB differential pair and ESD review.
- Power-current/thermal review for PCB-PWR including fault cases.
- DFT review: SWD, reset, rails, production UART and fixture-accessible test points.
- Generate and inspect Gerber, Excellon, IPC-356, pick-and-place, BOM/AVL, assembly drawings, fabrication notes and STEP.
- Independent Review A: schematic/net/pin/BOM check against source requirements.
- Independent Review B: PCB/CAM/assembly/DFM check against released source.

## Manufacturing prohibition

Do not manufacture or assemble EVT-PRE-20 PCB from the CSV sheets, component lists, current placeholder `.kicad_pro`, or any Gerber generated before both independent reviews pass. The release flag may change to `FOR_MANUFACTURE` only when the production gate and SHA-256 manifest are complete.
