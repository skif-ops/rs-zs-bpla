# PCB-MAIN routing program — status after the autorouting sessions (Rev A, 2026-09-27)

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
| 040 + U1.49 VCORE escape 041 (`53d46280…`) | **100** | **0 under the same candidate rules; VCORE PI/return and via-in-pad DFM review open** |
| 041 + western TP_EOL 3V3 branch 042 (`483f78ae…`) | **99** | **0 under the same candidate rules; test-pad supply and mixed-domain return review open** |
| 042 + PWR_GOOD test-pad branch 043 (`f6560764…`) | **98** | **0 under the same candidate rules; return transition review open** |
| 043 + I2C2_SDA_BUS test-pad branch 044 (`d3df48a6…`) | **97** | **0 under the same candidate rules; I2C rise-time/return review open** |
| 044 + local LORA_DIO1 U10/R65 link 045 (`da04ba89…`) | **96** | **0 under the same candidate rules; signal return and via DFM review open** |
| 045 + GNSS_ANT_SHORT_N U5 branch 046 (`59d2b0f0…`) | **95** | **0 under the same candidate rules; GNSS bias/RF coupling and via DFM review open** |
| 046 + GNSS_ANT_BIAS_RAW R61 branch 047 (`6658aedb…`) | **94** | **0 under the same candidate rules; bias-current/RF isolation and via DFM review open** |
| 047 + GNSS_ANT_SWITCHED R62 branch 048 (`2dee54ef…`) | **93** | **0 under the same candidate rules; GNSS bias/RF coupling and via-in-pad DFM review open** |
| 048 + local 3V3_DIGITAL In3 bridge 049 (`ca3381d9…`) | **92** | **0 under the same candidate rules; power/return and small-via DFM review open** |
| 049 + R49 rotation and local SIM2_DET relief 050 (`07904a6f…`) | **91** | **0 under the same candidate rules; SIM return and placement Review B open** |
| 050 + U23 SD_CMD_CARD escape 051 (`3bf02812…`) | **90** | **0 under the same candidate rules; SD return and via-in-pad DFM Review B open** |
| 051 + U23 SD_CK_CARD escape 052 (`77c3ebb6…`) | **89** | **0 under the same candidate rules; SD clock return and small-via DFM Review B open** |
| 052 + C19 3V3_DIGITAL feed from J_PWR.3 053 (`7ca19333…`) | **88** | **0 under the same candidate rules; power current/return and via-in-pad DFM Review B open** |
| 053 + J7.7→U15.6 SIM2_DET F.Cu link 054 (`86ea2df6…`) | **87** | **0 under the same candidate rules; SIM detect return Review B open** |
| 054 + J_PWR.5→C20.1 1V8_MIC supply link 055 (`b8dcaef5…`) | **86** | **0 under the same candidate rules; microphone supply/return Review B open** |
| 055 + U22→U21/J_MIC3 AAD_CFG bridge 056 (`eb40e9a6…`) | **85** | **0 under the same candidate rules; AAD return/audio coupling Review B open** |
| 060 + C54/J6→R50 SIM1_RST_CONN In3.Cu bridge 061 (`b733b350…`) | **80** | **0 under the same candidate rules; SIM return and small-via DFM Review B open** |
| 061 + C10/C11 VREF bypass net correction and two local 3V3 F.Cu links 062 (`ae099f30…`) | **79** | **0; nine-sheet ERC 0; analog-reference decoupling Review B open** |
| 062 + CELL_DBG_TXD_TP test-pad branch 063 (`02147cb8…`) | **78** | **0; nine-sheet ERC 0; test-pad return/DFM Review B open** |
| 063 + J_PWR.8→R103.1 FAULT branch 064 (`393f131f…`) | **77** | **0; nine-sheet ERC 0; FAULT return/DFM Review B open** |
| 064 + FAULT return GND_DIGITAL stitch 065 (`12130d52…`) | **77** | **0; nine-sheet ERC 0; return transition closer; Review B open** |
| 065 + U1.97→U13 SIM_MUX_SEL branch 066 (`f0d62adb…`) | **76** | **0; nine-sheet ERC 0; signal return and small-via DFM Review B open** |
| 066 + ten screened signal branches 067 (`22391d5e…`) | **66** | **0; nine-sheet ERC 0; 26 transitions and return/DFM Review B open** |
| 067 + six screened signal branches 068 (`d78d34cf…`) | **60** | **0; nine-sheet ERC 0; SD/PDM timing and return/DFM Review B open** |
| 068 + five screened signal branches 069 (`1c358e1e…`) | **55** | **0; nine-sheet ERC 0; LoRa/SIM timing and return/DFM Review B open** |
| 069 + four 1V8_MIC branches and FB1 output 070 (`0d968878…`) | **50** | **0; nine-sheet ERC 0; power-return/DFM Review B open** |

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

