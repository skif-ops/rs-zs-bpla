# PCB-PWR REV_GATE routing 004 — approval

- Reviewer: Скиф
- Decision date: 2026-09-21
- Decision: `ACCEPT_PCB_PWR_REV_GATE_ROUTING_004_SUBGATE`
- Candidate SHA-256: `f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c`
- Reviewed source commit/tree: `987a8fd43d057d0a1c24bd62f774ad404ed3affb` / `c4dd2255e3cd04a69de3979963a889b4cd7401a5`
- Evidence commit/tree: `19433a34b9c6bec5f45b79737d212b4803b5ff47` / `44f53e3fc079435cde1d301c9f03bd48f5acd57c`

Application is limited to the reviewed four 0.5 mm `F.Cu` segments from
`U1.5` to `Q1.4` on `REV_GATE`, with no vias and no change to predecessor
copper. Power-input load copper, buck hot-loop, switch-node, Kelvin and
feedback routing are not authorized by this decision.

Remaining routing, Review B, CAM, DFM, thermal and manufacturing gates remain
open. A fresh commit-bound application gate is required.
