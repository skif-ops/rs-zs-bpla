# EVT-PRE-20 PCB double-review release gate

Status: `ACTIVE / BLOCKING`
Applies to: `PCB-MAIN Rev.A`, `PCB-MIC Rev.A`, `PCB-PWR Rev.A`

No PCB may be marked `FOR_MANUFACTURE` until both reviews below are complete and the evidence set is archived.

## Review A - electrical/source verification

Purpose: prove that the schematic and net definition implement the approved EVT-PRE-20 architecture and do not silently carry superseded EVT/EVT-MB decisions.

Mandatory checks:

1. Exact MCU is STM32U585VIT6Q/LQFP100 and the CubeMX `.ioc` matches schematic pins one-for-one.
2. Every MCU pin in the schematic has a documented role, power function, explicit NC/reserved status, or test role.
3. PDM microphone subsystem is four T5838 channels with common clock and four independent data inputs; voltage-domain compatibility and skew controls are documented.
4. BG95 power, PWRKEY/RESET/STATUS/DTR/RI, UART level translation and burst-current decoupling match current Quectel requirements.
5. Dual SIM is Single-Standby only; two physical nano-SIM slots connect through the approved mux; switching is prohibited while BG95 is powered; local low-capacitance ESD is present.
6. Independent GNSS/PPS path remains available while cellular is active.
7. RU868 LoRa hardware and RF path do not depend on an EU868-only component or profile.
8. BLE commissioning/OTA coprocessor is the currently approved module and has safe boot/reset/programming access.
9. NOR, microSD and sensor buses have no pin/peripheral conflict with audio, LoRa, GNSS, cellular, USB or SWD.
10. PCB-PWR contains no obsolete solar-charge topology; the 10 A LiFePO4 MPPT is external.
11. All protection, pull, default-state and power-sequencing components are represented in the manufacturing BOM.
12. Connector logical pinout and harness register agree with schematic net names.
13. Schematic ERC is PASS with zero unexplained errors.
14. BOM/AVL has exact MPN, package, quantity, DNP and approved alternate policy for every fitted line.

Evidence required:
- signed Review-A checklist;
- exported schematic PDFs;
- CubeMX pin report / `.ioc`;
- ERC report;
- BOM diff against the released BOM register;
- net-name diff against the interconnect register;
- reviewer name/date/commit SHA.

## Review B - PCB/CAM/manufacturing verification

Purpose: independently prove that the PCB and generated factory files implement the reviewed schematic and are manufacturable/assemblable.

Mandatory checks:

1. PCB netlist matches released schematic; no unexplained net or component delta.
2. Board outline, mounting holes and keepouts match the released mechanical interface drawing.
3. RF traces/connectors/keepouts/ground stitching are reviewed for cellular, GNSS and LoRa.
4. Modem supply copper, vias, planes and bulk capacitors support worst-case current transient without unacceptable droop/heating.
5. PDM clock/data routing avoids RF/power aggressors; the four microphone harness paths are controlled for comparable delay.
6. USB D+/D- geometry, return path and ESD placement are checked.
7. SIM clock/data/reset traces are short, protected and isolated from RF/high-current switching nodes.
8. Production programming and EOL test points are accessible with the intended fixture after enclosure assembly where required.
9. DRC is PASS with zero blocker/critical violations.
10. Fabrication stackup, copper weights, minimum geometry and finish are accepted by the chosen factory.
11. Gerber/Excellon is opened in an independent CAM viewer and compared with KiCad source.
12. IPC-356/netlist is compared with the CAM result where supported.
13. Pick-and-place origin/rotation/side is checked against assembly drawing.
14. Assembly drawing shows reference designators, pin-1/polarity marks, DNP and connector orientation.
15. Factory DFM review is archived and all blocker/critical comments are closed.
16. SHA-256 hashes cover all source and generated manufacturing files.

Evidence required:
- signed Review-B checklist;
- DRC report;
- CAM screenshots/report;
- Gerber, drill and IPC-356;
- fabrication and assembly drawings;
- PnP/centroid and production BOM;
- DFM response/closure;
- reviewer name/date/commit SHA.

## Independence rule

Review B must not be a repetition of Review A. At minimum it must be performed as a separate pass after all Review-A corrections are committed, using newly generated production outputs. Ideally the second reviewer is a different person; if one engineer performs both passes, the second pass must be separated by a new commit and use a clean export/CAM session.

## Release states

- `CAPTURE_INPUT`: architecture/net input only; production forbidden.
- `SCHEMATIC_REVIEW`: native schematic exists; production forbidden.
- `LAYOUT_REVIEW`: PCB exists; production forbidden.
- `REVIEW_A_PASS`: electrical review passed; production still forbidden.
- `REVIEW_B_PASS`: manufacturing review passed; release manifest may be created.
- `FOR_MANUFACTURE`: both reviews passed, all P0 evidence present, SHA-256 manifest frozen.
- `HOLD`: any later design/BOM/mechanical change invalidates the previous release until affected reviews are repeated.

## Automatic invalidation

Any change to MCU MPN/package, pin map, microphone MPN/geometry, modem, SIM topology, GNSS, LoRa module/RF path, BLE module, power topology, PCB outline, connector pinout, critical protection, fabrication stackup or fitted BOM automatically returns the affected PCB to `HOLD` and requires re-review.