## 7. Bounded local routes 007–070 and current stop (2026-09-27)

The cumulative 070 is the latest comparative-DRC-clean routing experiment on this branch. It is **not applied** to the
authoritative board. The unchanged general PCB-MAIN project rejects the 0.25/0.15 mm vias introduced in 009 and 010 (five each of
`annular_width`, `drill_out_of_range`, `via_diameter`). Under an explicit *candidate-only* JLCPCB six-layer process
overlay (`min_via_diameter=0.25`, `min_through_hole_diameter=0.15`, `min_via_annular_width=0.05`), KiCad 9 comparative
DRC is 146→142→141→140→139→138→131→129→127→124→122→121→120→119→118→117→116→115→114→113→112→111→110→109→108→107→106→105→104→103→102→101→100→99→98→97→96→95→94→93→92→91→90→89→88→87→86→85→84→83→82→81→80→79→78→77→76→66→60→55→50 open with zero new violations at each accepted step. Candidate projects,
comparative DRC and generators are in the corresponding `PCB-ROUTING-P2-*/` directories. The published six-layer process basis is `https://jlcpcb.com/6-layer-pcb` (minimum
0.15/0.25 mm and via-in-pad option); a job-specific acceptance is still required.

- 007: eight short F.Cu links in 3V3_DIGITAL and 1V8_MIC; native DRC 156→148, no new violation.
- 008: two F.Cu branches of `GNSS_ANT_SHORT_N` from U9 to R62/C63;
  native DRC 148→146, no new violation. This status/sense net also
  reaches L2.1; L2.2 connects to `GNSS_RF_ANT_BIASED`. Bias/RF coupling
  through the 27 nH component requires explicit SI review.
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
- 041: connect U1.49 `VCORE_1V1` to the existing through via at
  (55.824, 34.9762) through a 0.25/0.15 mm via in the U1 pad and a
  0.3 mm, 3.241 mm In3.Cu link over In4.Cu GND_DIGITAL; DRC 101→100.
  VCORE supply PI, return path and filled/capped via-in-pad DFM remain
  unresolved Review B items.
- 042: connect the western 3V3_DIGITAL F.Cu island at (32.675, 18.9)
  to TP_EOL.2 on B.Cu through one 0.25/0.15 mm track via and a 0.3 mm,
  5.277 mm B.Cu route; DRC 100→99. The B.Cu route lies over the
  In4.Cu GND_MODEM region. Test-pad supply, mixed-domain return and small
  via DFM remain Review B items.
- 043: connect TP_EOL.7 `PWR_GOOD` by a 1.750 mm B.Cu stub, one
  0.25/0.15 mm off-pad via at (48.24, 24.75) and a 6.926 mm In3.Cu
  route to the existing run at (50.9, 18.6248); DRC 99→98. The end of
  the inner route crosses into the higher-priority In4.Cu GND_MODEM
  region. Return transition and small-via DFM review remain open.
- 044: connect TP_EOL.13 `I2C2_SDA_BUS` by a 1.768 mm B.Cu stub,
  one 0.25/0.15 mm off-pad via at (63.23, 24.75) and a 5.330 mm
  In3.Cu route to the existing SDA run at (62.833, 30.0044); DRC 98→97.
  I2C rise-time, digital return and small-via DFM review remain open.
- 045: join R65.1 to U10.13 `LORA_DIO1` through two 0.25/0.15 mm
  vias, a 1.500 mm F.Cu exit and a 6.377 mm In3.Cu route over
  In4.Cu GND_DIGITAL; DRC 97→96. The long leg to U1.17 remains open.
  Signal return and via-in-pad/small-via DFM review remain open.
- 046: join U5.2 to the existing `GNSS_ANT_SHORT_N` F.Cu run near
  (49.6776, 55.194) with two 0.25/0.15 mm vias and an 11.808 mm,
  0.15 mm B.Cu route over In4.Cu GND_DIGITAL; DRC 96→95. L2.1 on
  the same net remains disconnected. The L2 link to GNSS_RF_ANT_BIASED
  makes bias/RF coupling, return and via-in-pad DFM open Review B items.
