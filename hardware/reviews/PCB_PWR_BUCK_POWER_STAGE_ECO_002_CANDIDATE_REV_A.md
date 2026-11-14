# PCB-PWR dual-buck power-stage ECO-002 candidate

This isolated candidate replaces routing candidate 005 because its `0.5 mm`
pad-entry section occupied `4.578427 mm` per channel and did not satisfy the
project current/thermal criterion. The authoritative PCB-PWR board remains
unchanged. If accepted, ECO-002 also supersedes the applied ECO-001 poses of
`C4/C6/L1/L2` and replaces the two accepted BOOT traces; these changes are not
authorized by the proposal itself.

## Documentation and bounded delta

The placement and copper follow the TI LMR60440 layout guidance to keep the
bootstrap connection short and wide, keep SW-to-inductor copper short and of
minimum area, and place the input bypass close to VIN/GND. ECO-002 makes only
the following symmetric changes:

- rotate `U3/U4` by 90 degrees so each SW pad faces its inductor and each VIN
  pad faces its input capacitor;
- relocate `C4/C6`, `C20/C21`, and `L1/L2` within the existing buck regions;
- remove only the two now-invalid accepted BOOT segments;
- retain the other six accepted predecessor traces byte-for-byte;
- add three `0.5 mm` BOOT segments and one `2.1 mm` SW segment per channel,
  all on `F.Cu`, with zero vias and zero zones. The round SW endpoint overlaps
  the controller and bootstrap-capacitor SW pads as a compact pad-entry flare.

Candidate SHA-256:
`44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c`.

## Commit-bound rejection and serialization remediation

The first serialized candidate
`dd4c38c191b3087be8a58e9a4b7de4f7974de89797fba4583edbe674340ebda8`
was rejected by PCB Native run 353 at commit `85f50d0`. KiCad 9 reported
`86 -> 124` violations and `121 -> 116` unconnected items. All new electrical
errors were localized to the rotated `U3/U4` footprints.

The cause was a parent-only text replacement: the footprint `(at ... 90)`
angle changed while the serialized pad, property, and footprint-text board
orientations retained their previous angles. The remediated generator rotates
those child orientations together with the parent, matching KiCad's native
board serialization. It does not suppress or relax any DRC rule, change pad
geometry or nets, or modify the authoritative PCB-PWR board. The corrected
candidate therefore requires a fresh commit-bound KiCad 9 comparative DRC and
new exact human acceptance.

## Commit-bound silkscreen rejection and reference remediation

The rotation-corrected candidate
`516a2e0b99f2855e0b1542559b1f844d10e694893896568ef054095b79a5fa3d`
was rejected by PCB Native run 354 at commit `142c234`. Its electrical result
was correct: unconnected items fell exactly from `121` to `117`, and the four
error-level `clearance`, three `copper_edge_clearance`, and one
`courtyards_overlap` violations were unchanged. Total violations nevertheless
rose from `86` to `88` because the strict warning-fingerprint gate observed
`silk_over_copper` at `38 -> 39` and `silk_overlap` at `14 -> 15`.

The three added warnings were the `C4` and `C6` references over switch-node
copper and the `L1` polygon over the `R2` reference; the prior `R2` reference
over solder mask warning disappeared. The remediated candidate changes only
three serialized `F.SilkS` reference anchors: local `C4/C6 (0,-1.4,270)` move
to `(-2.5,0,270)`, and local `R2 (0,-1.4,0)` moves to `(0,1.4,0)`. Copper,
pads, nets, component poses, DRC rules, and the authoritative PCB-PWR board are
unchanged. A fresh commit-bound KiCad 9 comparative DRC remains mandatory.

## Pad-entry and EVT calculation

The SW segment is `2.1 mm` for its entire routed length; there is no external
sub-rule neck. Its round endpoint overlaps the small QFN SW pad while clearing
foreign copper, so only the component's own pad geometry remains narrower than
the route. Copper overlap is `0.140935 mm` at each controller SW pad and
`0.060000 mm` at each bootstrap-capacitor SW pad. This eliminates candidate
005's `4.578427 mm` by `0.5 mm` neck.

The resistance screen conservatively treats the complete `3.35 mm` distance
from the controller-pad edge to the inductor-pad edge as `2.1 mm` copper,
although the explicit segment is only `2.65 mm`. At `4 A`, `+70 °C`, and the
conservative `35 µm` routing screen this is `0.940172 mΩ`, `3.760689 mV`, and
`15.042756 mW` per channel. At the selected `70 µm` outer-copper target it is
`0.470086 mΩ`, `1.880345 mV`, and `7.521378 mW`. This passes the calculated
pad-entry criterion: `2.1 mm` exceeds both the conservative `35 µm` requirement
of `2.032863 mm` and the `70 µm` project minimum neck of `1.5 mm`.
Instrumented first-article verification at `+70 °C` remains required.

## Static geometry result

- fitted-body clearance: `0.200 mm` minimum, with no fitted or mounting-hole
  conflicts;
- SW-to-foreign-copper clearance: `0.564474 mm` minimum versus `0.400 mm`
  required;
- BOOT-to-foreign-copper clearance: `0.250 mm` minimum versus `0.250 mm`
  required;
- per-channel topology: BOOT-to-CBOOT `1.755349 mm`, SW-to-CBOOT
  `1.711061 mm`, SW-to-inductor `4.200539 mm`, VIN-to-input-capacitor
  `1.548308 mm`, and GND-to-input-capacitor `2.761001 mm`.

## Gates retained

Commit-bound KiCad 9 comparative DRC must add no DRC fingerprint counts, must
not increase total violations, and must reduce unconnected items exactly from
`121` to `117`. A green machine result permits exact human acceptance with
`ACCEPT_PCB_PWR_BUCK_POWER_STAGE_ECO_002_SUBGATE`; it does not itself apply the
candidate.

VIN/PGND hot-loop and return copper, output rails and returns, Kelvin and
feedback routing, overall routing, Review B, job DFM/CAM, and physical `+70 °C`
first-article validation remain open. No production or manufacturing release is
asserted by this proposal.
