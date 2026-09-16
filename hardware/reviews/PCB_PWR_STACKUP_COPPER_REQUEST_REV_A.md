# PCB-PWR Rev.A stackup and copper-process request

Status: `PACKET READY / TWO FABRICATOR RESPONSES REQUIRED / 0 OF 24 ROWS ACCEPTED / ROUTING NOT AUTHORIZED / NOT FOR MANUFACTURE`

This packet requests the external construction and process data required before
PCB-PWR current-carrying geometry can be calculated. It is a capability and
quotation input only. It is not a released outline, Gerber package, purchase
order, panel approval, routing authorization or fabrication release.

Machine contract:
`hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.json`

Blank response register:
`hardware/reviews/PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv`

Independent audit:
`tools/audit_pcb_pwr_stackup_copper_request_rev_a.py`

## Controlled source binding

The request is bound to the unrouted four-layer PCB-PWR candidate, its exact
60-footprint placement, all 31 pre-route net constraints, the Rev.A layer-count
authority, the power-design baseline and the still-open `DIM-003` request.

The present 90 x 60 x 1.6 mm canvas is provisional. It has no mounting holes,
tracks, vias or copper zones. Neither fabricator may treat those provisional
dimensions as fabrication authority. Any quotation using them must identify the
basis as provisional and must be refreshed after `DIM-003` acceptance.

## Request basis, not accepted construction

The controlled layer count is four: `F.Cu`, `In1.Cu`, `In2.Cu`, `B.Cu`. The
functional request intent is power/signal, reference, power/return and
power/signal. Outer 2 oz and inner 1 oz are targets only. Core/prepreg identity,
finished thickness, base and finished copper, hole-wall plating, material,
surface finish and numeric manufacturing rules remain unaccepted.

Both `FAB-A` and `FAB-B` must independently return all twelve requested items:

- complete four-layer cross-section and actual core/prepreg construction;
- laminate thermal/material properties and lot-control basis;
- finished-thickness capability and tolerance, explicitly conditional on
  `DIM-003`;
- base and finished copper plus hole-wall plating values and tolerances;
- thick-copper etch allowance and achievable final feature tolerance;
- preferred standard through-via construction and plating limits;
- thermal-via tent/fill/cap process capability and restrictions;
- minimum copper, registration, hole-position and copper-to-edge rules;
- solder-mask and surface-finish construction;
- copper-balance, panel, depanel and warpage assumptions;
- 100% net test, lot traceability and microsection/coupon evidence;
- a controlled DFM register with every exception attributable and closed.

A vendor may propose an alternative construction, but it may not silently
substitute a standard stack or modify the board. Every alternative becomes a
controlled project review input.

## Electrical and thermal boundary

The 5 A expected system basis, two 4 A buck ratings, 3.3 A modem peak basis and
-40...+70 °C ambient requirement are sizing inputs, not proof of acceptable
copper. The input fault/transient envelope, voltage-drop budget and allowable
conductor temperature rise remain open. Consequently this request contains no
accepted trace width, plane neck, via diameter, via count or thermal-via array.

Fabricator DFM can establish what construction can be built. It cannot approve
electrical current density, fault energy, Kelvin accuracy, converter stability
or +70 °C thermal margin. Those remain project calculations and physical EVT
gates after one construction is selected.

## Response and release rule

The response register contains 24 blocking rows: twelve for each independent
fabricator. All begin at `PENDING_EXTERNAL_RESPONSE`; response value, evidence,
responder and date are blank. The current state is `0/2` accepted fabricator
sets, `0/24` accepted rows and no selected construction.

Receiving both responses does not by itself authorize numeric geometry or
routing. The project must compare the offers, select and accept one
construction, close `DIM-003`, freeze current/fault envelopes, and approve
current-density, DC-drop, via-array, fault-energy and +70 °C thermal analyses.
Routing, KiCad DRC, native STEP/service review, CAM comparison, assembler DFM,
physical power evidence, signed Review B and manufacturing release remain
separate blocking gates.
