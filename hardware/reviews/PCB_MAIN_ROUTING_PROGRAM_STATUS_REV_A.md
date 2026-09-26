# PCB-MAIN routing program — status after the autorouting sessions (Rev A, 2026-09-26)

Not a candidate for application yet; nothing here changes the authoritative board (`30c6c93e…`, applied 003).

## 1. Result

| Path | Open connections (KiCad DRC, after fill) | New DRC errors |
|---|---|---|
| Authoritative board (003) | 421 | — |
| Stacked sessions A–C, candidate 005 (`231707ed…`) | 156 | 0 |
| Stacked + session D, candidate 006 (`18cd3efa…`) | 143 | 27 (not yet filtered) |
| Global session G, candidate G (`aec71de7…`) | 161 | 0 |
| Experiment P1: G + pogo rows TP_EOL/TP_CELL_DBG moved off U1 (`3a021176…`, not filtered) | 136 before filter (G: 131) | 30 |
| **Experiment P2: G + Freerouting fan-out, flagged pieces removed (`6da31a8c…`)** | **156** | **0** |
| P2 + eight local F.Cu links 007 (`d45b5b1d…`) | 148 | 0 |
| 007 + GNSS antenna-short sense 008 (`63de9049…`) | 146 | 0 |
| 008 + USB connector escape 009 (`c42e099c…`) | 142 | 0 under candidate-only 6-layer via rules |
| 009 + U1 3V3 escape 010 (`6cc9d30c…`) | 141 | 0 under the same candidate rules |
| 010 + CELL_DBG power test-pad via 011 (`ad6cbb02…`) | 140 | 0 under the same candidate rules |
| 011 + C7 placement relief 013 (`d18f20d2…`) | 139 | 0 under the same candidate rules |
| 013 + C5/U1.100 014 (`008b133f…`) | 138 | 0 under the same candidate rules |
| 014 + seven 3V3 local links 015 (`00b01ae3…`) | 131 | 0 under the same candidate rules |
| 015 + two power-island links 016 (`9574bdca…`) | 129 | 0 under the same candidate rules |
| 016 + I2C/GNSS control links 017 (`bedd7cba…`) | 127 | 0 under the same candidate rules |
| 017 + local AAD_CFG legs 018 (`0860bf13…`) | 124 | 0 under the same candidate rules |
| 018 + SIM_MUX_SEL links 019 (`b07416af…`) | 122 | 0 under the same candidate rules |
| 019 + SIM2_VDD_CONN link 020 (`7d45ad45…`) | 121 | 0 under the same candidate rules |
| 020 + TEST_UART_RX_U1 on In3 021 (`5b6290cc…`) | 120 | 0 under the same candidate rules; return-path review open |
| 021 + R28→R33 3V3 022 (`a47c8a87…`) | 119 | 0 under the same candidate rules |
| 022 + C35→R33 3V3 023 (`11c28e2f…`) | 118 | 0 under the same candidate rules; power-return review open |
| 023 + R1→X1 3V3 024 (`b0292903…`) | 117 | 0 under the same candidate rules; oscillator-power review open |
| 024 + R1→existing 3V3 track 025 (`f1b2e2b4…`) | 116 | 0 under the same candidate rules; oscillator-power review open |
| 025 + HW_REV0 on B.Cu 026 (`c6da5dc7…`) | 115 | 0 under the same candidate rules; return review open |
| 026 + USB_SHIELD group join 027 (`79e3d98e…`) | **114** | **0 under the same candidate rules; shield coupling review open** |
| 027 + SWD 3V3 B.Cu branch 028 (`f0e1243e…`) | **113** | **0 under the same candidate rules; test-pad power/return review open** |
| 028 + SD_D2 In3 crossing 029 (`cbbc51ed…`) | **112** | **0 under the same candidate rules; SD return/DFM review open** |
| 029 + C6→R14 3V3 branch 030 (`2cddda58…`) | **111** | **0 under the same candidate rules; pull-up power/DFM review open** |
| 030 + SD_D1 B.Cu crossing 031 (`c27f9873…`) | **110** | **0 under the same candidate rules; SD return/DFM review open** |
| 031 + C9 3V3 supply bridge 032 (`205da6e0…`) | **109** | **0 under the same candidate rules; capacitor supply/DFM review open** |
| 032 + C7/U1 3V3 island bridge 033 (`d28f9952…`) | **108** | **0 under the same candidate rules; capacitor supply/return review open** |
| 033 + U1.11 3V3 escape 034 (`4b9fd52b…`) | **107** | **0 under the same candidate rules; U1 power/DFM review open** |
| 034 + I2C2_SCL_BUS bridge 035 (`bcf0ba9b…`) | **106** | **0 under the same candidate rules; I2C rise-time/return review open** |
| 035 + SIM1_RST_CONN bridge 036 (`844e3f7f…`) | **105** | **0 under the same candidate rules; mixed-domain return review open** |
| 036 + R90 pull-up 3V3 branch 037 (`75558caa…`) | **104** | **0 under the same candidate rules; pull-up power/DFM review open** |
| 037 + CELL_DBG_RXD_TP bridge 038 (`2b3d8b12…`) | **103** | **0 under the same candidate rules; mixed return/PDM coupling review open** |
| 038 + TP_EOL 3V3 supply bridge 039 (`039c9f4e…`) | **102** | **0 under the same candidate rules; test-pad supply/return and via DFM review open** |
| 039 + FB1 input 3V8_MODEM bridge 040 (`0b1b7a44…`) | **101** | **0 under the same candidate rules; modem burst current/PI and via-in-pad DFM review open** |

