# PCB-PWR — corrected-netlabel reimport diagnostic, 2026-10-14

Status: NOT FOR MANUFACTURE. This is a separate Altium Designer 26.10.1.5 Trial import of the prepared KiCad copy on F:. All tracked KiCad source files and earlier Altium imports are preserved.

The Import Wizard placed the live project in `F:\Проекты\Codex\altium-netlabel-reimport-input\PCB-PWR\Imported PCB-PWR` despite the requested output directory `F:\Проекты\Codex\altium-netlabel-reimport-test`. This directory is a copy of that import plus verification outputs; no live Altium project was moved or overwritten.

KiCad 10.0.6 verified the prepared copy before import: PCB-PWR 32/32 source-to-prepared nets had identical names and ref/pin memberships, ERC had zero violations, and the PCB source file checksum was unchanged. The correction adds local net labels to Port wires only in the isolated import copy.

## Altium schematic connectivity

`validation/PCB-PWR-Protel2.NET` is the Altium **Design → Netlist For Project → Protel2** export generated from this import. `validation/PCB-PWR-KiCad-base.xml` is the baseline KiCad netlist. The reproducible comparison script `../../compare_compiled_netlists.py` produced `validation/schematic-netlist-comparison.json`:

- All 160 physical component ref/pin identifiers occur in both netlists.
- All 31 physical pin-to-net partitions and all 31 net names match exactly.
- KiCad's 32nd net is the intentionally unconnected single pin `U5-4`, which Altium omitted under its default single-pin netlist setting.
- Altium additionally lists the three virtual ERC source flags `#FLG01`, `#FLG02`, `#FLG03` on `VBAT_SYS`, `GND_PWR`, `3V3_DIGITAL`. In the original KiCad source they are marked off-board and out-of-BOM, without footprints. They are excluded from the physical comparison and must remain absent from PCB/BOM.

The first Altium validation at 17:12:52 reported 7 errors, 33 warnings and one cross-reference notice. Its `Net Identifier Scope` was `Automatic (Based on project contents)`. In a separate F: working copy, the only electrical-connectivity setting changed to `Hierarchical (Sheet entry <-> port connections, power ports global)` (`HierarchyMode=2`). The repeat validation at 17:36:44 reported **Compile successful, no errors found** with 28 warnings. The earlier four duplicate-net errors, three open-collector/power-pin errors, and four multiple-net-name warnings disappeared. This isolates the imported project's automatic scope selection as the cause of those compiler errors; it does not establish PCB release readiness.

The Protel2 netlist was regenerated after that setting change at 17:40:06 and compared again against both baseline and prepared KiCad XML netlists. All 160 physical pins, 31 physical net partitions, and 31 physical net names still match exactly. The comparison JSON files reflect this regenerated output.

The remaining 28 warnings comprise 14 electrical-pin/unspecified-port type checks, 11 nets reported with no driving source, and three missing-footprint warnings for virtual `#FLG` ERC symbols. The virtual flags are intentionally off-board and absent from the BOM in KiCad. The port/pin types and the eleven driver warnings require per-net review; they have not been suppressed. The copied `PCB-PWR.PrjPcb` stores local relative output/log paths for portability. The live imported project remains in its original F: import folder and was not moved.

The root SchDoc sheet symbols, sheet entries, net labels, and wires are identical between the previous and new imports in all 82 normalized records. The new child sheets contain the extra labels.

## PCB geometry

The updated comparison finds all 575 native KiCad routed segments in Altium, with no missing route and no wrong copper layer. Altium contains three additional controlled Top Layer stubs, so the routed-segment count is 575 KiCad versus 578 Altium. The remaining unchanged counts are 267/267 vias, 66/66 component origins, 210/210 pads, 31/31 PCB net names, and 4/4 board outline segments.

The three 0.25 mm wide, 0.50 mm long stubs connect the imported NetTie pads to the same-net polygon copper that KiCad fills over those pad centres:

- `NT1-1`, `GND_MODEM`: native coordinates `(75.10, 40.12)` to `(74.60, 40.12)` mm;
- `NT2-1`, `GND_DIGITAL`: native coordinates `(76.10, 48.52)` to `(76.60, 48.52)` mm;
- `NT2-2`, `GND_PWR`: native coordinates `(75.10, 48.52)` to `(74.60, 48.52)` mm.

The Altium geometry comparison found no removed track and exactly these three added tracks; outline, arcs, pads, vias, text, components and layer definitions are unchanged. Each stub centreline and both 0.125 mm edge offsets were sampled along its full length against the filled native KiCad zone of the same net. This verifies that the added copper remains inside copper already present in the native design. See `validation/PCB-PWR-nettie-zone-stub-verification-2026-10-15.json` and the updated `verification.json`.

Pad shape, rotation, solder-mask expansion, keepouts, complete zone geometry, stackup and manufacturing outputs are not yet fully validated.

## Altium PCB DRC, 2026-10-15

`validation/PCB-PWR-Altium-DRC-2026-10-15.drc` and the matching HTML report were generated by Altium Designer 26.10.1 Trial after repouring all 28 polygons. The result is **0 warnings and 0 rule violations**. The report explicitly records zero for clearance, short circuit, unrouted net, modified polygon, width, hole size, hole-to-hole clearance, solder-mask sliver, silk, antenna and height checks.

The conversion defect was specific to polygon-to-NetTie-pad connectivity. NT1-NT3 were already stored as Altium component kind `Net Tie No BOM`, and their pad numbers, nets, locations and 0.50 mm diameters matched KiCad. The native KiCad filled zones cover the relevant pad centres. Altium nevertheless kept the polygon clearance around `NT1-1`, `NT2-1` and `NT2-2`; changing polygon connect style did not remove the three unrouted connections. Short same-net stubs directed away from the opposite-net sibling pad bridge only this conversion gap.

After adding the three stubs and repouring, the Altium connectivity engine reported zero unrouted connections. A fresh modal DRC then produced the saved zero-warning, zero-violation report for `PCB-PWR.PcbDoc`. The repeat project validation at 21:42:47 had already reported `Compile successful, no errors found` with 28 retained schematic warnings; see `validation/altium-validation-2026-10-14.txt`.

This closes the three PCB-PWR DRC violations. It does not by itself establish manufacturing equivalence or authorize fabrication. The remaining conversion gates include the retained schematic warnings, pad/mask and keepout review, stackup and controlled-impedance review, output generation, and full cross-board release audit.

## Diagnostic Output Job, 2026-10-15

`EVT-PRE-20_PCB-PWR.OutJob` was opened successfully in Altium Designer 26.10.1 Trial. It defines portable, local outputs with no absolute workstation path:

- folder output: Gerber X2, NC Drill, CSV and IPC-D-356A fabrication testpoint reports, Pick&Place, BOM, DRC report, and STEP;
- PDF output: board stack, drill drawing, assembly drawing, all schematic sheets, and PCB prints;
- fabrication testpoint report: top and bottom layers, metric units, relative origin, CSV and IPC-D-356A enabled;
- release-managed output: disabled.

This is a verified configuration only. Its outputs were not generated and no manufacturing archive was released because the blockers documented below remain open. Running it now would create diagnostic data, not an approved production package.
