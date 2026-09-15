# EVT-PRE-20 hardware production release gate — Rev.A

Status: `ACTIVE / BLOCKING`

This gate is the release authority for the physical station hardware and its
procurement BOM. It intentionally excludes application firmware, server and
Android deliverables. Software becomes part of this gate only when an explicit
pinout, power sequence, hardware interface or production-test dependency requires
it.

## Two release decisions

`hardware design release` proves that the three PCBAs, system components,
mechanics and harness are technically complete and independently reviewed.
It requires production BOM QG-2, completed routing, DRC, CAM, DFM, Review B and
closed mechanical dimensions.

`purchase release` additionally requires exactly one selected lot quantity from
4, 10 or 20 stations and traceable supplier quotations. Comparable RFQs may be
collected for all three quantities before that selection; mixing their quantity
columns is prohibited.

The selected lot is `EVT-20` for 20 stations. This closes only the lot-selection
condition. It does not release purchasing while hardware design or supplier
evidence remains blocked.

The production interlock is implemented by:

```bash
python tools/audit_evt_pre_20_hardware_release.py --strict
```

Default mode records the same blockers without failing engineering CI. A PASS
must not be inferred from source completeness, BOM QG-1, unrouted placement
candidates or successful software tests.

PCB-MAIN has passed its bounded 2D placement-clearance subgate: the controlled
225-reference repack gives all 227 fitted assembly footprints an explicit
courtyard and the strict audit reports zero component, mounting-exclusion and
U.FL tool-zone conflicts. This is engineering progress only; the unrouted board
has no copper zones and still requires routed-board DRC, 3D/service evidence,
CAM, DFM and independent Review B.

PCB-MAIN also has explicit pre-route constraint coverage for all 186 native
nets. The independent audit enforces disjoint route classes, ground-domain
references, four USB differential-pair segments, seven 50-ohm RF nets and the
controlled modem-feed minimum widths. Numeric RF/USB geometry remains blocked
until the fabricator stackup is accepted, and the constraint PASS does not close
routing, copper, DRC, CAM, DFM or Review B.

PCB-PWR has explicit pre-route constraint coverage for all 31 native nets. The
independent audit binds the 5 A system basis, both 4 A buck channels, the 3.3 A
BG95 BB+RF peak basis, three separate harness returns/net ties, two switch nodes,
two bootstrap loops, two Kelvin lines, feedback and 100 kHz I2C. Numeric widths,
via arrays and plane geometry remain blocked on `DIM-003`, final current/fault
envelopes, selected stackup/copper weights and thermal/current-density review.
The board remains unrouted with zero copper zones; DRC, CAM, DFM and Review B are
open.

The PCB-MAIN stackup/impedance request packet is internally ready, but it has
0/2 fabricator responses accepted and no selected construction. Its 22-row
register is a quotation/capability input only; it is not Gerber, a purchase
order, routing authority or fabrication release.

The bounded PCB-MAIN assembler request for `U2`, `U25`, `U26` and `U9` is also
internally ready, but it has 0/14 assembler DFM/stencil responses accepted and
no selected assembler legal entity, manufacturing site or controlled process.
The blank response register does not approve U9 paste, any land/mask/stencil
rule, PnP polarity, first-article assembly, Review B or manufacturing release.

## Current blocker classes

- exact and released BAT1, PV1, MPPT1, ANT-CELL, ANT-GNSS, ANT-LORA, HARNESS and
  HSG-VC system identities;
- PCB-MAIN and PCB-PWR routing, DRC and CAM; PCB-PWR `DIM-003`, final stackup,
  numeric current-density/thermal geometry and physical power evidence; PCB-MIC independent Review B,
  CAM comparison, panelization and acoustic-stack review; all three boards'
  DFM and manufacturing release;
- selected-assembler acceptance of the PCB-MAIN U2/U25/U26 project IPC
  candidates, U9 process-dependent stencil adaptation, PnP polarity,
  first-article controls and closure of blocker/critical DFM findings;
- PCB-PWR DIM-003 and the remaining enclosure, antenna, harness, installation and
  environmental mechanical inputs;
- supplier/fabricator/assembler quotation evidence for the selected 20-station
  purchase scenario.

Physical EVT and operator/SIM evidence remain later acceptance evidence after
stations are assembled; they are not replaced by this pre-production audit.
