# PCB-MAIN Rev.A stackup and impedance request

Status: `PACKET READY / TWO FABRICATOR RESPONSES REQUIRED / ROUTING NOT AUTHORIZED / NOT FOR MANUFACTURE`

This packet requests the external data needed to replace provisional PCB-MAIN
stackup assumptions with a selected-fabricator construction. It is a capability
and quotation input, not a Gerber package, purchase order, panel approval or
fabrication release.

Machine contract:
`hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.json`

Blank response register:
`hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_RESPONSE_REV_A.csv`

Independent audit:
`tools/audit_pcb_main_stackup_impedance_request_rev_a.py`

## Source binding

| Item | Controlled value |
|---|---|
| Native PCB | `hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb` |
| Native PCB SHA-256 | `c61d7d279d18bf72b410011ffcc9587e9ee7b61e8afa93d29a6746ec544d4137` |
| Mechanical authority SHA-256 | `6a28821413fb631d299574e0a86fd87be4fa2b20606b60947700fc6e37ab3e44` |
| Placement manifest SHA-256 | `0fe702d03af4457a3d44aae93ea6ddc539040f38546d4b09f200612627890e35` |
| Routing authority SHA-256 | `f77948c4837448fbc6c3d0cfd6820354a0a8cab12925457bf90768704cb9e1dc` |

The request basis is the controlled 110 x 75 x 1.6 mm six-layer engineering
candidate. The current native board has zero tracks, zero vias and zero copper
zones. No vendor may treat this packet or the native board as fabrication data.

The six-layer count is controlled by
`hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv`; the final construction remains
open exactly as stated in this request.

## Requested construction

The functional layer intent is signal/RF, adjacent reference, power domains,
signal, adjacent reference and signal. This is only the request basis. Each
fabricator must return its actual core/prepreg construction and may propose a
controlled alternative; the project must review any alternative before it is
selected.

Both `FAB-A` and `FAB-B` must independently provide:

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
numeric geometry directly into KiCad.

## Controlled-impedance scope

The 50-ohm request covers exactly seven single-ended RF segments:
`CELL_RF`, `CELL_RF_ANT`, `GNSS_RF_ANT_BIASED`, `GNSS_RF_DC_BLOCK`,
`GNSS_RF_FILTERED`, `LORA_RF_ANT` and `LORA_RF_MODULE`.

The 90-ohm request covers four isolated USB pair groups:

- `USB_MAIN_MCU_SEGMENT`: `USB_DM_U1` / `USB_DP_U1`;
- `USB_MAIN_CONNECTOR_SEGMENT`: `USB_DM_CONN` / `USB_DP_CONN`;
- `USB_CELL_MODEM_SEGMENT`: `CELL_USB_DM_U8` / `CELL_USB_DP_U8`;
- `USB_CELL_FIXTURE_SEGMENT`: `CELL_USB_DM_TP` / `CELL_USB_DP_TP`.

The project does not prescribe width, pair gap, dielectric height, solver
frequency or impedance tolerance before the external responses are compared.
Those fields remain explicitly `null` in the machine contract.

## Ground-domain and routing interlock

`GND_MODEM`, `GND_DIGITAL` and `GND_MIC` remain separate on PCB-MAIN. A
fabricator stackup describes construction; it never authorizes joining those
nets or routing across an unreviewed plane split. Their only controlled joins
remain on PCB-PWR through `NT1`, `NT2` and `NT3`.

Receiving two completed response sets still does not automatically authorize
routing. The project must select one construction, record the comparison and
accept the RF/USB geometry through RF/SI review. Any resulting board rules or
source changes are a controlled ECO and invalidate the current board hash.

## Response and release rule

All 22 rows in the response register begin at `PENDING_EXTERNAL_RESPONSE`, with
11 questions for each of `FAB-A` and `FAB-B`. Response value, evidence reference,
responder and date remain blank until an attributable vendor reply is received.

Even after stackup selection, routed copper and domain pours, KiCad 9 DRC,
impedance-coupon implementation, STEP/service review, CAM comparison, assembler
DFM, signed Review B and manufacturing release remain separate blocking gates.
