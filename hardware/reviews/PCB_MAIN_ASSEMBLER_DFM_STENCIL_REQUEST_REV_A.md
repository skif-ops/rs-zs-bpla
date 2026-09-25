# PCB-MAIN Rev.A assembler DFM and stencil request

Status: `SUPERSEDED REQUEST / EVT STANDARD PCBA PROCESS ACCEPTED / PASTE WAITS FOR DRC-CAM / NOT FOR MANUFACTURE`

Decision `2026-09-21`: the standard SAC305/Type-4, 100 um stencil, aperture,
inspection and two-unit first-article process in
`EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.md` closes the external-answer
gate. Assembler identity is selected by the customer at checkout and is not an
engineering blocker. The questions below remain a process checklist; native
DRC/CAM and Review B are still mandatory.

Historically, this packet asked a candidate contract manufacturer to review four bounded
PCB-MAIN process risks: the package-derived land/mask/stencil candidates for
`U2`, `U25` and `U26`, plus the intentionally absent process-specific paste
apertures for `U9`. It is a capability and process-review input. It is not a
purchase order, paste-layer release, whole-board DFM closure or manufacturing
authorization.

Machine contract:
`hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.json`

Engineering-closure register:
`hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_RESPONSE_REV_A.csv`

Independent audit:
`tools/audit_pcb_main_assembler_dfm_stencil_request_rev_a.py`

## Source binding

| Item | Controlled SHA-256 |
|---|---|
| Historical pre-route PCB-MAIN board | `a50aa153d1dad2ccc9f0759213932767c9950c441a887aaf5ab2d3d9fb59a2d8` |
| Placement manifest | `df7cdbfc2ac023d43ac040b14eb99440fc392d402793d5a3b03f2fd560af6a6f` |
| U2 project footprint | `78a67dda268e971a3463c41a8fb8170c3c59a1d3af145c65ed6b7212d1d8af83` |
| U25/U26 project footprint | `b82af2a8e0eb455b430115ea8d9f2c4aeae30cc71de92823573d4f2d092bc6b9` |
| U9 project footprint | `9c38091a434fb82f84dac437901e0d544c8b2be6e5aa4ee0cfced36c6aa95d87` |
| IPC-candidate authority | `c93adc8d4f00235fa571e1aae39e6ddaffd33c6d8fd751e0105035bc7ddee360` |
| Footprint-disposition record | `560aa54c81f0b44bbaac0967abeefff362b8cd1751324d516aecb36350157811` |
| Footprint-review register | `e1fa9f08d8e055c57240b0cdef11a404f367926a5bbe29909ca13994a2c2f09b` |

The bound SHA above is the historical pre-route request basis. The active native
board is SHA-256
`30c6c93e5afbbc0888ed7c7e8693af6c6f0c7df8f5c4525e02c6d5a4c47b8739`
(PCB-MAIN inner reroute 003, accepted and applied 2026-09-25) with 1069 trace items
and ten copper zones; routing remains incomplete. No Gerber, paste Gerber, centroid
or assembly drawing is released by this packet; centroid and paste come from
controlled CAM of the native board after DRC. Any footprint or board-byte change
requires a new controlled review.

Controlled review of 003 for this subgate: the `U2`, `U25`, `U26` and `U9`
footprint blocks (position, rotation, lands, mask, paste, nets) are byte-identical
in the 003 board and its predecessor
`2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273`;
003 moves only `R9`, `R10` and `R11` (0402, 22 ohm) and reroutes non-impedance-
controlled OctoSPI/SDIO/EN_MODEM runs. The accepted process baseline and the
closed response register are unaffected.

## Historical response identity rule

The symbolic slot `ASM-MAIN-CANDIDATE` is not a selected supplier. For EVT the
customer selects the assembly service at order time, so supplier identity is a
commercial record rather than an engineering stop gate. Series qualification
must restore site, line, owner and controlled-process attribution.

The standard EVT baseline fixes paste alloy/type, stencil thickness, aperture
rules, reflow envelope and the inspection/first-article plan. The selected
assembler identity and manufacturing site remain `null` until customer checkout;
that commercial selection does not reopen the accepted engineering process.

## U2 — W25Q512JVFIQ package F

The current deterministic routing candidate has sixteen 2.05 x 0.60 mm
round-rect copper lands at 1.27 mm pitch and 9.30 mm row-center separation.
Native mask and paste are presently coextensive with copper. Winbond defines
the package outline and tolerances but does not provide a complete PCB/stencil
pattern for this package.

The EVT baseline accepts this copper geometry and specifies the solder-mask and
`1.85 x 0.55 mm` stencil aperture per pad with the `100 um` Type-4 process.
Checkout DFM must not alter it silently. Heel, toe and side wetting,
paste transfer and rework limits are checked on the first two assemblies.

## U25/U26 — TPD2EUSB30DRTR DRT0003A

Each instance has three 0.30 x 0.30 mm round-rect lands. Pads 1 and 2 are at
(-0.35, +0.425) and (+0.35, +0.425) mm; ground pad 3 is at
(0, -0.425) mm. Native mask and paste are coextensive with copper. TI MPDS340
defines the package outline but not a complete land/stencil recommendation.

The EVT baseline specifies `0.27 x 0.27 mm` apertures and the standard
inspection process. Checkout DFM must support the feature without bridging or
opens, or return a controlled ECO. Pin-1 orientation and the flow-through
placement intent remain mandatory. `U25` remains on
`USB_DP_CONN` / `USB_DM_CONN` / `GND_DIGITAL`; `U26` remains on
`CELL_USB_DP_TP` / `CELL_USB_DM_TP` / `GND_MODEM`.

Process-baseline acceptance does not close USB SI and does not
close USB impedance, routing or signal-integrity review. Those remain project
Review-B gates.

## U9 — MAX-M10S-00B LCC-18

The u-blox Figure 30/Table 44 copper and mask geometry is already controlled:
18 lands on 1.10 mm pitch with 9.50 mm row-center separation, regular lands
0.80 x 1.80 mm and corner lands 1/9/10/18 at 0.70 x 1.80 mm. All U9 pads in the
native source contain `F.Cu` and `F.Mask` only. There are intentionally zero
native `F.Paste` apertures so uncontrolled 1:1 paste cannot be generated. The
accepted EVT process adds only the exact controlled land-pattern apertures
during controlled CAM after native DRC.

The controlled CAM package must implement the accepted U9 aperture map tied to
u-blox UBX-20053088 R05 Figure 31 with the central baseline stencil, paste and
reflow values. It preserves pin-1 orientation and RF-zone cleanliness. Any
checkout-generated substitution or 1:1 paste is rejected or handled by ECO.

## Response and first-article rule

All 14 rows in the response register are
`CLOSED_EVT_ENGINEERING_BASELINE`. The accepted standard process and two-unit
first-article hold define paste, stencil, reflow and inspection for EVT; no
factory e-mail is required. The remaining lot may proceed only after its
first-article evidence is accepted.

All DFM comments must carry an ID, severity, owner, disposition and closure
evidence. Any proposed geometry or process change is a controlled ECO; a reply
must never silently rewrite the board or footprint libraries.

## Release boundary

The engineering-baseline closure covers only this bounded land/mask/stencil
process subgate. Routing, USB SI, U9 RF routing, controlled board
paste/centroid generation, KiCad 9 DRC, STEP/service review, checkout DFM, CAM
comparison, two-board first-article acceptance, signed Review B and
manufacturing release remain independent blockers.
