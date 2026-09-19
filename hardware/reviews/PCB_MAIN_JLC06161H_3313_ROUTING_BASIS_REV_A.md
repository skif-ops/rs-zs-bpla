# PCB-MAIN JLC06161H-3313 public routing design basis — Rev.A

Status: `NUMERIC ENGINEERING ROUTING INPUT PASS / FINAL FABRICATOR ACCEPTANCE PENDING / NOT FOR MANUFACTURE`

This record converts current official JLCPCB public data into a bounded numeric
input for the PCB-MAIN engineering routing candidate. It is not a returned RFQ,
a signed job stackup, a DFM disposition, a coupon plan or a fabrication release.

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
- Final production impedance tolerance: `OPEN`.
- Job-specific stackup, material declaration, solver report and coupon plan:
  `OPEN`.
- Fabricator DFM and assembler DFM: `OPEN`.
- KiCad DRC, routed return-path review, SI review and Review B: `OPEN`.
- Manufacturing release: `false`.

The two-slot response register remains the final manufacturing acceptance path.
Public standard data allows engineering work to continue; it does not populate
or accept any `FAB-A` or `FAB-B` response row.