- 047: join R61.1 to the existing `GNSS_ANT_BIAS_RAW` F.Cu run at
  (54.0168, 55.183) using two 0.25/0.15 mm vias and a 0.3 mm,
  6.049 mm In3.Cu route over In4.Cu GND_DIGITAL; DRC 95→94.
  GNSS active-antenna bias current, RF isolation and filled/capped
  via-in-pad DFM remain open. The Q4.4 branch is still disconnected.
- 048: join R62.1 `GNSS_ANT_SWITCHED` to the existing 0.3 mm B.Cu
  run at (53.5, 51.25) with one 0.25/0.15 mm via inside the R62 pad
  at (52.8, 51.25) and a 0.7 mm B.Cu link; DRC 94→93. The Q4.3
  branch remains open. GNSS bias/RF coupling and filled/capped
  via-in-pad DFM require Review B.
- 049: join two `3V3_DIGITAL` F.Cu islands near U1 with a 2.569 mm,
  0.15 mm In3.Cu segment, two 0.25/0.15 mm through vias and a 0.125 mm,
  0.25 mm F.Cu exit. The nearest In4.Cu reference is GND_DIGITAL along
  the entire inner segment. Native KiCad 9 comparative DRC 93→92 with no
  new violations (Actions run 36289895793). The narrow power segment,
  return/current budget and small-via DFM remain open for Review B.
- 050: rotate R49 180° in place to put its `3V3_DIGITAL` pad on the
  western side and `SIM2_DET` pad on the eastern side. Replace two old
  3V3 segments with a 0.725 mm, 0.30 mm F.Cu feed; add a 1.665 mm,
  0.20 mm F.Cu SIM2_DET link from R49.2 to C53.1. Both short lines
  remain over the In1.Cu GND_DIGITAL zone. The R49 reference remains
  at its original board position and is made upright. Native KiCad 9
  comparative DRC 92→91 with no new violations (Actions run
  36290574771). The long U1.4 leg, SIM return path and local placement
  review remain open.
- 051: remove two local F.Cu `GND_DIGITAL` segments and a ground via that
  block U23.4, then place a 0.25/0.15 mm ground via in U23.3. Escape
  `SD_CMD_CARD` from U23.4 on F.Cu to a 0.25/0.15 mm via at
  (81.8, 21.5), and route a 0.20 mm In3.Cu leg to a second such via
  in R80.2 at (83.325, 24.25). The inner leg is over In4.Cu
  GND_DIGITAL. Native KiCad 9 comparative DRC 91→90 with no new
  violations (Actions run 36292497980); `SD_CMD_CARD` leaves the open
  report. Ground relocation, SD return path and filled/capped via-in-pad
  DFM require Review B.
- 052: escape U23.5 `SD_CK_CARD` on F.Cu to a 0.25/0.15 mm via at
  (81.5, 22.0), then use a 4.448 mm, 0.20 mm In3.Cu leg to another
  0.25/0.15 mm via on the existing B.Cu clock run at (79.5, 18.0272).
  The inner leg lies over In4.Cu GND_DIGITAL. Native KiCad 9 comparative
  DRC 90→89 with no new violations (Actions run 36292883688); the net
  leaves the open report. SD clock return, timing and small-via DFM
  remain Review B items.
- 053: join C19.1's `3V3_DIGITAL` F.Cu island to the existing J_PWR.3
  through-hole pad using one 0.25/0.15 mm via in C19.1 and two
  0.30 mm B.Cu segments via (12.75, 25.55), 7.094 mm total. The B.Cu
  leg is in the In4.Cu GND_MODEM zone. Native KiCad 9 comparative DRC
  89→88 with no new violations (Actions run 36293598450). Supply
  current, decoupling loop, mixed-domain return and filled/capped
  via-in-pad DFM remain Review B items.
- 054: join J7.7 to U15.6 on `SIM2_DET` through the north F.Cu
  corridor using seven 0.15 mm segments, 15.817 mm total, with no new
  vias. The whole route lies within the In1.Cu GND_DIGITAL zone
  outline. Native KiCad 9 comparative DRC 88→87 with no new
  violations (Actions run 36297558328). The remaining `SIM2_DET`
  open branch terminates at U1.4; detect-signal return and connector
  behaviour remain Review B items.
