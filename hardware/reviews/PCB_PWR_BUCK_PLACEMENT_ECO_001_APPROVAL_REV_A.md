# PCB-PWR dual-buck placement ECO-001 approval — Rev.A

Decision: ACCEPT_PCB_PWR_BUCK_PLACEMENT_ECO_001_SUBGATE  
Reviewer: Скиф  
Date: 2026-09-21

The input Endth;lf. is the exact English-layout keystroke sequence for
Утверждаю. and accepts the explicitly pending PCB-PWR placement decision.

This approval is bound to reviewed GitHub commit
38d629c2e7f9a9956a93c8b9666b17e69905eeb6, tree
b935ed765133297099dee6af4799f598df832ab2, and candidate-board SHA-256
9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37.

The authorized placement delta is exactly:

| RefDes | From, mm/deg | To, mm/deg |
|---|---:|---:|
| C4 | 53.000, 10.000, 0 | 54.575, 16.400, 180 |
| C6 | 53.000, 38.000, 0 | 54.575, 44.400, 180 |
| L1 | 62.000, 14.000, 0 | 60.750, 14.000, 180 |
| L2 | 62.000, 42.000, 0 | 60.750, 42.000, 180 |

CI #580 / run 35586152428 and PCB Native Gate #307 / run
35586152390 both passed. Comparative KiCad 9 DRC recorded zero new
error-class violations, 126 -> 126 unconnected items and strict clearance
PASS with a 0.22 mm board minimum. Artifact 10632656386 has digest
sha256:c111a2146c6c07afb53686ea75c172dd8b7f445d2bed87ea3963fbf42e38d512.

The warning-only delta consists of two lib_footprint_mismatch warnings on
rotated C4/C6 instances whose non-pose footprint data remains identical, and
one L2/R10 silkscreen overlap. These items must be closed before Review B or
CAM and do not authorize a geometry change beyond a new controlled review.

This approval authorizes only the exact four-footprint placement application.
All unlisted footprints, nets, outline, layers and copper remain fixed.
Routing, final stackup acceptance, Review B, CAM, fabrication, assembly and
manufacturing release remain prohibited.
