# PCB-PWR Rev.A pre-route constraint authority

Status: `PASS / 31 NETS CLASSIFIED / DIM-003, STACKUP, ROUTING AND THERMAL EVIDENCE OPEN / NOT FOR MANUFACTURE`

Machine authority: `hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv`

Generator: `tools/generate_pcb_pwr_routing_authority_rev_a.py`

Independent audit: `tools/audit_pcb_pwr_routing_authority_rev_a.py`

CSV SHA-256: `53b1a1ecfee6f38544b593e63fb25faf3521140c794d3490951e30d0d6df52b1`

## Decision

Every one of the 31 non-empty PCB-PWR native nets has one explicit route class,
return/reference-domain rule, topology, current basis, geometry rule, layer/via
rule, aggressor-separation rule, priority and source authority. This closes only
pre-route constraint coverage. It does not authorize routing while the outline,
mounting pattern and terminal zones remain open under `DIM-003`.
The internal `DIM-003` request packet is ready, but its attributable response
register remains `0/18`; this is still an open routing prerequisite.

The internal two-fabricator stackup/copper packet is also ready at
`hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.md`, but
`PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv` remains `0/24` accepted across
`0/2` fabricator slots. It provides no selected construction, copper weight,
plating, via or manufacturing-minimum authority.

The committed board still has zero traces, zero vias and zero copper zones. The
manifest does not guess final trace widths, copper weights, via-array counts or
thermal geometry. Those values require the actual current envelope, DC-drop and
fault-energy calculations, +70 °C thermal evidence and an accepted four-layer
fabricator stackup.

The machine status binds a UUID/order-independent semantic board digest covering
the layer stack, outline, complete footprint placement, pad/net assignment and
absence of copper. The audit still reports the raw file SHA-256 for evidence, but
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
- Outer 2 oz / inner 1 oz remain request targets only. No numeric width, via
  count or plane geometry becomes authoritative until stackup, copper weight,
  current-density and thermal review are accepted.

## Route-order input

P0 covers return geometry, the complete power path, switch/boot loops, Kelvin
sense and feedback. P1 covers local analog/gate/mode networks plus control,
status and I²C. Within P0 the practical order is: freeze mechanics and stackup;
plan `GND_PWR` and net-tie joins; close hot loops; route Kelvin/feedback; then
size and route the high-current input and output paths.

## Exit criteria still open

Constraint coverage may remain PASS only while all of these are explicit:

- `DIM-003` frozen outline, mounting pattern, terminal/tool zones and PCB STEP;
- two complete attributable fabricator response sets, selected four-layer
  dielectric construction and accepted copper/plating authority;
- current-density, DC-drop, via-array, fault-energy and +70 °C thermal analysis;
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
python tools/audit_pcb_pwr_dim_003_request_rev_a.py
```

Neither command authorizes fabrication.
