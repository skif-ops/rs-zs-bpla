# PCB-MAIN passive courtyard rule - Rev.A

Status: `CONTROLLED PLACEMENT INPUT / NOT A MANUFACTURING RELEASE`

This rule closes the missing-body screening condition for the five generic
two-terminal passive packages used on PCB-MAIN. It covers 184 land patterns:
169 `FITTED` and 15 `DNP`. The electrical MPN, value, population and package
authority remains `PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv`.

## Derivation

Each rectangular `F.CrtYd` is the union of the two generated copper-land
rectangles expanded by 0.25 mm on all four sides. The expansion is the same
conservative envelope previously used by
`audit_pcb_main_placement_clearance_rev_a.py` when a courtyard was absent. The
new geometry therefore converts screening evidence into an explicit,
repeatable courtyard without reducing the checked clearance.

| Package | Pad centres X, mm | Copper pad, mm | Courtyard X, mm | Courtyard Y, mm |
|---|---:|---:|---:|---:|
| 0402 | +/-0.275 | 0.55 x 0.50 | -0.800...+0.800 | -0.500...+0.500 |
| 0603 | +/-0.450 | 0.80 x 0.80 | -1.100...+1.100 | -0.650...+0.650 |
| 0805 | +/-0.525 | 1.00 x 1.25 | -1.275...+1.275 | -0.875...+0.875 |
| 1206 | +/-0.775 | 1.60 x 1.60 | -1.825...+1.825 | -1.050...+1.050 |
| 1210 | +/-0.775 | 1.60 x 2.50 | -1.825...+1.825 | -1.500...+1.500 |

The geometry is emitted by both PCB-MAIN source paths:

- `generate_pcb_main_layout_candidate_rev_a.py` when a native board is rebuilt
  with KiCad `pcbnew`;
- `generate_pcb_main_placement_repack_rev_a.py` when the controlled placement
  manifest is generated or checked against the committed native board.

Each affected footprint carries:

- `DIONEA_COURTYARD_STATUS=CONTROLLED_PAD_ENVELOPE_PLUS_0.25_MM`;
- `DIONEA_COURTYARD_SOURCE=PCB_MAIN_PASSIVE_COURTYARD_RULE_REV_A`.

## Release boundary

This rule controls only the 2D assembly envelope used for deterministic
placement. It does not approve solder paste, tombstoning performance, assembly
process limits, 3D body height, routing, DRC, CAM, DFM or Review B. The exact
selected MPNs and the assembler remain responsible for final process approval.
