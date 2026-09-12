# PCB-MAIN Footprint Disposition, Rev.A

Status: `OPEN / NOT FOR MANUFACTURE`

This register separates manufacturer-controlled geometry, drawing-verified
KiCad-library geometry and patterns still awaiting review. A library match is
not manufacturing approval: every `KICAD_LIBRARY_PATTERN_REVIEW_PENDING` item
still requires drawing-to-land-pattern review before Review B can pass. The
machine-readable 19-pattern inventory is
`hardware/reviews/PCB_MAIN_KICAD_FOOTPRINT_REVIEW_REV_A.csv`.

## Current controlled result

| Class | Instances | Disposition |
|---|---:|---|
| Project-generated chip passives and mechanical holes | 188 | Placement use only; passive geometry remains subject to assembly-house rules |
| MAIN-AUTH-011 controlled pogo groups | 5 | 31 bottom pads verified by coordinate, diameter, mask and layer |
| Manufacturer-drawing controlled patterns | 48 | Fourteen initially controlled instances plus thirty-four reviewed instances controlled locally |
| Drawing-verified KiCad library patterns | 5 | Four Molex 504050-0691 instances and one GCT USB4105 instance have exact audited geometry |
| KiCad library patterns pending drawing review | 5 | Exact pad-number contract passes; drawing review remains open |
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

The first KiCad-library review tranche covers eight connector instances. The
four `J_MIC1..J_MIC4` Molex 504050-0691 patterns match customer drawing
`5040500000-SD`, PSD 000 Rev B: six 0.60 x 1.00 mm contacts on 1.50 mm pitch,
two 1.25 x 1.80 mm shell lands and 100% stencil apertures. `J11` matches GCT
USB4105 Rev B4 for all sixteen contact lands, two 0.65 mm NPTH locating holes
and four plated oval shell stakes. GCT does not define stencil apertures in that
drawing, so paste remains an assembly-process/DFM gate even though copper and
drill geometry are drawing-verified.

