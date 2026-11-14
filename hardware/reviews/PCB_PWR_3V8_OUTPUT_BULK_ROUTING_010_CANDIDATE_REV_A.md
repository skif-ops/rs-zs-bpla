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

Commit-bound evidence for proposal commit `e203af7924dbd007a21a3f4cd0bc7fc901a740e2`
and tree `83ebec4cdd38c95906b3e952a12f335ab46a41eb` passed: CI #751,
PCB-PWR Schematic #121 and PCB Native #386. KiCad 9 comparative DRC retained
85 violations, reduced unconnected items from 105 to 101, and introduced zero
new DRC fingerprints. The evidence artifact is `10802971000`, digest
`sha256:f84900812fa80350e4da4cbfeb9e5a017d72fc11d4fea4a7a09e1d8f020c1616`.
