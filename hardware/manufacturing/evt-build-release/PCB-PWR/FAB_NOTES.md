# PCB-PWR fabrication notes - EVT-PRE-20

Status: **EVT BUILD AUTHORIZED / CUSTOMER CHECKOUT REQUIRED.**

- Controlled native source: `native/PCB-PWR.kicad_pcb`.
- Copper layers: 4 (`F.Cu; In1.Cu; In2.Cu; B.Cu`).
- Finished thickness: 1.6 mm.
- Copper weight target: outer 2 oz; inner 1 oz.
- Layer intent: POWER_SIGNAL; REFERENCE; POWER_RETURN; POWER_SIGNAL.
- Stackup basis: JLC04161H-3313A, accepted DIM-003 and calculated current geometry.
- Surface finish: ENIG.
- Electrical test: 100 percent against `PCB-PWR.d356`.
- Gerber and Excellon outputs are generated from the included native board.
- Exact manufacturer/MPN data is retained; assembly supply mode is controlled by `hardware/EVT_PRE_20_PCBA_ASSEMBLER_PART_MAP_REV_A.csv`.
- DRC: 0 errors, 7 silkscreen warnings, 0 unconnected items.

Customer checkout parser/DFM confirmation remains mandatory. Protection, rail drop, transient, thermal, cold-start, EMI and DFT checks are performed on EVT first articles before releasing the remaining lot.
