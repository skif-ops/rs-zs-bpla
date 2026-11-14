# PCB-MAIN USB source-termination placement ECO-001 approval — Rev.A

Decision: `ACCEPT_USB_SOURCE_TERMINATION_PLACEMENT_SUBGATE`  
Reviewer: `Скиф`  
Date: `2026-09-20`

The user input `решение принимается, после продолжай работу` explicitly accepts
the pending placement decision. It is normalized to the exact token
`ACCEPT_USB_SOURCE_TERMINATION_PLACEMENT_SUBGATE`.

This approval is bound to reviewed GitHub commit
`a3d774c8e7b0bd0634a60cf44b1cdf3f828a3e8d`, tree
`fa9bfd800e79eadc56d379ee4a1591c06a5f9b48`, and candidate-board SHA-256
`d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e`.

The authorized geometry is exactly:

| RefDes | From, mm/deg | To, mm/deg |
|---|---:|---:|
| R91 | 49.00, 18.25, 180 | 64.00, 25.25, 0 |
| R92 | 55.00, 18.25, 180 | 64.00, 26.25, 0 |

U1, J11, U25, C12, R3, all pads, nets, copper, zones, keepouts and the board
outline remain fixed. The accepted cellular and GNSS RF remediations remain
fixed as well.

The reviewed evidence is CI `#554` / run `35523547763` and PCB Native Gate
`#281` / run `35523547766`, both successful. Comparative KiCad 9 DRC recorded
zero new errors, `429 -> 429` unconnected items, and strict placement clearance
passed. Artifact `10609108665` has digest
`sha256:2d450a717585fcba580851059ed278a0db8f8a3974d3f911993df31e08d6e24f`.

This approval authorizes only application of the exact two-footprint placement
delta. It does not approve USB copper, declare USB routing complete, accept the
final fabricator stackup or impedance tolerance, close Review B, or authorize
CAM or manufacturing release.
