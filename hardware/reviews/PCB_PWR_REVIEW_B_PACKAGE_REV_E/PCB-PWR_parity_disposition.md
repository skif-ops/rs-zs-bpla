# PCB-PWR Rev E — KiCad schematic-parity disposition

Source: `PCB-PWR_parity_drc.json` from the same board and hierarchical schematic. Every diagnostic is indexed by item UUID in the accompanying CSV.

| Class | Count | Disposition |
|---|---:|---|
| Hierarchical net name prefix | 171 | Equivalent final net name; primary connectivity audit PASS |
| U5 NC pad 4 | 1 | Intentionally unconnected |
| Datasheet field | 0 | Board field blank; schematic metadata retained |
| Value field | 9 | Metadata sync against controlled BOM remains open |
| Exclude-from-BOM attribute | 8 | Five DNP resistors and NT1–NT3; schematic flag sync remains open |

There is no observed physical net mismatch. The KiCad parity command remains a diagnostic and is **not marked PASS** while the 17 Value/BOM attribute items are open. KiCad 9 reports 189 entries; KiCad 10 additionally reports 62 blank Datasheet fields. The Rev E R4 archive retains the 251-entry KiCad 10 disposition separately. This disposition does not replace the independent human Review B signature.