- 055: join the J_PWR.5 `1V8_MIC` supply to C20.1 with four
  0.30 mm F.Cu segments, 10.724 mm total, without new vias. The
  route stays inside both the In1.Cu GND_DIGITAL and In2.Cu GND_MIC
  zone outlines. Native KiCad 9 comparative DRC 87→86 with no new
  violations (Actions run 36298313891). Microphone supply current,
  decoupling loop, mixed-domain return and audio coupling remain
  Review B items.
- 056: join the U22.5 `AAD_CFG_1V8_FANOUT` branch to the existing
  U21/J_MIC3 F.Cu run at (94.7325, 67.6) with a direct 0.20 mm,
  13.788 mm F.Cu segment and no new vias. The route lies within the
  In1.Cu GND_DIGITAL, In2.Cu GND_MIC and In4.Cu GND_DIGITAL zone
  outlines. Native KiCad 9 comparative DRC 86→85 with no new
  violations (Actions run 36299911437). AAD fanout return and audio
  coupling require Review B; the other four open fanout joins remain.
- 057: join J_MIC3.1 to J_MIC4.1 on `1V8_MIC` with five 0.30 mm F.Cu
  segments, 22.0361 mm total, without new vias. The route stays inside
  the In1.Cu GND_DIGITAL, In2.Cu GND_MIC and In4.Cu GND_DIGITAL zone
  outlines; its southernmost point is 5.3 mm from the board edge.
  Native KiCad 9 comparative DRC 85→84 with no new violations
  (Actions run 36300939051). Microphone supply current, decoupling and
  mixed-domain return remain Review B items.
- 058: join the F.Cu `3V3_DIGITAL` run at (59.75, 36.0) to U1.47
  with a 0.50 mm F.Cu stub and a 3.8688 mm, 0.25 mm In3.Cu path.
  Two 0.25/0.15 mm through vias are added, including one in U1.47.
  The In3.Cu route lies within the In1.Cu GND_DIGITAL, In2.Cu
  GND_MIC and In4.Cu GND_DIGITAL zone outlines. Native KiCad 9
  comparative DRC 84→83 with no new violations (Actions run
  36302332039). U1 supply current, return transition and filled/capped
  via-in-pad DFM remain Review B items.
- 059: join the C34 `3V3_DIGITAL` branch to the existing F.Cu run at
  (26.9, 29.175) with a 0.25 mm, 8.3784 mm B.Cu route and two
  0.25/0.15 mm through vias, one in C34.1. The route lies within the
  In1.Cu GND_DIGITAL, In2.Cu GND_MIC and In4.Cu GND_DIGITAL zone
  outlines. Native KiCad 9 comparative DRC 83→82 with no new
  violations (Actions run 36302625651). C34 supply current, return
  transition and filled/capped via-in-pad DFM remain Review B items.
- 060: extend the C34 `3V3_DIGITAL` branch from the existing through via
  at (26.9, 29.175) to the existing through via at (32.675, 18.9) with
  nine 0.30 mm In3.Cu segments, 15.2072 mm total, without new vias.
  The route lies within the In1.Cu GND_DIGITAL, In2.Cu GND_MIC and
  In4.Cu GND_DIGITAL zone outlines. Native KiCad 9 comparative DRC
  82→81 with no new violations (Actions run 36303052402). The longer
  3V3 supply path, current budget and mixed-domain return need Review B.
- 061: connect the C54/J6 `SIM1_RST_CONN` F.Cu island from a new
  0.25/0.15 mm through via at (18.175, 16.0), outside the C54 pad, to
  the existing R50.2 via at (24.075, 16.7). The new 0.15 mm In3.Cu
  segment is 5.9414 mm long and lies within the In4.Cu GND_MODEM
  zone outline. Native KiCad 9 comparative DRC 81→80 with no new
  violations (Actions run 36304585746). SIM reset return through the
  GND_MIC-adjacent In3 layer and small-via DFM remain Review B items.
- 062: correct the otherwise isolated C10/C11 `VREF+` bypass pads to
  `3V3_DIGITAL`, in accordance with the U1 pin-20 authority, on an isolated
  copy of the MCU schematic and PCB. Two 0.25 mm F.Cu segments join C11.1
  to C9.1 and C10.1 to C8.1 (2.50 mm total, no vias). The copied full
  hierarchy has native ERC 0; filled-board comparative DRC is 80→79
  with no new errors (Actions run 36305521530). The exact passive-support
  and routing-authority delta is staged but unapplied. Analog-reference
  decoupling and the remaining 3V3 connections need Review B.
