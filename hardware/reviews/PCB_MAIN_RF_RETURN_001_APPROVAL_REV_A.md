# PCB-MAIN cellular L2 return-plane subgate approval Rev.A

Decision: `ACCEPT_CELLULAR_L2_RETURN_PLANE_SUBGATE`  
Reviewer: `Скиф`  
Date: `2026-09-20`

The user input `принимаем оба и продолжаем` explicitly accepts both pending
RF remediation subgates. For `PCB-MAIN-RF-RETURN-001`, it is normalized to the
exact decision token `ACCEPT_CELLULAR_L2_RETURN_PLANE_SUBGATE`.

This approval is bound to reviewed GitHub commit
`239016fdd295426766cc88209822be39610297db`, tree
`7a6e0c226318bd85e6456d17bae119b489d2aff1`, and candidate-board SHA-256
`22ddd8c56ceabf397ed033a44235b439625d3104fa2cf798bb57b782d24b1352`.

The reviewed machine gates are PCB Native Gate `#267`, run `35508574131`, and
CI `#540`, run `35508574124`; both concluded `success`. Comparative KiCad 9
DRC retained `226 -> 226` violations, `0 -> 0` errors and `429 -> 429`
unconnected items. The filled candidate covered all 623 sampled cellular RF
centreline points with the connected `GND_MODEM` L2 polygon.

Authorized scope is exactly one unfilled `GND_MODEM` zone on `In1.Cu`, named
`PCB_MAIN_GND_MODEM_CELL_In1_Cu`, wholly inside `ZONE_CELL`. No accepted
trace, via, footprint, outline, stackup, net or existing zone may change.

The separately accepted GNSS ECO may be composed afterward only by preserving
this exact zone and proving the combined authoritative board by deterministic
regeneration, strict placement clearance, filled-plane coverage and comparative
KiCad 9 DRC.

This approval does not complete remaining routing, final SI/PI, final
fabricator stackup or impedance acceptance, Review B, CAM, DFM, procurement or
manufacturing release.
