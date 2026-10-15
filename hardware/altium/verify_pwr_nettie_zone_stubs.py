#!/usr/bin/env python3
"""Verify the three Altium PCB-PWR NetTie adapter stubs stay in KiCad copper.

Run with the Python bundled with KiCad so that ``pcbnew`` is available.
This check complements ``verify_diagnostic_pcb.py``: that script proves the
saved PcbDoc has exactly three extra routed segments, while this script proves
the intended extra copper lies inside the corresponding native filled zone.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pcbnew


STUBS = (
    {"ref": "NT1", "pad": "1", "net": "GND_MODEM", "dx_mm": -0.5, "dy_mm": 0.0},
    {"ref": "NT2", "pad": "1", "net": "GND_DIGITAL", "dx_mm": 0.5, "dy_mm": 0.0},
    {"ref": "NT2", "pad": "2", "net": "GND_PWR", "dx_mm": -0.5, "dy_mm": 0.0},
)
WIDTH_MM = 0.25
LONGITUDINAL_STEP_MM = 0.025
LATERAL_OFFSETS_MM = (-0.125, -0.0625, 0.0, 0.0625, 0.125)
ALTIUM_Y_REFLECTION_SUM_MM = 60.0


def hit(zone, layer, x_mm, y_mm):
    point = pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm))
    return bool(zone.HitTestFilledArea(layer, point))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    board_path = root / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
    board = pcbnew.LoadBoard(str(board_path))
    zones = list(board.Zones())
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}

    results = []
    all_pass = True
    for expected in STUBS:
        footprint = footprints[expected["ref"]]
        pad = next(p for p in footprint.Pads() if p.GetNumber() == expected["pad"])
        layer = pad.GetLayer()
        start_x = pcbnew.ToMM(pad.GetPosition().x)
        start_y = pcbnew.ToMM(pad.GetPosition().y)
        end_x = start_x + expected["dx_mm"]
        end_y = start_y + expected["dy_mm"]
        length = math.hypot(expected["dx_mm"], expected["dy_mm"])
        ux = expected["dx_mm"] / length
        uy = expected["dy_mm"] / length
        px, py = -uy, ux
        same_net_zones = [
            z
            for z in zones
            if z.IsOnLayer(layer) and z.GetNetname() == expected["net"]
        ]
        other_net_zones = [
            z
            for z in zones
            if z.IsOnLayer(layer)
            and z.GetNetname()
            and z.GetNetname() != expected["net"]
        ]

        steps = round(length / LONGITUDINAL_STEP_MM)
        sample_count = 0
        outside = []
        conflicts = []
        for index in range(steps + 1):
            along = length * index / steps
            for lateral in LATERAL_OFFSETS_MM:
                x_mm = start_x + ux * along + px * lateral
                y_mm = start_y + uy * along + py * lateral
                sample_count += 1
                if not any(hit(z, layer, x_mm, y_mm) for z in same_net_zones):
                    outside.append([round(x_mm, 6), round(y_mm, 6)])
                conflict_nets = sorted(
                    {z.GetNetname() for z in other_net_zones if hit(z, layer, x_mm, y_mm)}
                )
                if conflict_nets:
                    conflicts.append(
                        {
                            "point_mm": [round(x_mm, 6), round(y_mm, 6)],
                            "nets": conflict_nets,
                        }
                    )

        pad_net_ok = pad.GetNetname() == expected["net"]
        stub_pass = pad_net_ok and bool(same_net_zones) and not outside and not conflicts
        all_pass = all_pass and stub_pass
        results.append(
            {
                "ref": expected["ref"],
                "pad": expected["pad"],
                "net": expected["net"],
                "layer": board.GetLayerName(layer),
                "width_mm": WIDTH_MM,
                "length_mm": length,
                "native_start_mm": [round(start_x, 6), round(start_y, 6)],
                "native_end_mm": [round(end_x, 6), round(end_y, 6)],
                "altium_start_mm": [
                    round(start_x, 6),
                    round(ALTIUM_Y_REFLECTION_SUM_MM - start_y, 6),
                ],
                "altium_end_mm": [
                    round(end_x, 6),
                    round(ALTIUM_Y_REFLECTION_SUM_MM - end_y, 6),
                ],
                "same_net_zone_count": len(same_net_zones),
                "sample_count": sample_count,
                "outside_same_net_filled_zone": outside,
                "other_net_filled_zone_hits": conflicts,
                "pass": stub_pass,
            }
        )

    report = {
        "status": "PASS" if all_pass else "FAIL",
        "source_board": str(board_path.relative_to(root)).replace("\\", "/"),
        "method": {
            "longitudinal_step_mm": LONGITUDINAL_STEP_MM,
            "lateral_offsets_mm": list(LATERAL_OFFSETS_MM),
            "description": (
                "Sample the centreline and both edges of each 0.25 mm stub "
                "against KiCad's filled same-net zone and reject any sample "
                "inside filled copper of another net."
            ),
        },
        "stubs": results,
        "limitations": [
            "This is a dense discrete sample, not a constructive polygon proof.",
            "The saved Altium track set is verified separately by verify_diagnostic_pcb.py.",
            "This check does not establish full manufacturing equivalence.",
        ],
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    raise SystemExit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
