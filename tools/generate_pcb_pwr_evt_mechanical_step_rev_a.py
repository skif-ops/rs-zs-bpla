#!/usr/bin/env python3
"""Generate the frozen PCB-PWR EVT mechanical-envelope STEP.

The model intentionally contains conservative envelopes rather than vendor CAD.
It is a routing/mechanical-interface authority for the EVT lot and must be
revalidated with the serial enclosure and exact component models.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cadquery as cq


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/reviews/PCB_PWR_DIM_003_EVT_AUTHORITY_REV_A.json"
DEFAULT_OUTPUT = ROOT / "mechanics/pcb_pwr/PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_A.step"


def box_from_bounds(minimum: list[float], maximum: list[float]) -> cq.Workplane:
    dx, dy, dz = (maximum[index] - minimum[index] for index in range(3))
    return cq.Workplane("XY").box(dx, dy, dz, centered=False).translate(tuple(minimum))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, default=AUTHORITY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    authority = json.loads(args.authority.read_text(encoding="utf-8"))
    outline = authority["outline"]
    width, height = outline["size_mm"]
    thickness = outline["finished_thickness_mm"]
    mounting = authority["mounting"]

    board = cq.Workplane("XY").box(width, height, thickness, centered=False)
    for hole in mounting["holes"]:
        x, y = hole["xy_mm"]
        cutter = (
            cq.Workplane("XY")
            .center(x, y)
            .circle(mounting["nominal_drill_mm"] / 2.0)
            .extrude(thickness + 2.0, both=True)
        )
        board = board.cut(cutter)

    z_envelope = authority["assembled_z_envelope_mm"]
    assembly_envelope = box_from_bounds(
        [0.0, 0.0, z_envelope["minimum"]],
        [width, height, z_envelope["maximum"]],
    )
    j1 = authority["connector_service_volumes"]["J1"]
    j2 = authority["connector_service_volumes"]["J2"]
    j1_service = box_from_bounds(j1["mating_box_xyz_min_mm"], j1["mating_box_xyz_max_mm"])
    j2_service = box_from_bounds(j2["mating_box_xyz_min_mm"], j2["mating_box_xyz_max_mm"])

    assembly = cq.Assembly(name="PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_A")
    assembly.add(board, name="PCB_90x60x1p6_WITH_H1_H4", color=cq.Color(0.05, 0.35, 0.12, 0.9))
    assembly.add(assembly_envelope, name="CONSERVATIVE_ASSEMBLED_Z_ENVELOPE", color=cq.Color(0.5, 0.5, 0.5, 0.15))
    assembly.add(j1_service, name="J1_MATING_AND_CABLE_SERVICE", color=cq.Color(0.9, 0.5, 0.1, 0.2))
    assembly.add(j2_service, name="J2_MATING_AND_CABLE_SERVICE", color=cq.Color(0.1, 0.4, 0.9, 0.2))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    assembly.save(str(args.output), exportType="STEP")
    # OpenCascade emits cosmetic trailing spaces in STEP records. Normalize the
    # text so the frozen artifact is deterministic and passes repository
    # whitespace checks without changing any STEP entities or geometry.
    step_text = args.output.read_text(encoding="utf-8")
    normalized_step = "\n".join(line.rstrip() for line in step_text.splitlines()) + "\n"
    args.output.write_text(normalized_step, encoding="utf-8")
    print(args.output.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
