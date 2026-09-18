# PCB-MAIN mechanical and placement authority - EVT-PRE-20 Rev.A

Status: `MECHANICAL_PLACEMENT_AUTHORITY_PASS / LIMITED ECO APPLIED / PCB REVIEW B OPEN / NOT FOR MANUFACTURE`

This record closes `MAIN-AUTH-011`. It freezes the PCB-MAIN outline, mounting pattern, connector/card access directions, RF and quiet-zone allocations, BLE and enclosure keepouts, module zone anchors, and every production pogo-pad coordinate needed to begin native Rev.A capture and layout. It does not assert that a native schematic or board exists, that the assembly fits a released enclosure, or that Review A, Review B, RF validation, fixture MSA, environmental tests, or any physical test has passed.

Machine authority: `hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv`.

Authority CSV SHA-256: `8b3dbcb5b3fffe8ce393850e4fa65b178ea79c03b584c2f8b54e6fdfd93e42f9`.

## Accepted limited mechanical ECO

`PCB-MAIN-MECH-ECO-001` was accepted by reviewer `Скиф` on `15.09.2026`
with decision `ACCEPT_LIMITED_MECHANICAL_ECO`. The decision is bound to commit
`61cbe796de2f87560342a44b063ff6283a8ce1e8` and candidate SHA-256
`5ef7d0390da97796febbef6a69f0206a06efe00782e238bf7c8f32bf29d08fc1`.
The machine-readable signature is
`hardware/reviews/PCB_MAIN_MECHANICAL_ECO_APPROVAL_REV_A.json`.

The accepted delta changes only nine records: J_PWR Y to 15.00 mm, J_MIC1 Y
to 42.50 mm, J8 and J10 Y to 71.50 mm, J13 Y to 15.00 mm, U8 Y to 52.00 mm,
ZONE_CELL to Y 34.00 mm and height 40.00 mm, ZONE_LORA height to 28.00 mm,
and KO_MIC1_HARNESS to Y 37.50 mm with width 10.00 mm. All X coordinates,
rotations, board outline, mounting holes, electrical connectivity and every
other MAIN-AUTH-011 field remain unchanged.

This ECO clears the six locked-authority geometry conflicts. It does not
complete placement, routing, DRC, enclosure validation, Review B or
manufacturing release.

## Accepted limited mechanical ECO-002

`PCB-MAIN-MECH-ECO-002` was accepted by reviewer `Скиф` on `18.09.2026`
with decision `ACCEPT_LIMITED_MECHANICAL_ECO`. The decision is bound to the
exact candidate SHA-256
`5164195ebf6a9a66b6a30197abfcb314655bfe059d0aea5f3782a744069780ff`,
authority SHA-256
`8b3dbcb5b3fffe8ce393850e4fa65b178ea79c03b584c2f8b54e6fdfd93e42f9`
and generated-PCB SHA-256
`e81daf6d8cf0220f762c64f1fc637f65d71d6bc99128ab8c4993a540431e461e`.
The machine-readable signature is
`hardware/reviews/PCB_MAIN_MECH_ECO_002_APPROVAL.json`.

The accepted delta changes only `MECH-007` and `MECH-012`: the J_PWR
mating-face centre moves from `(0.00,15.00)` to `(0.00,22.00)` mm and the J6
card-opening centre moves from `(18.00,2.50)` to `(21.00,2.50)` mm. Both
rotations and all other authority fields remain unchanged. H1 at
`(8.00,5.00)` mm is retained from the accepted ECO-001 baseline and is not a
new ECO-002 change.

ECO-002 closes only the bounded J6/J_PWR/H1 2D geometry conflict. It does not
authorize routing, CAM, fabrication, assembly, Review B or manufacturing
release. The generated board is still an unrouted engineering candidate.

The authority contains 70 records: one board outline, one assembled-envelope allocation, four mounting holes, thirteen connector placements, four RF-module anchors, four exclusive RF zones, one audio/digital quiet zone, seven keepouts/cable corridors, one bottom fixture window, three fixture fiducials, and 31 individual pogo pads. Every record uses the PCB coordinate system defined below and is independently checked by `tools/verify_pcb_main_mechanical_placement_authority_rev_a.py`.

