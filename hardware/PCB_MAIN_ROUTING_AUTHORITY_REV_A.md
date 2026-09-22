# PCB-MAIN Rev.A pre-route constraint authority

Status: `PASS / 186 NETS CLASSIFIED / EVT STACKUP AND NUMERIC ROUTING BASIS ACCEPTED / ROUTING OPEN / NOT FOR MANUFACTURE`

Machine authority: `hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv`

Generator: `tools/generate_pcb_main_routing_authority_rev_a.py`

Independent audit: `tools/audit_pcb_main_routing_authority_rev_a.py`

CSV SHA-256: `36da48a6614de40bed1b52cb53b0b6a1367fabf0e0504e8c0f4297c5b962f6f0`

## Decision

Every one of the 186 non-empty PCB-MAIN native nets has one explicit route
class, reference-domain rule, topology, layer/via rule, priority and source
authority. This closes the constraint-coverage input and records the accepted
EVT geometry. The committed board is partially routed with 1023 trace items and
eight copper zones; remaining routing, DRC, CAM, Review B and manufacturing
release remain open.

The manifest does not use a guessed controlled-impedance trace width. A
controlled overlay selects the official JLCPCB public
`JLC06161H-3313` construction as the numeric basis for an engineering routing
candidate: `0.1509 mm` for 50-ohm single-ended traces and `0.1537 mm` width with
`0.2032 mm` pair gap for 90-ohm differential traces, all on L1 referenced to
L2. These values and `±10%` impedance tolerance are accepted for the EVT job.
The customer must select the matching construction at checkout; any parser or
DFM mismatch is a stop condition.

The overlay and its independent audit are
`hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.json`,
`hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.md` and
`tools/audit_pcb_main_jlc06161h_3313_routing_basis_rev_a.py`.

The historical two-fabricator request is
`hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.json`; its
human-readable packet and 22-row engineering-closure register are
`hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.md` and
`hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_RESPONSE_REV_A.csv`. All rows are
closed by the customer-authorized EVT baseline without claiming factory replies.
This authorizes routing, but not fabrication or assembly.

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

The seven RF nets carry the accepted EVT target token in the CSV; controlling
geometry is `0.1509 mm` on L1 over L2
against the named public construction. Signal-via count has a zero target; any exception
requires a reviewed transition and adjacent return vias. J8/J9/J10 remain the
conducted ports, and no RF tee or probe stub is allowed.

The four USB pair groups are independent:

- `USB_MAIN_MCU_SEGMENT`: `USB_DP_U1` / `USB_DM_U1`;
- `USB_MAIN_CONNECTOR_SEGMENT`: `USB_DP_CONN` / `USB_DM_CONN`;
- `USB_CELL_MODEM_SEGMENT`: `CELL_USB_DP_U8` / `CELL_USB_DM_U8`;
- `USB_CELL_FIXTURE_SEGMENT`: `CELL_USB_DP_TP` / `CELL_USB_DM_TP`.

Each group carries the accepted EVT target token in the CSV. The accepted EVT geometry is
`0.1537 mm` trace width and `0.2032 mm` pair gap on L1 over L2. Allowable skew
remains open until SI review; production tolerance is `±10%`. Main USB and BG95 recovery USB never
share copper nets. The pair geometry must be enforced by a differential-pair-
aware router and independently audited.

The former request packet asked `FAB-A` and `FAB-B` the same 11 construction,
impedance, capability and DFM questions. Its 22 rows are now non-blocking
engineering closures; project RF/SI review and checkout DFM remain mandatory.

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

- checkout selection of `JLC06161H-3313`, controlled impedance and zero
  unresolved parser/DFM errors;
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
