# PCB-PWR buck input hot-loop routing 006 — approval

- Reviewer: Скиф
- Decision date: 2026-09-23
- Decision: `ACCEPT_PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_SUBGATE`
- Candidate SHA-256: `9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0`
- Reviewed source commit/tree: `702ed8c9ae88832105e07d3278d112c10bf4c4d5` / `b3a256c68788de455946bf972b63c92d9bfdd694`
- Evidence commit/tree: `9290ca71e3f4f0209294d6a790edf04c40cf0e6e` / `2f3882226bc27f5f324154ad823b154ec0eb6ea1`

Application is limited to the exact reviewed thirteen F.Cu `VBAT_SYS` and
`GND_PWR` segments, eight 0.60/0.30 mm GND vias and two bounded In1.Cu local
return planes. All fourteen predecessor trace items and every footprint, pad,
net, outline and layer definition must be preserved.

The central C13 path, upstream trunk, global ground plane, output, Kelvin and
feedback routing remain outside this authorization. A fresh commit-bound
application gate is required. Overall routing, Review B, CAM, DFM, physical
EVT and manufacturing release remain open.
