# Дионея EVT-PRE-20 Rev.A - PCB-PWR provisional placement candidate

Status: `ELECTRICAL PLACEMENT CANVAS / DIM-003 OPEN / ROUTING ABSENT / NOT FOR MANUFACTURE`

This authority creates a reviewable native-board canvas without claiming enclosure or
fabrication approval. The `90 x 60 mm`, four-copper-layer and `1.6 mm` values are
deliberately provisional working values. They are not a mechanical freeze and must be
replaced or explicitly accepted after `DIM-003` supplies the assembled envelope,
terminal zones, mounting pattern and frozen PCB STEP.

## Controlled candidate content

- all 60 physical schematic references are present once and carry their exact native
  footprint and net assignment;
- J1 starts the west-side input/protection chain and J2 is provisionally oriented for
  an east-side harness exit;
- the 3V8 and 3V3 buck channels occupy separate upper and lower functional regions;
- the two LMR60440 input/bootstrap/inductor/output groups are kept close enough for
  power-loop review, but no copper geometry is inferred from placement alone;
- the INA226 and shunt occupy one Kelvin-review region;
- TP1-TP10 form a top-side `2.54 mm` pitch review row using the controlled no-paste
  `1.70 mm` target. Final side, fixture datum and probe access remain open;
- there are no mounting holes because their number and coordinates belong to
  `DIM-003` rather than electrical design authority.

## Hard interlocks

The candidate must contain zero tracks, zero vias and zero copper zones. DRC, Gerber,
drill, position, IPC-356 and STEP export are prohibited for this state. The independent
audit checks the complete reference/net/footprint set, every candidate coordinate,
the provisional outline/layer assumptions and the open `DIM-003` record.

Review B still requires frozen mechanics, stack-up and copper weight; high-current and
Kelvin routing; hot-loop and switch-node control; thermal/current-density calculation;
TVS/fuse coordination; DRC; DFM; load-step, cold-start, fault, EMI and fixture evidence.
