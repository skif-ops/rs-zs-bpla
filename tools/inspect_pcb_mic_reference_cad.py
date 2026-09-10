#!/usr/bin/env python3
"""Inspect secondary EasyEDA/LCSC reference footprints for PCB-MIC.

This tool never releases a footprint. It extracts the imported pad geometry and
compares the T5838 reference against manufacturer-datasheet dimensions. The report is
review evidence only; native PCB generation uses only geometry that passes this check.
Run with /usr/bin/python3 after KiCad/pcbnew is installed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pcbnew

NM_PER_MM = 1_000_000.0


def mm(v: int) -> float:
    return round(float(v) / NM_PER_MM, 4)


def load_mod(path: Path):
    fp = pcbnew.FootprintLoad(str(path.parent), path.stem)
    if fp is None:
        raise RuntimeError(f"could not load footprint {path}")
    return fp


def pad_record(pad) -> dict:
    pos = pad.GetPosition()
    size = pad.GetSize()
    return {
        "number": str(pad.GetNumber()),
        "x_mm": mm(pos.x),
        "y_mm": mm(pos.y),
        "w_mm": mm(size.x),
        "h_mm": mm(size.y),
        "shape": int(pad.GetShape()),
        "attribute": int(pad.GetAttribute()),
    }


def close(a: float, b: float, tol: float = 0.06) -> bool:
    return abs(a - b) <= tol


def t5838_geometry_check(pads: list[dict]) -> dict:
    # TDK DS-000383 v1.2 land pattern: 4 x 0.522 x 0.725 mm signal/power pads,
    # 2 x 0.30 x 0.30 mm small pads, plus center annular GND/acoustic-port geometry.
    # Imported CAD may model the annular GND as one or more custom pads; that part is
    # reported but intentionally not auto-approved.
    rect_sizes = [(min(p["w_mm"], p["h_mm"]), max(p["w_mm"], p["h_mm"])) for p in pads]
    large = [s for s in rect_sizes if close(s[0], 0.522) and close(s[1], 0.725)]
    small = [s for s in rect_sizes if close(s[0], 0.30) and close(s[1], 0.30)]
    numbered = sorted({p["number"] for p in pads if p["number"]})
    return {
        "expected_numbered_pins": ["1", "2", "3", "4", "5", "6", "7"],
        "numbered_pins": numbered,
        "large_0p522x0p725_count": len(large),
        "small_0p30x0p30_count": len(small),
        "manufacturer_geometry_partial_pass": (
            all(n in numbered for n in ["1", "2", "3", "4", "5", "6", "7"])
            and len(large) >= 4
            and len(small) >= 2
        ),
        "note": "Center GND ring/acoustic hole must be checked separately against TDK drawing; reference CAD is never authoritative.",
    }


def inspect_one(path: Path, kind: str) -> dict:
    fp = load_mod(path)
    pads = [pad_record(p) for p in fp.Pads()]
    out = {
        "path": str(path),
        "reference": fp.GetReference(),
        "value": fp.GetValue(),
        "pad_count": len(pads),
        "pads": pads,
    }
    if kind == "t5838":
        out["t5838_check"] = t5838_geometry_check(pads)
    if kind == "molex":
        numbered = sorted({p["number"] for p in pads if p["number"]})
        out["molex_check"] = {
            "expected_circuits": 6,
            "numbered_pins": numbered,
            "six_circuit_partial_pass": all(str(i) in numbered for i in range(1, 7)),
            "note": "Pitch, body/anchor geometry and board-edge orientation still require Molex drawing review.",
        }
    return out


def find_one(root: Path) -> Path:
    mods = sorted(root.rglob("*.kicad_mod"))
    if len(mods) != 1:
        raise RuntimeError(f"expected exactly one *.kicad_mod below {root}, found {len(mods)}: {mods}")
    return mods[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t5838-root", type=Path, required=True)
    ap.add_argument("--molex-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    report = {
        "status": "REFERENCE_ONLY_NOT_RELEASED",
        "kicad_build": pcbnew.GetBuildVersion(),
        "t5838": inspect_one(find_one(args.t5838_root), "t5838"),
        "molex_5040500691": inspect_one(find_one(args.molex_root), "molex"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Fail only for obvious reference mismatch. A pass still means secondary evidence,
    # not release approval.
    if not report["t5838"]["t5838_check"]["manufacturer_geometry_partial_pass"]:
        return 2
    if not report["molex_5040500691"]["molex_check"]["six_circuit_partial_pass"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
