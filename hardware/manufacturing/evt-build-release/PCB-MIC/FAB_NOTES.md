# PCB-MIC fabrication notes — EVT-PRE-20 candidate

Status: **CANDIDATE / HOLD FOR REVIEW B. Fabrication is not authorized.**

- Source commit: `b6d9d620`.
- Controlled native source: `native/PCB-MIC.kicad_pcb`.
- Copper layers: 2 (F.Cu;B.Cu).
- Finished thickness: 1.0 mm.
- Copper weight target: outer 1 oz.
- Layer intent: SIGNAL_POWER;GROUND_RETURN.
- Stackup basis: EVT_ACCEPTED_STANDARD_2L_FR4_ENIG / Native KiCad board and EVT engineering manufacturing baseline.
- Surface finish: ENIG for EVT-PRE-20.
- Electrical test: 100% against `PCB-MIC.d356`.
- Gerbers and Excellon drill are generated from the included native board using KiCad 10.0.6.
- JLC BOM retains manufacturer and MPN. Blank LCSC fields require assembler mapping or consigned-part confirmation.
- DRC summary: 0 error violations, 0 warning violations, 0 unconnected items.

Open gates: native DRC; CAM; first-panel acoustic inspection; independent Review B.
