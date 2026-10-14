# EVT-PRE-20 Altium Output Job status

Date: 2026-10-15
Status: **BLOCKED — NOT FOR MANUFACTURE**

Portable Altium Designer 26.10.1 output configurations now exist beside all three diagnostic projects:

| Board | Project | Output Job | Current verification state |
|---|---|---|---|
| PCB-MAIN | `PCB-MAIN/PCB-MAIN.PrjPcb` | `PCB-MAIN/EVT-PRE-20_PCB-MAIN.OutJob` | Compiles with 0 errors; 421 Altium unrouted violations remain. |
| PCB-PWR | `PCB-PWR/PCB-PWR.PrjPcb` | `PCB-PWR/EVT-PRE-20_PCB-PWR.OutJob` | Compiles with 0 errors; 3 Altium unrouted NetTie connections remain. |
| PCB-MIC | `PCB-MIC/PCB-MIC.PrjPcb` | `PCB-MIC/EVT-PRE-20_PCB-MIC.OutJob` | Compiles with 0 errors; 10 clearance findings remain. |

Each OutJob was opened in Altium Designer 26.10.1 Trial and contains:

- Gerber X2 and NC Drill;
- board stack and drill drawing;
- assembly drawings and schematic/PCB PDF prints;
- Pick&Place and BOM;
- fabrication testpoint CSV and IPC-D-356A reports in metric units, using the relative origin and both copper sides;
- DRC report and STEP export.

The PDF and folder containers use local relative paths. Release management is disabled. No absolute workstation path is stored.

These OutJobs are configuration artifacts. They have not been run to create a release set because the hardware release gate remains active. Generated outputs must be reviewed only after routing, DRC, PCB-to-schematic, footprint, BOM, placement, stackup, impedance, RF/power, DFM, mechanical, and Review B blockers are closed. Until then, no archive from these projects may be described as a production-ready EVT-PRE-20 manufacturing package.

All original KiCad files remain preserved under `hardware/kicad/`; this change neither removes nor replaces them.
