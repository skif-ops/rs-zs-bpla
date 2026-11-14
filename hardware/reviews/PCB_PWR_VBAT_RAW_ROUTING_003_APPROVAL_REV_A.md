# PCB-PWR VBAT_RAW routing 003 — approval

- Reviewer: Скиф
- Decision date: 2026-09-21
- Decision: `ACCEPT_PCB_PWR_VBAT_RAW_ROUTING_003_SUBGATE`
- Candidate SHA-256: `05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3`
- Reviewed source commit/tree: `4a1114ff952e263fa3d2001556ddefd69f5ec3bf` / `fe23fa669ce75427335867fba4378608c72f0e8e`
- Evidence commit/tree: `d14effba1e4c09af47f14d9471145c1cc06eb36f` / `33af7f7beff451ed060f40eb05c48ed52439986e`

Application is limited to the reviewed 4.0 mm `F.Cu` segment from `J1.1`
to `F1.1` on `VBAT_RAW`, with no vias and no change to predecessor copper.
Buck hot-loop and switch-node routing is not authorized by this decision.

Remaining routing, Review B, CAM, DFM, thermal and manufacturing gates remain
open. A fresh commit-bound application gate is required.
