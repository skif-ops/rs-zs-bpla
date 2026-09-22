# PCB-PWR JLC04161H-3313 conservative EVT routing basis — Rev.A

Status: `EVT ENGINEERING STACKUP AND NUMERIC ROUTING INPUT PASS / JOB DFM, FAULT AND THERMAL ACCEPTANCE PENDING / NOT FOR MANUFACTURE`

This record converts a public four-layer manufacturing reference and a deliberately
conservative 35 µm copper screen into bounded numeric input for a PCB-PWR EVT
engineering routing candidate. Under the project-owner decision to use a
standard process and calculated values for EVT, it also selects the ordering
profile below. It is not a DFM disposition, current-capacity certification,
physical thermal result or fabrication release.

Machine contract:
`hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json`

Per-net rule manifest:
`hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv`

Independent audit:
`tools/audit_pcb_pwr_jlc04161h_3313_evt_routing_basis_rev_a.py`

## Public reference and job boundary

Retrieved on `2026-09-21` from the official JLCPCB impedance/stackup and PCB
capabilities pages. The public four-layer `JLC04161H-3313` reference uses
35 µm outer copper, 15.2 µm displayed inner copper, 99.4 µm 3313 prepreg on
each side and a 1.265 mm core. JLCPCB publicly lists 1 oz and 2 oz outer options
and 0.5 oz, 1 oz and 2 oz inner options for four-layer construction.

The EVT ordering profile is `JLC04161H-3313`, 1.6 mm, outer 2 oz / inner 1 oz.
The routing calculation deliberately retains 35 µm as its lower-bound copper
screen, so it does not rely on the heavier order target for width compliance.
The 24-row response register is closed `24/24` by the project-owner-authorized
EVT engineering baseline. No factory e-mail or signed reply is required. The
customer-order checkout DFM channel remains available for job-specific parser
or process deviations, but it is not a prerequisite for engineering routing.

## Conservative conductor screen

The engineering screen deliberately uses only 35 µm finished copper even though
the job target is heavier. It applies the legacy external-conductor empirical
equation `I = 0.048 × ΔT^0.44 × A^0.725` at a 10 °C rise. This is a comparative
sizing screen, not an IPC qualification claim and not a substitute for the
selected-fabricator field solver, fault-energy analysis or physical +70 °C test.

| Current basis | Calculated minimum at 35 µm | Selected candidate width |
|---:|---:|---:|
| 5.0 A input and primary return | 2.765521 mm | 4.0 mm |
| 4.0 A buck rail/return | 2.032863 mm | 3.0 mm |
| 4.0 A local switch node | 2.032863 mm | 2.1 mm, shortest practical F.Cu area |
| 3.3 A modem peak cross-check | 1.559093 mm | covered by 3.0 mm rail rule |
| 0.3 A microphone rail/return | 0.057078 mm | 0.5 mm |

At 70 °C, using copper resistivity `2.062766e-8 ohm·m`, the one-way candidate
length ceilings are 67.870035 mm for 5 A / 4.0 mm / 50 mV, 63.628158 mm for
4 A / 3.0 mm / 50 mV, and 56.558362 mm for 0.3 A / 0.5 mm / 20 mV. These are
route-level budget checks; connector, harness, shunt, fuse, FET, inductor and
return-path drops remain separate.

## Candidate classes

| Numeric class | Width | Clearance | Nets / rule |
|---|---:|---:|---|
| `PWR_INPUT_5A` | 4.0 mm | 0.30 mm | `VBAT_RAW` through `VBAT_SYS`; same-layer continuous outer copper preferred |
| `PWR_RETURN_5A` | 4.0 mm | 0.30 mm | `GND_PWR`; continuous plane plus outer copper |
| `PWR_RAIL_4A` | 3.0 mm | 0.30 mm | 3V8/3V3 rails and paired modem/digital returns |
| `PWR_RAIL_0P3A` | 0.5 mm | 0.25 mm | 1V8 rail and microphone return |
| `PWR_SWITCH_4A` | 2.1 mm | 0.40 mm | local F.Cu, minimum area, zero-via target |
| `PWR_LOCAL` | 0.5 mm | 0.25 mm | bootstrap, timing, gate and mode networks |
| `PWR_SENSE` | 0.25 mm | 0.30 mm | Kelvin pair and feedback; quiet corridor, zero-via target |
| `CONTROL` | 0.25 mm | 0.20 mm | enable, status and 100 kHz I²C |

If a high-current layer transition cannot be avoided, the engineering candidate
uses provisional arrays of 12 vias at 5 A, 10 vias at 4 A or 2 vias at 0.3 A,
with 0.6/0.3 mm diameter/drill. The resistance check assumes 20 µm hole-wall
plating solely for screening. Plating is not accepted, current sharing is not
proven and the final via arrays remain blocked on the returned job construction,
thermal review and DFM.

## Acceptance boundary

- Numeric input for a bounded EVT engineering routing candidate: `PASS`.
- Public reference selected as the EVT ordering profile: `true`.
- Outer 2 oz / inner 1 oz selected as the EVT ordering profile: `true`.
- Routing design copper lower bound: `35 µm`.
- Two-fabricator responses required before routing: `false`.
- EVT engineering-baseline closures: `24/24`; external fabricator replies required: `false`.
- Fault-energy and +70 °C physical thermal acceptance: `OPEN`.
- Routed copper, KiCad DRC, CAM, DFM and independent Review B: `OPEN`.
- Manufacturing release: `false`.

The response register is populated by the controlled EVT engineering baseline,
not by a claimed factory reply. This record permits the next engineering-candidate
step. At customer order checkout, any actual parser or DFM error must still be
resolved; this record cannot authorize fabrication by itself.
