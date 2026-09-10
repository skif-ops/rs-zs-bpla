#!/usr/bin/env python3
"""Normalize PCB-MIC J1 to the Molex 5040500000-SD Rev.B recommended pattern.

The imported EasyEDA/LCSC footprint is secondary reference CAD only. Before any DRC or
fabrication export, this stage forces the six electrical pads to the Molex recommended
0.60 x 1.00 mm pattern and independently checks the 1.50 mm pitch, B=7.50 mm six-way
span, 1.25 x 1.80 mm nail pads, and the 3.79 mm nominal copper-to-copper row gap.

Source authority: Molex product customer drawing 5040500000-SD, PSD 000, Rev.B,
applicable to 4-8, 10 and 12 circuit Pico-Lock 1.5 right-angle headers.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pcbnew

SIGNAL_W = 0.60
SIGNAL_H = 1.00
PITCH = 1.50
SIX_WAY_SPAN_B = 7.50
NAIL_W = 1.25
NAIL_H = 1.80
ROW_COPPER_GAP = 3.79


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def to_mm(value: int) -> float:
    return float(pcbnew.ToMM(value))


def size_mm(pad) -> tuple[float, float]:
    s = pad.GetSize()
    return to_mm(s.x), to_mm(s.y)


def position_mm(pad) -> tuple[float, float]:
    p = pad.GetPosition()
    return to_mm(p.x), to_mm(p.y)


def close(actual: float, expected: float, tol: float, label: str) -> None:
    if abs(actual - expected) > tol:
        raise RuntimeError(f"{label}: {actual:.5f} mm != {expected:.5f} mm +/- {tol:.5f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    args = ap.parse_args()

    board = pcbnew.LoadBoard(str(args.board))
    if board is None:
        raise RuntimeError(f"cannot load board {args.board}")
    refs = {fp.GetReference(): fp for fp in board.GetFootprints()}
    if "J1" not in refs:
        raise RuntimeError("PCB-MIC J1 missing")
    j1 = refs["J1"]
    if str(j1.GetValue()) != "5040500691":
        raise RuntimeError(f"J1 value is not Molex 5040500691: {j1.GetValue()!r}")

    signals = []
    for number in map(str, range(1, 7)):
        pads = [p for p in j1.Pads() if str(p.GetNumber()) == number]
        if len(pads) != 1:
            raise RuntimeError(f"J1 circuit {number}: expected one pad, found {len(pads)}")
        pad = pads[0]
        pad.SetSize(pcbnew.VECTOR2I(mm(SIGNAL_W), mm(SIGNAL_H)))
        try:
            pad.SetLocalSolderPasteMargin(0)
        except Exception:
            pass
        signals.append(pad)

    nails = [p for p in j1.Pads() if str(p.GetNumber()) == ""]
    if len(nails) != 2:
        raise RuntimeError(f"J1: expected two unnumbered nail pads, found {len(nails)}")

    # Manufacturer-pattern consistency checks are done in board coordinates, so they
    # remain valid for the fixed 180-degree Rev.A placement.
    signal_xy = sorted(position_mm(p) for p in signals)
    signal_x = sorted(x for x, _ in signal_xy)
    signal_y = [y for _, y in signal_xy]
    for i, (a, b) in enumerate(zip(signal_x, signal_x[1:]), start=1):
        close(b - a, PITCH, 0.01, f"J1 circuit pitch {i}-{i+1}")
    close(signal_x[-1] - signal_x[0], SIX_WAY_SPAN_B, 0.01, "J1 six-way B span")
    if max(signal_y) - min(signal_y) > 0.01:
        raise RuntimeError(f"J1 signal pads are not collinear: Y={signal_y}")

    nail_xy = sorted(position_mm(p) for p in nails)
    nail_y = [y for _, y in nail_xy]
    if max(nail_y) - min(nail_y) > 0.01:
        raise RuntimeError(f"J1 nail pads are not collinear: Y={nail_y}")
    for i, pad in enumerate(nails, start=1):
        w, h = size_mm(pad)
        # Rotation 180 degrees preserves width/height for these rectangular pads.
        close(w, NAIL_W, 0.01, f"J1 nail {i} width")
        close(h, NAIL_H, 0.01, f"J1 nail {i} height")

    signal_row_y = sum(signal_y) / len(signal_y)
    nail_row_y = sum(nail_y) / len(nail_y)
    center_distance = abs(signal_row_y - nail_row_y)
    copper_gap = center_distance - SIGNAL_H / 2.0 - NAIL_H / 2.0
    close(copper_gap, ROW_COPPER_GAP, 0.02, "J1 signal-to-nail copper gap")

    pcbnew.SaveBoard(str(args.board), board)
    print("PCB-MIC Molex 5040500691 manufacturer-pattern normalization PASS")
    print(
        f"signals: 6 x {SIGNAL_W:.2f}x{SIGNAL_H:.2f} mm, pitch {PITCH:.2f} mm, "
        f"B={SIX_WAY_SPAN_B:.2f} mm"
    )
    print(
        f"nails: 2 x {NAIL_W:.2f}x{NAIL_H:.2f} mm; "
        f"signal-to-nail copper gap={copper_gap:.2f} mm"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
