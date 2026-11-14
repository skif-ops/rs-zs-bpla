# PCB-PWR Rev.A TI primary-source evidence

Status: `PASS PRIMARY-SOURCE BINDING / SCHEMATIC UNCHANGED / HUMAN HIERARCHY ACCEPTED / NOT FOR MANUFACTURE`

This record answers the two data-sheet questions raised during the independent
read-only review of PCB-PWR at branch commit `4c73232151bc132443c256e1a37f43ccae24c18f`.
It binds the exact TI documents to the existing native netlist. It does not alter
the schematic, authorize routing or close any physical qualification.

Machine-readable companion:
`hardware/reviews/PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.json`.

## 1. Exact LMR60440 orderable and mode selection

| TI evidence | Controlled fact |
|---|---|
| SNAS877, December 2024, PDF page 3, Section 4 Device Comparison Table | Exact orderable `LMR604403SRAKR`: 4 A, `3.3V fixed / adjustable`, spread spectrum enabled. |
| SNAS877, PDF page 13, Section 7.3.5 | Fixed mode is selected when FB-to-VOUT resistance is below `1 ohm`; adjustable mode is selected when the parallel feedback resistance exceeds `3 kohm`; typical FB reference is `1 V`. |
| SNAS877, PDF page 6, Section 6.5 | For the 3.3 V orderable with FB shorted to VOUT, TI specifies `3.24 / 3.30 / 3.35 V` min/typ/max in the stated FPWM test condition. |
| TI Package Option Addendum dated 8 November 2025, PDF page 1 | Exact `LMR604403SRAKR` is `Active`, `Production`, WQFN-HR `RAK`, 9 pins, 3000-piece large tape-and-reel, marking `4403S`, operating range `-40...+125 C`. |

Source bindings:

- TI SNAS877: `https://www.ti.com/lit/ds/symlink/lmr60440.pdf`, retrieved
  2026-09-17, 38 pages, 1,675,183 bytes, SHA-256
  `d2feebeb32432de6f7d7da1e45d0d7dcad01f0ddd14fc1a403941efb2c0387db`.
- TI Package Option Addendum:
  `https://www.ti.com/ods/sysadd/oa/symlink/lmr60440_oa.pdf`, retrieved
  2026-09-17, document date 2025-11-08, 2 pages, 16,856 bytes, SHA-256
  `9dfebc7b17b130ce20b3509dfa5992d8f86493511154632305df1160d03f40c5`.

### Existing design binding

| RefDes | Native connection | Independent calculation | Result |
|---|---|---:|---|
| `U3` | pin 6 FB is `FB_3V8`; `R1=100 kohm` from `3V8_MODEM`, `R2=35.7 kohm` to `GND_PWR` | `R1 || R2 = 26.308 kohm > 3 kohm`; `1 V x (1 + 100/35.7) = 3.801120 V` | Adjustable mode, nominal 3.8 V. |
| `U4` | pin 6 FB and the post-inductor output are the same native net `3V3_DIGITAL`, with no divider | Direct FB-to-VOUT connection selects the fixed option of this exact orderable | Fixed 3.3 V mode. |

Therefore the same exact MPN is intentionally and validly used in both
configurations. The hypothesized approximately 12.5 V modem output or
approximately 1 V digital rail does not follow from SNAS877 for this orderable.

## 2. LM74700-Q1 VCAP value

TI SNOSD17G Rev.G, PDF page 5, Section 6.3 Recommended Operating Conditions,
specifies `0.1 uF` for VCAP-to-ANODE external capacitance. Section 6.5 on PDF
page 6 also states its electrical-characteristic test conditions with
`C(VCAP)=0.1 uF`.

Source binding: `https://www.ti.com/lit/ds/symlink/lm74700-q1.pdf`, retrieved
2026-09-17, 36 pages, 2,657,068 bytes, SHA-256
`e16b3a8c0023201fafa5825436f5f2dd6f885b92b84e65602b3f50d741c58b6f`.

Existing `C1=100 nF, 25 V` is connected from `LM74700_VCAP` to
`VBAT_FUSED`, which is the LM74700 ANODE net. It matches the TI requirement; no
VCAP value ECO is required.

## 3. Local buck input network and placement boundary

SNAS877 Table 8-3 on PDF page 22 treats the local input functions separately:
`CIN_HF=0.1 uF`, rated at least 50 V and placed as close as design rules allow,
plus `CIN=4.7 uF`, rated at least 50 V and adjacent to the device.

| Channel | Local `CIN` | Local `CIN_HF` | Current provisional center distances | Status |
|---|---|---|---:|---|
| `U3` 3V8 | `C11`, 4.7 uF / 50 V | `C20`, 100 nF / 50 V | `6.00 mm` / `2.60 mm` | Placement candidate exists; routed VIN-PGND loop is not accepted. |
| `U4` 3V3 | `C12`, 4.7 uF / 50 V | `C21`, 100 nF / 50 V | `6.00 mm` / `2.60 mm` | Placement candidate exists; routed VIN-PGND loop is not accepted. |

`C13` is the central `VBAT_SYS` 100 uF hybrid damping capacitor. Its provisional
center distances are `19.70 mm` to U3 and `12.81 mm` to U4. It is explicitly not
used as a substitute for either local `CIN` or `CIN_HF` network.

The open capacitor item is therefore not the absence of nominal local bulk
capacitance. It is the effective capacitance of C11/C12 at bias and temperature,
followed by routed hot-loop review of C11/C20/U3 and C12/C21/U4.

## 4. Items deliberately still open

- no input ferrite or common-mode choke is fitted; `EVT-PWR-02/03/04` must
  produce conducted-emissions, coexistence and signed filter/no-filter evidence
  before routing;
- F1 `0451008.MRL` remains an EVT candidate pending +70 C thermal, time-current,
  protected-copper/harness I-squared-t and battery-side primary-fuse coordination;
- `PG_3V8` remains at TP5 only and R15 remains DNP by the frozen 12-pin contract;
- the PCB-MAIN C36/C44 local 100 uF networks and the <=100 milliohm / >=3.3 V
  modem-feed contract still require physical burst and hot-harness evidence;
- DIM-003, selected stackup/copper, routing, DRC, DFM and independent Review B
  remain open.

## 5. Review boundary

This evidence record makes no electrical change. The reviewed native source
remains commit `e32c0aa9e510e8321e24ebb3ee2056100c5f3a1a`; the readable A3 PDF
remains SHA-256
`7abb5e83e5d8cc72178c37fbf559bd77ca0d915b1c92f94e12ed278ce83bf130`.
Reviewer `Скиф` accepted that exact source/PDF pair on `2026-09-17` with
decision `ACCEPT_HIERARCHY_ONLY`; the signed record is
`hardware/reviews/PCB_PWR_HIERARCHY_REVIEW_REV_A.md`. Routing, procurement and
manufacturing remain prohibited.
