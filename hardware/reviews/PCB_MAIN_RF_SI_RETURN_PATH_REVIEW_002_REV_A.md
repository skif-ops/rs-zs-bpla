# PCB-MAIN RF/SI return-path repeat review 002 — Rev.A

Status: `PENDING COMMIT-BOUND COMBINED KICAD 9 GATE / NOT FOR MANUFACTURE`

Reviewed authoritative PCB SHA-256:
`f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9`.

Both independently reviewed remediations are now applied. The cellular
application first established exact byte identity with candidate
`22ddd8c56ceabf397ed033a44235b439625d3104fa2cf798bb57b782d24b1352`.
The GNSS application then composed its exact reviewed placement/copper delta
while preserving the cellular zone. Removing that exact zone from the composed
board recovers the reviewed GNSS candidate
`d4c0eaa95bb62c7b9ae15b110fb3a76e6a056f462f0a36a734b3fa63730d2aee`.

Static checks pass: U9/J9 remain fixed, only FL1/C64 move, strict 2D placement
clearance is clear, and `GNSS_RF_FILTERED` is `1.326997 mm` over a
`1.299279 mm` pad span. The unfilled source contains exactly one accepted
`GND_MODEM` `In1.Cu` cellular zone.

Closure is intentionally deferred until the commit-bound combined gate refills
the final board, proves both cellular and GNSS L2 centreline coverage, and runs
comparative KiCad 9 DRC against the accepted RF-P0 baseline with no new errors
or unconnected regression.

Remaining routing, final job-specific stackup/tolerance/coupon acceptance,
final SI/PI, both fabricator responses, selected-assembler DFM/stencil response,
Review B, CAM and manufacturing release remain open.
