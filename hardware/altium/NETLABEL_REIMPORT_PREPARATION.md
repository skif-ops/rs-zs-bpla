# Hierarchical port / local label reimport preparation

The KiCad-to-Altium import separated a child-sheet Port from a same-named local Net Label when they were on different wire segments. Altium treats these identifier types as distinct until a wire connects them. On `PCB-PWR_01_INPUT_PROTECTION.SchDoc`, manually adding `I2C2_SCL` to the wire attached to the Port removed exactly two validation errors: `Duplicate Net Names Wire I2C2_SCL` and `Net I2C2_SCL has only one pin (Pin U2-5)`. The project went from 21 to 19 errors; three ERC-source-flag footprint warnings remain. This is an observed pilot, not full schematic equivalence.

`prepare_netlabel_reimport.py` creates a **new** KiCad import copy from an existing prepared KiCad copy. It adds local labels to 16 affected port wires in PCB-PWR and 48 in PCB-MAIN. The original tracked KiCad sources under `hardware/kicad/native/` are unchanged. The copy used on 2026-10-14 is `F:\Проекты\Codex\altium-netlabel-reimport-input`, derived from `F:\Проекты\Codex\altium-layer-map-test-complete`; the latter already contains the isolated PWR/MIC copper-layer-ID corrections used for the previous import.

Verification of the prepared KiCad copy with KiCad 10.0.6:

| Board | Original net count | Prepared net count | Changed net names or pin memberships | Prepared ERC violations |
| --- | ---: | ---: | ---: | ---: |
| PCB-PWR | 32 | 32 | 0 | 0 |
| PCB-MAIN | 355 | 355 | 0 | 0 |

This verifies the **KiCad copy only**. After reimport into a new Altium project, revalidate the Altium schematic, export and compare the compiled pin-to-net mapping, and rerun PCB geometry, rules, and schematic-to-PCB checks. Keep the earlier import until the new one passes those checks. Do not release manufacturing outputs from either import yet.

Recreate on a fresh destination:

```powershell
py hardware\altium\prepare_netlabel_reimport.py <prepared-kicad-input-root> <new-empty-output-root>
```

Reference: [Altium schematic connectivity](https://www.altium.com/documentation/altium-designer/schematic/creating-circuit-connectivity).
