# PCB-PWR VBAT_SYS C13-to-C12 routing 008 — approval

- Reviewer: Скиф
- Decision date: 2026-09-24
- Decision: `ACCEPT_PCB_PWR_VBAT_SYS_C13_C12_ROUTING_008_SUBGATE`
- Candidate SHA-256: `bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e`
- Reviewed source commit/tree: `c9625333e0ac4982b17a17d06208879e5f008e5c` / `78aa8fd4f34b4c8ed0572e09ab4c1b1535dfa30a`
- Evidence commit/tree: `8db70e9ae40f51190fe74f0461c16e8a9e65e6ca` / `5f257fe4f862fbad2feb5acdef8656bcacd3e5c2`

Application is limited to the exact reviewed two 3.0 mm F.Cu `VBAT_SYS`
segments linking `C13.1` to `C12.1`. All 37 predecessor trace items, both
bounded In1.Cu zones, every footprint, pad, net, outline and layer definition
must be preserved.

Routing from C13 to C11 and U2, global ground, outputs, Kelvin and feedback
remain outside this authorization. A fresh commit-bound application gate is
required. Overall routing, Review B, CAM, DFM, physical EVT and manufacturing
release remain open.
