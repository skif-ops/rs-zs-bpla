# PCB-MIC acoustic-clearance ECO-001 application, Rev.A

Status: `APPLIED / KICAD DRC PASS / ALTIUM DRC PASS / REVIEW A+B REPEAT REQUIRED / NOT FOR MANUFACTURE`

Date: `2026-10-15`

## Purpose

This ECO resolves the two ordinary GND-track clearances and eight MK1 acoustic-land points recorded by the 2026-10-14 Altium DRC while preserving the controlled manufacturing contract:

- ordinary NPTH-to-copper clearance: 0.20 mm;
- local MK1 manufacturer-copper clearance: 0.125 mm;
- sole acoustic exception: 0.10 mm between the MK1 pad-3 manufacturer ground land and the 0.8 mm MK1 acoustic NPTH.

## Applied change

| Object | Before | After |
|---|---:|---:|
| 32 MK1 pad-3 rectangular fragments | nominal radius 0.6625 mm | nominal radius 0.6725 mm |
| GND track at acoustic-hole right side | starts X=12.70 mm | starts X=12.75 mm |
| GND track at acoustic-hole lower-left side | ends X=11.70, Y=16.05 mm | ends X=11.695, Y=16.04 mm |
| KiCad general hole clearance | 0.25 mm | 0.20 mm |
| KiCad acoustic exception | broad MK1 footprint condition | pad 3 versus MK1 NPTH only |
| Altium acoustic exception | any two objects in MK1 | `MK1-3` versus `MK1-Un1` only |
| Altium local copper rule | absent | 0.125 mm, MK1-3 versus ordinary MK1 pads |

The board-embedded footprint and the library footprint were edited together. No KiCad source file was removed, renamed or replaced by an Altium-only source.

## Source binding

| File | Before SHA-256 | Applied SHA-256 |
|---|---|---|
| `hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_pcb` | `F558E030FA561A472D76360F714226A4E1ED3E6D95521591BEA8EE4CA41504CB` | `BA2AF99FE3B0B850A2801B9B73F1333D48C55A56D59E91187495D5E95910D93A` |
| `hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_pro` | `780ED8AC63E0997A79F5D792AD403E43FCD3F05C083C0A69CA2ACC489871D6E9` | `6E408ECBE38FF0C1D8D29C93D6AA284271E7F8300B3F4AAF2C42B169601D68AB` |
| `hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_dru` | `6D2B24A1BA18610024FA97DB254EC51FDDE566F4886DD345443FA9924CB4DFB1` | `F3DEB4CA6169AA1FF40B5A02BE31A0EB624E570ABE906C804F1C6DA894C4D6B9` |
| `hardware/kicad/native/PCB-MIC/libs/Dioneya.pretty/T5838_RevA.kicad_mod` | `055B5247E081BFCD248C177AA102D79C6F019A5FAA96120C78186B907066C1C2` | `213BB0BD9E5E3E8B31AEADF044F643FAAE2D0BF808FC60C56BFE9A90DD07753C` |
| `hardware/altium/netlabel-reimport-diagnostic/PCB-MIC/PCB-MIC.PcbDoc` | `57F6F52981506828906E4EDD9844A90EAC9A99EFEC16115C61BFBA847B33724B` | `5694BA909348205998DAA8E907407898A46A35665A23B05F51CD2E193DCD3A7E` |

## Verification results

| Check | Result |
|---|---|
| KiCad 10.0 board DRC | 0 violations, 0 unconnected items |
| KiCad 10.0 schematic parity | 55 items, still open |
| Altium 26.10.1 fresh DRC | 0 warnings, 0 rule violations |
| KiCad-to-Altium routes | 27/27 |
| KiCad-to-Altium vias | 5/5 |
| KiCad-to-Altium pads | 53/53 |
| KiCad-to-Altium components | 6/6 |
| KiCad-to-Altium outline | 4/4 |
| Original-to-final Altium semantic comparison | PASS, 8/8 checks |

The semantic comparison proves that the Altium delta is limited to the 32 MK1 pad-3 coordinates, two GND track geometries, the narrowed acoustic rule, one new local rule and the priority of the general rule. It also proves that the board outline, stack, component records, net classes and all other exposed semantic objects are unchanged.

## Evidence

- `hardware/altium/netlabel-reimport-diagnostic/PCB-MIC/validation/PCB-MIC-KiCad-DRC-2026-10-15.json`
- `hardware/altium/netlabel-reimport-diagnostic/PCB-MIC/validation/PCB-MIC-KiCad-DRC-parity-2026-10-15.json`
- `hardware/altium/netlabel-reimport-diagnostic/PCB-MIC/validation/PCB-MIC-Altium-DRC-2026-10-15.drc`
- `hardware/altium/netlabel-reimport-diagnostic/PCB-MIC/validation/PCB-MIC-Altium-DRC-2026-10-15.html`
- `hardware/altium/netlabel-reimport-diagnostic/PCB-MIC/validation/PCB-MIC-acoustic-ECO-semantic-compare-2026-10-15.json`
- `hardware/altium/netlabel-reimport-diagnostic/PCB-MIC/validation/PCB-MIC-Altium-layout-original-2026-10-15.json`
- `hardware/altium/netlabel-reimport-diagnostic/PCB-MIC/validation/PCB-MIC-Altium-layout-final-2026-10-15.json`

## Release effect

This application record is not an engineering approval or a manufacturing release. Earlier Review A and copper-return signatures remain valid historical evidence for their recorded board hashes. The current source has a new hash, so Review A/Review B binding, CAM generation and the complete production archive must be repeated. The 55 schematic-parity items, first-panel bore inspection and physical EVT acoustic validation remain blocking gates.

