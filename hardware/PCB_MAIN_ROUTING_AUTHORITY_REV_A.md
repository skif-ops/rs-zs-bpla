# PCB-MAIN Rev.A pre-route constraint authority

Status: `PASS / 186 NETS CLASSIFIED / ROUTING AND FACTORY STACKUP OPEN / NOT FOR MANUFACTURE`

Machine authority: `hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv`

Generator: `tools/generate_pcb_main_routing_authority_rev_a.py`

Independent audit: `tools/audit_pcb_main_routing_authority_rev_a.py`

CSV SHA-256: `f77948c4837448fbc6c3d0cfd6820354a0a8cab12925457bf90768704cb9e1dc`

## Decision

Every one of the 186 non-empty PCB-MAIN native nets has one explicit route
class, reference-domain rule, topology, layer/via rule, priority and source
authority. This closes only the constraint-coverage input needed to begin
routing. The committed board still has zero tracks, zero vias and zero board
copper zones; therefore routing, DRC, CAM, Review B and manufacturing release
remain open.

The manifest deliberately does not assign a guessed controlled-impedance trace
width. The selected fabricator must provide the final six-layer stackup,
dielectric data, copper thickness and impedance construction before numeric RF
or USB geometry is entered into KiCad.

The controlled two-fabricator request is
`hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.json`; its
human-readable packet and blank 22-row response register are
`hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.md` and
`hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_RESPONSE_REV_A.csv`. Both
fabricator slots remain pending, so this handoff has zero accepted constructions
and does not authorize routing.

## Controlled class inventory

| Route class | Nets | Binding rule |
|---|---:|---|
| `RETURN_PLANE` | 3 | `GND_MODEM`, `GND_DIGITAL` and `GND_MIC` remain separate on PCB-MAIN; stitching never creates a cross-domain join |
| `RF_50OHM` | 7 | Cellular, GNSS and RU868 chains are 50 ohm single-ended, same-layer, no-stub routes over uninterrupted local return |
| `USB_90OHM_DIFF` | 8 | Four isolated DP/DM segments are 90 ohm differential pairs with matched transitions and no pair mixing |
| `MODEM_BURST_POWER` | 3 | Star feed; `3V8_MODEM_BB` is at least 0.60 mm equivalent width and `3V8_MODEM_RF` at least 2.70 mm with no neck-down |
| `SWITCH_NODE` | 1 | `SMPS_SW` is the shortest practical local F.Cu connection with no test stub and no routing into RF/GNSS/audio areas |
| `POWER_RAIL` | 12 | Width is derived from load current, DC drop and thermal review; return follows each controlled load domain |
| `EDGE_CLOCK` | 22 | Source-series segment or controlled fanout; minimize transitions and preserve continuous return |
| `EDGE_DATA` | 43 | OCTOSPI, SDIO, LoRa SPI, PDM and SIM segments retain their source/receiver topology and timing group |
| `I2C_OPEN_DRAIN` | 4 | Open-drain multi-drop topology is retained through the two damping links |
| `UART_SIGNAL` | 20 | Each MCU, BLE, GNSS, modem or fixture UART segment remains point-to-point across its series element |
| `MIC_WAKE_SIGNAL` | 8 | Four inputs and the two-stage OR tree retain microphone/digital domain boundaries |
| `ANALOG_SENSE_BIAS` | 10 | Bias, supervisor, CC, shield and VBUS-sense networks remain short and separated from switch/RF aggressors |
| `MODEM_SIM_CONTROL` | 19 | Modem and SIM controls retain the fail-closed topology and explicit cross-domain review flags |
| `FIXTURE_DEBUG` | 7 | Fixture-only routes remain distinct; STM32, nRF and BG95 recovery domains are never merged |
| `LOW_SPEED_CONTROL` | 19 | Remaining interrupts, enables, status, straps and tamper paths are explicitly enumerated rather than accepted by a wildcard |

The inventory totals 186. A new or renamed native net makes the generator and
independent audit fail until its route class is reviewed explicitly.

## Return-domain interlock

- `GND_MODEM`, `GND_DIGITAL` and `GND_MIC` use only their own copper and vias on
  PCB-MAIN. Their controlled joins remain `NT1`, `NT2` and `NT3` on PCB-PWR.
- Eleven modem/digital and seven microphone/digital signal segments carry an
  explicit `CROSS_*_REVIEW_B` marker. Routing them across an unreferenced plane
  split is prohibited; Review B must demonstrate the complete current-return
  path rather than treating the signal name as proof.
- `1V8_MIC` and `3V3_DIGITAL` are marked `RETURN_AT_LOAD_PER_GROUND_AUTHORITY`
  because their loads intentionally include more than one return domain. This
  marker is not permission to join those grounds on PCB-MAIN.
- `USB_SHIELD` remains a controlled coupling network, not a fourth signal
  ground or an alias for `GND_DIGITAL`.

## Controlled-impedance handoff

The seven RF nets have target `50_OHM_SINGLE_ENDED_FACTORY_STACKUP_PENDING`.
Signal-via count has a zero target; any exception requires a reviewed transition
and adjacent return vias. J8/J9/J10 remain the conducted ports, and no RF tee or
probe stub is allowed.

The four USB pair groups are independent:

- `USB_MAIN_MCU_SEGMENT`: `USB_DP_U1` / `USB_DM_U1`;
- `USB_MAIN_CONNECTOR_SEGMENT`: `USB_DP_CONN` / `USB_DM_CONN`;
- `USB_CELL_MODEM_SEGMENT`: `CELL_USB_DP_U8` / `CELL_USB_DM_U8`;
- `USB_CELL_FIXTURE_SEGMENT`: `CELL_USB_DP_TP` / `CELL_USB_DM_TP`.

Each group has target `90_OHM_DIFFERENTIAL_FACTORY_STACKUP_PENDING`. Numeric
width, gap and allowable skew remain open until the fabricator stackup and SI
review are available. Main USB and BG95 recovery USB never share copper nets.

The request packet asks `FAB-A` and `FAB-B` the same 11 construction,
impedance, capability and DFM questions. Selection requires two attributable
responses plus project RF/SI review; the response template currently records
`0/2` accepted fabricators.

## Route-order input

The controlled priority is:

1. P0: return-domain plane geometry and keepouts, `SMPS_SW`, modem burst feeds,
   RF chains and USB pairs;
2. P1: remaining power, clocks, timing buses, I2C, UART, microphone wake,
   analog/sense and modem/SIM controls;
3. P2: fixture-only and enumerated low-speed control paths.

The BLE antenna all-layer keepout and the mechanical RF/audio ownership zones
remain governed by `MAIN-AUTH-011`; this manifest does not relax them. Routing
must preserve the 2D placement-clearance PASS already recorded in Review B.

## Exit criteria still open

Constraint coverage may be called PASS only while the following remain explicit
blockers:

- final fabricator stackup and numeric 50-ohm/90-ohm geometry;
- routed copper, domain pours, stitching and impedance coupons;
- zero-unrouted KiCad 9 DRC and schematic parity;
- native STEP/service-volume review;
- Gerber/Excellon, IPC-356, PnP, assembly/fabrication drawings and hash binding;
- independent CAM comparison, assembler DFM and signed Review B.

Run the controls with:

```bash
python tools/generate_pcb_main_routing_authority_rev_a.py --check
python tools/audit_pcb_main_routing_authority_rev_a.py
```

Neither command authorizes fabrication.
