# PCB-PWR hierarchy review response - 2026-09-17

Status: `TI PRIMARY EVIDENCE BOUND / CIN_HF ECO APPLIED / COMMIT-BOUND ERC+PDF PASS / HUMAN HIERARCHY ACCEPTED / NOT FOR MANUFACTURE`

Scope: disposition of the independent read-only review of the five-sheet
PCB-PWR hierarchy. This record does not authorize routing, procurement, CAM or
manufacture.

| # | Disposition | Controlled response |
|---:|---|---|
| 1 | `CLOSED - PRIMARY EVIDENCE BOUND` | TI SNAS877 PDF page 3, Section 4 identifies exact orderable `LMR604403SRAKR` as `3.3V fixed / adjustable`; TI's 2025-11-08 package-option addendum lists that exact orderable as `Active` and `Production`. SNAS877 page 13, Section 7.3.5 defines FB-to-VOUT below 1 Ohm as fixed mode and divider parallel resistance above 3 kOhm as adjustable mode. U3 has `100 kOhm || 35.7 kOhm = 26.308 kOhm` and produces nominal 3.801120 V. U4 has FB directly on 3V3 and selects fixed 3.3 V. Exact URLs, document hashes and netlist binding are controlled in `PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.{md,json}`. The catastrophic 12.5 V / 1 V ambiguity is therefore not present. |
| 2 | `CLOSED - PRIMARY EVIDENCE BOUND` | TI LM74700-Q1 SNOSD17G Rev.G PDF page 5, Section 6.3 specifies `0.1 uF` from VCAP to ANODE; page 6 uses the same value for electrical-characteristic test conditions. Existing C1 = 100 nF is correct; no 1 uF ECO is made. Exact source SHA-256 and design binding are controlled in `PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.{md,json}`. |
| 3 | `OPEN - PHYSICAL QUALIFICATION` | 5 A is a conservative qualification/protection envelope, not predicted normal draw. The two full-rated buck outputs total 28.4 W, equivalent to about 2.47 A at 12.8 V/90% or 3.34 A at 10 V/85%. `0451008.MRL` remains an EVT candidate with standard and +70 C derating, protected-copper/harness I2t and primary-fuse coordination still blocking. The controlled input harness is 18 AWG / 0.75 mm2, not 20 AWG. |
| 4 | `OPEN - PRE-ROUTE DECISION` | No input ferrite/CMC is fitted. A filter is not added without source-impedance, damping and stability work because TI warns that input filters can destabilize the regulator. `EVT-PWR-02/03/04` now require conducted-emissions, RF coexistence and a signed filter/no-filter decision before routing. |
| 5 | `PARTIAL - ECO APPLIED` | C11/C12 nominal 4.7 uF / 50 V match TI's adjacent CIN value, but their exact effective capacitance at 10.0...14.6 V remains open. C20/C21, each 100 nF / 50 V X7R, are added locally at U3/U4 VIN-PGND per TI Table 8-3. Provisional center distances are 6.00 mm for C11/C12 and 2.60 mm for C20/C21 from their ICs; this is placement evidence, not routed-loop acceptance. C13 is central VBAT_SYS damping at 19.70/12.81 mm from U3/U4 and is not a substitute for either local input network. |
| 6 | `CONTROLLED - PHYSICAL EVIDENCE OPEN` | PCB-MAIN already requires C36 and C44, each 100 uF KEMET `T520D107M006ATE015`, at the BG95 BB/RF branches. The interboard path is one 3V8 contact plus one return, both 18 AWG. The frozen contract now explicitly requires <=100 mOhm end-to-end RF path at 25 C and >=3.3 V at all four U8 VBAT pads during LTE/EGPRS bursts, including hot harness evidence. |
| 7 | `INTENTIONAL LIMITATION` | `PG_3V8` remains available at TP5 only; R15 is DNP. `PWR_GOOD` is the 3V3 AON status because 3V8 can be intentionally disabled. Firmware must infer modem-rail health from modem state and INA226 data. A direct PG_3V8 GPIO requires an interboard ECO because no connector pin is reserved. |

## Controlled primary-source record

The exact retrieved document metadata, SHA-256 values, page/section claims,
orderable status, design equations, pin/net binding and placement distances are
machine-audited in:

- `hardware/reviews/PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.md`;
- `hardware/reviews/PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.json`;
- `tools/audit_pcb_pwr_design_rev_a.py`.

## Primary sources

- [TI LMR60440 datasheet SNAS877](https://www.ti.com/lit/ds/symlink/lmr60440.pdf),
  retrieved SHA-256
  `d2feebeb32432de6f7d7da1e45d0d7dcad01f0ddd14fc1a403941efb2c0387db`.
- [TI LMR60440 package-option addendum](https://www.ti.com/ods/sysadd/oa/symlink/lmr60440_oa.pdf),
  dated 2025-11-08, retrieved SHA-256
  `9dfebc7b17b130ce20b3509dfa5992d8f86493511154632305df1160d03f40c5`.
- [TI LM74700-Q1 datasheet Rev.G](https://www.ti.com/lit/ds/symlink/lm74700-q1.pdf),
  retrieved SHA-256
  `e16b3a8c0023201fafa5825436f5f2dd6f885b92b84e65602b3f50d741c58b6f`.
- [TDK CGA6P3X7R1H475K250AB product data](https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=CGA6P3X7R1H475K250AB)
- [Littelfuse 451/453 series datasheet](https://www.littelfuse.com/assetdocs/fuse-451-and-453-datasheet?assetguid=533cd5cc-956c-4243-867f-6ab5a62f6ba1)

## Release boundary

Adding C20/C21 changes the electrical pin/net set and supersedes all earlier
PCB-PWR ERC/PDF and hierarchy decisions for the active source. For source
commit `e32c0aa9e510e8321e24ebb3ee2056100c5f3a1a`, commit-bound KiCad 9.0.9
ERC passes with zero violations across all five sheets. The five-page A3 PDF
SHA-256 is
`7abb5e83e5d8cc72178c37fbf559bd77ca0d915b1c92f94e12ed278ce83bf130`;
visual preflight passes without text/symbol/connection overlap or clipping.
Reviewer `Скиф` accepted this exact pair on `2026-09-17` with decision
`ACCEPT_HIERARCHY_ONLY`; the signed record is
`PCB_PWR_HIERARCHY_REVIEW_REV_A.md`. Routing and manufacturing remain false.

The first post-ECO PDF candidate was rejected during visual preflight: net-label
text still crossed its connection wire and long child-sheet titles entered the
revision column. The deterministic hierarchy generator now bottom-justifies all
visible local/hierarchical labels and uses compact title-block titles. This is a
presentation-only remediation on top of the C20/C21 electrical ECO and still
required fresh commit-bound ERC/PDF evidence. Schematic Gate
[#35217048575](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35217048575)
now supplies that evidence; the independent human review is accepted only for
the later active C20/C21 source/PDF pair identified above.
