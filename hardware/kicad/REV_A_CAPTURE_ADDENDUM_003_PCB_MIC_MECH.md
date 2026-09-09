# EVT-PRE-20 Rev.A capture addendum 003 - PCB-MIC mechanical freeze

Status: `AUTHORITATIVE ADDENDUM / MECHANICAL FREEZE / NOT FOR MANUFACTURE`
Date: 2026-09-09

This addendum closes `DIM-004` and supersedes any PCB-MIC text that calls the leaf outline, board thickness, acoustic port or mounting pattern provisional.

## A. Frozen PCB-MIC mechanical contract

Coordinate origin is the lower-left corner of the generated PCB outline.

| Parameter | Rev.A value |
|---|---|
| PCB outline | 24.0 x 22.0 mm |
| PCB thickness | 1.0 mm |
| Layer count | 2 copper layers |
| Base material | FR-4 |
| Surface finish | ENIG |
| T5838 body reference center | X=12.0 mm, Y=16.0 mm |
| Acoustic PCB opening | NPTH diameter 0.8 mm, X=12.0 mm, Y=16.65 mm |
| H1 mounting hole | M2 clearance NPTH diameter 2.2 mm, X=4.0 mm, Y=16.65 mm |
| H2 mounting hole | M2 clearance NPTH diameter 2.2 mm, X=20.0 mm, Y=16.65 mm |
| J1 placement baseline | center X=12.0 mm, Y=5.0 mm, 180 deg in generator |

H1, the acoustic opening and H2 lie on one mechanical datum line. The two M2 holes have 16.0 mm center-to-center spacing.

## B. Acoustic rules

- The T5838 bottom acoustic port opens through the dedicated 0.8 mm NPTH.
- Copper, solder mask, solder paste, adhesive, conformal coating, membrane glue and enclosure features shall not obstruct the acoustic path.
- The microphone-to-membrane cavity is a separate acoustic/mechanical release item and remains governed by `PCB-MIC-004` and the acoustic test program.
- PCB thickness of 1.0 mm is frozen for Rev.A. The acoustic acceptance criterion is measured response/phase, not PCB thickness alone.
- No mounting screw, washer or metallic insert may overlap the acoustic inlet or the microphone body keepout.

## C. Mounting rules

- H1/H2 are unplated mechanical holes and carry no electrical net.
- The mic pod shall locate the leaf from the two M2 holes and the acoustic datum without applying bending load to the T5838 package.
- Fastener stack, spacer height and membrane compression are finalized in the mic-pod tolerance stack. They may not move the PCB hole coordinates without a Rev.A ECO.

## D. Connector control

The active connector remains Molex Pico-Lock 1.50 mm `5040500691`, six circuits. Electrical pin order is controlled by `hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv`.

The imported EasyEDA/LCSC footprint remains secondary reference data only. Signal-pad pitch/body/anchor geometry must agree with the Molex manufacturer drawing before Review B. A DRC pass does not waive this requirement.

## E. Native CAD enforcement

`tools/finalize_pcb_mic_mechanical_rev_a.py` applies board thickness and H1/H2 after electrical board generation.

`tools/audit_pcb_mic_mechanical_rev_a.py` independently checks:
- 24 x 22 mm outline;
- 1.0 mm thickness;
- H1/H2 coordinates and 2.2 mm drills;
- acoustic port coordinate and 0.8 mm drill;
- absence of the obsolete `DIM-004 OPEN` fabrication note.

The separate native geometry audit remains authoritative for the T5838 land pattern and connector circuit count.

## F. Release state

Closing `DIM-004` does not make PCB-MIC manufacturing-ready. Release remains blocked until all of the following have evidence:

1. native KiCad 9 schematic and PCB materialize successfully;
2. ERC and DRC pass without unexplained waivers;
3. Gerber/Excellon/PnP outputs are independently CAM-reviewed;
4. T5838 and Molex manufacturer geometry review passes;
5. panelization/depanel method protects the MEMS microphone;
6. membrane/tolerance stack is frozen and acoustically validated;
7. Review A and Review B pass;
8. PCB/PCBA manufacturer DFM comments are closed.