At the end of the autorouting experiments P2 was the best clean result (156 open, 0 new errors, 22 dangling fan-out
vias to clean); it is built from
the same router input as G with fan-out enabled, and only the connected pieces of new copper flagged by KiCad DRC are
left out (199 items). Candidate G below is kept as the fan-out-free reference: one reproducible session from the 003 board, clean after the DRC filter, not
dependent on the chain A–D. It adds 123 nets, 2014 segments and 275 vias (F.Cu / In3.Cu / B.Cu) and moves L1 to the
SMPS pins of U1 (53.75, 40.75, 180): SMPS_SW ≈ 2.5 mm instead of ≈ 18 mm. Reference (share of length over its own
ground domain): F.Cu/GND_DIGITAL 92.5 %, B.Cu/GND_DIGITAL 84.8 %, B.Cu/GND_MODEM 88.6 %, **F.Cu/GND_MODEM 32.7 %**.

## 2. Owner decisions (2026-09-26)
1. Power by pours — accepted; the 3V3_DIGITAL In3 pour was then dropped (option A: traces): In2 carries the GND_MIC
   plane under almost the whole board (5677 mm², 0.11 mm from In3). The earlier statement that GND_MIC covers only a
   small area was wrong.
2. In3 for slow classes (LOW_SPEED_CONTROL, FIXTURE_DEBUG, ANALOG_SENSE_BIAS, MIC_WAKE_SIGNAL, I2C_OPEN_DRAIN,
   UART_SIGNAL) — accepted; used in sessions D, E, G.
3. USB connector pair as two loose lines — rejected: it stays a 90 Ω pair (0.1537 / 0.2032 mm, F.Cu over In1).

## 3. Freerouting findings (handled in the router input)
- Back-side parts (TP_EOL, TP_BLE_SWD, TP_MCU_SWD, TP_CELL_USB, TP_CELL_DBG): their mirrored pads were misplaced;
  they are described as front parts with pre-mirrored images and B.Cu pads.
- RoundRect polygon pads (L1, R62, FB1): routed through; replaced by their bounding rectangles.
- A net with an emptied pin list makes its pads permeable; nets not to be routed are locked to a plane layer instead
  (grounds stay emptied — no front-side ground pad was crossed).
- Every candidate is filtered by KiCad 9.0.9 DRC: nets whose new copper has an error are left out whole.

## 4. Open connections of candidate G (161 in 68 nets; list: `OPEN_CONNECTIONS_G.json`)

| Class | Open |
|---|---|
| POWER_RAIL (3V3_DIGITAL 27, 1V8_MIC 14, VCORE_1V1 5, …) | 53 |
| EDGE_DATA / EDGE_CLOCK (SD, SPI, PDM, AAD fan-out) | 30 |
| MODEM_BURST_POWER (3V8_MODEM_BB 9, 3V8_MODEM_RF 4, 3V8_MODEM 2) | 15 |
| LOW_SPEED_CONTROL, MODEM_SIM_CONTROL, ANALOG_SENSE_BIAS, I2C, UART, FIXTURE_DEBUG, MIC_WAKE | 56 |
| USB_90OHM_DIFF (connector pair) | 6 |
| SWITCH_NODE (SMPS_SW) | 1 |

