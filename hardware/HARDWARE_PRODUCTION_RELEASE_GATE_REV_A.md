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

The production interlock is implemented by:

```bash
python tools/audit_evt_pre_20_hardware_release.py --strict
```

Default mode records the same blockers without failing engineering CI. A PASS
must not be inferred from source completeness, BOM QG-1, unrouted placement
candidates or successful software tests.

## Current blocker classes

- exact and released BAT1, PV1, MPPT1, ANT-CELL, ANT-GNSS, ANT-LORA, HARNESS and
  HSG-VC system identities;
- PCB-MAIN and PCB-PWR routing; all three boards' DRC, CAM, production outputs,
  DFM and independent Review B;
- assembler acceptance of the PCB-MAIN U2/U25/U26 project IPC candidates and
  process-dependent stencil/mask rules;
- PCB-PWR DIM-003 and the remaining enclosure, antenna, harness, installation and
  environmental mechanical inputs;
- supplier/fabricator/assembler quotation evidence and one selected 4/10/20
  purchase scenario.

Physical EVT and operator/SIM evidence remain later acceptance evidence after
stations are assembled; they are not replaced by this pre-production audit.
