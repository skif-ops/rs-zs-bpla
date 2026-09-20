# PCB-MAIN GNSS RF placement/routeability subgate approval Rev.A

Decision: `ACCEPT_GNSS_RF_PLACEMENT_ROUTEABILITY_SUBGATE`  
Reviewer: `Скиф`  
Date: `2026-09-20`

The user input `принимаем оба и продолжаем` explicitly accepts both pending
RF remediation subgates. For `PCB-MAIN-GNSS-RF-ECO-001`, it is normalized to
the exact decision token `ACCEPT_GNSS_RF_PLACEMENT_ROUTEABILITY_SUBGATE`.

This approval is bound to reviewed GitHub commit
`67538ba5dfea4cde08c06738cc6b537847a25398`, tree
`f45c0923461b299eb3ccfaa97eb9ca2cf069a285`, and candidate-board SHA-256
`d4c0eaa95bb62c7b9ae15b110fb3a76e6a056f462f0a36a734b3fa63730d2aee`.

The reviewed machine gates are PCB Native Gate `#273`, run `35511383587`, and
CI `#546`, run `35511383579`; both concluded `success`. Comparative KiCad 9
DRC held errors at `0 -> 0` and unconnected items at `429 -> 429`. Strict 2D
placement clearance passed, and the filled candidate covered all 406 sampled
GNSS RF centreline points with connected `GND_DIGITAL` L2 copper.

Authorized scope is the exact reviewed delta: keep U9/J9 fixed; move only FL1
to `(56.8, 51.6, 270)` and C64 to `(58.3, 51.6, 180)`; replace only the
identified GNSS RF and FL1 ground-fanout copper. The post-SAW route becomes
`1.326997 mm` while the three-net GNSS RF total remains bounded.

The separately accepted cellular L2 zone must remain byte-exact when this
delta is composed onto the authoritative board. The combined state requires
deterministic regeneration, strict placement clearance, both filled-reference
coverage checks and comparative KiCad 9 DRC.

This approval does not complete remaining routing, final SI/PI, final
fabricator stackup or impedance acceptance, Review B, CAM, DFM, procurement or
manufacturing release.