The three `J8..J10` Hirose U.FL patterns exposed a real library discrepancy:
KiCad's copper agrees with the recommended mounting pattern, but its paste
copies the copper while Hirose specifies smaller metal-mask apertures. They are
therefore replaced by the project-local `Hirose_U.FL-R-SMT-1` pattern. It keeps
the 1.05 x 1.00 mm signal land and two 2.20 x 1.05 mm ground lands, while using
separate 0.85 x 0.80 mm signal and 2.00 x 0.90 mm ground paste apertures from
the official [Hirose U.FL catalog](https://www.hirose.com/en/product/document?clcode=&productname=&series=U.FL&documenttype=Catalog&lang=en&documentid=ed_U.FL_CAT),
dated 2026-08-01. The other reviewed sources are the official
[Molex 504050-0691 drawing](https://www.molex.com/pdm_docs/sd/5040500691_sd.pdf)
and [GCT USB4105 drawing](https://gct.co/files/drawings/usb4105.pdf).

The second KiCad-library review tranche closes `U3` and `U11` as project-local
manufacturer-controlled patterns. For `U3`, the KiCad copper already matches
the `LIS2DW12` LGA-12L package and ST's land rule: 0.275 x 0.250 mm package
pads become 0.375 x 0.350 mm PCB lands at 0.5 mm pitch. The library footprint
did not implement TN0018's larger solder-mask opening or its 70-90% stencil-area
rule. The local pattern therefore uses a 0.05 mm mask expansion and -10% paste
ratio per dimension, yielding 81% paste area. Sources are
[DS11811 Rev 9](https://www.st.com/resource/en/datasheet/lis2dw12.pdf), SHA-256
`5208623aa91c63a33be0e930518c20f5210c4eb76932350f35369687ae1d0dd5`, and
[TN0018 Rev 8](https://www.st.com/resource/en/technical_note/tn0018-surface-mounting-guidelines-for-mems-sensors-in-an-lga-package-stmicroelectronics.pdf),
SHA-256 `4dc419fabe93f7f0b1ee5730967ed74573aa0dc91188cf88749ce10d5ab4a34e`.

For `U11`, all 61 KiCad copper/paste/mask lands match Raytac's 230606 Eagle
library and solder-pad drawing. The embedded library rule area, however, began
at board X=106.25 mm, 0.05 mm inside the frozen X=106.20 mm antenna boundary.
The local `Raytac_MDBT50Q-P1MV2` pattern corrects the all-layer no-copper/no-via/
no-pad/no-component region to exactly 3.80 x 10.50 mm through the east board
edge, while retaining the 1.60 x 1.20 mm F.Cu feed keepout. The official
[Footprint Design Guide 230606](https://www.raytac.com/document/act.php?act=1&index_id=30)
archive is SHA-256
`7ff6f11d0185a9db73c7140a4fe7e70b31615539916e60d5c27af8178f9f9fc2`.

The third KiCad-library review tranche closes `U1`. ST DS13086 Rev 10 identifies
the selected `STM32U585VIT6Q` package as LQFP100 code `1L` and Figure 96 gives
the footprint example directly: 100 rectangular 1.20 x 0.30 mm lands at
0.50 mm pitch, with 16.70 mm outer, 14.30 mm inner and 12.30 mm row spans.
The KiCad IPC footprint instead used 1.60 x 0.30 mm round-rect lands at
7.675 mm centers, so it was not marked drawing-verified. The project-local
`ST_STM32U585_LQFP100_1L` pattern uses the exact ST copper geometry at
7.750 mm centers; mask and stencil adaptation remain an assembly-process/DFM
control. The official [DS13086 Rev 10](https://www.st.com/resource/en/datasheet/stm32u585ai.pdf)
document is SHA-256
`6483871075d4889d39356648a9c1f1fb34f48dce2ce3e8c5a8d73a73f7e935e3`.

The fourth KiCad-library review tranche closes `U7`, `U13`, `U16`, and `U17`
with project-local TI `PW` patterns. The review exposed a functional package
error in the prior placement candidate: all three 24-pin devices used KiCad
`TSSOP-24_4.4x6.5mm_P0.5mm`, but the selected TI `PWR` orderables use
`PW0024A` with 0.65 mm pitch and a 7.7-7.9 mm body. TI drawing 4220208/A
defines 24 lands of 1.50 x 0.45 mm, R0.05 corners, 0.65 mm pitch and 5.80 mm
row-center spacing. `U17` already had the right 0.65 mm pitch, but its KiCad
lands were 1.475 x 0.40 mm at 5.725 mm row spacing rather than the PW0014A
4220202/B example. The two local footprints implement the exact TI copper,
equal-size stencil apertures and preferred 0.05 mm NSMD expansion. Sources are
[SN74AXC8T245 SCES875C](https://www.ti.com/lit/ds/symlink/sn74axc8t245.pdf),
SHA-256 `6cf4003c438c0546fb86f0932613896197dd19a75bdb307f385eb6e75535126e`,
[TS3A27518E SCDS260F](https://www.ti.com/lit/ds/symlink/ts3a27518e.pdf),
SHA-256 `d87c216911176dca84cc9cee5efb6f45b18021977f94a97c7fae989484a73392`,
and [SN74LVC32A SCAS286U](https://www.ti.com/lit/ds/symlink/sn74lvc32a.pdf),
SHA-256 `807f6fff7977736035c2a3144d530be7ad737a163b2f0fd11002a45953b47230`.

The fifth KiCad-library review tranche closes `U18` and `U19..U24/U27` with
project-local TI `DRL0006A` and `DQA0010A` patterns. `U18` already had the
correct 0.67 x 0.30 mm copper at 0.50 mm pitch and 1.48 mm row spacing, but the
local pattern additionally fixes R0.05 corners and the preferred 0.05 mm NSMD
opening from TI drawing 4223266/F. The seven DQA instances required a copper
correction: the KiCad pattern used 0.77 mm row spacing and uniform 0.55 x
0.30 mm lands, while TI 4220328/A requires 0.835 mm row spacing, 0.565 x
0.20 mm signal lands, and 0.565 x 0.40 mm GND lands 3/8. The local DQA
pattern also implements the preferred 0.07 mm NSMD opening and separate
0.565 x 0.36 mm stencil apertures on GND lands. Sources are the official
[DRL0006A drawing](https://www.ti.com/lit/pdf/MPDS159I), SHA-256
`588597e633a3f02cd4546fd98f6872ef98a6578e1285db325eda3bbb16a516ee`,
and [TPD4E05U06 data sheet](https://www.ti.com/lit/ds/symlink/tpd4e05u06.pdf),
SHA-256 `c167cf1e72a5473a4d2c59b6a3c0251498701da05b7785919b9ceaae3b3e02c6`.

The sixth tranche closes the seven `TPD1E05U06DYAR` instances `D4` and
`D6..D11` with project-local TI `DYA0002A` geometry. The KiCad SOD-523
pattern used 0.60 x 0.70 mm lands at 1.40 mm center spacing. TI drawing
4224978/B instead defines two 0.67 x 0.40 mm R0.05 lands at 1.48 mm center
spacing, equal-size stencil apertures and a preferred 0.05 mm NSMD opening.
The official [TPDxE05U06 Rev.O data sheet](https://www.ti.com/lit/ds/symlink/tpd1e05u06.pdf)
is SHA-256
`c167cf1e72a5473a4d2c59b6a3c0251498701da05b7785919b9ceaae3b3e02c6`.

The seventh tranche closes `D1/D2` from the Nexperia `PESD5V0S1UL` v5
Figure 11 reflow footprint. The KiCad pattern already had the correct 0.40 x
0.70 mm copper, separate 0.30 x 0.60 mm paste apertures and 0.70 mm center
spacing, but used R0.025 corners and relied on the board-global mask setting.
The project-local pattern implements the specified R0.05 corners and explicit
0.50 x 0.80 mm solder-resist openings while retaining copper and paste sizes.
The official [PESD5V0S1UL v5 data sheet](https://assets.nexperia.com/documents/data-sheet/PESD5V0S1UL.pdf)
is SHA-256
`8ddea76afa74f87de5d3662e4d9149bf7397761fa99dc29b44bfbe42872d447e`.

The eighth tranche closes `Q1/Q2/Q3` from the Nexperia `MMBT3904` v5
Figure 8 reflow footprint. The prior KiCad IPC pattern used 1.475 x 0.60 mm
round-rect lands at 1.875/1.90 mm center spacing. The project-local pattern
uses the manufacturer's rectangular 0.60 x 0.70 mm copper lands, 0.50 x
0.60 mm stencil apertures and 0.75 x 0.85 mm solder-resist openings at
1.90 mm lead pitch and 2.00 mm row spacing. It is rotated into the established
board orientation without changing pin 1 base, pin 2 emitter or pin 3
collector. The official [MMBT3904 v5 data sheet](https://assets.nexperia.com/documents/data-sheet/MMBT3904.pdf)
is SHA-256
`ade27b408c77a94ea4448c8473a9e80096dd60da3e1914e004c52344e9cd8d00`.

The ninth tranche closes `U6` from the TI `SN74LVC1G07` Rev AG package
drawing DBV0005A `4214839/K`. The prior KiCad IPC pattern used 1.325 x
0.60 mm lands at 2.275 mm row-center separation. The project-local pattern
uses the manufacturer's 1.10 x 0.60 mm R0.05 lands and equal stencil
apertures at 0.95 mm lead pitch and 2.60 mm row spacing, with the preferred
NSMD opening expanded 0.07 mm per side. Pin numbering and the established
board orientation are unchanged. The official
[SN74LVC1G07 Rev AG data sheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g07.pdf)
is SHA-256
`0c2f8b64141be3a64001a589f966901a55e5724e8bca963f8361939694f2b8e7`.

The tenth tranche closes `U14/U15` from the ST `ESDALC6V1-5P6` Rev 3
Figure 14 SOT666 footprint. Rotated into the established board orientation,
the manufacturer's six rectangular 0.30 x 0.99 mm lands become 0.99 x
0.30 mm at 0.50 mm lead pitch and 1.61 mm row-center separation. The prior
KiCad IPC pattern used mixed 0.50/0.65 mm land lengths, 0.30/0.375 mm
widths and 1.70/1.85 mm row spacing. Pin numbering is retained. ST does not
specify solder-mask or stencil geometry in Figure 14, so those remain explicit
assembly-process/DFM controls. The official
[ESDALC6V1-5P6 Rev 3 data sheet](https://www.st.com/resource/en/datasheet/esdalc6v1-5p6.pdf)
is SHA-256
`ea14ac3604fa4887d91b9fbc55ab9d04a23ba6597b22a817e64185d519fb9e28`.

The eleventh tranche closes `Q4` from Vishay `Si1016X` Rev E and the embedded
Application Note 826 recommended minimum pads for the six-lead SC-89 package.
Rotated into the established board orientation, the six rectangular 0.300 x
0.478 mm pads become 0.478 x 0.300 mm at 0.500 mm lead pitch and 1.276 mm
row-center separation. The prior KiCad IPC pattern used 0.70 x 0.34 mm
round-rect lands and 1.50 mm row spacing. Pin numbering is retained. Vishay
does not specify solder-mask or stencil geometry in the pad guideline, so those
remain explicit assembly-process/DFM controls. The official
[Si1016X Rev E data sheet and Application Note 826](https://www.vishay.com/docs/71168/si1016x.pdf)
is SHA-256
`5e561d2786874eb79c8c6e36e4eb4d9b0de774384005e72c4998ab3dcc2cf518`.

`U2` was also reviewed but remains pending. Winbond W25Q512JV Rev B confirms
the selected package `F`, its 1.27 mm pitch and full package tolerances, but
does not publish a PCB land pattern for the 16-pin SOIC. The existing KiCad
2.05 x 0.60 mm lands therefore cannot be promoted from a package-outline-only
comparison; independent IPC/assembly-process control is still required.

`U25` and `U26` were reviewed against TI DRT0003A `MPDS340`. That document
defines the package outline and lead tolerances but does not publish a PCB land
pattern or stencil recommendation. The existing KiCad `Texas_DRT-3` geometry
therefore remains pending independent IPC/assembly-process control.

## Remaining provisional references

None.

## Release rule

Review B remains `OPEN`. No Gerber, drill, paste, pick-and-place, IPC-356 or
STEP output from this candidate may be released until:

1. the zero-provisional footprint state remains true for the release commit;
2. the remaining 5 KiCad-derived instances pass drawing-to-pattern review;
3. placement and routing audits pass in KiCad 9;
4. DRC reports zero blocker/critical and zero unrouted items;
5. RA-003 layout evidence is complete; physical droop and ripple measurement
   remains an EVT acceptance item and cannot be closed by CAD alone.
