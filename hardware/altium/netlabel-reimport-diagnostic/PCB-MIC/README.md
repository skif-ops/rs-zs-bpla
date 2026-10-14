# PCB-MIC — Altium rule-normalization diagnostic, 2026-10-14

Status: **NOT FOR MANUFACTURE**. This directory records a separate Altium Designer 26.10.1 Trial verification copy made from the tracked `layer-corrected-import/PCB-MIC` project. The live working copy was kept at `F:\Проекты\Codex\altium-mic-diagnostic-test`. No KiCad source file was edited, moved, or deleted.

## Schematic connectivity

Altium project validation at 22:45:27 Europe/Moscow reported **Compile successful, no errors found**. `validation/PCB-MIC-Protel2.NET` is the Altium **Design → Netlist For Project → Protel2** export generated immediately after that validation. `validation/PCB-MIC-KiCad-base.xml` is a fresh KiCad 10.0.6 XML export from the tracked native schematic.

The reproducible script `../../compare_compiled_netlists.py` produced `validation/schematic-netlist-comparison.json`:

- all 17 physical component ref/pin identifiers occur in both netlists;
- all 7 physical pin-to-net partitions match exactly;
- all 7 physical net names match exactly;
- KiCad's other two nets are intentionally unconnected singleton pins `J1-7` and `J1-8`, which Altium omitted under its default single-pin netlist setting.

This establishes compiled physical pin-to-net equivalence for the imported schematic. It does not establish PCB manufacturing equivalence.

## PCB geometry

The repository verification scripts were rerun against this saved `PCB-MIC.PcbDoc`:

- 27/27 routed segments match endpoints, width, net and copper layer;
- 5/5 vias match position, diameter, drill, net and layer span;
- 6/6 component origins match;
- 53/53 pads match position, size, drill, net and named pad number within 0.00025 mm;
- 7/7 PCB net names match;
- 4/4 board-outline segments match within 0.001 mm.

See `verification.json`, `pad-verification.json`, and `outline-verification.json` for the exact results and stated scope limits. These checks do not cover every pad shape/rotation, solder-mask expansion, keepout, filled copper, mechanical drawing, or final CAM output.

## Altium PCB rules and DRC

The imported rules were normalized in this isolated copy to reflect the controlled EVT baseline instead of Altium import defaults:

- general clearance: 0.20 mm;
- signal width: minimum 0.15 mm, preferred 0.20 mm, maximum 10 mm;
- via style: minimum 0.50/0.30 mm, preferred 0.60/0.30 mm, maximum 1.27/0.711 mm (diameter/drill);
- imported assembly/fabrication testpoint usage requirements disabled because they are not requirements of the KiCad source;
- a higher-priority diagnostic rule applies 0.10 mm only when both objects are within `MK1`.

The controlled manufacturing handoff distinguishes 0.125 mm copper clearance around the MK1 local ground land from 0.10 mm hole clearance. Altium's imported clearance rule does not encode those two quantities separately. The 0.10 mm `InComponent('MK1')` rule is therefore diagnostic and must not be treated as the final release rule.

`validation/PCB-MIC-Altium-DRC-2026-10-14.drc` reports **10 violations and 0 waived violations**:

- 2 general-clearance violations from the MK1 acoustic hole to ordinary F.Cu tracks: 0.191 mm and 0.150 mm against 0.20 mm;
- 8 internal MK1 hole-to-pad points: 0.096 mm against the diagnostic 0.10 mm minimum;
- Short-Circuit Constraint: 0;
- Un-Routed Net Constraint: 0;
- Width Constraint: 0;
- Hole Size Constraint: 0;
- testpoint usage violations: 0.

The native KiCad rule file uses a broader MK1 footprint condition and currently reports zero DRC violations, while the controlled manufacturing handoff limits the exception to the manufacturer ground land around the acoustic bore. The Altium violations above are therefore retained as unresolved engineering findings rather than waived.

## Diagnostic Output Job, 2026-10-15

`EVT-PRE-20_PCB-MIC.OutJob` was opened successfully in Altium Designer 26.10.1 Trial. It defines portable, local outputs with no absolute workstation path:

- folder output: Gerber X2, NC Drill, CSV and IPC-D-356A fabrication testpoint reports, Pick&Place, BOM, DRC report, and STEP;
- PDF output: board stack, drill drawing, assembly drawing, all schematic sheets, and PCB prints;
- fabrication testpoint report: top and bottom layers, metric units, relative origin, CSV and IPC-D-356A enabled;
- release-managed output: disabled.

This is a verified configuration only. Its outputs were not generated and no manufacturing archive was released because the blockers documented below remain open. Running it now would create diagnostic data, not an approved production package.

The two ordinary-track clearances, the eight acoustic-land points, final MK1 rule implementation, remaining footprint/mask/keepout/CAM checks, and Review B must be closed before fabrication or assembly release.
