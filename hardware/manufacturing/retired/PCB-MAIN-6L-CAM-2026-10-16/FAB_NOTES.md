# PCB-MAIN fabrication notes — EVT-PRE-20 candidate

Status: **CANDIDATE / HOLD FOR REVIEW B. Fabrication is not authorized.**

- Source commit: `b6d9d620`.
- Controlled native source: `native/PCB-MAIN.kicad_pcb`.
- Copper layers: 6 (F.Cu;In1.Cu;In2.Cu;In3.Cu;In4.Cu;B.Cu).
- Finished thickness: 1.6 mm.
- Copper weight target: outer 1 oz; inner 0.5 oz.
- Layer intent: SIGNAL_RF;REFERENCE;POWER_DOMAINS;SIGNAL;REFERENCE;SIGNAL.
- Stackup basis: EVT_ACCEPTED_JLC06161H_3313 / Native KiCad board and EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.
- Surface finish: ENIG for EVT-PRE-20.
- Electrical test: 100% against `PCB-MAIN.d356`.
- Gerbers and Excellon drill are generated from the included native board using KiCad 10.0.6.
- JLC BOM retains manufacturer and MPN. Blank LCSC fields require assembler mapping or consigned-part confirmation.
- DRC summary: 203 error violations, 464 warning violations, 499 unconnected items.

Open gates: routing; native DRC; CAM; independent Review B; EVT validation.
