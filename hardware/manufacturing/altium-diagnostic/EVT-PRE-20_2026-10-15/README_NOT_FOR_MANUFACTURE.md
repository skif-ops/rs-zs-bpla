# EVT-PRE-20 Altium diagnostic manufacturing bundle

Date: 2026-10-15  
Branch: `evt-pre-20`  
Status: **NOT FOR MANUFACTURE**

This bundle records the current Altium conversion work for PCB-MAIN, PCB-PWR, and PCB-MIC. It also retains the original KiCad projects, validation evidence, BOM documents, and the earlier KiCad engineering snapshot.

Altium source documents in the archive are taken from the tracked branch state. Uncommitted local Altium document changes and automatic history files are excluded.

Do not send this bundle to a factory as an approved release. The files are suitable for review, comparison, and continued engineering work.

## Board status

| Board | Verified results | Open release blockers |
|---|---|---|
| PCB-MIC | KiCad ERC and DRC: 0. Altium compile: 0 errors. KiCad-to-Altium connectivity: 17/17 physical pins and 7/7 nets. Altium DRC: 0 warnings and 0 rule violations. Two-layer Gerber X2, NC Drill, Pick&Place, IPC-D-356/test-point data, DRC report, and STEP were generated. | Controlled manufacturing handoff, Review B, CAM/DFM, and independent manufacturing acceptance remain open. |
| PCB-PWR | Altium compile: 0 errors, 31 warnings. Connectivity: 161/161 physical pins, 31/31 multi-pin nets, and 1/1 singleton membership. Altium DRC: 0 warnings and 0 rule violations after the documented NetTie adapter repair. Four-layer Gerber X2, NC Drill, Pick&Place, IPC-D-356/test-point data, DRC report, and STEP were generated. | Native KiCad DRC still has 7 silk-over-copper warnings. Input-protection qualification, DIM-003 mechanics, stackup/copper authority, routing/placement gates, Review B, CAM/DFM, and independent acceptance remain open. |
| PCB-MAIN | Altium compile: 0 errors, 146 warnings. KiCad-to-Altium connectivity: 1074/1074 physical pins, 186/186 multi-pin nets, and 169/169 singleton memberships. The tracked Altium board is six copper layers. Gerber X2 was regenerated from that exact board and contains F.Cu, In1.Cu-In4.Cu, B.Cu, profile, masks, paste, legends, PTH, and NPTH files. | Altium DRC reports 421 unrouted violations. Native KiCad reports 667 DRC violations, 499 unconnected items, and 601 schematic-to-PCB parity items. RF, power integrity, stackup authority, mechanics, CAM/DFM, and Review B gates remain open. The PCB-MAIN outputs remain diagnostic and are not valid for manufacture. |

## Known output limitations

- The Altium 26 PDF container failed. Board Stack Report requested Microsoft Excel, then the Altium script stopped with a source-array exception. No valid newly generated Altium documentation PDF is included.
- A fresh Altium BOM was not generated because the imported OutJob has no approved BOM template. The bundle includes the tracked EVT-PRE-20 BOM documents and per-board BOM CSV files from the engineering snapshot. The strict audit reports BOM evidence/hash drift, so these BOM files are reference material until QG-2 is repaired and accepted.
- PCB-MAIN Gerber X2 was regenerated from a repair copy whose `PCB-MAIN.PcbDoc` SHA-256 exactly matches the tracked board. The saved OutJob selection now includes all six copper layers. Before a later regeneration, recheck the copper, mask, paste, legend, drill, and profile selections in Altium.
- The STEP exports contain only the board data/models available in the imported projects. Missing 3D models were not invented.

## Included material

- `ALTIUM/`: Altium projects, libraries, OutJobs, and source documents.
- `ALTIUM_OUTPUTS/`: generated Gerber X2, NC Drill, Pick&Place, test-point/IPC-D-356, DRC, and STEP files.
- `KICAD_ORIGINALS/`: preserved KiCad sources and local libraries. They were not deleted or replaced.
- `VALIDATION/`: connectivity, ERC, DRC, geometry, and repair evidence.
- `BOM/`: tracked project BOM documents and per-board engineering-snapshot BOM CSV files.
- `KICAD_ENGINEERING_SNAPSHOT/`: the earlier full KiCad engineering snapshot, kept separately from the Altium diagnostics.
- `STATUS.json`, `MANIFEST.csv`, and `SHA256SUMS.txt`: machine-readable status and archive checksums.

## Release decision

The strict EVT-PRE-20 hardware audit remains **BLOCKED**. PCB-MIC has the strongest conversion evidence, PCB-PWR has usable diagnostic fabrication outputs with open release gates, and PCB-MAIN now has a six-layer Altium Gerber set, but its 421 unrouted violations and remaining engineering gates must be resolved before a production package can be approved.
