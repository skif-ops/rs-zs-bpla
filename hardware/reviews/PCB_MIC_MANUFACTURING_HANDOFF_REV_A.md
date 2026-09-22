# PCB-MIC Rev.A manufacturing handoff

Status: `EVT STANDARD PROCESS ACCEPTED / EXTERNAL REPLY NOT REQUIRED / REVIEW B OPEN / NOT FOR MANUFACTURE`

Decision `2026-09-21`: the standard two-layer/PCBA process and the tightly
bounded MK1 acoustic-land exception are accepted in
`EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.md`. The nine register rows are
engineering-baseline closures, not claimed factory replies. First-panel bore
inspection, native DRC/CAM and Review B remain mandatory.

Historically, this packet was the controlled input for PCB fabricator and PCBA assembler DFM. It is
not a quotation acceptance, purchase release, panel approval or fabrication order.
The returned response must be recorded in
`hardware/reviews/PCB_MIC_DFM_RESPONSE_REV_A.csv`. Its nine technical rows are
now project engineering closures for EVT. This cannot change Review B or
manufacturing release to `PASS`.

## Source binding

| Item | Controlled value |
|---|---|
| Native PCB | `hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_pcb` |
| Native PCB SHA-256 | `a292a6ec2be555519a4fcc44f3d6cfdf0bc38a7f214caff6e71786942e3e4031` |
| Repeat Review-A commit | `e17a86bc78ba979f74c5549b378e94f7f3447fe4` |
| Copper-return decision commit | `7aeec13aa0c7ba1b3cd9095b800c6d08755912a3` |
| Copper-return acceptance-state commit | `8aa4a3d21b55956625db643e22436f248f75b258` |
| Machine contract | `hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.json` |
| Response register | `hardware/reviews/PCB_MIC_DFM_RESPONSE_REV_A.csv` |

Any proposed edit to the board, schematic, footprint, BOM, drill, CAM or mechanical
contract is an ECO. It must not be applied directly to a vendor copy and does not
inherit the recorded Review-A or copper-return acceptance.

## Frozen unit-board contract

The coordinate origin is the lower-left corner of the unit-board outline.

| Parameter | Rev.A value |
|---|---|
| Outline | 24.0 x 22.0 mm |
| Finished thickness | 1.0 mm |
| Copper layers | 2 |
| Base material | FR-4 |
| Surface finish | ENIG |
| T5838 body reference center | X=12.0 mm, Y=16.0 mm |
| Acoustic opening | 0.8 mm NPTH at X=12.0 mm, Y=16.65 mm |
| H1 | 2.2 mm NPTH at X=4.0 mm, Y=16.65 mm |
| H2 | 2.2 mm NPTH at X=20.0 mm, Y=16.65 mm |
| Fitted side | C1, J1, MK1 and R1 on top; no fitted bottom references |

The MK1-local design rule is 0.125 mm minimum copper clearance. Ordinary
NPTH-to-copper clearance is 0.20 mm; the sole 0.10 mm exception applies only to
the manufacturer-derived MK1 ground land around the acoustic bore, never to a
signal trace or zone. First-panel inspection must confirm a clean bore without
copper breakout. A zero-violation internal DRC does not replace that inspection.

## Controlled candidate outputs

The handoff must use one commit-bound archive containing the Gerber job and layers,
Excellon drill, IPC-356, pick-and-place CSV, manufacturing BOM, assembly/fabrication
PDF and board-sized F.Cu/B.Cu review SVGs. Every file must match the archive SHA-256
manifest. The PCB Native Gate artifact also carries the handoff audit, this packet,
the machine contract and the engineering-closure register under `PCB-MIC/`.
These outputs remain candidates until Review B closes.

## Panelization and depanel response

The fabricator must propose a controlled panel drawing that identifies the array,
unit orientation, breakaway geometry, tooling rails, fiducials, tooling holes and unit
marking. The proposed tab, route or V-score geometry must not intersect the T5838 body
or courtyard, the 0.8 mm acoustic opening or acoustic path, or H1/H2.

The fabricator and assembler must jointly identify a MEMS-safe depanel method and a
sample-inspection method. It must prevent unacceptable board bending, package stress
and debris ingress at the acoustic opening.

No panel array, rail width, tab location, V-score location, router path, paste
reduction or reflow profile is frozen by this packet. Those values require a vendor
proposal and controlled acceptance before manufacture.

## Assembly acoustic-process control

The acoustic path must not be obstructed by copper, solder mask, solder paste,
adhesive, conformal coating, membrane glue, an enclosure feature, mounting hardware,
fixtures or process residue. The assembler must return a process keepout drawing and
written acceptance covering dispensing, coating, cleaning, inspection and handling.

Placement review must confirm C1, J1, MK1 and R1 as top-side fitted references and
must compare centroid origin, rotations, connector orientation and component polarity
against the assembly drawing.

## Response and release rule

All nine rows in `PCB_MIC_DFM_RESPONSE_REV_A.csv` are
`CLOSED_EVT_ENGINEERING_BASELINE`, cite the controlling manual and are
non-blocking. They are not claimed factory replies. A checkout DFM error,
first-panel defect or source change remains open until dispositioned through the
project ECO process.

Even after fabricator and assembler DFM acceptance, the membrane/cavity tolerance
stack, assembled acoustic inspection, physical EVT calibration, independent Review-B
signature and manufacturing release remain separate blocking gates.
