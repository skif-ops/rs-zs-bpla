# PCB-MAIN Footprint Disposition, Rev.A

Status: `OPEN / NOT FOR MANUFACTURE`

This register separates geometry already embedded from the KiCad standard
library from geometry that is still a placement-only placeholder.  A library
match is not manufacturing approval: every `KICAD_LIBRARY_PATTERN_REVIEW_PENDING`
item still requires drawing-to-land-pattern review before Review B can pass.

## Current controlled result

| Class | Instances | Disposition |
|---|---:|---|
| Project-generated chip passives and mechanical holes | 183 | Placement use only; passive geometry remains subject to assembly-house rules |
| MAIN-AUTH-011 controlled pogo groups | 5 | 31 bottom pads verified by coordinate, diameter, mask and layer |
| KiCad library patterns | 44 | Exact pad-number contract passes; drawing review remains open |
| Provisional manufacturer-specific patterns | 14 | Blocker; replace from controlled manufacturer drawing |

The controlled updates reduced the provisional set from 52 to 14 instances by
using existing KiCad patterns for U.FL, USB4105, SOT-666, SOD-523, DRT-3,
DRL-6, KEMET 7343-31, Raytac MDBT50Q, Molex 504050-0691, TI DQA USON-10
and TI DBV SOT-23-5. The five pogo
groups are generated directly from MAIN-AUTH-011 as 31 bottom-side 1.70 mm
pads with 2.10 mm mask openings and no paste. Logical aliases such as `SHIELD`
are applied without changing copper geometry. Unnumbered mounting and
paste-only pads are retained but excluded from the schematic pin-set comparison.

## Remaining provisional references

`D3`, `D5`, `FL1`, `J12`, `J13`, `J6`, `J7`, `J_PWR`, `U10`, `U4`, `U5`,
`U8`, `U9`, `X1`.

## Release rule

Review B remains `OPEN`. No Gerber, drill, paste, pick-and-place, IPC-356 or
STEP output from this candidate may be released until:

1. all 14 provisional instances are replaced by controlled land patterns;
2. the 44 KiCad-derived instances pass drawing-to-pattern review;
3. placement and routing audits pass in KiCad 9;
4. DRC reports zero blocker/critical and zero unrouted items;
5. RA-003 layout evidence is complete; physical droop and ripple measurement
   remains an EVT acceptance item and cannot be closed by CAD alone.
