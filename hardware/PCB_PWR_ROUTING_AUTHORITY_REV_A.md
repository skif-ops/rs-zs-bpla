# PCB-PWR Rev.A pre-route constraint authority

Status: `PASS / 31 NETS CLASSIFIED / DIM-003 AND EVT STACKUP ACCEPTED / NUMERIC EVT BASIS PASS / ROUTING AND PHYSICAL THERMAL EVIDENCE OPEN / NOT FOR MANUFACTURE`

Machine authority: `hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv`

Generator: `tools/generate_pcb_pwr_routing_authority_rev_a.py`

Independent audit: `tools/audit_pcb_pwr_routing_authority_rev_a.py`

CSV SHA-256: `53b1a1ecfee6f38544b593e63fb25faf3521140c794d3490951e30d0d6df52b1`

## Decision

Every one of the 31 non-empty PCB-PWR native nets has one explicit route class,
return/reference-domain rule, topology, current basis, geometry rule, layer/via
rule, aggressor-separation rule, priority and source authority. This closes only
pre-route constraint coverage. `DIM-003` is accepted `18/18` for the EVT test
batch, including the outline, H1-H4 mounting pattern, terminal/service zones,
fixture datum and conservative STEP envelope. Serial mechanical revalidation is
mandatory. A separate conservative numeric overlay and the accepted
`JLC04161H-3313A` process authorize bounded EVT engineering routing. Remaining
routing and manufacturing release remain blocked by physical fault/thermal,
DRC, CAM, checkout DFM and Review B gates below.

Numeric overlay:
`hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json`

Per-net numeric rules:
`hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv`

The historical two-fabricator stackup/copper packet is retained at
`hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.md`. Its `24/24` rows are
closed by project engineering under customer EVT authority. No factory reply is
required; selected values are 1.6 mm, outer 70 µm, inner 35 µm, minimum average
hole-wall plating 18 µm and ENIG.

The historical ECO-002 board has 14 accepted F.Cu trace items, zero vias and
zero zones; its ECO-002 commit-bound application gate passed at CI #692,
PCB-PWR Schematic #103 and PCB Native
#357. The accepted hot-loop candidate 006 has 35 trace items (including eight
0.60/0.30 mm vias) and two bounded In1.Cu local return zones. Its commit-bound application gate passes
at CI #715 and PCB Native #364 (KiCad 9 DRC 85 → 85; unconnected 117 → 108;
zero DRC fingerprint delta). The authoritative successor now exactly matches
accepted shunt-to-bulk candidate 007, adding only two F.Cu `VBAT_SYS` segments
from `RSH1.2` to `C13.1` for 37 total trace items. Its candidate gate passed at
CI #720 and PCB Native #367 (85 → 85 violations; unconnected 108 → 107); its
separate application gate passes at CI #725, PCB-PWR Schematic #110 and PCB
Native #370 with the same DRC comparison and zero fingerprint delta. Via-current and via-under-pad fabrication
qualification, physical
+70 °C first-article validation and all other routing remain open. The
accepted successor candidate 008 applies only the lower 3.0 mm F.Cu branch
from `C13.1` to `C12.1`; its commit-bound gate passes at CI #731, PCB-PWR
Schematic #112 and PCB Native #372 (85 → 85 violations, 107 → 106 unconnected,
zero DRC fingerprint delta). It is now applied byte-for-byte for 39 total trace
items; its separate application gate is pending. The U2-constrained
upper branch to `C11.1` is explicitly deferred.

The
numeric overlay uses a deliberately conservative 35 µm / 10 °C-rise engineering
screen: 4.0 mm for the 5 A input/primary return, 3.0 mm for 4 A rails/returns,
2.1 mm for local 4 A switch nodes and 0.5 mm for the 0.3 A rail/return. It also
defines provisional transition arrays and DC-drop length ceilings for a candidate.
These rules are accepted for EVT routing but are not physical current-capacity or
thermal proof. Final release still requires the actual current/fault envelope,
rail-drop/load-step checks and +70 °C evidence.

The machine status binds a UUID/order-independent semantic board digest covering
the layer stack, outline, complete footprint placement, pad/net assignment and
the exact bounded routing state. The audit still reports the raw file SHA-256 for evidence, but
does not mistake KiCad-generated UUID/order changes for an electrical or layout
change.

## Controlled class inventory

