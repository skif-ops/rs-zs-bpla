# PCB-MAIN SD_D0_CARD corridor relief screen (2026-09-27)

Baseline: candidate 062 in draft PR #93, native KiCad 9 comparative DRC
79 unconnected items. This screen makes **no PCB change**.

The short `SD_D0_CARD` open pair R86.2 (85.075, 23.0) → R81.2
(88.575, 23.0) is 3.50 mm center-to-center. A straight 0.15 mm F.Cu
segment with 0.20 mm clearance intersects the existing R89.1
`3V3_DIGITAL` pad, R89.2 `SD_D3_CARD` pad, R81.1 `SD_D0_U1` pad,
the 3V3 branch at x≈85.55–86.18 and the local SD_D3 copper at
x≈86.83–87.57. Deleting only the 3V3 trace cannot open this corridor;
the pad placement also blocks it.

R81.2 cannot use a 0.25/0.15 mm *through* via in its current position:
`TP_BLE_SWD.3` (`NRF_SWCLK`) occupies B.Cu x=88.23–89.93,
y=22.15–23.85, covering R81.2 at (88.575, 23.0). A 0.1 mm grid
scan of off-pad via points within 1.5 mm of R81.2, requiring 0.20 mm
all-layer copper clearance and a clear short F.Cu stub, found **zero**
legal points in x=87.7–89.4, y=22.2–24.2. The U24/J12 side of this net
has nine sampled via landing points on its existing F.Cu run; the R81
side is the blocker.

Next controlled placement study: repack R81/R89 and their local SD
traces while keeping the series resistors and return/timing constraints;
compare the resulting filled-board native DRC. Any proposal to move
`TP_BLE_SWD` must preserve the closed fixture coordinates or explicitly
update and validate that fixture. A blind via or a via under the existing
test pad has not been adopted. `SD_D0_CARD` still has two open items,
including the U24/J12 branch and R86/R81 branch.
