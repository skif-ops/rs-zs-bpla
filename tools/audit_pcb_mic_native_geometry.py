#!/usr/bin/env python3
"""Independent second-control geometry audit for the generated PCB-MIC Rev.A board.

This script deliberately does not import the PCB generator. Expected dimensions are
re-stated from controlled manufacturer data and the frozen Rev.A annulus discretization
so a generator regression cannot make both creation and verification wrong in the same
way.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pcbnew


def mm_pos(item):
    p = item.GetPosition()
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def mm_size(pad):
    s = pad.GetSize()
    return pcbnew.ToMM(s.x), pcbnew.ToMM(s.y)


def close(actual: float, expected: float, tol: float, label: str) -> None:
    if abs(actual - expected) > tol:
        raise RuntimeError(f"{label}: {actual:.6f} mm != {expected:.6f} mm +/- {tol:.6f}")


def angle_error_180(actual_deg: float, expected_deg: float) -> float:
    """Smallest angular error for a rectangle, whose orientation repeats every 180 deg."""
    return abs(((actual_deg - expected_deg + 90.0) % 180.0) - 90.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    args = ap.parse_args()

    board = pcbnew.LoadBoard(str(args.board))
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    if "MK1" not in fps or "J1" not in fps:
        raise RuntimeError(f"required footprints missing from native board: {sorted(fps)}")

    mk1 = fps["MK1"]
    pads = list(mk1.Pads())
    numbered = {}
    for pad in pads:
        numbered.setdefault(str(pad.GetNumber()), []).append(pad)

    # Controlled TDK peripheral land geometry after the fixed 270-degree Rev.A rotation.
    expected = {
        "1": ((11.37, 14.58), (0.522, 0.725)),
        "2": ((11.37, 15.40), (0.522, 0.725)),
        "4": ((10.93, 17.42), (0.300, 0.300)),
        "5": ((13.07, 17.42), (0.300, 0.300)),
        "6": ((12.63, 15.40), (0.522, 0.725)),
        "7": ((12.63, 14.58), (0.522, 0.725)),
    }
    for number, (expected_xy, expected_wh) in expected.items():
        candidates = numbered.get(number, [])
        if len(candidates) != 1:
            raise RuntimeError(f"MK1 pad {number}: expected exactly one, got {len(candidates)}")
        pad = candidates[0]
        x, y = mm_pos(pad)
        w, h = mm_size(pad)
        close(x, expected_xy[0], 0.002, f"MK1 pad {number} X")
        close(y, expected_xy[1], 0.002, f"MK1 pad {number} Y")
        close(w, expected_wh[0], 0.002, f"MK1 pad {number} W")
        close(h, expected_wh[1], 0.002, f"MK1 pad {number} H")

    # TDK Figure 36: GND land OD 1.625 mm, ID 1.025 mm.
    # Rev.A discretization uses 32 rectangles. Their H=0.300 mm is radial thickness;
    # W=0.145691 mm is the tangential overlap dimension. The independent orientation
    # check below proves H is radial instead of merely assuming it from size ordering.
    ring = numbered.get("3", [])
    if len(ring) != 32:
        raise RuntimeError(f"MK1 GND annulus: expected 32 controlled segments, got {len(ring)}")
    cx, cy = 12.0, 16.65
    expected_center_radius = 0.6625
    expected_tangent_w = 0.145691
    expected_radial_h = 0.300000
    center_radii = []
    radial_widths = []

    for i, pad in enumerate(ring):
        x, y = mm_pos(pad)
        w, h = mm_size(pad)
        radius = math.hypot(x - cx, y - cy)
        center_radii.append(radius)
        radial_widths.append(h)

        close(radius, expected_center_radius, 0.003, f"MK1 GND segment {i} center radius")
        close(w, expected_tangent_w, 0.003, f"MK1 GND segment {i} tangential W")
        close(h, expected_radial_h, 0.003, f"MK1 GND segment {i} radial H")

        radial_angle = math.degrees(math.atan2(y - cy, x - cx)) % 360.0
        expected_orientation = (radial_angle + 90.0) % 360.0
        actual_orientation = float(pad.GetOrientationDegrees()) % 360.0
        error = angle_error_180(actual_orientation, expected_orientation)
        if error > 0.05:
            raise RuntimeError(
                f"MK1 GND segment {i} orientation: actual {actual_orientation:.4f} deg, "
                f"expected tangential {expected_orientation:.4f} deg, error {error:.4f} deg"
            )

    effective_od = 2.0 * (
        sum(center_radii) / len(center_radii)
        + sum(radial_widths) / len(radial_widths) / 2.0
    )
    effective_id = 2.0 * (
        sum(center_radii) / len(center_radii)
        - sum(radial_widths) / len(radial_widths) / 2.0
    )
    close(effective_od, 1.625, 0.006, "MK1 effective GND OD")
    close(effective_id, 1.025, 0.006, "MK1 effective GND ID")

    # Acoustic opening: Rev.A = 0.8 mm NPTH, within TDK's 0.5..1.0 mm recommendation.
    npths = [p for p in pads if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    if len(npths) != 1:
        raise RuntimeError(f"MK1 acoustic NPTH count: expected one, got {len(npths)}")
    hole = npths[0]
    hx, hy = mm_pos(hole)
    drill = hole.GetDrillSize()
    close(hx, cx, 0.002, "MK1 acoustic NPTH X")
    close(hy, cy, 0.002, "MK1 acoustic NPTH Y")
    close(pcbnew.ToMM(drill.x), 0.800, 0.002, "MK1 acoustic NPTH drill X")
    close(pcbnew.ToMM(drill.y), 0.800, 0.002, "MK1 acoustic NPTH drill Y")

    # Connector control: 6 electrical circuits, two mechanical hold-down pads unnumbered.
    j1 = fps["J1"]
    j_numbers = [str(p.GetNumber()) for p in j1.Pads()]
    for n in ("1", "2", "3", "4", "5", "6"):
        if j_numbers.count(n) != 1:
            raise RuntimeError(f"J1 circuit {n}: expected exactly one pad")
    if j_numbers.count("") != 2:
        raise RuntimeError(f"J1 mechanical hold-down pads: expected 2 unnumbered, got {j_numbers.count('')}")

    print("PCB-MIC independent native geometry audit PASS")
    print(f"T5838 effective GND OD={effective_od:.4f} mm ID={effective_id:.4f} mm")
    print("T5838 acoustic NPTH=0.800 mm at (12.000,16.650)")
    print("T5838 annulus orientation PASS: H is radial, W is tangential")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
