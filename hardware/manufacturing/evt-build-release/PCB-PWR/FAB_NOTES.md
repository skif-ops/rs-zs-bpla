# PCB-PWR fabrication notes — EVT-PRE-20 candidate

Status: **CANDIDATE / HOLD FOR REVIEW B. Fabrication is not authorized.**

- Source commit: `b6d9d620`.
- Controlled native source: `native/PCB-PWR.kicad_pcb`.
- Copper layers: 4 (F.Cu;In1.Cu;In2.Cu;B.Cu).
- Finished thickness: 1.6 mm.
- Copper weight target: outer 2 oz; inner 1 oz.
- Layer intent: POWER_SIGNAL;REFERENCE;POWER_RETURN;POWER_SIGNAL.
- Stackup basis: EVT_ACCEPTED_JLC04161H_3313A / Native KiCad board; accepted DIM-003; EVT engineering baseline; calculated current geometry.
- Surface finish: ENIG for EVT-PRE-20.
- Electrical test: 100% against `PCB-PWR.d356`.
- Gerbers and Excellon drill are generated from the included native board using KiCad 10.0.6.
- JLC BOM retains manufacturer and MPN. Blank LCSC fields require assembler mapping or consigned-part confirmation.
- DRC summary: 0 error violations, 7 warning violations, 0 unconnected items.

Open gates: routing; native DRC; CAM; plus70C thermal EVT; independent Review B; series mechanical revalidation.