## Primary evidence and upstream constraints

- `hardware/kicad/PCB_RULES.md`: six-layer EVT target, continuous RF/high-speed returns, separation of cellular current/RF from audio, GNSS upper view and no guessed 50 Ohm width before the factory stackup.
- `hardware/PCB_DOUBLE_REVIEW_GATE.md`: outline, holes, keepouts, RF, DFT access, stackup and CAM remain mandatory Review-B checks.
- Raytac `MDBT50Q-P1MV2` Version L and Footprint Design Guide 230606: module dimensions and antenna-end all-layer exclusion.
- Quectel `BG95 Series Hardware Design` v1.6, u-blox MAX-M10S integration data, and Ebyte E22-M documentation already identified by the closed device authorities.
- Molex `43045-1202` product data: right-angle 12-circuit Micro-Fit header, 1.60 mm recommended PCB and 10.29 mm mated-height datum: `https://www.molex.com/en-us/products/part-detail/430451202`.
- Molex `504050-0691` product data: right-angle six-circuit Pico-Lock header and 2.00 mm mated height: `https://www.molex.com/en-us/products/part-detail/5040500691`.
- GCT `USB4105`: top-mount, horizontal side-entry USB-C family with the selected 1.20 mm shell-stake option: `https://gct.co/connector/usb4105`.
- GCT `MEM2052`: top-mount push-push microSD socket with normally-open card detect: `https://gct.co/connector/mem2052`.

Manufacturer land patterns and component drawings remain authoritative for pad, shell-tab, anchor and courtyard geometry. This authority adds PCB-level coordinates and access constraints; it does not redraw or approximate those manufacturer patterns.

## Coordinate and rotation convention

- Top view: board origin is the south-west tangent corner of `Edge.Cuts`; +X points east, +Y points north, and +Z points from bottom to top.
- The bare PCB is a 110.00 x 75.00 mm rounded rectangle with four tangent R3.00 mm corners and nominal thickness 1.60 mm.
- H1-H4 are 3.20 mm NPTH at `(8,5)`, `(105,5)`, `(105,70)`, and `(5,70)` mm. H1 is shifted 3 mm east by `PCB-MAIN-ECO-001` to clear the J_PWR through-hole field; each hole has an all-layer copper exclusion diameter of 8.0 mm and component exclusion diameter of 10.0 mm.
- Card and edge-connector anchors are their mating/card-opening face centres. U.FL anchors are centre contact 1. Module anchors are manufacturer body centres. Test and fiducial anchors are copper centres.
- Connector rotation is normalized with the local mating/insertion vector along +Y at 0 degrees and increases counter-clockwise. Module rotation uses the normalized manufacturer top-view footprint; the U11 normalized antenna end is local +Y, so rotation 270 degrees points it east.
- The allocated unmated PCBA body envelope is 110 x 75 x 12 mm. Removable connector mates, card withdrawal, service-tool motion and cable bend volumes are excluded and controlled separately by the access rules in the CSV. The envelope must be checked against the generated native PCB STEP before enclosure release.

## Frozen placement result

| Domain | Frozen result |
|---|---|
| Board and fastening | 110 x 75 x 1.60 mm PCB, R3 corners, four symmetric M3 clearance NPTHs |
| Service edge | J6/J7 nano-SIM, J11 USB-C and J12 microSD all insert or mate south; J_PWR exits west and J13 exits east |
| Microphone harness | J_MIC1 exits west, J_MIC2/J_MIC3 north and J_MIC4 east; every latch has a dedicated pull and strain-relief corridor that cannot be crossed by RF coax or the power harness |
| Cellular | U8/J8 and their matching/bulk network are confined to `ZONE_CELL`; the short/wide BB/RF feeds and no-stub RF route remain Review-B items |
| GNSS | U9/J9 and supervisor/SAW network are confined to `ZONE_GNSS`; the mechanical upper-view reservation prohibits solar, metal and cable bundles above the route |
| RU868 | U10/J10 are confined to `ZONE_LORA`; J10 remains the conducted-test port and no other regional RF configuration is introduced |
| BLE | U11 antenna end is flush to the east edge; 3.8 x 10.5 mm of the board is an all-layer copper/component keepout and the external enclosure exclusion extends 15 mm beyond the edge |
| Audio/digital | `ZONE_AUDIO_DIGITAL` excludes modem VBAT/RF, SIM, GNSS bias and LoRa RF paths from the U1/PDM/clock routing area |
| Production fixture | 31 bottom pads, 1.70 mm copper with 2.10 mm mask opening and no paste, arranged on 2.54 mm pitch inside a bottom-only component-free fixture window with three fiducials |

