# PCB-PWR Rev.A stackup and copper-process request

Status: `SUPERSEDED REQUEST / EVT STACKUP AND CALCULATED GEOMETRY ACCEPTED / ROUTING INPUT AUTHORIZED / NOT FOR MANUFACTURE`

Decision `2026-09-21`: `JLC04161H-3313A`, outer/inner copper `70/35 um`,
plating floor `18 um`, and the calculated current/via table in
`PCB_PWR_CURRENT_GEOMETRY_BASIS_REV_A.csv` replace the wait for two factory
answers. Customer checkout DFM is a stop gate. Routing, DRC, CAM, thermal EVT
and Review B remain open. This historical request is retained as a capability
checklist, not as a Gerber package, purchase order or fabrication release.

Machine contract:
`hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.json`

Engineering-closure register:
`hardware/reviews/PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv`

Independent audit:
`tools/audit_pcb_pwr_stackup_copper_request_rev_a.py`

## Controlled source binding

The request originated from the unrouted four-layer PCB-PWR candidate, its exact
62-footprint electrical placement plus four board-only mounting holes, all 31
pre-route net constraints, the Rev.A layer-count authority, the power-design
baseline and the EVT-accepted `DIM-003` authority.

The 90 x 60 x 1.6 mm EVT canvas and round H1-H4 NPTH pattern are mechanically
accepted, with serial revalidation required. The active controlled successor has
four routed trace items for the accepted bootstrap, LM74700 VCAP and VBAT_RAW
subgates and zero copper zones; the remaining routing is incomplete. No party may treat the
EVT mechanical or stackup authority as a complete fabrication release.

## Accepted EVT construction

The controlled layer count is four: `F.Cu`, `In1.Cu`, `In2.Cu`, `B.Cu`. The
functional intent is power/signal, reference, power/return and power/signal.
For EVT, `JLC04161H-3313A`, 2 oz outer/1 oz inner copper, `1.6 mm ±10%`, ENIG,
green LPI and at least `18 um` average hole-wall plating are accepted. Numeric
routing values are controlled by `hardware/PCB_PWR_CURRENT_GEOMETRY_BASIS_REV_A.csv`.

The retained twelve-question lists for `FAB-A` and `FAB-B` are historical
capability/series-transfer checklists:

- complete four-layer cross-section and actual core/prepreg construction;
- laminate thermal/material properties and lot-control basis;
- finished-thickness capability and tolerance, explicitly conditional on
  the accepted EVT `DIM-003` thickness requirement;
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
-40...+70 °C ambient requirement define the calculated EVT routing minimums.
Widths, necks and via arrays are accepted as routing inputs, but are not proof of
fault energy, rail drop or powered +70 °C thermal performance.

The `PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A` overlay applies a
conservative 35 µm / 10 °C-rise screen to bounded engineering routing. Checkout
must still match the selected 2 oz / 1 oz construction and stop on any parser or
DFM mismatch.

Fabricator DFM can establish what construction can be built. It cannot approve
electrical current density, fault energy, Kelvin accuracy, converter stability
or +70 °C thermal margin. Those remain project calculations and physical EVT
gates after one construction is selected.

## Response and release rule

The response register retains 24 historical rows, twelve for each former
fabricator slot. All 24 are `CLOSED_EVT_ENGINEERING_BASELINE`, cite the central
baseline and are non-blocking. No row is represented as a factory reply.

The engineering decision authorizes numeric geometry and routing against the
selected public construction. KiCad DRC, native STEP/service review, CAM
comparison, checkout DFM, physical rail-drop/fault/+70 °C evidence, signed
Review B and manufacturing release remain separate blocking gates. Serial
mechanical revalidation remains mandatory for series transfer.
