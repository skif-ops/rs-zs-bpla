# PCB-MAIN Rev.A assembler DFM and stencil request

Status: `PACKET READY / SELECTED ASSEMBLER RESPONSE REQUIRED / PASTE NOT RELEASED / NOT FOR MANUFACTURE`

This packet asks a candidate contract manufacturer to review four bounded
PCB-MAIN process risks: the package-derived land/mask/stencil candidates for
`U2`, `U25` and `U26`, plus the intentionally absent process-specific paste
apertures for `U9`. It is a capability and process-review input. It is not a
purchase order, paste-layer release, whole-board DFM closure or manufacturing
authorization.

Machine contract:
`hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.json`

Blank response register:
`hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_RESPONSE_REV_A.csv`

Independent audit:
`tools/audit_pcb_main_assembler_dfm_stencil_request_rev_a.py`

## Source binding

| Item | Controlled SHA-256 |
|---|---|
| Native PCB-MAIN board | `c61d7d279d18bf72b410011ffcc9587e9ee7b61e8afa93d29a6746ec544d4137` |
| Placement manifest | `0fe702d03af4457a3d44aae93ea6ddc539040f38546d4b09f200612627890e35` |
| U2 project footprint | `78a67dda268e971a3463c41a8fb8170c3c59a1d3af145c65ed6b7212d1d8af83` |
| U25/U26 project footprint | `b82af2a8e0eb455b430115ea8d9f2c4aeae30cc71de92823573d4f2d092bc6b9` |
| U9 project footprint | `9c38091a434fb82f84dac437901e0d544c8b2be6e5aa4ee0cfced36c6aa95d87` |
| IPC-candidate authority | `c93adc8d4f00235fa571e1aae39e6ddaffd33c6d8fd751e0105035bc7ddee360` |
| Footprint-disposition record | `d979df98c7e12cd70e9b49d8fe1f9955d303cafd4fdf4088121bf1691436db97` |
| Footprint-review register | `8ddb512f9bf5dcc7df4c9be8a9099e93154d1276fb930403e8020cc030dc3b56` |

The bound native board is still unrouted and has no copper zones. No Gerber,
paste Gerber, centroid or assembly drawing from it is released by this packet.
Any footprint or board-byte change invalidates the hashes and requires a new
controlled review.

## Response identity rule

The symbolic slot `ASM-MAIN-CANDIDATE` is not a selected supplier. A valid
response must name the contract manufacturer's legal entity, manufacturing
site, responsible process engineer, quotation/reference, assembly line and
controlled process revision. A response from a sales alias without a named
site and attributable technical owner cannot close a gate.

The assembler must identify the exact paste product/alloy/type, stencil
material and thickness, aperture-cut/finish process, any step-stencil or local
support, the controlled reflow profile and the inspection/first-article plan.
Those fields are deliberately `null` in the machine contract until an external
response is reviewed.

## U2 — W25Q512JVFIQ package F

The current deterministic routing candidate has sixteen 2.05 x 0.60 mm
round-rect copper lands at 1.27 mm pitch and 9.30 mm row-center separation.
Native mask and paste are presently coextensive with copper. Winbond defines
the package outline and tolerances but does not provide a complete PCB/stencil
pattern for this package.

The selected assembler must either accept this copper geometry against the
ordered package tolerances or return a numeric ECO. It must separately state
the solder-mask expansion/dam rule and exact stencil aperture dimensions,
shape, orientation and reduction for its actual paste and stencil thickness.
Heel, toe and side allowance, paste-transfer margin, inspection criteria and
rework limits must be documented. The current coextensive paste/mask geometry
is not an approval.

## U25/U26 — TPD2EUSB30DRTR DRT0003A

Each instance has three 0.30 x 0.30 mm round-rect lands. Pads 1 and 2 are at
(-0.35, +0.425) and (+0.35, +0.425) mm; ground pad 3 is at
(0, -0.425) mm. Native mask and paste are coextensive with copper. TI MPDS340
defines the package outline but not a complete land/stencil recommendation.

The assembler must confirm that its mask registration, minimum dam, stencil
cutting, paste release, placement and inspection processes support this feature
without bridging or opens, or return a controlled numeric ECO. It must preserve
pin-1 orientation and the flow-through placement intent. `U25` remains on
`USB_DP_CONN` / `USB_DM_CONN` / `GND_DIGITAL`; `U26` remains on
`CELL_USB_DP_TP` / `CELL_USB_DM_TP` / `GND_MODEM`.

Assembler acceptance of package processing does not close USB SI and does not
close USB impedance, routing or signal-integrity review. Those remain project
Review-B gates.

## U9 — MAX-M10S-00B LCC-18

The u-blox Figure 30/Table 44 copper and mask geometry is already controlled:
18 lands on 1.10 mm pitch with 9.50 mm row-center separation, regular lands
0.80 x 1.80 mm and corner lands 1/9/10/18 at 0.70 x 1.80 mm. All U9 pads in the
native source contain `F.Cu` and `F.Mask` only. There are intentionally zero
`F.Paste` apertures because the process-specific Figure 31 adaptation has not
been approved.

The assembler must return its complete U9 stencil proposal tied to u-blox
UBX-20053088 R05 Figure 31: every aperture's coordinates, size, shape,
orientation and area reduction, plus stencil thickness, paste-transfer basis,
reflow profile and bridging/voiding inspection criteria. The proposal must
also preserve package pin-1 orientation and RF-zone cleanliness. Paste data
may be added to KiCad only through a reviewed ECO after acceptance.

## Response and first-article rule

All 14 rows in the response register begin at
`PENDING_EXTERNAL_RESPONSE`. Response value, evidence reference, responder and
date remain blank. The selected assembler must return an attributable answer
for every row and a first-article plan covering quantity, AOI/microscope or
other suitable inspection, objective acceptance criteria, rework controls and
retained records.

All DFM comments must carry an ID, severity, owner, disposition and closure
evidence. Any proposed geometry or process change is a controlled ECO; a reply
must never silently rewrite the board or footprint libraries.

## Release boundary

Even a complete accepted response closes only this bounded land/mask/stencil
process subgate. Final stackup selection, routing, USB SI, U9 RF routing, board
paste/centroid generation, KiCad 9 DRC, STEP/service review, complete
fabricator and assembler DFM, CAM comparison, signed Review B and manufacturing
release remain independent blockers.
