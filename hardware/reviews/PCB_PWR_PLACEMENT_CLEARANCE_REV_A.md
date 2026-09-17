# PCB-PWR Rev.A fitted 2D placement-clearance record

Status: `PASS SUBGATE / DIM-003 AND REVIEW B OPEN / NOT FOR MANUFACTURE`

This record closes only the simultaneously fitted assembly-body clearance defect
on the provisional PCB-PWR canvas. It does not freeze the outline, mounting
pattern, connector/tool volumes, DFT fixture, height envelope or routed copper.

## Input finding

The initial 60-reference placement contained six positive fitted-courtyard
collisions:

| Pair | Disposition |
|---|---|
| `U2 / C2` | Move the INA226 bypass capacitor away from the VSSOP courtyard. |
| `C3 / C14` | Separate the upper 3V8 output-bank pair. |
| `C15 / C16` | Separate the lower 3V8 output-bank pair. |
| `C5 / C17` | Separate the upper 3V3 output-bank pair. |
| `C18 / C19` | Separate the lower 3V3 output-bank pair. |
| `C19 / U5` | Move C19 away from the auxiliary LDO while retaining it in the post-inductor bank. |

`C9 / F1` did not overlap, but its `0.14 mm` courtyard gap was below the
controlled `0.20 mm` planning minimum and was included in the same repack.

## Controlled coordinate delta

| RefDes | Previous X/Y, mm | Controlled X/Y, mm | Functional intent |
|---|---:|---:|---|
| `C9` | `16.00 / 27.00` | `16.00 / 26.75` | Input high-frequency bypass, clear of F1. |
| `C2` | `48.00 / 22.00` | `48.50 / 22.00` | INA226 local bypass, clear of U2. |
| `C14` | `73.00 / 10.00` | `74.00 / 10.00` | 3V8 output-bank separation. |
| `C16` | `73.00 / 17.00` | `74.00 / 17.00` | 3V8 output-bank separation. |
| `C17` | `73.00 / 38.00` | `74.00 / 38.00` | 3V3 output-bank separation. |
| `C19` | `73.00 / 45.00` | `74.00 / 42.25` | Clear C18 and U5; remain in the 3V3 post-inductor bank. |

No other placement coordinate or rotation changes. The native layout audit still
binds all 60 references to the placement CSV and exact schematic pin/net set.

## Independent result and boundary

`tools/audit_pcb_pwr_placement_clearance_rev_a.py --strict` verifies:

- `42/42` fitted footprints have controlled front courtyards;
- minimum required fitted-courtyard clearance is `0.20 mm`;
- minimum observed clearance is `0.22 mm` (`D1 / F1`);
- fitted-courtyard clearance conflicts are `0`;
- five DNP footprints and thirteen PCB features are excluded from the assembly
  body calculation; their pad, fixture and service validation remains open;
- the provisional east-edge J2 overhang remains an explicit intent, not a
  mating, bend-radius or enclosure-clearance pass;
- tracks, vias and copper zones remain absent.

The machine control uses a UUID/order-independent board digest so the committed
board and a fresh KiCad 9 materialization must produce the same placement result.
`DIM-003`, mounting holes, J1/J2 service volumes, TP1-TP10 fixture access,
assembled STEP, stackup, numeric power geometry, routing, DRC, CAM, DFM, physical
evidence and independent Review B remain blocking.
The controlled DIM-003 request packet is ready, but its response register is
still `0/18`; no item in that list is accepted by this clearance result.
