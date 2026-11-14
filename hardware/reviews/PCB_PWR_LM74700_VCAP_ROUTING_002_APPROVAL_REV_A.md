# PCB-PWR LM74700 VCAP routing 002 — approval

- Reviewer: Скиф
- Decision date: 2026-09-21
- Decision: `ACCEPT_PCB_PWR_LM74700_VCAP_ROUTING_002_SUBGATE`
- Candidate SHA-256: `3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5`
- Reviewed source commit/tree: `186ad093d23d015cedbdbc7234f11ad3944cb843` / `751b9193422d1a9b84b47327196f7f39f1863b40`
- Evidence commit/tree: `724a70e9df9c82051bf8f07c1c2e32266645bfba` / `82b065a51ead0d3480e5f31c0c763a8a66a08043`

Application is limited to the reviewed 0.5 mm `F.Cu` segment from `U1.1`
to `C1.1` on `LM74700_VCAP`, with no vias and no change to predecessor
copper. Narrow substitution for the 2.1 mm switch-node rules is not
authorized.

Remaining routing, Review B, CAM, DFM, thermal and manufacturing gates remain
open. A fresh commit-bound application gate is required.
