# PCB-PWR dual-buck placement ECO-001 — Rev.A

Status: `STATIC PROPOSAL READY / COMMIT-BOUND KICAD 9 GATE PENDING / NOT APPLIED / NOT FOR MANUFACTURE`

`PCB-PWR-BUCK-PLACEMENT-ECO-001` is a bounded placement-only response to the
first PCB-PWR routeability audit. The authoritative board remains byte-identical
to the accepted DIM-003 placement canvas and still contains zero routed copper.

TI SNAS877 section 8.4 requires the bootstrap capacitor to sit close to the
LMR60440 with short, wide BOOT/SW paths and the SW-to-inductor copper to remain
short, wide, and minimum-area. The current canvas has each bootstrap capacitor
about 5 mm from its controller pins and presents each inductor SW pad away from
the controller. Routing that geometry would preserve an avoidable high-di/dt
loop defect, so placement must be corrected first.

Primary source: [TI LMR60440 SNAS877 layout guidelines](https://www.ti.com/document-viewer/LMR60440/datasheet/GUID-BAF92739-0CA9-4578-99BE-026DEB792C01).

## Exact placement delta

| Ref | From `(x, y, rot)` mm/deg | To `(x, y, rot)` mm/deg | Intent |
|---|---:|---:|---|
| `C4` | `(53.000, 10.000, 0)` | `(54.575, 16.400, 180)` | BOOT pad 1 and SW pad 2 face the matching U3 pins |
| `C6` | `(53.000, 38.000, 0)` | `(54.575, 44.400, 180)` | BOOT pad 1 and SW pad 2 face the matching U4 pins |
| `L1` | `(62.000, 14.000, 0)` | `(60.750, 14.000, 180)` | SW pad 1 faces U3; output pad 2 faces the 3V8 bank |
| `L2` | `(62.000, 42.000, 0)` | `(60.750, 42.000, 180)` | SW pad 1 faces U4; output pad 2 faces the 3V3 bank |

No controller, input capacitor, output capacitor, connector, test point,
mounting hole, outline, layer, rule, net, track, via, or zone changes.

## Static result

Both channels have the same symmetric result:

| Pad-to-pad routeability metric | Base | Candidate | Improvement |
|---|---:|---:|---:|
| controller BOOT to CBOOT | `5.661241 mm` | `1.281610 mm` | `77.362%` |
| controller SW to CBOOT | `4.966352 mm` | `1.309926 mm` | `73.624%` |
| controller SW to inductor SW | `10.045682 mm` | `4.356803 mm` | `56.630%` |
| inductor output to nearest output capacitor | `8.343035 mm` | `5.420814 mm` | `35.026%` |

The independent axis-aligned fitted-courtyard audit remains clean at `44/44`
fitted bodies, zero component conflicts, zero mounting-body conflicts and zero
mounting-pad conflicts. The board-wide minimum remains `0.22 mm` at `F1/D1`.
The four new controlled gaps are `C4/U3 = 0.24 mm`, `C6/U4 = 0.24 mm`,
`L1/U3 = 0.25 mm`, and `L2/U4 = 0.25 mm`.

## Identity and gate

- Base SHA-256: `fdd53e669a167df8925c38e289993c38b818c231eddd0be54de378b51538bf48`
- Candidate SHA-256: `9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37`
- Generator SHA-256: `5dcf33e2a13cc09a30f86e6405178d044cd741064e31f03a89805b0d10a690a7`
- Generator: `tools/generate_pcb_pwr_buck_placement_eco_001_candidate_rev_a.py`
- Independent audit: `tools/audit_pcb_pwr_buck_placement_eco_001_candidate_rev_a.py`

The next commit-bound PCB Native Gate must regenerate the candidate byte for
byte, parse both boards with KiCad 9, run comparative DRC, preserve the exact
unconnected-item count, introduce zero new error-class violations, and repeat
the strict fitted/mounting clearance audit.

Even after a green machine gate, application requires the exact decision
`ACCEPT_PCB_PWR_BUCK_PLACEMENT_ECO_001_SUBGATE`. Acceptance would authorize
only this four-footprint hash-bound placement delta. It would not authorize
routing, Review B, CAM, fabrication, assembly, or manufacturing release.
