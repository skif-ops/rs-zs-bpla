# PCB-PWR VBAT_SYS C13-to-C11 routing 009 candidate

Status: `CANDIDATE / COMMIT-BOUND KICAD 9 COMPARATIVE DRC PENDING / HUMAN ACCEPTANCE REQUIRED / NOT APPLIED / NOT FOR MANUFACTURE`

This isolated successor to accepted routing 008 adds four `3.0 mm` F.Cu
segments from `C13.1` to `C11.1`. The route leaves C13 upward, crosses the
open corridor below INA226 `U2`, passes its left side, and enters C11 from the
left. It adds no vias or zones and preserves all predecessor objects.

The conservative foreign-copper screen reports `0.575 mm` minimum edge
clearance, limited by `U2.1`. Total new branch length is `31.325 mm`.

The authoritative PCB-PWR file is unchanged. Application requires the exact
decision `ACCEPT_PCB_PWR_VBAT_SYS_C13_C11_ROUTING_009_SUBGATE` after the
commit-bound CI and KiCad 9 comparative DRC gate passes. Routing completeness,
Review B, CAM/DFM, and manufacturing release remain false.
