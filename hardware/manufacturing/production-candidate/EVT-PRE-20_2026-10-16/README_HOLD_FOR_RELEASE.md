# EVT-PRE-20 full production candidate — 2026-10-16

Status: **HOLD FOR ENGINEERING CLOSURE**. Manufacturing and assembly are not authorized.

The external archive `EVT-PRE-20_FULL_PRODUCTION_CANDIDATE_2026-10-16.zip` was built from clean commit `0842954eee85612aad1e327c1d69d05998e9f381`. PCB-MAIN Rev.B with eight copper layers is the primary EVT baseline. The selected stack is `JLC08161H-3313`, nominal thickness 1.6 mm. The former six-layer Rev.A source and CAM are retained in the archive under `PCB-MAIN/History/`.

The archive contains Altium projects and preserved KiCad sources for PCB-MAIN, PCB-PWR and PCB-MIC, Gerber/drill/IPC-D-356/BOM/Pick&Place/STEP outputs, DRC/ERC evidence, review files, procurement documents, harness data and mechanical/manufacturing documents.

- Archive bytes: `27513157`
- Archive SHA-256: `79E854ED0ABF691402C6C50A84C4CBC17BCB98D80EDDBD92E5793731170DD9D7`
- Payload files: `1157`
- ZIP members: `1158`
- Manifest, CRC, payload hashes and path confinement: `PASS`

PCB-MAIN KiCad DRC has 0 errors, 0 unconnected items and 30 warnings; ERC has 0 violations. Altium compilation has 0 errors and 146 warnings; PCB DRC retains 3 `Net Antennae` warnings. Independent hierarchy acceptance and fabricator confirmation of the selected stack, dielectric, impedance, RF/SI, POFV and DFM remain open. PCB-PWR and PCB-MIC retain the Review and physical verification gates recorded in `STATUS.json` and the final audit reports.

`PAYLOAD_SHA256SUMS.json` records every archived payload file.