- 063: connect the `CELL_DBG_TXD_TP` run's existing through via at
  (46.474, 31.7499) to a new 0.25/0.15 mm through via at (47.9, 31.4)
  with 1.4683 mm of 0.15 mm In3.Cu trace, then 2.1563 mm of B.Cu trace
  to TP_CELL_DBG.2. The route is within the In1.Cu GND_DIGITAL,
  In2.Cu GND_MIC and In4.Cu GND_DIGITAL zone outlines. Native KiCad 9
  full-hierarchy ERC is 0; filled-board comparative DRC is 79→78 with
  no new errors or schematic-parity differences (Actions run 36306717954).
  The nearest GND_DIGITAL stitching via to the new transition is about
  3.0 mm; test-pad access, mixed-domain return and small-via DFM remain
  Review B items.
- 064: connect J_PWR.8 to R103.1 on `FAULT` with four 0.15 mm B.Cu
  segments (15.1362 mm) and one 0.15 mm F.Cu stub (1.5876 mm), using a
  new 0.25/0.15 mm through via at (25.1, 22.7) outside the R103 pad.
  Both legs lie within the In1.Cu GND_DIGITAL, In2.Cu GND_MIC and
  In4.Cu GND_DIGITAL zone outlines. Native KiCad 9 full-hierarchy ERC
  is 0; filled-board comparative DRC is 78→77 with no new errors or
  schematic-parity differences (Actions run 36307648451). The TP_EOL.8
  FAULT branch, signal return and small-via DFM remain Review B items.
- 065: add one 0.50/0.30 mm GND_DIGITAL through via at (25.1, 23.9),
  1.20 mm from the FAULT transition added by 064. The via lies within
  the In1.Cu and In4.Cu GND_DIGITAL zone outlines; minimum screened
  other-net copper clearance is 0.3671 mm. Native KiCad 9 full-hierarchy
  ERC is 0; filled-board comparative DRC remains 77 open with no new
  errors or schematic-parity differences (Actions run 36308501262).
  Ground-domain return, TP_EOL.8 and DFM remain Review B items.
- 066: connect `SIM_MUX_SEL` U1.97 to the existing U13 branch through
  two 0.25/0.15 mm vias at (47.5, 21.4) and (41.6, 20.7), two short
  F.Cu links and a three-segment B.Cu route (8.7609 mm total). The
  transitions are 1.2134 and 1.4792 mm from existing GND_DIGITAL
  stitching vias. The route lies inside the In1.Cu GND_DIGITAL,
  In2.Cu GND_MIC and In4.Cu GND_DIGITAL reference outlines. Native
  KiCad 9 full-hierarchy ERC is 0; filled-board comparative DRC is
  77→76 with no new errors or schematic-parity differences (Actions
  run 36309060929). Signal return, SIM switching integrity and small-via
  DFM remain Review B items.
- 067: add ten independent, exact-geometry-screened connections:
  `AAD_CFG_1V8_FANOUT`, `CELL_DTR_U16`, `FAULT`, `I2C2_SCL_U1`,
  `I2C2_SDA_U1`, `NRST`, `REV_STRAP0`, `SIM_MUX_EN`, `SWDIO`, and
  `USB_VBUS_SENSE`. The 0.15 mm routes total 177.2818 mm and use 26
  0.25/0.15 mm candidate-process through vias. The cross-domain AAD
  and cellular routes remain Review B return-path items. Native KiCad
  9.0.9 full-hierarchy ERC is 0; filled-board comparative DRC is
  76→66 with zero new errors or warnings (Actions run 36310099284).
  The `SIM_MUX_EN` termination is snapped to its existing track endpoint
  to avoid a dangling-track warning.
- 068: add six connections on `HW_REV1`, `I2C2_SCL_BUS`,
  `LORA_NSS_U1`, `PDM_DATA3`, `SD_D2_CARD` and `TAMPER_IN_U1`.
  Total new trace length is 140.6642 mm with 19 small through vias.
  The SD_D2 In3 route ends at the exact existing via centre to avoid
  a dangling-track warning. Native KiCad 9.0.9 full-hierarchy ERC is
  0; comparative filled-board DRC is 66→60 with zero new errors or
  warnings (Actions run 36310559015). SD/PDM timing, signal return
  and small-via DFM remain Review B items.
