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
`dd4c38c191b3087be8a58e9a4b7de4f7974de89797fba4583edbe674340ebda8`.

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
