# PCB-PWR dual buck input hot-loop routing candidate 006

Creation is authorized by
`ACCEPT_PCB_PWR_ROUTING_CANDIDATE_006_CREATION_SUBGATE`. The required via/plane
scope revision is authorized separately by
`ACCEPT_PCB_PWR_ROUTING_CANDIDATE_006_VIA_PLANE_SCOPE_REVISION_SUBGATE`.

## Exact bounded delta

- Route the local `VBAT_SYS` path through `C11-C20-U3.1` and
  `C12-C21-U4.1`, including the required `U4.9 EN` VIN tie.
- Connect each main/HF input-capacitor ground pair on F.Cu.
- Add four `GND_PWR` vias per channel: one at the main CIN, one at CINHF and
  two in the matching TI RAK pad 2.
- Add one rectangular local `GND_PWR` return plane on `In1.Cu` per channel.
  These are bounded hot-loop planes, not a global board ground plane.
- Preserve all fourteen accepted ECO-002 trace items and every footprint,
  pad, net, outline, layer definition and mechanical object.
- Keep the authoritative board unchanged until a separate exact human
  acceptance and application gate.

Candidate SHA-256:
`9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0`.

## PGND routeability and via boundary

The accepted TI `RAK0009A` land pattern has no DRC-clean F.Cu escape corridor
from internal pad 2. TI drawing `4229353/J` explicitly provides an optional
two-via topology and requires vias under paste to be filled, plugged or
tented. Candidate 006 therefore uses two vias in each controller PGND pad.

All eight vias use the project-standard `0.60 mm` diameter and `0.30 mm`
finished drill. The candidate deliberately does **not** claim compliance with
the generic twelve-parallel-via rule for a full 5 A layer transition: this is a
local 4 A buck-return branch constrained by the TI PowerPAD geometry. Via
plating/current capacity, via-under-pad process, solder acceptance, ripple,
EMI and powered `+70 °C` behavior remain physical EVT/DFM gates.

## Gates retained

Commit-bound KiCad 9 comparative DRC must preserve `85 -> 85` violations,
introduce no DRC fingerprint delta and reduce unconnected items exactly
`117 -> 108`. Only after that result may the owner accept the exact candidate
with `ACCEPT_PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_SUBGATE`.

`C13`, the upstream `RSH1 -> VBAT_SYS` trunk, the global GND plane, output
rails, Kelvin/feedback routes and all other copper remain outside this
candidate. Overall routing, Review B, CAM, DFM, physical EVT and manufacturing
release remain open.
