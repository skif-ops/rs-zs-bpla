# PCB-MAIN signal hard-nets candidate Rev.A

Date: 2026-09-19  
Configuration: EVT-PRE-20 Rev.A  
Candidate ID: `PCB-MAIN-SIGNAL-HARD-NETS-001`

## Result

An isolated routing candidate was generated from the accepted ground-domain board. It closes the previously deferred signal fragments on eight native nets (nine reported fragments because `BOOT0` had two open branches):

`BLE_RX_U1`, `CELL_RX_U16`, `SD_D2_U1`, `SD_CMD_U1`, `NOR_IO0_U1`, `NOR_IO2_U1`, `EN_MODEM`, and `BOOT0`.

The candidate adds 102 track segments and 9 through vias. Native unfilled connectivity changes from 717 to 707 unconnected items; after local KiCad 7 zone refill it changes from 464 to 454. No accepted track, via, zone, footprint, net, board-setup, or mechanical item is removed or modified.

The first 0.25 mm-grid draft was rejected locally because it used a 0.65 mm grid origin and a stale 0.10 mm routing-clearance assumption. The replacement candidate aligns the grid at 0.50 mm, applies the 0.20 mm copper rule and 0.25 mm finished-hole rule, and introduces no new KiCad 7 comparative DRC error category or count. This remains preflight evidence only; commit-bound KiCad 9 is authoritative for the subgate.

## Identity

- Authoritative base SHA-256: `9c8abfabc18fa22b53c94b6b4d7946dbe1dfab797fbff9d00d7c3408aece1b9e`
- Candidate SHA-256: `7dea2fdce607dbf7df2205e74b188d45e2def07c5329bacb4f9503ddcf7ae6f3`
- Candidate board: `hardware/kicad/candidates/PCB-MAIN-SIGNAL-HARD-NETS-001/PCB-MAIN_SIGNAL_HARD_NETS_CANDIDATE_REV_A.kicad_pcb`
- Static audit: `tools/audit_pcb_main_signal_hard_nets_candidate_rev_a.py`

## Routing inventory

| Net | Segments | Vias | Length, mm | Layers |
|---|---:|---:|---:|---|
| `BLE_RX_U1` | 17 | 0 | 50.571 | F.Cu |
| `BOOT0` | 14 | 2 | 19.039 | F.Cu, B.Cu |
| `CELL_RX_U16` | 26 | 0 | 41.006 | F.Cu |
| `EN_MODEM` | 7 | 1 | 43.518 | F.Cu, In2.Cu |
| `NOR_IO0_U1` | 11 | 2 | 20.028 | F.Cu, In2.Cu |
| `NOR_IO2_U1` | 5 | 2 | 20.786 | F.Cu, In3.Cu |
| `SD_CMD_U1` | 13 | 0 | 30.993 | F.Cu |
| `SD_D2_U1` | 9 | 2 | 35.889 | F.Cu, In2.Cu |

## Decision boundary

This is a proposal-only routing subgate. It is not applied to the authoritative board. KiCad 9 zone refill and comparative DRC remain mandatory before acceptance. Return-path, SI, PI, thermal, Review B, CAM, DFM, and manufacturing release remain open. Procurement availability is outside this gate and is handled by the customer.
