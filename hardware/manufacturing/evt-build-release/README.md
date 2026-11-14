# EVT-PRE-20 current-source EVT build release - 2026-10-16

Status: **EVT BUILD AUTHORIZED / CUSTOMER CHECKOUT REQUIRED.**

PCB-MAIN is `COMPLETE-105 Rev.B`, eight copper layers, preferred order stack `JLC08161H-3313`, 1.6 mm, ENIG, 1 oz outer / 0.5 oz inner copper. The controlled package contains all eight copper Gerbers, drills, IPC-D-356, BOM, placement, drawings, KiCad sources and the 76-site epoxy-fill/copper-cap POFV control. Current checks: ERC 0, DRC errors 0, unconnected 0. Three Altium `Net Antennae` warnings are accepted import-rule artifacts because route and physical-path parity is complete and the native KiCad board is clean.

PCB-PWR is 4-layer and PCB-MIC is 2-layer. Both have complete Gerber/drill/IPC-D-356/BOM/placement/STEP packages, DRC errors 0 and unconnected 0. Their active `STATUS.json` records are `ACCEPTED` for the EVT build.

The public factory/DFM basis is `hardware/reviews/EVT_FACTORY_PUBLIC_CAPABILITY_BASELINE_REV_B.json`. The strict release report is `artifacts/evt_pre_20_evt_build_release_audit_final.json` and is `PASS`.

The customer owns order placement. At checkout the customer must select the controlled stack/material options, require epoxy fill and copper cap for all 76 MAIN locations, resolve every upload-parser/DFM error without automatic geometry changes, download and compare the job-specific production files, and confirm them in the factory portal.

Physical first-article checks remain mandatory before the remaining lot or any serial transfer: SPI/AOI/X-ray, current-limited startup, PWR protection/thermal/cold/EMI, RF/antenna tests, MIC acoustic calibration, harness crimp/electrical checks and housing fit/seal/IP/service checks.
