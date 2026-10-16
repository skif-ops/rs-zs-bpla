# EVT-PRE-20 - manufacturing release record Rev.B

Release date: 2026-10-16.

## Result

`tools/audit_evt_pre_20_evt_build_release.py --strict` returns `PASS` with no blockers. PCB-MAIN is the accepted 8-layer Rev.B design. PCB-PWR is 4-layer and PCB-MIC is 2-layer. KiCad sources remain preserved; Altium projects and outputs are included in the full package.

Completed without hardware:

- PCB and schematic source inventory, layer authority and KiCad-to-Altium evidence;
- ERC/DRC/unconnected checks and controlled CAM output sets;
- public factory stack, geometry, POFV, PCBA, stencil, placement and checkout rules;
- Review B release records for the EVT file sets;
- exact PCBA part map for 253 fitted lines and desktop closure for 202 BOM lines;
- complete harness build baseline with 38 controlled conductors;
- station mechanical BOM and all EVT dimension inputs;
- 3D-print housing master STEP, six STL files, drawing PDF, BOM, ASA profile and geometry validation.

Customer-owned order actions:

- supplier/assembler selection, stock, price, payment and delivery;
- factory portal selections and resolution of any job-specific parser/DFM finding;
- comparison and confirmation of the exact production files generated for the order.

Post-build EVT actions:

- first-article PCB/PCBA, harness and housing inspection;
- PWR protection, transient, thermal, cold and EMI tests;
- RF/antenna VSWR, sensitivity and coexistence;
- MIC port, membrane, gain, noise, phase and delay calibration;
- IP, fit, service, insert/fastener and installed mechanical checks.

These physical results block release of the remaining held lot after first articles and block serial transfer. They do not block placement of the EVT order.