- 069: add five connections on `AAD_CFG_1V8_U7`, `LORA_RESET_N`,
  `LORA_SCK_U10`, `SIM1_DET` and `SWCLK`. The 0.15 mm tracks total
  117.8945 mm with twelve 0.25/0.15 mm vias; `SIM1_DET` uses a
  candidate-only via-in-pad escape. The F.Cu and B.Cu legs were
  screened against their nearest In1.Cu and In4.Cu reference zones;
  In3.Cu against In2.Cu. Native KiCad 9.0.9 full-hierarchy ERC is
  0; comparative filled-board DRC is 60→55 with zero new errors or
  warnings (Actions run 36310817626). Via-in-pad, LoRa/SIM timing,
  return and DFM remain Review B items.
- 070: join four microphone supply islands on `1V8_MIC` with 0.25 mm
  traces and nine 0.50/0.30 mm through vias; connect FB1.2 to the
  existing `3V8_MODEM_BB` via with a 3.61 mm 0.8 mm F.Cu branch.
  All new traces total 100.7369 mm. The FB1 branch is over the
  In1.Cu GND_DIGITAL outline; a modem current-return transition is
  explicitly a Review B item. Native KiCad 9.0.9 full-hierarchy
  ERC is 0; comparative filled-board DRC is 55→50 with zero new
  errors or warnings (Actions run 36311257488). Mic power quietness,
  supply voltage drop and via DFM also remain Review B items.

Remaining 50 open connections span 38 nets: `3V3_DIGITAL` 6, `1V8_MIC` 2, `AAD_CFG_1V8_FANOUT` 3,
`SIM2_DET` 1, and 38 others. The earlier 009
first-pass 0.25/0.15 mm via-in-pad clearance scan admitted only 13 of 40; most others hit existing B.Cu/In3 copper. A clean
route requires placement/rip-up and local power/return design, followed by native DRC and SI/PI review.

Do not copy 070 to `hardware/kicad/native/PCB-MAIN`: Review B, complete connectivity, SI/PI/DFM and CAM are open.

## 8. Locality scan and relief targets through 040

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
| U23.4→SD_CMD_CARD run, 2.85 mm | Addressed by local ground relocation and In3.Cu route in candidate 051; return-path and via-in-pad DFM Review B remain open. |
| FB1.2→3V8_MODEM_BB, 3.68 mm | The now-connected 3V8_MODEM B.Cu feed lies between FB1.2 and the existing BB run. On In3.Cu the long CELL_USB_VBUS trace at x≈37.57 blocks a short direct power branch. Needs power-channel relief with burst-current and PI assessment. |

The B.Cu test-pad search found no clean direct pad-to-existing-via
join; the direct CELL_DBG_TXD_TP run from TP_CELL_DBG.2 to the existing
via at (46.474, 31.7499) was blocked by NOR_IO3_U1. Candidate 063
uses a new via and a short In3.Cu link to close this branch. Manual push-and-shove, selective
rip-up and U1 breakout remain the critical path to zero open connections.

After 041, a 0.15 mm grid search of the F.Cu-only open pairs within 12 mm
(0.20 mm copper clearance, 2.5 mm bounding-box margin) found no other
local path among the sampled digital/control and power pairs. It found a
~9.6 mm path from the 0.8 mm `3V8_MODEM_RF` feed to C47 only at 0.4 mm
width; the 0.6 and 0.8 mm trials had no corridor. The narrow and long
RF-supply capacitor branch over In1.Cu GND_DIGITAL was not accepted.
Move/repack the modem bulk/decoupling group and review its supply and return
instead. This grid scan is a screening result, not a proof of unroutability.

Later inner/back-layer probes found a narrow 3V3 route of about 8.4 mm
from the supply run to C34 (100 nF); it was not accepted because the
long narrow decoupling loop and GND_MODEM reference need placement/power
review. The `GNSS_ANT_BIAS_RAW` Q4.4 branch likewise admits only a
roughly 16 mm back-side detour in the sampled corridor; it was left open
for local placement/channel relief and GNSS bias/RF review.
The `GNSS_ANT_SWITCHED` Q4.3 leg has only a roughly 14.7 mm In3.Cu
or 23.6 mm B.Cu detour to the existing through via in the sampled
channel. It remains open pending shorter RF-bias-network layout relief.

## 9. Native KiCad 9 continuation through candidate 088 (2026-09-27)

Draft PR #93, branch `feature/pcb-main-completion`, retains PCB-MAIN 003 as the
authoritative board. Comparative filled-board KiCad 9.0.9 checks under the
candidate-only 0.25/0.15 mm via rules gave:

