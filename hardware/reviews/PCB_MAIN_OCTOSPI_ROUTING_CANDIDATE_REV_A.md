# PCB-MAIN OctoSPI routing candidate Rev.A

Candidate: `PCB-MAIN-OCTOSPI-ROUTING-001`  
Status: `ENGINEERING PROPOSAL / NOT APPLIED / NOT FOR MANUFACTURE`

This bounded candidate adds routing only for the eleven nets between STM32U585,
the series-damping network and W25Q512JV. It preserves every previously accepted
track, via, zone, footprint, placement, outline, net and board rule.

| Control | Value |
|---|---:|
| Reviewed base SHA-256 | `7dea2fdce607dbf7df2205e74b188d45e2def07c5329bacb4f9503ddcf7ae6f3` |
| Candidate SHA-256 | `758c9bfdf2d91a7dd4f69f00b94ac7d7cccff15f1415c6c72e68d5604ee67193` |
| Added segments / vias | `121 / 25` |
| Added track length | `282.362979395 mm` |
| Native unconnected count | `707 -> 697` |
| Existing copper removed or modified | `0` |
| Rip-ups / failed connections | `0 / 0` |

The corrected candidate uses the board-rule `0.20 mm` copper clearance.  A
deterministic R8 escape places `NOR_CLK_U1` on In2.Cu and `NOR_CLK_U2` on
In3.Cu before the remaining nine nets are grid-routed at `0.125 mm`.

Human acceptance, commit-bound KiCad 9 comparative DRC, SI/return-path review,
remaining routing, Review B and manufacturing release remain mandatory.
