# PCB-MAIN — verified Strict Hierarchical reimport diagnostic, 2026-10-14

Status: **NOT FOR MANUFACTURE**. This is a separate Altium Designer 26.10.1 Trial import of the prepared KiCad copy on F:. All tracked KiCad source files and earlier Altium imports remain preserved.

The Import Wizard source was `F:\Проекты\Codex\altium-netlabel-reimport-input\PCB-MAIN`; the live Altium project remains at `F:\Проекты\Codex\altium-netlabel-reimport-test\PCB-MAIN\Imported PCB-MAIN`. This directory is a repository copy of that import plus verification outputs. No live Altium project was moved or overwritten.

KiCad 10.0.6 verified the prepared copy before import: PCB-MAIN retained all 355 source nets with no changed names or ref/pin memberships, and prepared ERC reported zero violations. The isolated preparation adds local labels to 48 port wires; the tracked source under `hardware/kicad/native/PCB-MAIN` is unchanged.

## Altium schematic connectivity

The imported project uses `Strict Hierarchical (Sheet entry <-> port connections, power ports local)` (`HierarchyMode=4`). Altium validation at 19:43:27 reported **Compile successful, no errors found** with 146 warnings. Under `Hierarchical (power ports global)` the same import had 12 errors: nine duplicate-net diagnostics for `1V8_MIC`/`3V3_DIGITAL` and three multiple-output-pin diagnostics. Strict scope removed those errors.

`validation/PCB-MAIN-Protel2.NET` is the Altium **Design → Netlist For Project → Protel2** export regenerated after the Strict Hierarchical validation at 19:46:37. `validation/PCB-MAIN-KiCad-base.xml` is a fresh export from the tracked KiCad source; `validation/PCB-MAIN-KiCad-prepared.xml` is the isolated prepared-import source. The reproducible script `../../compare_compiled_netlists.py` produced the two comparison JSON files:

- All 905 physical component ref/pin identifiers occur in all compared netlists.
- All 186 physical pin-to-net partitions match exactly.
- All 186 physical net names match exactly.
- KiCad has 169 intentionally unconnected singleton pins omitted by Altium because single-pin nets are disabled.
- Neither side adds virtual physical nodes.

KiCad printed its existing annotation-error warning while exporting the tracked source netlist. The XML export completed and the exact physical comparison passed; this warning remains a source-schematic review item.

The remaining 146 Altium messages are warnings, including imported port/pin electrical-type checks, nets without a driving source, and missing schematic footprint-model links. They are not suppressed and still require per-net and per-component review. A concise validation record is in `validation/altium-validation-2026-10-14.txt`.

## PCB geometry

Independent comparisons found:

- 765/765 routed segments with matching geometry, width, layer and net;
- 304/304 vias with matching geometry and Top-to-Bottom span;
- 251/251 component origins;
- 1143/1143 pads on matching refdes, position, size, drill and net (1077 named pads also matched by pad number; 66 unnumbered pads were matched without a number check);
- 186/186 PCB net names;
- 8/8 board-outline line/arc segments within 0.001 mm.

The JSON reports document the comparison method and limits. Pad shape, rotation, mask/paste expansion, keepouts, filled-copper and zone semantics, layer-stack materials/impedance, Altium PCB DRC, schematic-to-PCB synchronization, RF/power review, BOM/Pick&Place and manufacturing outputs are not yet validated. This import must not be released for fabrication or assembly.
