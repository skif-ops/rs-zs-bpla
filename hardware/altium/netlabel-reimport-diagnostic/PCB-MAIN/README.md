# PCB-MAIN — verified Strict Hierarchical reimport diagnostic, 2026-10-14

Status: **NOT FOR MANUFACTURE**. This is a separate Altium Designer 26.10.1 Trial import of the prepared KiCad copy on F:. All tracked KiCad source files and earlier Altium imports remain preserved.

The Import Wizard source was `F:\Проекты\Codex\altium-netlabel-reimport-input\PCB-MAIN`. Schematic and netlist validation was performed on the isolated reimport. PCB DRC was repeated on a clean extraction of commit `1eb454a9bea2bfcfb7a23cee828c2ff847cdfdbc` under `F:\Проекты\Codex\altium-main-drc-test-20261014\head`. This directory contains the repository copy plus verification outputs; no KiCad project was moved, overwritten or deleted.

KiCad 10.0.6 verified the prepared copy before import: PCB-MAIN retained all 355 source nets with no changed names or ref/pin memberships, and prepared schematic ERC reported zero violations. The isolated preparation adds local labels to 48 port wires; the tracked source under `hardware/kicad/native/PCB-MAIN` is unchanged.

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

The 765 routed segments use four widths: 575 at 0.1500 mm, 140 RF segments at 0.1509 mm, 46 USB differential segments at 0.1537 mm and 4 `GND_MODEM` segments at 0.3000 mm. All 304 vias are 0.50/0.30 mm. Pad shape, rotation, mask/paste expansion, keepouts, filled-copper and zone semantics, and layer-stack materials/impedance remain outside the exact comparison.

## PCB DRC and source-board state

KiCad 10.0.6 was run on the tracked source with `pcb drc --severity-all --all-track-errors --schematic-parity`. `validation/PCB-MAIN-KiCad-DRC-2026-10-14.json` records:

- 667 rule violations: 203 errors and 464 warnings;
- 499 unconnected items;
- 601 schematic-parity issues;
- rule categories: 199 `silk_over_copper`, 199 `track_width`, 199 `via_dangling`, 66 `silk_overlap`, 4 `hole_clearance`;
- parity categories: 199 `footprint_symbol_field_mismatch`, 199 `footprint_symbol_mismatch`, 199 `net_conflict`, 4 `extra_footprint`.

The first Altium PCB DRC used the imported default width and hole-size rules. It reported 1188 violations: 761 width, 421 un-routed and 6 hole-size. Clearance and short-circuit violations were both zero. The width violations came from the imported generic 0.254 mm minimum, which conflicts with every routed segment in this design. The six hole-size violations were the four 3.2 mm mounting holes `H1`–`H4` and two 3.0 mm unnumbered `J_PWR` holes against a 2.54 mm maximum. The complete initial report is `validation/PCB-MAIN-Altium-DRC-imported-rules-2026-10-14.drc`.

For classification only, the diagnostic Altium copy was changed to width minimum/preferred 0.15 mm on all six copper layers, maximum 10 mm, and a global hole-size range of 0.025–3.2 mm. The repeated DRC at 23:21:19 reported **421 violations, all Un-Routed Net**. Width, hole size, clearance, short circuit and all other enabled rule groups reported zero. The report is `validation/PCB-MAIN-Altium-DRC-normalized-rules-2026-10-14.drc`.

These normalized limits are diagnostic settings, not approved fabrication constraints. The engineering baseline explicitly defines 0.1509 mm for 50-ohm RF and 0.1537/0.2032 mm width/gap for 90-ohm differential routing, but does not approve a general 0.15 mm manufacturing minimum. The global 3.2 mm maximum is also broader than a production-scoped mechanical-hole exception. Altium warned that some imported rule definitions were incorrect when the editor closed; automatic correction was declined so the imported rules would not be changed silently.

KiCad already reports 499 unconnected items, so Altium's 421 ratsnest violations do not by themselves prove a conversion loss. A direct diagnostic comparison found 208 exact endpoint pairs shared by the 419 unique Altium pad-to-pad pairs and the 248 parseable KiCad pad-to-pad pairs. Another 251 KiCad entries involve track or via endpoints and cannot be compared as pad pairs; both tools also choose different spanning-tree edges for the same incomplete net. See `validation/PCB-MAIN-unrouted-comparison-2026-10-14.json`. Routing completion and native polygon/plane connectivity review are still required.

## Diagnostic Output Job, 2026-10-15

`EVT-PRE-20_PCB-MAIN.OutJob` was opened successfully in Altium Designer 26.10.1 Trial. It defines portable, local outputs with no absolute workstation path:

- folder output: Gerber X2, NC Drill, CSV and IPC-D-356A fabrication testpoint reports, Pick&Place, BOM, DRC report, and STEP;
- PDF output: board stack, drill drawing, assembly drawing, all schematic sheets, and PCB prints;
- fabrication testpoint report: top and bottom layers, metric units, relative origin, CSV and IPC-D-356A enabled;
- release-managed output: disabled.

This is a verified configuration only. Its outputs were not generated and no manufacturing archive was released because the blockers documented below remain open. Running it now would create diagnostic data, not an approved production package.

## Release blockers

- Complete and verify the 421 Altium unrouted connections against the 499 KiCad unconnected items.
- Resolve the 667 KiCad rule violations and 601 schematic-parity issues rather than suppressing them.
- Replace the broad diagnostic width and hole-size limits with reviewed net-class and mechanical-hole rules.
- Validate stackup materials and controlled impedance, RF return paths, differential pairs, power integrity, filled copper and keepouts.
- Complete schematic-to-PCB synchronization, BOM and Pick&Place validation, native Altium DRC/CAM review, then generate and inspect the configured outputs.

This import must not be released for fabrication or assembly.
