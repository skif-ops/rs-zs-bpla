# PCB-MAIN Footprint Disposition, Rev.A

Status: `OPEN / NOT FOR MANUFACTURE`

This register separates geometry already embedded from the KiCad standard
library from geometry that is still a placement-only placeholder.  A library
match is not manufacturing approval: every `KICAD_LIBRARY_PATTERN_REVIEW_PENDING`
item still requires drawing-to-land-pattern review before Review B can pass.

## Current controlled result

| Class | Instances | Disposition |
|---|---:|---|
| Project-generated chip passives and mechanical holes | 188 | Placement use only; passive geometry remains subject to assembly-house rules |
| KiCad library patterns | 31 | Exact pad-number contract passes; drawing review remains open |
| Provisional manufacturer-specific patterns | 32 | Blocker; replace from controlled manufacturer drawing |

The present update reduced the provisional set from 52 to 32 instances by
using existing KiCad patterns for U.FL, USB4105, SOT-666, SOD-523, DRT-3,
DRL-6 and KEMET 7343-31. Logical aliases such as `SHIELD` are applied without
changing copper geometry. Unnumbered mounting and paste-only pads are retained
but excluded from the schematic pin-set comparison.

## Remaining provisional references

`D3`, `D5`, `FL1`, `J12`, `J13`, `J6`, `J7`, `J_MIC1`, `J_MIC2`, `J_MIC3`,
`J_MIC4`, `J_PWR`, `TP_BLE_SWD`, `TP_CELL_DBG`, `TP_CELL_USB`, `TP_EOL`,
`TP_MCU_SWD`, `U10`, `U11`, `U19`, `U20`, `U21`, `U22`, `U23`, `U24`, `U27`,
`U4`, `U5`, `U6`, `U8`, `U9`, `X1`.

## Release rule

Review B remains `OPEN`. No Gerber, drill, paste, pick-and-place, IPC-356 or
STEP output from this candidate may be released until:

1. all 32 provisional instances are replaced by controlled land patterns;
2. the 31 KiCad-derived instances pass drawing-to-pattern review;
3. placement and routing audits pass in KiCad 9;
4. DRC reports zero blocker/critical and zero unrouted items;
5. RA-003 layout evidence is complete; physical droop and ripple measurement
   remains an EVT acceptance item and cannot be closed by CAD alone.
