# PCB-MAIN JLC06161H-3313 public routing design basis — Rev.A

Status: `EVT JOB STACKUP ACCEPTED / NUMERIC ROUTING INPUT PASS / DRC-CAM-REVIEW B OPEN / NOT FOR MANUFACTURE`

This record converts current official JLCPCB public data into the selected
numeric stackup and routing input for the PCB-MAIN EVT candidate. A factory
e-mail or signed job stackup is not required for this customer-ordered test lot.
It is not Gerber, CAM approval or a fabrication release.

Machine authority:
`hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.json`

Independent audit:
`tools/audit_pcb_main_jlc06161h_3313_routing_basis_rev_a.py`

## Official source and observed inputs

Retrieved on `2026-09-19` from:

- <https://jlcpcb.com/impedance>
- <https://jlcpcb.com/pcb-impedance-calculator>

The official calculator was set to rigid, six copper layers, nominal 1.6 mm
board thickness, 0.5 oz inner copper, 1 oz outer copper and millimetres. Its
recommended public standard was `JLC06161H-3313`, displayed as standard with
finished thickness `1.54 mm ±10%`.

The displayed construction is symmetrical:

| Layer/material | Thickness, mm |
|---|---:|
| L1 copper | 0.0350 |
| 3313 RC57% prepreg | 0.0994 |
| L2 copper | 0.0152 |
| core without copper | 0.5500 |
| L3 copper | 0.0152 |
| 2116 RC54% prepreg | 0.1088 |
| L4 copper | 0.0152 |
| core without copper | 0.5500 |
| L5 copper | 0.0152 |
| 3313 RC57% prepreg | 0.0994 |
| L6 copper | 0.0350 |

## Numeric engineering geometry

Both structures use outer L1 referenced to adjacent L2:

| Controlled structure | Target | Width | Gap |
|---|---:|---:|---:|
| RF single-ended, non-coplanar | 50 ohm | 0.1509 mm | N/A |
| USB differential, non-coplanar | 90 ohm | 0.1537 mm | 0.2032 mm |

These values replace prior provisional or guessed widths only for an engineering
candidate against this named public construction. The pair gap must be enforced
by a differential-pair-aware route and independently audited; a generic
single-net autorouter result cannot claim USB geometry PASS.

## Acceptance boundary

- Numeric RF/USB input for the engineering routing candidate: `PASS`.
- Published construction selected as the EVT job stackup: `PASS`.
- Production impedance tolerance: `±10%`, accepted for EVT.
- Standard controlled-impedance coupon/TDR report: accepted when offered by
  checkout; absence of a bespoke coupon plan is not an EVT blocker.
- Customer checkout/file-parser DFM: mandatory stop gate.
- KiCad DRC, routed return-path review, SI review and Review B: `OPEN`.
- Manufacturing release: `false`.

The former two-slot response register is retained as decision history. Its 22
rows are closed by the customer-authorized engineering baseline, not represented
as factory replies. Supplier selection at checkout is non-blocking; any portal
DFM error or mismatch against this construction stops the order.
