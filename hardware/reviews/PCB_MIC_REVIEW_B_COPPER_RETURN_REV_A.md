# PCB-MIC Rev.A Review B copper-return and decoupling packet

Status: `HOLD / INDEPENDENT HUMAN DECISION REQUIRED / REVIEW B OPEN / NOT FOR MANUFACTURE`

This packet isolates the PCB-MIC copper-return and T5838 decoupling decision from
the already signed Review A. It does not change the native PCB, schematic or project
and it does not grant a Review-B signature or manufacturing release.

## Controlled source binding

| Item | Controlled value |
|---|---|
| Signed Review-A commit | `3e215e26e0d4cb160b309de3d3fd5a3145a756bf` |
| Signed native PCB SHA-256 | `aecd1a374b5f66d32a5ae056eb4ad452d68e2a2391e65f6068acc8cad37f2295` |
| Microphone | TDK InvenSense `MMICT5838-00-012` |
| Decoupling capacitor | TDK `CGA2B3X7R1E104K050BB`, 100 nF, 25 V, X7R, 0402 |
| Frozen datasheet authority | TDK `DS-000383`, Revision 1.2, 2025-09-04 |
| Frozen datasheet SHA-256 | `5befb710bfe7a415cdc1aba41ebc18b484d7f9fc320ce15a7481507531cf58a4` |
| Machine measurement | `tools/audit_pcb_mic_copper_return_rev_a.py` |
| Generated layer drawing | `artifacts/kicad-native/PCB-MIC/PCB-MIC_copper_review.pdf` |
| Generated JSON evidence | `artifacts/kicad-native/PCB-MIC/copper_return_review_audit.json` |

Each CI execution binds the generated evidence to its checked-out commit while also
proving that the native PCB bytes still equal the signed Review-A PCB.

The baseline CAM inspected for this finding is PCB Native Gate
[run #155](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34835113074),
evidence commit `7d7776e67001c0cff00643f524ceff9d0f0536af`, artifact ID
`10343758832`, artifact SHA-256
`2867ce92728a8f7c490f4856155a1ceb987b92e47165c1c8627ace57030cffd8`.

## Reproducible measurements

The independent audit parses the native KiCad S-expression with Python's standard
library. It does not use `pcbnew`, `kiutils`, either PCB generator or the existing CAM
preflight parser.

| Routed path | Trace length | Vias | Minimum width | Layer length |
|---|---:|---:|---:|---|
| J1.1 to C1.1, 1V8 feed | 15.369931 mm | 2 | 0.300 mm | F.Cu 3.984774 mm; B.Cu 11.385157 mm |
| C1.1 to MK1.7, local VDD leg | 1.658011 mm | 0 | 0.300 mm | F.Cu 1.658011 mm |
| C1.2 to MK1.2, explicit GND return | 22.248973 mm | 2 | 0.160 mm | F.Cu 3.698972 mm; B.Cu 18.550001 mm |
| J1.2 to MK1.2, connector return | 28.303419 mm | 2 | 0.160 mm | F.Cu 3.953418 mm; B.Cu 24.350001 mm |

The measured C1-to-MK1 decoupling-loop trace length is `23.906984 mm`, consisting
of the 1.658011 mm VDD leg and the 22.248973 mm explicit GND return. No project-
controlled normative maximum for this loop is frozen, so the measurement cannot
self-authorize acceptance.

## Blocking finding PCB-MIC-RB-CU-001

The signed source contains a B.Cu GND zone named
`PCB_MIC_BCU_GND_REFERENCE`, but it contains zero cached filled polygons. The
commit-bound KiCad 9.0.9 B.Cu Gerber from the baseline run contains zero
Gerber regions and only five explicit GND conductor draws. Therefore the named zone
is not part of the emitted fabrication copper; the 22.248973 mm routed path above is
the actual explicit C1-to-MK1 return represented in that CAM output.

Disposition: `HOLD`. An independent reviewer must choose one of these outcomes:

1. `ECO_REQUIRED`: return the board to layout work, create a short controlled local
   return/plane solution, rerun Review A for the changed PCB bytes, and then repeat
   Review B.
2. `ACCEPT_WITH_EVIDENCE`: record a reasoned acceptance against the generated copper
   PDF and JSON plus fabricator confirmation that the reviewed copper is exactly what
   will be manufactured.

The second outcome must not be inferred from DRC, connectivity or this document.

## Independent human review checklist

- [ ] Open both pages of `PCB-MIC_copper_review.pdf` and verify F.Cu and B.Cu against
  the signed native board hash above.
- [ ] Confirm that the C1.1-to-MK1.7 VDD leg reaches the microphone without a via or
  intervening branch.
- [ ] Review the complete C1.2-to-MK1 ground-return path, including both vias, the
  B.Cu detour and the 0.16 mm MK1.2 local connection.
- [ ] Confirm whether the absence of a materialized B.Cu GND region is intended.
- [ ] Decide `ECO_REQUIRED` or `ACCEPT_WITH_EVIDENCE`; do not leave the decision
  implicit.
- [ ] Check that any proposed copper change preserves the 0.8 mm acoustic NPTH and
  all copper, mask, paste, adhesive and coating keepouts.
- [ ] Record the reviewer, date, reviewed commit, artifact ID/digest and exact
  disposition in the parent Review-B checklist.

## Signature fields

- Reviewer: `OPEN`
- Date: `OPEN`
- Reviewed evidence commit: `OPEN`
- Workflow run and artifact: `OPEN`
- Disposition: `HOLD`
- Review B complete: `false`
- Manufacturing release: `false`