The four RF zones do not overlap. The cellular/GNSS and GNSS/RU868 zone boundaries retain explicit gaps, while BLE has a separate edge volume. The zones are routing and component ownership constraints, not permission to guess controlled-impedance geometry. Native layout must use the final six-layer fabricator stackup to calculate every 50 Ohm trace and must preserve uninterrupted reference ground and via fencing.

## Production fixture contract

All test pads are on the bottom side and are accessed in the `DOWN_Z` direction by a rigid, keyed nest. Pads are single-row west-to-east groups; contact numbers increase with X. The exact electrical net still comes from the previously closed electrical authorities, and the independent verifier compares both sources contact by contact.

| Group | Contacts | Y (mm) | First X (mm) | Last X (mm) | Pitch |
|---|---:|---:|---:|---:|---:|
| `TP_EOL` | 13 | 23.00 | 33.00 | 63.48 | 2.54 mm |
| `TP_MCU_SWD` | 5 | 23.00 | 69.00 | 79.16 | 2.54 mm |
| `TP_BLE_SWD` | 4 | 23.00 | 84.00 | 91.62 | 2.54 mm |
| `TP_CELL_USB` | 4 | 30.00 | 33.00 | 40.62 | 2.54 mm |
| `TP_CELL_DBG` | 5 | 30.00 | 47.00 | 57.16 | 2.54 mm |

The fixture must not source `3V3_DIGITAL`, `3V8_MODEM`, `1V8_MIC`, `U8_VDD_EXT_1V8` or either VTREF contact. `BOOT0` may be driven only while STM32 reset is asserted. I2C2 access is open drain. BG95 debug is 1.8 V referenced and high impedance until VREF is valid. `CELL_USB_VBUS` is the only controlled current-limited fixture source in these groups. STM32 and nRF SWD remain electrically and physically separate.

## Service and enclosure boundary

- Card/USB openings require a sealed service-cover architecture; the ports are not exposed as permanent unsealed apertures.
- Straight-pull and bend-start allocations in the CSV are minimum packaging inputs, not a release of an unselected cable assembly. Cable OD, exact bend radius, retention and ingress details remain system/mechanical inputs.
- U.FL tool clearance is an 8 mm local diameter to at least 15 mm above each receptacle. The selected coax and antenna drawings must still prove bend radius, pull retention, temperature and final enclosure routing.
- PCB-MAIN remains mechanically separated from the four external PCB-MIC leaves. The 120 mm / +150 mm acoustic coordinates, upward ports, membranes, drainage and as-built microphone coordinates are not replaced by this board authority.

## Review and release boundary

Closing `MAIN-AUTH-011` completes the controlled pre-schematic input set. Native
`PCB-MAIN.kicad_sch` is present, independently net-audited, passes KiCad 9 ERC
with zero violations and has signed Review A. Native `PCB-MAIN.kicad_pcb` is
present as an unrouted placement candidate, so Review B remains blocked by
routing, DRC, DFM and physical evidence. The 110 x 75 x 12 mm envelope is a
locked capture allocation, but `mechanics/common/OPEN_DIMENSIONS.csv` keeps the
enclosure interface in `CONTROLLED_PENDING_NATIVE_STEP` until the generated STEP
and service sweeps are checked.

All physical tests remain `NOT RUN`. No RF tuning, BLE range, GNSS sensitivity, modem burst margin, fixture MSA, insertion/pull, enclosure fit, IP, thermal, vibration, or environmental result is inferred. Production Gerbers, the production BOM and any `FOR_MANUFACTURE` state remain blocked by incomplete placement and routing, strict DRC/CAM/DFM evidence, native STEP review, independent PCB-MAIN Review B and physical EVT.