| Candidate | Open connections | New DRC violations | ERC violations |
|---|---:|---:|---:|
| 071 | 48 | 0 | 0 |
| 072 | 45 | 0 | 0 |
| 073, UUID repair | 45 | 0 | 0 |
| 074, GNSS bias branches | 43 | 0 | 0 |
| 075, microphone rail branches and LORA_TXEN | 40 | 0 | 0 |
| 076, U3 local 3V3 relief | 39 | 0 | 0 |
| 077, 3V3_DIGITAL In3 bridge | **38** | **0** | **0** |
| 078, U1 3V3 escape relief | **37** | **0** | **0** |
| 079, AAD_CFG_1V8_FANOUT branch | **36** | **0** | **0** |
| 080, 3V8_MODEM_RF C47 branch | **35** | **0** | **0** |
| 081, CELL_DBG_RXD_TP debug branch | **34** | **0** | **0** |
| 082, CELL_USB_BOOT_TP test branch | **33** | **0** | **0** |
| 083, CELL_USIM_CLK_1V8 branch | **32** | **0** | **0** |
| 084, 3V8_MODEM_RF C46 branch | **31** | **0** | **0** |
| 085, U19 PDM_DATA1 relief | **30** | **0** | **0** |
| 086, R4 3V3 relief | **29** | **0** | **0** |
| 087, SD_D3_CARD U23/D11 relief | **28** | **0** | **0** |
| 088, SD_D3_CARD upper branch | **27** | **0** | **0** |

076 moves the existing GND_DIGITAL via next to U3.6 from
(66.099999, 30.600) to (66.099999, 30.650) mm and changes it from
0.50/0.30 to 0.25/0.15 mm. A 1.525 mm, 0.15 mm F.Cu segment then joins
U3.2 and U3.9 on 3V3_DIGITAL. This preserves the ground connection and
clears the tight local channel. Its generator, candidate board, filled-board
DRC and ERC evidence are under `PCB-ROUTING-P2-U3-POWER-076/`.

077 bridges the 3V3_DIGITAL gap between the (16.975, 34.600) and
(17.175, 28.850) mm copper clusters. It adds 8.027 mm of 0.25 mm tracks
on F.Cu and In3.Cu and two 0.25/0.15 mm through vias. The route was screened
against the existing copper and ground reference; filled-board native KiCad
9.0.9 DRC went from 39 to 38 without new violations, and the nine-sheet
ERC remained at zero. The generator, route coordinates, candidate board,
and reports are under `PCB-ROUTING-P2-ASTAR-077/`. Power and DFM Review B
remain open.

078 moves the B.Cu CELL_RESET_N_CMD and In3.Cu TEST_UART_RX_U1
segments beside U1.27, then joins its 3V3_DIGITAL pad to an In3.Cu
branch with two candidate-process vias. The filled-board native DRC went
from 38 to 37 without new violations. 079 adds 52.332 mm of AAD_CFG_1V8_FANOUT
copper, including 49.922 mm on B.Cu above the In4.Cu GND_DIGITAL outline,
and two candidate-process vias. Its right via was moved onto an existing
same-net F.Cu track to clear a copper sliver. The filled-board native DRC
went from 37 to 36 without new violations; ERC remains zero. Return path
across ground domains, timing, and small-via DFM remain open for Review B.

080 joins the C47 10 pF RF supply pad with a 4.324 mm, 0.40 mm F.Cu
branch and no vias. Native filled-board DRC went 36→35 with no new
violations. All of this branch lies over In1.Cu GND_DIGITAL, whereas
the net is assigned to GND_MODEM. RF decoupling current, return path and
the narrower branch require PI/Review B before any application.

081 joins the CELL_DBG_RXD_TP test pad to its resistor branch with
30.661 mm of copper and four candidate-process vias. Native filled-board
DRC went 35→34 with no new violations, ERC zero. Its 17.847 mm In3.Cu
section lies over GND_MIC and the outer sections over GND_DIGITAL for a
modem-domain debug signal. Cross-domain return and fixture timing need
Review B. An independent CELL_USB_BOOT_TP grid proposal shares this
channel and shorts to 081, so it was rejected.

Re-running the grid search after 081 found a separate CELL_USB_BOOT_TP
path, accepted as 082. It is 54.058 mm with six candidate-process vias;
its filled-board DRC went 34→33 with no new violations. The route is
long and crosses the MIC/digital reference areas. 083 adds a 36.252 mm
USIM clock branch with three vias, including 26.955 mm on In3.Cu over
GND_MIC. DRC went 33→32 with no new violations. Signal timing, return
and DFM are Review B holds.

