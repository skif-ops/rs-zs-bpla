# PCB-MAIN STTS22H footprint ECO-004 candidate — Rev.A

Status: `PROPOSAL / MACHINE GATE REQUIRED / SIGNATURE REQUIRED / NOT A FABRICATION RELEASE`

This package isolates a U4 land-pattern correction discovered during controlled
ground-fanout work. The authoritative PCB-MAIN board remains unchanged and unrouted.
The candidate is evidence for an ECO decision, not production copper.

## Defect and manufacturer basis

U4 is `STTS22HTR` in STMicroelectronics' UDFN-6L 2 x 2 mm package. The controlled
source identifies [ST DS12606 Rev 8, Figures 10 and 11](https://www.st.com/resource/en/datasheet/stts22h.pdf)
as the land-pattern and solder-mask authority; the [ST product page](https://www.st.com/en/mems-and-sensors/stts22h.html)
confirms the package and exposes the manufacturer's CAD resources.

The current project footprint places each 0.70 mm-high signal pad row at
`y = +/-0.540 mm` around a 0.65 mm-high exposed pad. The resulting copper relation is:

`0.540 - 0.350 - 0.325 = -0.135 mm`

Thus every signal pad physically overlaps the exposed pad by `0.135 mm`. Native DRC
reports six copper-clearance and six solder-mask-bridge errors at U4. This contradicts
the already controlled `0.19 mm` lead-to-EP minimum recorded by the layout generator.
The corrected row center follows directly:

`0.325 + 0.350 + 0.190 = 0.865 mm`

The defect is classified as a project land-pattern transcription error. It is not a
supplier availability question, and no manufacturer response is required to evaluate
this bounded geometry correction.

## Proposed bounded delta

Only U4 footprint-internal geometry changes:

| Item | Existing | Candidate |
|---|---:|---:|
| Pads 1, 2, 3 row Y | `+0.540 mm` | `+0.865 mm` |
| Pads 4, 5, 6 row Y | `-0.540 mm` | `-0.865 mm` |
| F.CrtYd Y bounds | `-1.25 / +1.25 mm` | `-1.50 / +1.50 mm` |
| U4 reference-text Y | `-1.20 mm` | `-1.80 mm` |

U4 remains at `(66.00, 36.50, 0 deg)`. The exposed pad, pad sizes, shapes, layers,
nets and `0.18 mm` local clearance do not change. No other footprint, board outline,
mounting feature, net, BOM identity or placement changes. The candidate remains at
zero tracks and zero zones.

The footprint review register currently omits U4: it contains 19 pattern rows and
44 registered instances. Acceptance therefore also requires adding U4 to that
controlled register and extending the independent layout audit with exact U4 geometry.

## Verification

The deterministic materializer reconstructs the candidate from the current board
using exactly eight line replacements. The machine audit independently checks the
generated SHA-256 and reconstructs the candidate library footprint using exactly
seven line replacements. It rejects every change outside this bounded delta.

Local KiCad 7.0.11 comparative results, with the candidate bound to the same project
settings as the baseline:

| Check | Baseline | Candidate |
|---|---:|---:|
| Unconnected relationships | 718 | 718 |
| DRC violations (excluding unconnected section) | 440 | 427 |
| Clearance errors | 6 | 0 |
| Solder-mask-bridge errors | 6 | 0 |
| Strict 2D placement conflicts | 0 | 0 |

The candidate removes the exact 12 U4 errors and adds no error. KiCad 9 comparative
DRC is required in CI before the proposal is ready for a human decision.

Candidate board materializer:
`tools/materialize_pcb_main_stts22h_footprint_eco_004_rev_a.py`

Materialized board name and SHA-256:
`PCB-MAIN_STTS22H_ECO_004.kicad_pcb` /
`a50aa153d1dad2ccc9f0759213932767c9950c441a887aaf5ab2d3d9fb59a2d8`

Candidate footprint:
`hardware/kicad/candidates/PCB-MAIN-STTS22H-ECO-004/STTS22H_UDFN-6L_ECO_004.kicad_mod`

Independent audit:
`tools/audit_pcb_main_stts22h_footprint_eco_004_rev_a.py`

## Requested decision and boundary

After the machine gate is green, the independent reviewer may record one decision:

- `ACCEPT_STTS22H_FOOTPRINT_ECO_004`: apply only this bounded U4 correction to
  controlled library, generator, register, audit and unrouted board sources, then
  continue routing engineering from the corrected geometry.
- `REJECT_STTS22H_FOOTPRINT_ECO_004`: retain the current authoritative sources and
  stop routing work that depends on U4 geometry.

Acceptance does **not** approve routing copper, complete PCB-MAIN Review B, authorize
CAM generation, or release the design for fabrication or assembly.
