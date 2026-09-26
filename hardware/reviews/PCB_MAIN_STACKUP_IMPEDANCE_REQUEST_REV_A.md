# PCB-MAIN Rev.A stackup and impedance request

Status: `SUPERSEDED REQUEST / EVT PUBLIC STACKUP ACCEPTED / ROUTING INPUT AUTHORIZED / NOT FOR MANUFACTURE`

Decision `2026-09-21`: the customer-authorized EVT engineering baseline selects
`JLC06161H-3313`, 50-ohm width `0.1509 mm`, and 90-ohm width/gap
`0.1537/0.2032 mm`. No factory e-mail or signed response is required. The
questions below are retained as historical checklist content; the controlling
decision is `EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.md`. Native routing,
DRC, CAM and Review B remain open.

Historically, this packet requested the external data needed to replace provisional PCB-MAIN
manufacturing assumptions with a selected job-specific fabricator construction.
It is retained as a capability checklist, not a Gerber package, purchase order,
panel approval or fabrication release. The public `JLC06161H-3313` basis now
closes its technical rows for EVT under the project decision above.

Machine contract:
`hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.json`

Engineering-closure register:
`hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_RESPONSE_REV_A.csv`

Independent audit:
`tools/audit_pcb_main_stackup_impedance_request_rev_a.py`

## Source binding

| Item | Controlled value |
|---|---|
| Historical request-basis PCB | `hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb` |
| Historical pre-route PCB SHA-256 | `a50aa153d1dad2ccc9f0759213932767c9950c441a887aaf5ab2d3d9fb59a2d8` |
| Mechanical authority SHA-256 | `8b3dbcb5b3fffe8ce393850e4fa65b178ea79c03b584c2f8b54e6fdfd93e42f9` |
| Placement manifest SHA-256 | `df7cdbfc2ac023d43ac040b14eb99440fc392d402793d5a3b03f2fd560af6a6f` |
| Routing authority SHA-256 | `36da48a6614de40bed1b52cb53b0b6a1367fabf0e0504e8c0f4297c5b962f6f0` |

The request basis is the historical controlled 110 x 75 x 1.6 mm six-layer
pre-route candidate. The active native board is SHA-256
`30c6c93e5afbbc0888ed7c7e8693af6c6f0c7df8f5c4525e02c6d5a4c47b8739`
(PCB-MAIN inner reroute 003, accepted and applied 2026-09-25) with 1069 trace items
and ten copper zones; routing remains incomplete. 003 changes neither the stackup
nor the layer count, and none of its rerouted nets is impedance-controlled. No
vendor may treat this historical packet or the active board as released
fabrication data.

The six-layer count and selected EVT construction are controlled by
`hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv` and the central baseline. Routing,
DRC, CAM and Review B remain open.

## Requested construction

The functional layer intent is signal/RF, adjacent reference, power domains,
signal, adjacent reference and signal. This is the retained request basis. The
selected EVT public construction is controlled by the central baseline. Any
checkout-proposed alternative must return as a controlled DFM deviation and be
reviewed before selection.

The historical `FAB-A` and `FAB-B` checklist requested:

- the complete six-layer cross-section with finished-thickness tolerance, core
  and prepreg identities, glass styles or equivalent construction identifiers,
  dielectric thicknesses and resin/material system;
- laminate and solder-mask Dk/Df values with the cited test method and frequency,
  plus Tg and material/lot traceability;
- base and finished outer copper, inner copper and hole-wall plating thicknesses
  with tolerances;
- solver-backed 50-ohm single-ended geometry and 90-ohm differential geometry,
  explicitly stating route layer, reference layer, width, gap where applicable,
  copper thickness, dielectric height, solder-mask model, solver frequency and
  guaranteed production tolerance;
- impedance coupon construction, location, coupon-per-panel rule, measurement
  method and the report supplied with each lot;
- minimum copper width/spacing, solder-mask dam and registration, copper-to-edge
  rule, finished drill, annular ring, via aspect-ratio and plating capability;
- surface-finish and solder-mask proposal, panel/quotation assumptions, 100%
  net-test capability against the released IPC-356, DFM process and lot
  traceability.

The response may identify a limitation or proposed ECO. It must not silently
modify the board, substitute its standard stack without disclosure or insert
returned production geometry directly into KiCad before project review.

## Controlled-impedance scope

The 50-ohm request covers exactly seven single-ended RF segments:
`CELL_RF`, `CELL_RF_ANT`, `GNSS_RF_ANT_BIASED`, `GNSS_RF_DC_BLOCK`,
`GNSS_RF_FILTERED`, `LORA_RF_ANT` and `LORA_RF_MODULE`.

The 90-ohm request covers four isolated USB pair groups:

- `USB_MAIN_MCU_SEGMENT`: `USB_DM_U1` / `USB_DP_U1`;
- `USB_MAIN_CONNECTOR_SEGMENT`: `USB_DM_CONN` / `USB_DP_CONN`;
- `USB_CELL_MODEM_SEGMENT`: `CELL_USB_DM_U8` / `CELL_USB_DP_U8`;
- `USB_CELL_FIXTURE_SEGMENT`: `CELL_USB_DM_TP` / `CELL_USB_DP_TP`.

For EVT, the central baseline prescribes the selected width, pair gap,
dielectric height and `±10%` impedance tolerance. The bounded public basis is
controlled in `PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.json`. Series transfer
requires a fresh process/stackup review.

## Ground-domain and routing interlock

`GND_MODEM`, `GND_DIGITAL` and `GND_MIC` remain separate on PCB-MAIN. A
fabricator stackup describes construction; it never authorizes joining those
nets or routing across an unreviewed plane split. Their only controlled joins
remain on PCB-PWR through `NT1`, `NT2` and `NT3`.

The accepted EVT construction authorizes routing but not production or
fabrication. RF/SI review, native DRC, CAM and Review B still control release.
Any resulting board-rule or source change is a controlled ECO and invalidates
the current board hash.

## Response and release rule

All 22 rows in the response register are
`CLOSED_EVT_ENGINEERING_BASELINE`. They cite the public engineering baseline,
carry the project decision owner/date and are non-blocking. They are not claimed
as attributable vendor replies.

Even after stackup selection, routed copper and domain pours, KiCad 9 DRC,
impedance-coupon implementation, STEP/service review, CAM comparison, assembler
DFM, signed Review B and manufacturing release remain separate blocking gates.
