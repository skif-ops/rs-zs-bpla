# PCB-MIC — acoustic-clearance ECO verification, 2026-10-15

Status: **NOT FOR MANUFACTURE**. This directory contains the Altium Designer 26.10.1 Trial verification project for the tracked PCB-MIC KiCad source. The 2026-10-15 ECO closes the known acoustic-hole clearance violations in both KiCad and Altium. All KiCad source files remain in the repository; no source file was deleted or renamed.

## Applied ECO

The change is intentionally limited to the T5838/MK1 acoustic area:

- the 32 rectangular fragments of MK1 pad 3 moved radially outward by 0.010 mm, from a nominal 0.6625 mm radius to 0.6725 mm;
- the GND track starting at `(12.70, 16.65)` mm now starts at `(12.75, 16.65)` mm, giving 0.200000 mm clearance to the 0.8 mm acoustic NPTH;
- the other nearby GND track endpoint moved from `(11.70, 16.05)` mm to `(11.695, 16.04)` mm, giving 0.202001 mm clearance;
- KiCad's ordinary hole-to-copper minimum is 0.20 mm;
- the local MK1 copper rule is 0.125 mm;
- the sole 0.10 mm exception is scoped to MK1 pad 3 versus the MK1 acoustic NPTH;
- the Altium rule scopes and priorities implement the same three levels: acoustic exception 0.10 mm, MK1 manufacturer copper 0.125 mm, general clearance 0.20 mm.

The embedded KiCad board footprint and `libs/Dioneya.pretty/T5838_RevA.kicad_mod` were changed together.

## KiCad verification

KiCad 10.0 CLI was run against the tracked native board after the ECO:

- PCB DRC violations: **0**;
- unconnected items: **0**;
- schematic-parity items: **55**.

The zero-violation board report is `validation/PCB-MIC-KiCad-DRC-2026-10-15.json`. The separate parity report is `validation/PCB-MIC-KiCad-DRC-parity-2026-10-15.json`. The 55 parity findings remain a release blocker and are not hidden by the clean board-only DRC result.

## Altium verification

Fresh Altium DRC at 12:50:38 Europe/Moscow reported **0 warnings and 0 rule violations**. The report covers the active rules, including:

- acoustic exception, 0.10 mm: 0 violations;
- MK1 manufacturer copper, 0.125 mm: 0 violations;
- general clearance, 0.20 mm: 0 violations;
- short circuit, unrouted net, width, hole size and modified-polygon checks: 0 violations.

Reports:

- `validation/PCB-MIC-Altium-DRC-2026-10-15.drc`;
- `validation/PCB-MIC-Altium-DRC-2026-10-15.html`.

## Independent semantic comparison

`tools/verify_pcb_mic_acoustic_eco.py` compares complete semantic models read from the original and final Altium boards. `validation/PCB-MIC-acoustic-ECO-semantic-compare-2026-10-15.json` passes all eight checks:

- board outline, layer stack, component records and net classes are unchanged;
- 53 pads exist before and after; exactly 32 changed, all are MK1 pad 3, and only their X/Y positions changed;
- 106 copper objects exist before and after; exactly two GND track geometries changed;
- no rule was removed;
- one 0.125 mm local rule was added;
- only the acoustic-rule scope and the general-rule priority changed among existing rules.

The geometry cross-check against the current KiCad board was also rerun:

- routed segments: 27/27;
- vias: 5/5;
- component origins: 6/6;
- pads: 53/53;
- PCB net names: 7/7;
- board outline: 4/4.

See `verification.json`, `pad-verification.json`, and `outline-verification.json` for the exact scope and limitations.

## Schematic connectivity

The schematic was not changed by this ECO. The 2026-10-14 Altium project validation and compiled-netlist comparison remain applicable to the unchanged schematic: 17/17 physical pins, seven physical partitions, and seven physical net names matched. KiCad single-pin nets `J1-7` and `J1-8` were omitted by Altium's default single-pin netlist setting.

This compiled-netlist result does not close the 55 current KiCad schematic-parity findings reported against the PCB.

## Output Job and release state

`EVT-PRE-20_PCB-MIC.OutJob` remains a verified portable configuration for Gerber X2, NC Drill, IPC-D-356A, Pick&Place, BOM, DRC, STEP and PDF drawings. Production outputs have not been regenerated from this ECO and no manufacturing archive has been released.

Before manufacture, the project still requires:

- disposition of the 55 KiCad schematic-parity findings;
- regenerated CAM and assembly outputs from the controlled source;
- mask, paste, keepout, fabrication drawing and acoustic-path review;
- repeated Review A/Review B binding to the new source hash;
- first-panel acoustic-bore inspection and physical EVT acoustic validation.
