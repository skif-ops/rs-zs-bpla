# PCB-PWR VBAT_SYS shunt-to-bulk routing 007 — approval

- Reviewer: Скиф
- Decision date: 2026-09-23
- Decision: `ACCEPT_PCB_PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_SUBGATE`
- Candidate SHA-256: `bb17dbead2445bcf4464960a83e13302347ce90463928ab09563afb3f0a3876b`
- Reviewed source commit/tree: `d962bf7cd9ef36c2b85363527a45ca467d059625` / `7a9b7eaf12db43e7ea4ebb45b20ed9be5d492a7c`
- Evidence commit/tree: `2f09a44a168efecf47445f06dbc67af5dfb49d49` / `96d8baef094b6bd64e21b3a5481a714636b356e5`

Application is limited to the exact reviewed two F.Cu `VBAT_SYS` segments
linking `RSH1.2` to `C13.1`: a 1.0 mm pad escape and a 4.0 mm expansion.
All 35 predecessor trace items, both bounded In1.Cu zones, every footprint,
pad, net, outline and layer definition must be preserved.

Routing from C13 to C11/C12, the upstream control pin, global ground, outputs,
Kelvin and feedback remain outside this authorization. A fresh commit-bound
application gate is required. Overall routing, Review B, CAM, DFM, physical
EVT and manufacturing release remain open.