## 5. Why it stops here, and what is needed
Five autorouting sessions converge to 140–160 open connections whatever the order: on F.Cu, B.Cu and In3 the present
placement leaves no channel. More router passes do not help. The main choke is the escape of U1 (STM32U585, LQFP100):
42 of the 161 open connections (32 nets) end at an isolated U1 pin, ten of them 3V3_DIGITAL supply pins. The remaining
work is layout work:

1. **U1 escape and placement relief (owner decision needed):** open the U1 fan-out first (decoupling and series parts
   around the LQFP ring, escape vias outside the pad ring); move/rotate local passive groups to open channels, e.g. the modem
   bulk capacitors of 3V8_MODEM_BB/RF (C37–C47, D1, D2, R42 at x 6–10 mm) are 20–25 mm from the U8 supply pins; the
   1V8_MIC and 3V3_DIGITAL decoupling around U1/U7. Then one more global session from the relieved placement.
2. **Manual routing** of what remains (the 003 router, net groups, rip-up of blocking autorouted copper, KiCad DRC).
3. **USB connector pair:** the recorded DFM hold (`PCB_MAIN_USB_ROUTEABILITY_REVIEW_REV_A.md`) requires a via smaller
   than 0.50/0.30 mm. Section 7 records a candidate-only 0.25/0.15 mm via-in-pad route under the published six-layer
   process limits; finished drill, annular ring, filling/capping and SI/DFM acceptance remain open.
4. **Modem-domain reference:** F.Cu/GND_MODEM 32.7 % — modem-domain nets on F.Cu leave the In1 GND_MODEM zone;
   to be constrained by region in the next session or rerouted on B.Cu.

Tools: `tools/apply_pcb_routing_global_g_rev_a.py`, `tools/apply_pcb_main_routing_g_candidate_rev_a.py` (this
branch); sessions A–E and candidates 004–006 on `feature/pcb-routing-004`.

## 6. Experiments after candidate G (2026-09-26)
- **P1 — pogo rows off U1** (TP_EOL to (47.5, 9.0), TP_CELL_DBG to (22.5, 28.0); BOOT0 copper removed). Router:
  148 unrouted (G: 144); before the DRC filter 136 open (G: 131). No gain: the bottom pogo pads are not what limits the
  U1 escape. MAIN-AUTH-011 (pogo coordinates) stays closed.
- **P2 — fan-out enabled** (same input as G). Router: 120 unrouted (G: 144); before the DRC filter 107 open. The 24 DRC
  errors fell into large connected pieces of 3V3_DIGITAL and 1V8_MIC; removing only the flagged pieces leaves 156 open.

Conclusion: seven autorouting variants converge to 155–160 open connections. The remainder needs interactive routing
(KiCad push-and-shove by a layout engineer, or a generalised version of the 003 router in net groups).
Tools: `tools/apply_pcb_routing_relief_p1_rev_a.py`, `tools/apply_pcb_routing_fanout_p2_rev_a.py`.

## 7. Bounded local routes 007–040 and current stop (2026-09-26)

The cumulative 040 is the lowest comparative-DRC-clean routing experiment on this branch. It is **not applied** to the
authoritative board. The unchanged general PCB-MAIN project rejects the 0.25/0.15 mm vias introduced in 009 and 010 (five each of
`annular_width`, `drill_out_of_range`, `via_diameter`). Under an explicit *candidate-only* JLCPCB six-layer process
overlay (`min_via_diameter=0.25`, `min_through_hole_diameter=0.15`, `min_via_annular_width=0.05`), KiCad 9 comparative
DRC is 146→142→141→140→139→138→131→129→127→124→122→121→120→119→118→117→116→115→114→113→112→111→110→109→108→107→106→105→104→103→102→101 open with zero new violations at each accepted step. Candidate projects,
comparative DRC and generators are in the corresponding `PCB-ROUTING-P2-*/` directories. The published six-layer process basis is `https://jlcpcb.com/6-layer-pcb` (minimum
0.15/0.25 mm and via-in-pad option); a job-specific acceptance is still required.

