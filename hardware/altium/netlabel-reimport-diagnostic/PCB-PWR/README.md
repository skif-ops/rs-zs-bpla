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

Independent comparisons in this directory found 575/575 routed segments, 267/267 vias, 66/66 component origins, 210/210 pads, 31/31 PCB net names, and 4/4 board outline segments matching the original KiCad PCB within the limitations in each JSON report. Pad shape, rotation, solder-mask expansion, keepouts, zone geometry, stackup, DRC and manufacturing outputs are not validated. The imported PCB must not be released for fabrication or assembly.
