# PCB-PWR buck bootstrap routing 001 — approval

- Reviewer: Скиф
- Decision date: 2026-09-21
- Decision: `ACCEPT_PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_SUBGATE`
- Reviewed candidate SHA-256: `a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236`
- Reviewed source commit/tree: `1c7c37044a5e8b76cadab6e7435142858546254a` / `8eae1a27e7687688274199833091c3e59617bf53`
- Gate-evidence commit/tree: `eaa98ac68f08c64ebaee8681cbabb7f3fc71b446` / `a21c65709a84ce9621551a86d7137f181b224c4d`

## Authorized delta

Apply exactly two reviewed 0.5 mm `F.Cu` segments:

- `BOOT_3V8`: `U3.4` to `C4.1`;
- `BOOT_3V3`: `U4.4` to `C6.1`.

No vias, component movement, pad/net change, non-bootstrap copper, switch-node,
rail, return, feedback, control, or net-tie routing is authorized.

This approval does not close remaining routing, Review B, CAM, DFM, thermal or
manufacturing gates. A fresh commit-bound application gate is required.