- 007: eight short F.Cu links in 3V3_DIGITAL and 1V8_MIC; native DRC 156→148, no new violation.
- 008: two F.Cu branches of `GNSS_ANT_SHORT_N` (MAX-M10S antenna-short status, not RF) from U9 to R62/C63;
  native DRC 148→146, no new violation.
- 009: connector-side USB-C duplicated D+/D− contacts and symmetric connector-to-U25 F.Cu paths. Five P2 CC1
  segments are replaced with a B.Cu CC1 route. Four 0.25/0.15 mm vias, three in SMD pads, require filled/capped
  via-in-pad and finished-drill/annular-ring review. Main paired F.Cu segments are each 1.5669 mm; this does not
  establish end-to-end skew through the duplicated contact branches. The nearest existing GND_DIGITAL via to the
  B6 D+ transition is 2.37 mm. USB pair/return SI review is open.
- 010: one U1 3V3_DIGITAL pad escapes via a 0.25/0.15 mm pad via and a 13.97 mm, 0.25 mm B.Cu link to TP_EOL.
  Comparative DRC 142→141, zero new violations. This long narrow supply branch needs power-integrity review and
  must not be treated as a released power design.
- 011: one standard 0.50/0.30 mm via joins the existing F.Cu `U8_VDD_EXT_1V8` run to the B.Cu
  `TP_CELL_DBG` pad; comparative DRC 141→140, zero new violations. Via-in-pad compatibility with the test contact
  remains a DFM check.
- 012 trial: a 0.25/0.15 mm via at `TP_BLE_SWD` had comparative DRC 140→140 and was removed from the branch.
- 013: rotate C7 by 180° and move it 0.15 mm left. A 1.825 mm F.Cu link joins C7.1 to U1.6;
  a 1.975 mm F.Cu link returns C7.2 to an existing GND_DIGITAL via. Two obsolete ground tracks are removed.
  The C7 reference moves to F.Fab to avoid new silkscreen overlap. Comparative DRC 140→139, zero new violations.
- 014: 0.25 mm F.Cu run from U1.100 to the nearby C5 3V3 decoupler, 1.56 mm; DRC 139→138.
- 015: seven 0.25 mm F.Cu 3V3_DIGITAL links, 18.31 mm total, including U1.73↔U1.75
  and local passive islands; DRC 138→131.
- 016: a 0.30 mm F.Cu tie from C5 to an existing 3V3 track, and a 0.25 mm local 1V8_MIC
  tie at U18; 6.87 mm total, DRC 131→129. Power/return review remains open.
- 017: 0.20 mm F.Cu links on I2C2_SCL_BUS (U3.1→R15.2) and GNSS_ANT_GATE
  (R61.2→existing track), 6.294 mm total; DRC 129→127. GNSS_ANT_GATE is a control signal, not RF.
- 018: three local 0.20 mm F.Cu `AAD_CFG_1V8_FANOUT` legs from U20/U21/U22
  to J_MIC2/J_MIC3/J_MIC4, 25.655 mm total; DRC 127→124. The shared fanout and the microphone-domain
  return path remain open.
- 019: two 0.20 mm F.Cu links join U13.24→R45.1 and U13.14→U13.24 on `SIM_MUX_SEL`,
  12.99 mm total; DRC 124→122. U1.97 still needs its connection.
- 020: one 0.25 mm F.Cu `SIM2_VDD_CONN` tie from U15.1 to an existing supply run,
  10.794 mm; DRC 122→121. SIM supply/return review is open.
- 021: experimental 0.15 mm `TEST_UART_RX_U1` route on In3.Cu (11.912 mm), with two
  0.50/0.30 mm through vias and short F.Cu stubs from R102.2 to U1.15; DRC 121→120. The In3 trace
  crosses the In2.Cu GND_MIC reference area. Digital return-path Review B is open; this experiment is not released.
- 022: direct 0.25 mm F.Cu 3V3_DIGITAL link R28.1→R33.1 (1.25 mm), over In1.Cu GND_MODEM;
  DRC 120→119. The 3V3 return at these modem-area loads remains a Review B check.
- 023: 0.25 mm F.Cu 3V3_DIGITAL link C35.1→R33.1, 2.4 mm around occupied copper,
  over In1.Cu GND_MODEM; DRC 119→118. Power-return Review B remains open.
