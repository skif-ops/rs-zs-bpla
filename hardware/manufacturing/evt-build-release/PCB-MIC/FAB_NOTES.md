# PCB-MIC fabrication notes - EVT-PRE-20

Status: **EVT BUILD AUTHORIZED / CUSTOMER CHECKOUT REQUIRED.**

- Controlled native source: `native/PCB-MIC.kicad_pcb`.
- Copper layers: 2 (`F.Cu; B.Cu`).
- Finished thickness: 1.0 mm.
- Copper weight target: outer 1 oz.
- Layer intent: SIGNAL_POWER; GROUND_RETURN.
- Stackup basis: standard 2-layer FR-4 ENIG.
- Electrical test: 100 percent against `PCB-MIC.d356`.
- Gerber and Excellon outputs are generated from the included native board.
- Exact manufacturer/MPN data is retained; assembly supply mode is controlled by `hardware/EVT_PRE_20_PCBA_ASSEMBLER_PART_MAP_REV_A.csv`.
- DRC: 0 errors, 0 warnings, 0 unconnected items.
- Acoustic NPTH and membrane/adhesive keepout must remain clear through panelization, assembly and coating.

Customer checkout parser/DFM confirmation remains mandatory. First-panel acoustic-port inspection and per-board gain/noise/phase/delay calibration are performed on EVT first articles before releasing the remaining lot.
