# PCB-MAIN RF/SI and return-path review 001 — Rev.A

Status: `ECO_REQUIRED / RF P0 REMAINS A BOUNDED ENGINEERING SUBGATE / NOT FOR MANUFACTURE`

Reviewed authoritative PCB SHA-256:
`9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040`.

The accepted `PCB-MAIN-RF-P0-001` copper is electrically connected and passed
comparative KiCad 9 DRC, but that gate deliberately left RF/SI and return-path
review open. This review evaluates the seven routed RF nets against their own
route authority and the public `JLC06161H-3313` L1-over-L2 engineering basis.

## Result

The seven nets retain the accepted mechanical inventory: 138 `F.Cu` segments,
width `0.1509 mm`, and zero signal vias. Five GNSS/LoRa nets have the required
`GND_DIGITAL` zone on `In1.Cu` at outline level. That is not a final SI or
filled-plane acceptance, but it is consistent with the selected L1/L2
engineering structure.

Two blocking defects remain:

1. `CELL_RF` and `CELL_RF_ANT` require `GND_MODEM`, but the accepted ground
   candidate places `GND_MODEM` only on `In4.Cu`. `GND_DIGITAL` is intentionally
   absent from `ZONE_CELL`. The cellular traces therefore do not have the L2
   reference used to calculate `0.1509 mm`; passing DRC cannot repair that
   impedance/return-path mismatch.
2. `GNSS_RF_FILTERED` runs `25.325357 mm` between U9.11 and FL1.A although the
   pad-to-pad distance is `15.543668 mm` (stretch ratio `1.629304`). RF_IN faces
   away from the SAW, so the route exits the module edge and wraps around U9.
   This does not demonstrate the existing authority requirement to keep the SAW
   close to U9 RF_IN while avoiding signal routing under U9.

The review disposition is therefore `ECO_REQUIRED`; routing and Review B remain
open. The earlier RF P0 acceptance is not revoked: it remains useful as a
hash-bound engineering routing subgate, but it is not final RF copper.

## Bounded remediation

- `PCB-MAIN-RF-RETURN-001` adds one local `GND_MODEM` zone on `In1.Cu`, wholly
  inside the locked `ZONE_CELL` cut-out. It changes no accepted trace, via,
  footprint, outline, net or existing zone. This may close only the cellular
  L2-reference subgate after comparative KiCad 9 DRC and human acceptance.
- A separate GNSS placement/routing ECO must re-orient or locally repack
  `U9/FL1/C64`, regenerate the affected U9 ground fanout and GNSS RF copper, and
  repeat placement, DRC and RF return-path review. It must not be hidden inside
  the cellular plane change.

Final job-specific stackup/tolerance/coupon acceptance, both fabricator
responses, selected-assembler DFM/stencil response, remaining routing, complete
SI/PI review, Review B, CAM and manufacture remain blocked.
