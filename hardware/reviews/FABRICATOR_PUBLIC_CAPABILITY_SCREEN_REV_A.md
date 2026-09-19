# Fabricator public-capability screen — Rev.A

Status: `CANDIDATE SCREEN PASS / JOB-SPECIFIC RESPONSES REQUIRED / NOT FOR MANUFACTURE`

Retrieval date: `2026-09-19`

This record identifies two candidates to receive the identical `FAB-A` and
`FAB-B` request packets. It does not populate an acceptance row, select a
fabricator, freeze a stackup or authorize routing.

## FAB-A candidate — JLCPCB

Official source: <https://jlcpcb.com/impedance>

The published controlled-impedance page states headline multilayer capability
of 3.5 mil minimum track/space, 0.20 mm minimum via and 0.25 mm minimum BGA. It
publishes 4-layer and 6-layer controlled-impedance constructions, outer copper
options of 1 oz and 2 oz, inner copper options of 0.5 oz, 1 oz and 2 oz, and
multiple 1.6 mm six-layer constructions. One named published construction is
`JLC06161H-3313`.

Candidate-screen result: `PASS TO RECEIVE RFQ`. The public page is generic and
does not close any project response row. The project still requires an
attributable job-specific construction, 50-ohm and 90-ohm solver geometry,
tolerances, coupon plan, net-test/traceability terms and DFM closure.

## FAB-B candidate — PCBWay

Official sources:

- <https://www.pcbway.com/multi-layer-laminated-structure.html>
- <https://www.pcbway.com/pcb_prototype/_Stack_up_for_Prototypes.html>
- <https://www.pcbway.com/pcb_prototype/What_is_layer_stack_up.html>

PCBWay publishes default multilayer stackups and states a general range of
4–14 layers, 0.4–3.0 mm board thickness, 1–4 oz outer copper and 1–2 oz inner
copper. Its prototype guidance explicitly warns that custom and
controlled-impedance stackups may be adjusted for manufacturing capability or
material availability.

Candidate-screen result: `PASS TO RECEIVE RFQ`. The warning reinforces the
project interlock: public nominal data cannot be treated as the returned
job-specific stackup or as routing authority.

## Disposition

- Suggested issuance mapping: `FAB-A -> JLCPCB`, `FAB-B -> PCBWay`.
- Accepted response rows remain `0`.
- Selected construction remains `NONE`.
- Numeric RF/USB geometry on PCB-MAIN and numeric power copper/via geometry on
  PCB-PWR remain prohibited until the applicable returned response set and
  project review are accepted.
