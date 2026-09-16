# PCB-PWR Rev.A DIM-003 mechanical freeze request

Status: `PACKET READY / 0 OF 18 RESPONSES ACCEPTED / ROUTING NOT AUTHORIZED / NOT FOR MANUFACTURE`

This packet converts the open `DIM-003` line into a bounded, attributable
mechanical-freeze request for PCB-PWR. It is an engineering input request, not
acceptance of the provisional outline, a routed-board release, a fixture
release, a harness drawing or manufacturing authorization.

Machine contract:
`hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.json`

Blank response register:
`hardware/reviews/PCB_PWR_DIM_003_RESPONSE_REV_A.csv`

Independent audit:
`tools/audit_pcb_pwr_dim_003_request_rev_a.py`

## Controlled provisional basis

| Item | Current reference basis | Release state |
|---|---|---|
| PCB outline | `90.00 x 60.00 mm` | provisional; explicit acceptance or ECO required |
| PCB thickness | `1.60 mm` | provisional until DIM-003 and fabricator stackup agree |
| Copper layers | `4` | frozen count; dielectric construction and copper weights open |
| Mounting holes | `0` | absent; pattern must be supplied by DIM-003 |
| J1 | `(6.00, 28.00) mm`, `0 deg`, top-entry intent | mating, cable and tool volumes open |
| J2 | `(90.00, 56.00) mm`, `270 deg`, east-exit intent | mating, bundle, bend and tool volumes open |
| DFT row | `TP1..TP10`, top, `2.54 mm` pitch | fixture datum, probe access and wear limits open |
| Routed copper | `0` tracks, `0` vias, `0` zones | routing remains prohibited |

The reference coordinates are copied from the controlled placement authority.
They are not enclosure or fixture dimensions. An attributable response must
either accept them in a frozen datum or return a controlled ECO before routing.

## Required response set

All 18 rows of the response register are blocking. Together they require:

- one coordinate system shared by board, enclosure, harness and fixture CAD;
- an explicit disposition of the provisional outline followed by complete
  Edge.Cuts geometry, tolerances, finished thickness and mounting pattern;
- mounting hardware, top/bottom assembled height envelopes and enclosure
  wall, boss, rib, fastener and conductive-part keep-outs;
- separate J1 and J2 mating/tool volumes and cable/bundle bend, strain-relief
  and service volumes using the controlled mating parts;
- DFT datum, retention, probe geometry, travel, access and wear criteria for
  all ten test points;
- thermal-interface boundary conditions and the assembly/service sequence;
- board-side harness length datums that can replace the present TBD cut
  lengths only after enclosure routing is frozen;
- a versioned PCB assembly STEP, independent interference review and recorded
  SHA-256.

Response value, evidence reference, responder and date remain blank until the
responsible discipline returns real evidence. `ACCEPTED` is valid only when all
four attribution fields are populated and the cited controlled evidence exists.

## Acceptance and ECO rule

The present board has passed only fitted-body 2D clearance. Any accepted
DIM-003 change to the outline, holes, J1/J2 positions, DFT row, keep-outs or
assembled envelope requires a controlled PCB ECO and repeat placement,
clearance, routing-authority and Review-B checks. The accepted STEP must match
the post-ECO native PCB, not this provisional request basis.

Closing all 18 rows does not by itself authorize routing. Selected-fabricator
stackup and copper weights, numeric current-density and thermal geometry,
fault/transient coordination and the remaining Review-B gates stay separate.

## Release interlock

At packet creation all 18 dispositions are
`PENDING_EXTERNAL_RESPONSE`; accepted rows are `0`, `DIM-003` remains open and
the routing, harness-length, fixture, Review-B and manufacturing-release flags
remain false.