- 024: 0.15 mm F.Cu 3V3_DIGITAL escape R1.1→X1.3 (SiT1552), 3.36 mm around NRST/LSE copper;
  DRC 118→117. The [SiTime SiT1552 Rev 1.43 datasheet](https://www.sitime.com/datasheet/1552) specifies
  approximately 1 µA typical core current, but the full oscillator load,
  startup and supply integrity remain to be reviewed before release.
- 025: 0.25 mm F.Cu 3V3_DIGITAL branch R1.1→existing power trace, 2.18 mm;
  DRC 117→116. It feeds the narrow 024 branch; oscillator supply review stays open.
- 026: `HW_REV0` from R4.2 to R3.1 with two standard 0.50/0.30 mm vias,
  0.15 mm B.Cu run of 16.656 mm over In4.Cu GND_DIGITAL and short F.Cu stubs;
  DRC 116→115. The nearest existing GND_DIGITAL via at the R3 transition is 1.505 mm;
  return-path Review B remains open.
- 027: join the two `USB_SHIELD` connector groups on In3.Cu with a 0.25 mm,
  10.28 mm path around the J11 unplated mounting holes; DRC 115→114. The first direct
  8.64 mm trial was rejected by CI (`hole_clearance` +1), corrected before committing
  the candidate. The shield-to-ground coupling network remains a Review B check.
- 028: 0.30 mm B.Cu `3V3_DIGITAL` branch from TP_MCU_SWD.1 to an existing through via
  at (72.8704, 28.4649), 6.697 mm over In4.Cu GND_DIGITAL; DRC 114→113. The
  SWD test-pad supply and return remain a Review B check.
- 029: bridge `SD_D2_CARD` between R83.2 and R88.2 across the existing F.Cu
  `SD_D3_CARD` run using two 0.25/0.15 mm through vias, a 0.15 mm In3.Cu
  link and a 0.42 mm F.Cu exit, 1.421 mm total; DRC 113→112. The route
  references In4.Cu GND_DIGITAL. SD signal return and via-in-pad DFM review are open.
- 030: connect the 2.2 kΩ I2C2_SDA pull-up R14.1 to the C6 3V3_DIGITAL
  capacitor island with two 0.25/0.15 mm through vias and a 0.15 mm
  In3.Cu link plus two short F.Cu exits, 2.689 mm total; DRC 112→111.
  Pull-up supply/return and via-in-pad DFM review remain open.
- 031: connect `SD_D1_CARD` from the existing F.Cu run near R82 to R87.2
  with a 0.15 mm B.Cu detour and two 0.25/0.15 mm through vias, one at
  R87.2; 2.655 mm total over In4.Cu GND_DIGITAL. DRC 111→110 and the net
  leaves the open-connection report. SD return and via-in-pad DFM review remain open.
- 032: connect the C9 3V3_DIGITAL capacitor island to the existing R14/C6
  through via at (40.175, 31.7) with one new 0.25/0.15 mm via on its F.Cu
  supply track and a 0.30 mm In3.Cu link, 4.064 mm; DRC 110→109.
  Capacitor supply/return and small-via DFM review remain open.
- 033: join the C7/U1 3V3_DIGITAL island from the existing via at
  (44.25, 26.5) to the C6 island via at (41.75, 30.4) with 0.25 mm In3.Cu
  copper, 4.660 mm, and no added vias; DRC 109→108. The local supply and
  return path still require Review B.
- 034: escape U1.11 3V3_DIGITAL with a 0.25/0.15 mm via-in-pad and a 0.30 mm,
  2.50 mm In3.Cu link to the existing via at (44.25, 26.5); DRC 108→107.
  U1 power integrity and filled/capped via-in-pad DFM review remain open.
- 035: join the U3-side I2C2_SCL_BUS F.Cu run to the U4-side through via at
  (65.6851, 38.1701) using one 0.25/0.15 mm via on the F.Cu track and a
  0.15 mm In3.Cu route, 9.820 mm; DRC 107→106. I2C rise-time and digital
  return-path review remain open.
- 036: bridge SIM1_RST_CONN from U14.3 to R50.2 with two 0.25/0.15 mm vias,
  a 0.15 mm In3.Cu route and a short F.Cu exit, 4.605 mm total; DRC 106→105.
  The F.Cu stub is over In1.Cu GND_DIGITAL while the In3.Cu route is over
  In4.Cu GND_MODEM. The mixed-domain return transition and via-in-pad DFM
  are unresolved Review B items; this is not a released SIM route.
- 037: feed the 10 kΩ SD_DET pull-up R90.1 from the nearby 3V3_DIGITAL F.Cu
  track at (80.01, 20.5) via two 0.25/0.15 mm through vias, a 0.15 mm B.Cu
  link and a short F.Cu exit, 3.198 mm total; DRC 105→104. Pull-up supply
  and small-via DFM review remain open.
- 038: connect U27.2 `CELL_DBG_RXD_TP` to the existing via at (40.3804,
  57.475) with one 0.25/0.15 mm near-pad via, a short F.Cu stub and 0.15 mm
  In3.Cu detour, 7.327 mm total; DRC 104→103. The F.Cu stub references
  In1.Cu GND_DIGITAL, while the In3.Cu path is screened against In4.Cu
  GND_MODEM. Mixed-domain return, nearby PDM coupling and filled/capped
  near-pad via DFM remain unresolved Review B items.
- 039: join the upper 3V3_DIGITAL F.Cu track island near (45.6069, 20.562)
  to the existing B.Cu branch at (44.34, 23.5) with one 0.25/0.15 mm
  through via and a 0.15 mm B.Cu route, 3.400 mm total; DRC 103→102.
  Test-pad supply/return and small-via DFM review remain open.
- 040: join FB1.1 `3V8_MODEM` to the existing 0.8 mm B.Cu supply run
  at (39, 52) with a 0.50/0.30 mm via inside the bead's SMD pad at
  (38.5, 52) and a 0.8 mm, 0.5 mm long B.Cu tie; DRC 102→101.
  The modem burst current, power integrity and filled/capped via-in-pad
  manufacturing process require Review B; DRC alone cannot release this feed.

Remaining 101 open connections span 64 nets: `3V3_DIGITAL` 12, `1V8_MIC` 8, `AAD_CFG_1V8_FANOUT` 5,
`SIM2_DET` 3, and 73 others. Of 36 distinct U1 pads now appearing in the open-connection report, the earlier 009
first-pass 0.25/0.15 mm via-in-pad clearance scan admitted only 13 of 40; most others hit existing B.Cu/In3 copper. A clean
route requires placement/rip-up and local power/return design, followed by native DRC and SI/PI review.

Do not copy 040 to `hardware/kicad/native/PCB-MAIN`: Review B, complete connectivity, SI/PI/DFM and CAM are open.

## 8. Locality scan and relief targets after 033

A geometry scan of the remaining F.Cu pad-to-pad DRC pairs within 15 mm
(0.15 mm trial width, 0.20 mm copper clearance, 0.25 mm hole clearance,
0.25/0.15 mm candidate-process through vias, In4.Cu GND_DIGITAL reference)
found no further unobstructed straight two-via route. The C6→R14 case was
consumed by 030. The R14→C9 disconnection was subsequently closed by a
via on the existing C9 track in 032; 033 joined C7 through two existing vias.
This is a screening result, not proof that all push-and-shove routes fail.

Near-term layout relief targets from the same scan:

| Open pair | Obstacle / required action |
|---|---|
| U3.2→U3.9, 3V3_DIGITAL, 1.53 mm | Package pads block F.Cu; a through via at U3.2 meets GNSS_TX_U9 on In3.Cu and NOR_IO3_U2 on B.Cu. Requires local escape/placement or rip-up. |
| R49.2→C53.1, SIM2_DET, 2.15 mm | F.Cu 3V3_DIGITAL blocks the direct path; the sampled pad-neighbourhood via positions are occupied on In3/B.Cu. Requires local rip-up. |
| R86.2→R81.2, SD_D0_CARD, 3.50 mm | A 3V3_DIGITAL branch occupies both inner/back-side escape space near R86; sampled short via positions fail. Requires local channel relief with SD return-path review. |

The B.Cu test-pad search likewise found no further clean direct pad-to-existing-via
join; the short CELL_DBG_TXD_TP candidate from TP_CELL_DBG.2 to the existing
via at (46.474, 31.7499) is blocked by NOR_IO3_U1 and has no unobstructed
local B.Cu detour in the sampled corridor. Manual push-and-shove, selective
rip-up and U1 breakout remain the critical path to zero open connections.
