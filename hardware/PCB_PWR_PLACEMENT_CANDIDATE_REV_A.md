# Дионея EVT-PRE-20 Rev.A - PCB-PWR provisional placement candidate

Status: `FITTED 2D CLEARANCE PASS / DIM-003 OPEN / ROUTING ABSENT / NOT FOR MANUFACTURE`

This authority creates a reviewable native-board canvas without claiming enclosure or
fabrication approval. The four-copper-layer count is frozen for Rev.A by
`hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv`. The `90 x 60 mm` outline and
`1.6 mm` thickness remain deliberately provisional working values. They are not a
mechanical freeze and must be replaced or explicitly accepted after `DIM-003`
supplies the assembled envelope, terminal zones, mounting pattern and frozen PCB STEP.
The bounded request and blank `0/18` response register are controlled in
`hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.md`; packet readiness does not
accept any provisional geometry.

## Controlled candidate content

- all 62 physical schematic references are present once and carry their exact native
  footprint and net assignment;
- J1 starts the west-side input/protection chain and J2 is provisionally oriented for
  an east-side harness exit;
- the 3V8 and 3V3 buck channels occupy separate upper and lower functional regions;
- the two LMR60440 input/bootstrap/inductor/output groups are kept close enough for
  power-loop review, but no copper geometry is inferred from placement alone;
- the INA226 and shunt occupy one Kelvin-review region;
- TP1-TP10 form a top-side `2.54 mm` pitch review row using the controlled no-paste
  `1.70 mm` target. Final side, fixture datum and probe access remain open;
- there are no mounting holes because their number and coordinates belong to
  `DIM-003` rather than electrical design authority.
- all 44 simultaneously fitted assembly bodies have controlled courtyards and
  pass the independent `0.20 mm` 2D clearance subgate; the minimum observed
  fitted-courtyard clearance is `0.22 mm`.

## Hard interlocks

The candidate must contain zero tracks, zero vias and zero copper zones. DRC, Gerber,
drill, position, IPC-356 and STEP export are prohibited for this state. The independent
audit checks the complete reference/net/footprint set, every candidate coordinate,
the frozen layer count, provisional outline/thickness assumptions and the open
`DIM-003` record.

The bounded fitted-body clearance repack and its independent strict audit are
recorded in `hardware/reviews/PCB_PWR_PLACEMENT_CLEARANCE_REV_A.md`. Five DNP
footprints and thirteen PCB features are not assembly bodies; their copper,
fixture and service-access checks remain mandatory. J2's provisional east-edge
overhang is not a mating, cable-bend, enclosure or 3D clearance approval.

All 31 native nets now have controlled pre-route coverage in
`hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv`. That manifest adds current,
return-domain, topology, layer/via and separation inputs without relaxing this
placement interlock: actual routing remains prohibited until `DIM-003`, the
fabricator stackup/copper weights and numeric current-density/thermal geometry
are accepted.

The two-fabricator stackup/copper request is controlled in
`hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.md`. Its blank register
remains `0/24` rows and `0/2` accepted fabricator sets; request readiness does
not freeze copper weights, plating, via rules or numeric geometry.

Review B still requires frozen mechanics, final stack-up and copper weight; high-current and
Kelvin routing; hot-loop and switch-node control; thermal/current-density calculation;
TVS/fuse coordination; DRC; DFM; load-step, cold-start, fault, EMI and fixture evidence.
