# PCB-MAIN OctoSPI R8 ECO-002 candidate Rev.A

Candidate: `PCB-MAIN-OCTOSPI-R8-ECO-002`  
Status: `ENGINEERING PROPOSAL / NOT APPLIED / NOT FOR MANUFACTURE`

The prior routing-only candidate `PCB-MAIN-OCTOSPI-ROUTING-001` was rejected by
KiCad 9 comparative DRC because R8.2 has no legal escape without via-in-pad.
This bounded ECO moves only R8 from `(55.0, 19.5)` to `(54.5, 16.0)` mm and
routes the same eleven OctoSPI nets. Every accepted track and via is preserved.

| Control | Value |
|---|---:|
| Reviewed base SHA-256 | `7dea2fdce607dbf7df2205e74b188d45e2def07c5329bacb4f9503ddcf7ae6f3` |
| Candidate SHA-256 | `946b52f40fac863e80ba476374707821f330c0d5c31c1b487cbc6a5d20cb7b43` |
| R8 displacement | `(-0.5, -3.5) mm` |
| Other footprints changed | `0` |
| Added segments / vias | `140 / 22` |
| Added track length | `290.374522443 mm` |
| Native unconnected count | `707 -> 697` |
| Existing copper removed or modified | `0` |
| Rip-ups / failed connections | `1 / 0` |
| Board clearance / routing guard | `0.20 / 0.25 mm` |

Human acceptance, commit-bound KiCad 9 comparative DRC, SI/return-path review,
remaining routing, Review B and manufacturing release remain mandatory.
