# PCB-PWR hierarchy review response - 2026-09-17

Status: `CIN_HF ECO APPLIED / COMMIT-BOUND ERC+PDF PASS / HUMAN REVIEW PENDING / NOT FOR MANUFACTURE`

Scope: disposition of the independent read-only review of the five-sheet
PCB-PWR hierarchy. This record does not authorize routing, procurement, CAM or
manufacture.

| # | Disposition | Controlled response |
|---:|---|---|
| 1 | `CLOSED` | TI SNAS877 identifies exact orderable `LMR604403SRAKR` as `3.3-V fixed / adjustable`. FB-to-VOUT below 1 Ohm selects fixed mode; divider parallel resistance above 3 kOhm selects adjustable mode. U3 has `100 kOhm || 35.7 kOhm = 26.3 kOhm` and produces nominal 3.801 V. U4 has FB directly on 3V3 and selects fixed 3.3 V. The catastrophic 12.5 V / 1 V ambiguity is therefore not present. |
| 2 | `CLOSED` | LM74700-Q1 Rev.G recommends `0.1 uF` from VCAP to ANODE and specifies electrical characteristics with that value. Existing C1 = 100 nF is correct; no 1 uF ECO is made. |
| 3 | `OPEN - PHYSICAL QUALIFICATION` | 5 A is a conservative qualification/protection envelope, not predicted normal draw. The two full-rated buck outputs total 28.4 W, equivalent to about 2.47 A at 12.8 V/90% or 3.34 A at 10 V/85%. `0451008.MRL` remains an EVT candidate with standard and +70 C derating, protected-copper/harness I2t and primary-fuse coordination still blocking. The controlled input harness is 18 AWG / 0.75 mm2, not 20 AWG. |
| 4 | `OPEN - PRE-ROUTE DECISION` | No input ferrite/CMC is fitted. A filter is not added without source-impedance, damping and stability work because TI warns that input filters can destabilize the regulator. `EVT-PWR-02/03/04` now require conducted-emissions, RF coexistence and a signed filter/no-filter decision before routing. |
| 5 | `PARTIAL - ECO APPLIED` | C11/C12 nominal 4.7 uF / 50 V match TI's adjacent CIN value, but their exact effective capacitance at 10.0...14.6 V remains open. C20/C21, each 100 nF / 50 V X7R, are added locally at U3/U4 VIN-PGND per TI Table 8-3. C13 is treated only as central VBAT_SYS damping, not as a substitute for either local HF loop. |
| 6 | `CONTROLLED - PHYSICAL EVIDENCE OPEN` | PCB-MAIN already requires C36 and C44, each 100 uF KEMET `T520D107M006ATE015`, at the BG95 BB/RF branches. The interboard path is one 3V8 contact plus one return, both 18 AWG. The frozen contract now explicitly requires <=100 mOhm end-to-end RF path at 25 C and >=3.3 V at all four U8 VBAT pads during LTE/EGPRS bursts, including hot harness evidence. |
| 7 | `INTENTIONAL LIMITATION` | `PG_3V8` remains available at TP5 only; R15 is DNP. `PWR_GOOD` is the 3V3 AON status because 3V8 can be intentionally disabled. Firmware must infer modem-rail health from modem state and INA226 data. A direct PG_3V8 GPIO requires an interboard ECO because no connector pin is reserved. |

## Primary sources

- [TI LMR60440 datasheet SNAS877](https://www.ti.com/lit/gpn/LMR60440)
- [TI LM74700-Q1 datasheet Rev.G](https://www.ti.com/lit/ds/symlink/lm74700-q1.pdf)
- [TDK CGA6P3X7R1H475K250AB product data](https://product.tdk.com/en/search/capacitor/ceramic/mlcc/info?part_no=CGA6P3X7R1H475K250AB)
- [Littelfuse 451/453 series datasheet](https://www.littelfuse.com/assetdocs/fuse-451-and-453-datasheet?assetguid=533cd5cc-956c-4243-867f-6ab5a62f6ba1)

## Release boundary

Adding C20/C21 changes the electrical pin/net set and supersedes all earlier
PCB-PWR ERC/PDF and hierarchy decisions for the active source. For source
commit `e32c0aa9e510e8321e24ebb3ee2056100c5f3a1a`, commit-bound KiCad 9.0.9
ERC passes with zero violations across all five sheets. The five-page A3 PDF
SHA-256 is
`7abb5e83e5d8cc72178c37fbf559bd77ca0d915b1c92f94e12ed278ce83bf130`;
visual preflight passes without text/symbol/connection overlap or clipping. A
new independent `ACCEPT_HIERARCHY_ONLY` remains required. Routing and
manufacturing remain false.

The first post-ECO PDF candidate was rejected during visual preflight: net-label
text still crossed its connection wire and long child-sheet titles entered the
revision column. The deterministic hierarchy generator now bottom-justifies all
visible local/hierarchical labels and uses compact title-block titles. This is a
presentation-only remediation on top of the C20/C21 electrical ECO and still
required fresh commit-bound ERC/PDF evidence. Schematic Gate
[#35217048575](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35217048575)
now supplies that evidence; independent human review is still open.
