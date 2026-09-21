# Fabricator public-capability screen — Rev.A

Status: `CANDIDATE SCREEN PASS / JOB-SPECIFIC RESPONSES REQUIRED / NOT FOR MANUFACTURE`

Retrieval date: `2026-09-21`

This record identifies two candidates to receive the identical `FAB-A` and
`FAB-B` request packets. It does not populate an acceptance row, select a
production fabricator, freeze a final job stackup or authorize manufacture.

## FAB-A candidate — JLCPCB

Official source: <https://jlcpcb.com/impedance>

Official calculator: <https://jlcpcb.com/pcb-impedance-calculator>

Official capability table: <https://jlcpcb.com/capabilities/pcb-capabilities>

The published controlled-impedance page states headline multilayer capability
of 3.5 mil minimum track/space, 0.20 mm minimum via and 0.25 mm minimum BGA. It
publishes 4-layer and 6-layer controlled-impedance constructions, outer copper
options of 1 oz and 2 oz, inner copper options of 0.5 oz, 1 oz and 2 oz, and
multiple 1.6 mm six-layer constructions. One named published construction is
`JLC06161H-3313`.

The same page publishes four-layer `JLC04161H-3313` with 35 µm outer copper,
15.2 µm displayed inner copper, 99.4 µm 3313 prepreg on each side and a
1.265 mm core. This is the dielectric/capability reference for the separate
PCB-PWR 35 µm conservative engineering screen; it is not the selected 2 oz / 1 oz
finished job construction.

Using the official calculator with rigid board, six layers, nominal 1.6 mm,
0.5 oz inner copper, 1 oz outer copper and millimetres selected the recommended
public standard `JLC06161H-3313`, displayed at `1.54 mm ±10%`. For L1 referenced
to L2 it returned `0.1509 mm` width for 50-ohm single-ended non-coplanar routing
and `0.1537 mm` width with `0.2032 mm` gap for 90-ohm differential non-coplanar
routing. Those values are controlled separately as an engineering-candidate
numeric basis.

Candidate-screen result: `PASS TO RECEIVE RFQ AND USE PUBLIC NUMERIC BASIS FOR
ENGINEERING CANDIDATE`. The public pages do not close any project response row.
The project still requires an attributable job-specific construction, confirmed
50-ohm and 90-ohm solver geometry, production tolerances, coupon plan,
net-test/traceability terms and DFM closure before manufacture.

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
- PCB-MAIN may use the bounded JLC public RF/USB numbers for an engineering
  routing candidate only. Pair-aware routing, independent geometry audit and
  all final job-specific response gates remain mandatory.
- PCB-PWR may use the bounded `JLC04161H-3313` / 35 µm screen for an engineering
  routing candidate only. Finished-job copper/plating, via-current capacity,
  fault energy, +70 °C thermal acceptance and manufacture remain prohibited until
  the attributable response and project-review gates close.