| Route class | Nets | Binding rule |
|---|---:|---|
| `POWER_INPUT_HIGH_CURRENT` | 4 | `VBAT_RAW` through `VBAT_SYS` preserve the series protection/shunt chain; geometry is derived from the 5 A working basis plus fault and transient evidence |
| `POWER_OUTPUT_HIGH_CURRENT` | 1 | `3V8_MODEM` is sized from the 4 A converter rating, 3.3 A BG95 BB+RF peak basis, DC drop and thermal evidence |
| `POWER_RAIL` | 2 | `3V3_DIGITAL` and `1V8_MIC` retain their separate harness return domains and load-specific current basis |
| `POWER_RETURN_PLANE` | 1 | `GND_PWR` is the continuous primary electrical/thermal return; voids and current density require Review B |
| `SEPARATE_HARNESS_RETURN` | 3 | `GND_MODEM`, `GND_DIGITAL` and `GND_MIC` join `GND_PWR` only through `NT1`, `NT2` and `NT3` respectively |
| `SWITCH_NODE` | 2 | Both switch nodes are minimum-area local F.Cu nets with no test stub and zero-via target |
| `BOOTSTRAP_LOOP` | 2 | Each bootstrap capacitor forms a shortest-practical local loop with its assigned controller and switch node |
| `KELVIN_SENSE` | 2 | True four-terminal shunt pickup reaches INA226 without shared load copper; test points are high-impedance branches only |
| `FEEDBACK_SENSE` | 1 | `FB_3V8` senses after the inductor/output capacitor and stays outside the switch-node field |
| `ANALOG_TIMING` | 3 | VCAP and RT networks remain local, short and isolated from high-di/dt loops |
| `GATE_DRIVE` | 1 | `REV_GATE` remains a local controller-to-MOSFET gate path |
| `MODE_CONTROL` | 2 | Buck mode straps remain local static networks |
| `LOW_SPEED_CONTROL` | 2 | MAIN enables cross the digital/power reference boundary only through the controlled `GND_DIGITAL`/`NT2` return path |
| `OPEN_DRAIN_STATUS` | 3 | `PWR_GOOD` and `FAULT` return through the digital harness domain; diagnostic `PG_3V8` remains local |
| `I2C_OPEN_DRAIN` | 2 | Initial 100 kHz bus; pull-ups remain authoritative on PCB-MAIN and both PCB-PWR pull-up footprints remain DNP |

The inventory totals 31. A new, deleted or renamed native/capture net fails both
the deterministic generator and the separately maintained audit.

## Current and geometry boundary

- Input and `GND_PWR` use the controlled 5 A expected-system basis, but the BMS,
  MPPT transient, fuse/TVS coordination and fault-energy envelope are not frozen.
- The 3V8 path uses the 4 A LMR60440 rating and 3.3 A combined BG95 BB+RF peak
  basis. This is a sizing input, not a claim that droop or thermal limits pass.
- The 3V3 path uses the 4 A regulator rating while the real load envelope remains
  open. Its fixed-output feedback pickup must be a quiet connection from the
  output-capacitor node to U4 FB, never from the switch node.
- The 1V8 path uses the 0.3 A TPS7A20 rating; acoustic noise, actual load and
  +70 °C performance still require physical evidence.
- Outer 2 oz / inner 1 oz and minimum 18 µm average hole-wall plating are the
  accepted EVT order values. The 35 µm screen remains the conservative routing
  lower bound. Numeric routing geometry is authorized, while via sharing,
  fault-energy and physical thermal performance remain EVT validation items.

## Route-order input

P0 covers return geometry, the complete power path, switch/boot loops, Kelvin
sense and feedback. P1 covers local analog/gate/mode networks plus control,
status and I²C. Within P0 the practical order is: preserve accepted EVT
mechanics; plan `GND_PWR` and net-tie joins; close hot loops; route
Kelvin/feedback; then route the high-current input and output paths against the
numeric overlay. Final production geometry remains a later acceptance step.

## Exit criteria still open

Constraint coverage may remain PASS only while all of these are explicit:

- preservation of the accepted EVT `DIM-003` outline, H1-H4 exclusions,
  terminal/tool zones and STEP envelope, plus serial revalidation before series;
- preservation of the accepted `JLC04161H-3313A` checkout values with no
  unresolved parser or DFM error;
- physical DC-drop, via-sharing, fault-energy and +70 °C thermal evidence;
- routed hot loops, switch nodes, Kelvin pair, feedback pickup, rail/return
  copper and all remaining nets;
- zero-unrouted KiCad 9 DRC, native STEP and connector/tool-access review;
- Gerber/Excellon, IPC-356, PnP, BOM and drawings generated from the reviewed
  commit and independently compared;
- load-step, cold-start, transient/fault and EMI evidence; factory DFM and signed
  independent Review B.

Run the controls with:

```bash
python tools/generate_pcb_pwr_routing_authority_rev_a.py --check
python tools/audit_pcb_pwr_routing_authority_rev_a.py
python tools/generate_pcb_pwr_evt_route_rules_rev_a.py --check
python tools/audit_pcb_pwr_jlc04161h_3313_evt_routing_basis_rev_a.py
python tools/audit_pcb_pwr_dim_003_request_rev_a.py
```

None of these commands authorizes fabrication.
