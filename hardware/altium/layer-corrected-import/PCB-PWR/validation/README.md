# PCB-PWR Altium schematic validation, 2026-10-14

Status: **blocked for manufacturing**. This note records observations from the Altium 26.10.1 `Validate PCB Project` Messages panel at 16:21:39 Moscow time. It is not a netlist-equivalence claim.

## Reported diagnostics

- 16 `Duplicate Net Names Wire` errors: `3V3_DIGITAL` (3), `3V8_MODEM` (1), `EN_MODEM` (1), `FAULT` (1), `GND_PWR` (4), `I2C2_SCL` (1), `I2C2_SDA` (1), `PWR_GOOD` (1), `VBAT_SYS` (3).
- Five `Net ... has only one pin` errors: `3V3_DIGITAL` at `U2-6`, `EN_MODEM` at `U3-9`, `FAULT` at `U2-3`, `I2C2_SCL` at `U2-5`, `I2C2_SDA` at `U2-4`.
- Three missing-footprint warnings for `#FLG01`, `#FLG02`, `#FLG03`, all `ERC_SOURCE_FLAG`.

## Evidence from source and imported documents

The unchanged KiCad source netlist contains these connections:

| Net | KiCad source pins | Representative pins |
| --- | ---: | --- |
| `3V3_DIGITAL` | 16 | `U2-6`, `J2-3` |
| `EN_MODEM` | 3 | `U3-9`, `J2-9` |
| `FAULT` | 4 | `U2-3`, `J2-8` |
| `I2C2_SCL` | 4 | `U2-5`, `J2-11` |
| `I2C2_SDA` | 4 | `U2-4`, `J2-12` |

The imported child SchDoc files contain both Net Label objects and Port objects with these names. Inspection of their wire endpoints shows that same-named labels and ports are on separate local wire segments. Across the four child sheets, 16 name pairs appear as both Port and Net Label; none of those pairs shares a physical wire segment in the saved import. This is a candidate cause of the duplicate-net and single-pin errors, **not yet a proven complete explanation**.

The original KiCad instances of `#FLG01`, `#FLG02`, and `#FLG03` each have `(in_bom no) (on_board no)` and an empty footprint. They are schematic ERC flags, so a physical footprint must not be invented to silence Altium's warnings. Verify Altium exclusion from PCB and BOM instead.

## Repair and release gate

1. Pilot completed: a second `I2C2_SCL` Net Label was placed at Altium schematic coordinate `(165, 230)` on the Port wire; the existing `U2-5` label remains. Altium validation at 16:45:36 removed both related errors. Total errors fell from 21 to 19, with the three footprint warnings unchanged. This demonstrates the repair for one net only.
2. The reproducible KiCad import-copy preparation in `../../../NETLABEL_REIMPORT_PREPARATION.md` adds the remaining affected port-wire labels before a new import. Preserve the intended sheet hierarchy; avoid changing global net-identifier scope or disabling error reporting merely to clear messages.
3. Export a compiled Altium schematic netlist and compare the complete pin-to-net mapping against KiCad. Recheck schematic-to-PCB parity, DRC, RF/power rules, and assembly outputs before any manufacturing release.

References: [Altium connectivity](https://www.altium.com/documentation/altium-designer/schematic/creating-circuit-connectivity), [Altium validation diagnostics](https://www.altium.com/documentation/altium-designer/schematic/design-validation).
