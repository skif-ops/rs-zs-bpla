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
| 008 + USB connector escape 009 (`c42e099c…`) | **142** | **0 under candidate-only 6-layer via rules** |
| 009 + U1 3V3 escape 010 (`6cc9d30c…`) | 141 | 0 under the same candidate rules |
| 010 + CELL_DBG power test-pad via 011 (`ad6cbb02…`) | **140** | **0 under the same candidate rules** |

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

## 7. Bounded local routes 007–011 and current stop (2026-09-26)

The cumulative 011 is the lowest comparative-DRC-clean routing experiment on this branch. It is **not applied** to the
authoritative board. The unchanged general PCB-MAIN project rejects the 0.25/0.15 mm vias introduced in 009 and 010 (five each of
`annular_width`, `drill_out_of_range`, `via_diameter`). Under an explicit *candidate-only* JLCPCB six-layer process
overlay (`min_via_diameter=0.25`, `min_through_hole_diameter=0.15`, `min_via_annular_width=0.05`), KiCad 9 comparative
DRC is 146→142→141→140 open with zero new violations at each step. Candidate projects, comparative DRC and generators are in
`PCB-ROUTING-P2-USB-009/`, `PCB-ROUTING-P2-U1-POWER-010/` and `PCB-ROUTING-P2-CELL-DBG-011/`. The published six-layer process basis is `https://jlcpcb.com/6-layer-pcb` (minimum
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

Remaining 140 open connections span 71 nets: `3V3_DIGITAL` 33, `1V8_MIC` 9, `AAD_CFG_1V8_FANOUT` 8,
`I2C2_SCL_BUS` 4, and 86 others. Of 37 U1 pads now appearing in the open-connection report, the earlier 009
first-pass 0.25/0.15 mm via-in-pad clearance scan admitted only 13 of 40; most others hit existing B.Cu/In3 copper. A clean
route requires placement/rip-up and local power/return design, followed by native DRC and SI/PI review.

Do not copy 011 to `hardware/kicad/native/PCB-MAIN`: Review B, complete connectivity, SI/PI/DFM and CAM are open.
