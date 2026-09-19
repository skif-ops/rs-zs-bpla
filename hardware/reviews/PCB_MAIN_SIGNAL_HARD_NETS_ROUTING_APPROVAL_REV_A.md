# PCB-MAIN signal hard-nets routing approval Rev.A

Date: 2026-09-19  
Configuration: EVT-PRE-20 Rev.A  
Reviewer: Скиф

## Decision

`ACCEPT_SIGNAL_HARD_NETS_ROUTING_SUBGATE`

The decision applies only to proposal `PCB-MAIN-SIGNAL-HARD-NETS-001` reviewed at GitHub commit `4f3e5b18a49ebe2d11a33fcb833e57e18c56e34d`, tree `45add456a5fae77b8010b270b35492819b153268`, and candidate PCB SHA-256 `7dea2fdce607dbf7df2205e74b188d45e2def07c5329bacb4f9503ddcf7ae6f3`.

Machine evidence:

- PCB Native Gate `35446985180`: `success`;
- KiCad 9 comparative DRC step for `PCB-MAIN-SIGNAL-HARD-NETS-001`: `success`;
- CI `35446985202`: `success`.

The exact reviewed candidate may be applied to authoritative PCB-MAIN. This approval does not authorize changes to the reviewed route geometry, does not declare routing complete, and does not close return-path, SI, PI, thermal, Review B, CAM, DFM, or manufacturing release.
