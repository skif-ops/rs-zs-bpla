# PCB-PWR VBAT_SYS C13-to-C11 routing 009 — approval

- Reviewer: Скиф
- Decision date: 2026-09-24
- Decision: `ACCEPT_PCB_PWR_VBAT_SYS_C13_C11_ROUTING_009_SUBGATE`
- Candidate SHA-256: `9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf`
- Reviewed source commit/tree: `88121e99401c09ad37694cbfc7bee1473e4519a8` / `56337e9cdf4ec7e4f36246c1a2ed68d998fcfc08`
- Evidence commit/tree: `5924c131fbf08e1792bbcb2aa23bea8de42cebf3` / `48b3d64fc5201e8508f46a0ef7f829790e1a8927`

Application is limited to the exact reviewed four 3.0 mm F.Cu `VBAT_SYS`
segments linking `C13.1` to `C11.1`. All 39 predecessor trace items, both
bounded In1.Cu zones, every footprint, pad, net, outline and layer definition
must be preserved.

Global ground, buck output, Kelvin, feedback, remaining hot-loop work and all
other routing remain outside this authorization. A fresh commit-bound
application gate is required. Overall routing, Review B, CAM, DFM, physical
EVT and manufacturing release remain open.
