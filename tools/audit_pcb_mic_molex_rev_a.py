#!/usr/bin/env python3
"""Independent audit of the PCB-MIC Rev.A Molex 5040500691 land pattern.

Expected values are restated directly from Molex customer drawing 5040500000-SD Rev.B
and are deliberately not imported from the normalization script or EasyEDA reference.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pcbnew

EXPECTED_VALUE = "5040500691"
EXPECTED_SIGNAL_W = 0.60
EXPECTED_SIGNAL_H = 1.00
EXPECTED_PITCH = 1.50
EXPECTED_SPAN_B = 7.50
EXPECTED_NAIL_W = 1.25
EXPECTED_NAIL_H = 1.80
EXPECTED_ROW_GAP = 3.79


def to_mm(value: int) -> float:
    return float(pcbnew.ToMM(value))


def xy(pad) -> tuple[float, float]:
    p = pad.GetPosition()
    return to_mm(p.x), to_mm(p.y)


def wh(pad) -> tuple[float, float]:
    s = pad.GetSize()
    return to_mm(s.x), to_mm(s.y)


def close(actual: float, expected: float, tol: float, label: str) -> None:
    if abs(actual - expected) > tol:
        raise RuntimeError(f"{label}: {actual:.5f} mm != {expected:.5f} mm +/- {tol:.5f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    args = ap.parse_args()

    board = pcbnew.LoadBoard(str(args.board))
    refs = {fp.GetReference(): fp for fp in board.GetFootprints()}
    if "J1" not in refs:
        raise RuntimeError("J1 missing")
    j1 = refs["J1"]
    if str(j1.GetValue()) != EXPECTED_VALUE:
        raise RuntimeError(f"J1 value mismatch: {j1.GetValue()!r}")

    signals = []
    for number in map(str, range(1, 7)):
        pads = [p for p in j1.Pads() if str(p.GetNumber()) == number]
        if len(pads) != 1:
            raise RuntimeError(f"J1 circuit {number}: expected one pad, got {len(pads)}")
        pad = pads[0]
        w, h = wh(pad)
        close(w, EXPECTED_SIGNAL_W, 0.005, f"J1 pad {number} width")
        close(h, EXPECTED_SIGNAL_H, 0.005, f"J1 pad {number} height")
        signals.append(pad)

    nails = [p for p in j1.Pads() if str(p.GetNumber()) == ""]
    if len(nails) != 2:
        raise RuntimeError(f"J1 nail count: expected 2, got {len(nails)}")
    for i, pad in enumerate(nails, start=1):
        w, h = wh(pad)
        close(w, EXPECTED_NAIL_W, 0.005, f"J1 nail {i} width")
        close(h, EXPECTED_NAIL_H, 0.005, f"J1 nail {i} height")

    signal_positions = [xy(p) for p in signals]
    xs = sorted(x for x, _ in signal_positions)
    ys = [y for _, y in signal_positions]
    if max(ys) - min(ys) > 0.005:
        raise RuntimeError(f"J1 signal row not collinear: {ys}")
    for i, (left, right) in enumerate(zip(xs, xs[1:]), start=1):
        close(right - left, EXPECTED_PITCH, 0.005, f"J1 pitch pair {i}")
    close(xs[-1] - xs[0], EXPECTED_SPAN_B, 0.005, "J1 B span")

    nail_positions = [xy(p) for p in nails]
    nail_ys = [y for _, y in nail_positions]
    if max(nail_ys) - min(nail_ys) > 0.005:
        raise RuntimeError(f"J1 nail row not collinear: {nail_ys}")
    signal_row_y = sum(ys) / len(ys)
    nail_row_y = sum(nail_ys) / len(nail_ys)
    row_gap = abs(signal_row_y - nail_row_y) - EXPECTED_SIGNAL_H / 2.0 - EXPECTED_NAIL_H / 2.0
    close(row_gap, EXPECTED_ROW_GAP, 0.02, "J1 recommended-pattern row gap")

    print("PCB-MIC Molex 5040500691 independent manufacturer-pattern audit PASS")
    print(
        f"6 signal pads {EXPECTED_SIGNAL_W:.2f}x{EXPECTED_SIGNAL_H:.2f} mm; "
        f"pitch={EXPECTED_PITCH:.2f} mm; B={EXPECTED_SPAN_B:.2f} mm"
    )
    print(
        f"2 nail pads {EXPECTED_NAIL_W:.2f}x{EXPECTED_NAIL_H:.2f} mm; "
        f"copper row gap={row_gap:.2f} mm"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
