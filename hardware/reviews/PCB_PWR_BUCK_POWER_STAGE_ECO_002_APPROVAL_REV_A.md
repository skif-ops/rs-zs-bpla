# PCB-PWR dual-buck power-stage ECO-002 — approval

- Reviewer: Скиф
- Decision date: 2026-09-23
- Decision: `ACCEPT_PCB_PWR_BUCK_POWER_STAGE_ECO_002_SUBGATE`
- Candidate SHA-256: `44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c`
- Candidate semantic SHA-256: `0e52d4cbc80104691e3793a579c7c7a8570e3640fabc2fb02bd7ea2e65643555`
- Reviewed source commit/tree: `753631012b5b20a46452998e9ad46502e3e1e4e1` / `978d4ac932f8b8deeb965b595a226ab8e3e6cae8`
- Machine evidence: CI 678, PCB-PWR Schematic 101, PCB Native 355
- KiCad 9 result: violations `86 -> 85`, unconnected items `121 -> 117`, zero new DRC fingerprint counts

Application is authorized only for the exact reviewed ECO-002 candidate. The
bounded delta moves `U3/U4`, `C4/C6`, `C20/C21`, and `L1/L2`; replaces only
the two invalidated BOOT segments; retains six unrelated predecessor segments;
adds eight reviewed `F.Cu` BOOT/SW segments with zero vias and zero zones; and
moves only the `C4`, `C6`, and `R2` reference anchors for the silkscreen
remediation. Pad geometry, nets, and DRC rules remain unchanged.

This decision authorizes preparation of the exact application. It does not by
itself modify the authoritative PCB-PWR board or release manufacturing. A fresh
commit-bound application gate must again prove exact byte identity, no new DRC
fingerprint counts, no increase above 86 violations, and unconnected items
exactly `121 -> 117`.

VIN/PGND hot-loop and return copper outside the reviewed delta, output rails and
returns, Kelvin and feedback routing, overall routing, Review B, DFM/CAM, and
physical `+70 °C` first-article validation remain open.
