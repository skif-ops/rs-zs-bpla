# PCB-PWR 3V8 output bulk routing 010 — candidate

This bounded candidate connects `L1.2` only to the local `3V8_MODEM` output
capacitor bank `C3/C14/C15/C16`. It adds ten F.Cu segments, uses 3.0 mm trunk
geometry with two explicit 0.5 mm pad-entry transitions, and adds no vias or
zones. Conservative screened foreign-copper edge clearance is 0.350 mm.

The candidate does not connect the long J2 feed, feedback divider, test point,
3V3/1V8 rails, Kelvin pair, ground planes, controls or I2C. The authoritative
PCB is unchanged. Application requires the exact owner decision
`ACCEPT_PCB_PWR_3V8_OUTPUT_BULK_ROUTING_010_SUBGATE` after commit-bound KiCad 9
comparative DRC. Review B, CAM/DFM, physical thermal validation and
manufacturing release remain open.
