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
| Manufacturer-drawing controlled patterns | 14 | Nexperia SOD962-2, ST UDFN-6L, ADI DCB, SiTime JE CSP, u-blox MAX-M10S, Ebyte E22-M22S, Abracon 1109-5, two TE 2336582-1 instances, Quectel BG95-M3, GCT MEM2052, Molex 504050-0291 and Molex 43045-1202 controlled locally |
| KiCad library patterns | 44 | Exact pad-number contract passes; drawing review remains open |
| Provisional manufacturer-specific patterns | 0 | Closed for the current component set; any substitution reopens this gate |

Earlier controlled updates reduced the provisional set from 52 to 4 instances by
using existing KiCad patterns for U.FL, USB4105, SOT-666, SOD-523, DRT-3,
DRL-6, KEMET 7343-31, Raytac MDBT50Q, Molex 504050-0691, TI DQA USON-10
and TI DBV SOT-23-5. The five pogo
groups are generated directly from MAIN-AUTH-011 as 31 bottom-side 1.70 mm
pads with 2.10 mm mask openings and no paste. Logical aliases such as `SHIELD`
are applied without changing copper geometry. Unnumbered mounting and
paste-only pads are retained but excluded from the schematic pin-set comparison.
The `D3` and `D5` SOD962-2 patterns are project-local and derived from Nexperia
PESD5V0C1BSF data sheet v3, Figure 14; their source files are hash-bound by the
capture manifest.
The same control now covers `U4` from ST DS12606 Rev8 Figures 10/11, `U5`
from Analog Devices/LTC drawing 05-08-1715 and `X1` from SiTime SiT1552
Rev 1.43 POD-35 Rev A. The X1 land pattern has four 0.25 mm NSMD pads on a
1.00 x 0.41 mm pitch with 0.35 mm solder-mask openings.
`U9` is controlled from u-blox UBX-20053088 R05 Figure 30 and Table 44. Its
18-pad copper and solder-mask pattern uses 1.10 mm pitch, 1.80 x 0.80 mm
regular lands and 1.80 x 0.70 mm corner lands. Paste geometry remains open
for assembly-process adaptation per Figure 31 and is not asserted as released.
`U10` is controlled from Ebyte E22-M series user manual v1.2 section 3.2:
22 bottom lands are 0.90 x 0.80 mm with 1.27 mm intra-group pitch and
5.57 mm separation between the two groups on each side. Pad 21 is the
castellated ANT connection; the module IPEX option remains prohibited by the
electrical authority for this build.
`FL1` is controlled from the Abracon ABSES5AF-L100KM data sheet revised
2025-09-16. Its five 0.30 x 0.25 mm lands retain the asymmetric A/B/C/D/E
orientation and 0.375/0.250 mm coordinate contract of the recommended pattern.
`J6` and `J7` share one project-local pattern controlled from TE customer drawing
C-2336582 Rev A2. The six SIM contacts retain the drawing's 1.27 mm pitch and
0.80 x 1.14 mm lands; card detect, two shell lands and six 1.20 mm NPTH locating
holes are represented separately. Logical pin aliases follow the signed dual-SIM
authority without altering the manufacturer geometry.

The final four manufacturer-specific patterns are now locally controlled:
`U8` follows Quectel BG95 Series Hardware Design V1.8 Figure 46; `J12`
follows GCT MEM2052 drawing Rev A3; `J13` follows Molex customer drawing
`5040500000-SD`, PSD 001 Rev B; and `J_PWR` follows Molex customer drawing
`SD-43045-001`, PSD 001 Rev H1. The controlled sources are the official
[Quectel V1.8 hardware design](https://www.quectel.com/content/uploads/2021/03/Quectel_BG95_Series_Hardware_Design_V1.8.pdf),
[GCT MEM2052 drawing](https://gct.co/files/drawings/mem2052.pdf),
[Molex 504050-0291 drawing](https://www.molex.com/pdm_docs/sd/5040500291_sd.pdf)
and [Molex 43045-1202 drawing](https://www.molex.com/pdm_docs/sd/430451202_sd.pdf).
Their complete pad coordinates, sizes, drill diameters and logical pad sets are
asserted independently by the layout audit.

## Remaining provisional references

None.

## Release rule

Review B remains `OPEN`. No Gerber, drill, paste, pick-and-place, IPC-356 or
STEP output from this candidate may be released until:

1. the zero-provisional footprint state remains true for the release commit;
2. the 44 KiCad-derived instances pass drawing-to-pattern review;
3. placement and routing audits pass in KiCad 9;
4. DRC reports zero blocker/critical and zero unrouted items;
5. RA-003 layout evidence is complete; physical droop and ripple measurement
   remains an EVT acceptance item and cannot be closed by CAD alone.
