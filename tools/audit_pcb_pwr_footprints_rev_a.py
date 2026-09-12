#!/usr/bin/env python3
"""Audit manufacturer-controlled PCB-PWR footprints against frozen geometry."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from kiutils.footprint import Footprint

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY = ROOT / "hardware/kicad/native/PCB-PWR/libs/DioneyaPWR.pretty"


def rounded_pad(pad) -> tuple[str, float, float, float, float, tuple[str, ...]]:
    return (
        str(pad.number),
        round(float(pad.position.X), 4), round(float(pad.position.Y), 4),
        round(float(pad.size.X), 4), round(float(pad.size.Y), 4),
        tuple(str(layer) for layer in pad.layers),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    args = ap.parse_args()

    path = args.library / "CSD18540Q5B_DNK.kicad_mod"
    if not path.is_file():
        raise RuntimeError(f"controlled CSD18540 footprint missing: {path}")
    fp = Footprint.from_file(str(path), encoding="utf-8")
    if str(fp.entryName) != "CSD18540Q5B_DNK":
        raise RuntimeError(f"unexpected footprint name: {fp.entryName}")

    copper = [rounded_pad(p) for p in fp.pads if str(p.number)]
    paste = [rounded_pad(p) for p in fp.pads if not str(p.number)]
    expected_copper = {
        ("1", 2.770, 1.905, 1.372, 0.710, ("F.Cu", "F.Mask")),
        ("2", 2.770, 0.635, 1.372, 0.710, ("F.Cu", "F.Mask")),
        ("3", 2.770, -0.635, 1.372, 0.710, ("F.Cu", "F.Mask")),
        ("4", 2.770, -1.905, 1.372, 0.710, ("F.Cu", "F.Mask")),
        ("5", -1.236, -1.905, 4.440, 0.710, ("F.Cu", "F.Mask")),
        ("6", -1.236, -0.635, 4.440, 0.710, ("F.Cu", "F.Mask")),
        ("7", -1.236, 0.635, 4.440, 0.710, ("F.Cu", "F.Mask")),
        ("8", -1.236, 1.905, 4.440, 0.710, ("F.Cu", "F.Mask")),
        ("5", -0.941, -1.270, 3.850, 0.560, ("F.Cu", "F.Mask")),
        ("5", -0.941, 0.000, 3.850, 0.560, ("F.Cu", "F.Mask")),
        ("5", -0.941, 1.270, 3.850, 0.560, ("F.Cu", "F.Mask")),
    }
    if set(copper) != expected_copper or len(copper) != len(expected_copper):
        raise RuntimeError(f"CSD18540 copper geometry drift: {copper}")
    if Counter(p[0] for p in copper) != Counter({"1": 1, "2": 1, "3": 1, "4": 1, "5": 4, "6": 1, "7": 1, "8": 1}):
        raise RuntimeError("CSD18540 electrical pad-number coverage drift")

    expected_paste = set()
    for y in (-1.905, -0.635, 0.635, 1.905):
        expected_paste.add(("", -2.910, y, 0.766, 0.508, ("F.Paste",)))
        expected_paste.add(("", 2.758, y, 1.072, 0.562, ("F.Paste",)))
    for y in (-1.569, -0.523, 0.523, 1.569):
        expected_paste.add(("", -1.594, y, 1.294, 0.746, ("F.Paste",)))
        expected_paste.add(("", 0.050, y, 1.294, 0.746, ("F.Paste",)))
    if set(paste) != expected_paste or len(paste) != 16:
        raise RuntimeError(f"CSD18540 stencil geometry drift: {paste}")

    print("PCB-PWR manufacturer footprint audit PASS")
    print("Q1 CSD18540Q5B: TI SLPS488B copper + 16-aperture stencil exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