084 joins the C46 33 pF RF supply capacitor with 22.062 mm of 0.40 mm
copper and three vias, 17.265 mm of it on B.Cu above GND_MODEM. DRC
went 32→31 without new violations. The RF decoupling loop and brief
MIC/digital ground crossings need PI and return-path Review B. 085
reroutes PDM_CLK on B.Cu and the existing 0.80 mm 3V8_MODEM In3.Cu
feed near U19, then connects PDM_DATA1 through a 0.25/0.15 mm via in
U19.2. The nearby GND_MIC via is moved and resized to 0.25/0.15 mm,
with a 0.348 mm F.Cu link to preserve ground continuity. Filled-board
DRC went 31→30 without new violations; ERC stays zero. U19 via-in-pad,
microphone return, modem supply and finished-drill DFM need Review B.

086 removes a redundant GND_DIGITAL stitching via at (56.9, 20.0) mm
that blocked the R4.1 escape, then joins R4.1 to its upper 3V3_DIGITAL
source with 4.028 mm of 0.25 mm copper on F.Cu/In3.Cu and two
0.25/0.15 mm vias. Filled-board DRC went 30→29 with no new violations;
ERC remains zero. The loss of this ground stitch, local return path and
finished-drill DFM need Review B before any release.

087 moves ESD diode D11 0.4 mm left, restores its 3V3_DIGITAL and
GND_DIGITAL F.Cu connections, then escapes SD_D3_CARD from U23.2 to
the existing card-side trace. The signal route is 21.096 mm of 0.15 mm
copper on F.Cu/B.Cu/In3.Cu with three 0.25/0.15 mm vias. Filled-board
DRC went 29→28 without new violations and ERC stayed zero. Card-bus
timing/skew, return, ESD placement and via DFM need Review B.

088 joins the upper SD_D3_CARD source to the U23/card-side branch with
14.740 mm of 0.15 mm F.Cu/B.Cu copper and two 0.25/0.15 mm vias.
Filled-board DRC went 28→27 without new violations, ERC zero. The
combined 087–088 SDIO length, skew and return require Review B.

Post-088 probes examined all 27 remaining airwires: the unmodified
0.15/0.25 mm grid router found **zero** directly routeable gaps.
Six R89 placement experiments for the adjacent SD_D0_CARD channel
created two open connections at R89 and 4–16 new DRC errors apiece,
so none was adopted. Removing eleven local LORA_DIO1 In3 segments
did not yield an alternate path around a prospective U1.27 3V3 via.
A single-neighbor rip-up screen found only obstructed or long
routes (for example GNSS_TX_U1 69–79 mm with 9–10 vias and
LORA_SCK_U1 51–64 mm with 5–8 vias). The PDM_DATA2 virtual
U1 via at (52.5, 22.1) mm conflicts with NRST and BOOT0 copper
and was rejected before native DRC. The next routing work needs
coordinated placement relief and rerouting in the U1, SDIO and
power corridors; the accepted candidate remains 088 with 27 open.

The 075 routes total 107.8935 mm and 15 new vias, including a 45.1553 mm
1V8_MIC branch; they are routing experiments. Power integrity, microphone
noise, LoRa return path, and via-in-pad/finished-drill DFM require Review B.
A reference-aware GNSS_TX_U1 A* probe after 075 needed roughly 82 mm and
seven vias to join points only 19.95 mm apart; it was rejected rather than
added to the candidate. The SD_D0_CARD local F.Cu trial after 076 reduced
one open connection but shorted SD_D2_U1; it was rejected as well.
After 077, additional grid routes for LSE_IN, GNSS_TX_U1 and the USB
connector pair required about 91/83/50 mm and 11/7/3 transitions respectively;
the LSE placement and USB 90-ohm pair constraints rule out accepting them.
The U1.27 3V3 escape obstruction was relieved in 078. A subsequent
Freerouting 2.4.1 session supplied the AAD branch in 079; its other
session copper did not yield another clean connection. The 079 short-gap
reference-aware grid probe found no unobstructed path for its ten closest
pairs. Trial PDM_DATA1_1V8 and R4 power routes reduced the open count
by one but caused new copper short/clearance violations, so neither
was incorporated.

The current target of zero open connections has **not** been met. Further
placement relief and selective rip-up around U1, SDIO, and the modem power
group are needed. No candidate in this section is applied to PCB-MAIN 003 or
released for manufacture.
