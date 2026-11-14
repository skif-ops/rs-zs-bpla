# PCB-PWR dual buck switch-node routing candidate 005

Creation is authorized by
`ACCEPT_PCB_PWR_ROUTING_CANDIDATE_005_CREATION_SUBGATE`.

## Exact bounded delta

- Route only `SW_3V8` from `U3.3` through `C4.2` to `L1.1`.
- Route only `SW_3V3` from `U4.3` through `C6.2` to `L2.1`.
- Add fourteen `F.Cu` segments, seven per symmetric channel, with no vias or
  copper zones.
- Preserve the eight accepted predecessor trace items and every footprint, pad,
  net, layer, outline and mechanical object.
- Keep the authoritative board unchanged until a separate exact human
  acceptance and application gate.

Candidate SHA-256:
`5d135a38774c4e223c1db8d6a3fc0e8c9c492fe3ba24f5e2ec4c1b00ab2166d7`.

## Visible pad-entry constraint

The accepted `U3/U4` geometry does not permit a full-width `2.1 mm` segment to
terminate at pad 3 while maintaining the controlled `0.4 mm` switch-node
separation from adjacent GND pad 2 and the already accepted BOOT copper. The
candidate therefore does not hide a uniform narrow substitute:

| Width per channel | Length | Function |
|---:|---:|---|
| `0.5 mm` | `4.578427 mm` | QFN pad exit, C4/C6 SW-pad connection and clearance corridor |
| `1.0 mm` | `0.350000 mm` | first explicit expansion |
| `1.5 mm` | `0.851469 mm` | second explicit expansion |
| `2.1 mm` | `1.690000 mm` | nominal-width body into L1/L2 pad 1 |

Each route is `7.469896 mm`. A conservative pad/accepted-track geometry screen
finds `0.403 mm` minimum foreign-copper edge clearance against the required
`0.4 mm`. This is routeability evidence only. The pad-limited neckdown has not
passed final current-density, +70 °C thermal or physical EVT validation and is
not manufacturing authority.

## Gates retained

Commit-bound KiCad 9 comparative DRC must preserve `86 -> 86` violations,
introduce no DRC fingerprint delta and reduce unconnected items exactly
`121 -> 117`. Only after that result may the owner accept the exact candidate
with `ACCEPT_PCB_PWR_BUCK_SWITCH_NODE_ROUTING_005_SUBGATE`.

The VIN/PGND hot loops, GND return copper, input load path, Kelvin and feedback
routing, final thermal/current-density evidence, overall routing, Review B,
CAM, DFM and manufacturing release remain open.
