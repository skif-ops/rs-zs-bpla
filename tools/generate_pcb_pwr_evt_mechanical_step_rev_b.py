#!/usr/bin/env python3
"""Generate the PCB-PWR DIM-003 Rev B EVT envelope in the lower-left, Y-up datum.

The source board uses KiCad's upper-left, Y-down coordinates. The Rev B authority
contains already transformed mechanical coordinates and preserves the ECO-006 PCB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import cadquery as cq


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/reviews/PCB_PWR_DIM_003_EVT_AUTHORITY_REV_B.json"
DEFAULT_OUTPUT = ROOT / "mechanics/pcb_pwr/PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_B.step"
DEFAULT_REPORT = ROOT / "mechanics/pcb_pwr/PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_B.json"


def box_from_bounds(minimum: list[float], maximum: list[float]) -> cq.Workplane:
    dx, dy, dz = (maximum[index] - minimum[index] for index in range(3))
    assert min(dx, dy, dz) > 0
    return cq.Workplane("XY").box(dx, dy, dz, centered=False).translate(tuple(minimum))


def build(authority: dict) -> cq.Assembly:
    width, height = authority["outline"]["size_mm"]
    thickness = authority["outline"]["finished_thickness_mm"]
    mounting = authority["mounting"]
    board = cq.Workplane("XY").box(width, height, thickness, centered=False)
    for hole in mounting["holes"]:
        x, y = hole["xy_mm"]
        cutter = cq.Workplane("XY").center(x, y).circle(
            mounting["nominal_drill_mm"] / 2
        ).extrude(thickness + 2, both=True)
        board = board.cut(cutter)

    z = authority["assembled_z_envelope_mm"]
    envelope = box_from_bounds([0, 0, z["minimum"]], [width, height, z["maximum"]])
    j1 = authority["connector_service_volumes"]["J1"]
    j2 = authority["connector_service_volumes"]["J2"]
    assembly = cq.Assembly(name="PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_B")
    assembly.add(board, name="PCB_90x60x1p6_WITH_H1_H4")
    assembly.add(envelope, name="CONSERVATIVE_ASSEMBLED_Z_ENVELOPE")
    assembly.add(box_from_bounds(j1["mating_box_xyz_min_mm"], j1["mating_box_xyz_max_mm"]),
                 name="J1_MATING_AND_CABLE_SERVICE")
    assembly.add(box_from_bounds(j2["mating_box_xyz_min_mm"], j2["mating_box_xyz_max_mm"]),
                 name="J2_MATING_AND_CABLE_SERVICE")
    return assembly


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, default=AUTHORITY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    authority = json.loads(args.authority.read_text(encoding="utf-8"))
    assert authority["revision"] == "B"
    assert authority["coordinate_system"]["origin"] == "LOWER_LEFT_EDGE_CUT_INTERSECTION"
    assert authority["coordinate_system"]["y_axis"] == "NORTH_ALONG_60_MM_EDGE"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    build(authority).save(str(args.output), exportType="STEP")
    step_text = args.output.read_text(encoding="utf-8")
    step_text = re.sub(r"('Open CASCADE Shape Model',)'[^']+'",
                       r"\g<1>'2026-09-28T00:00:00'", step_text, count=1)
    step_text = "\n".join(line.rstrip() for line in step_text.splitlines()) + "\n"
    args.output.write_text(step_text, encoding="utf-8")

    report = {
        "schema": "dioneya-pcb-pwr-dim-003-rev-b-step-evidence-v1",
        "authority": args.authority.name,
        "source_board_sha256": authority["source_board_sha256"],
        "coordinate_transform": authority["coordinate_system"]["board_source"]["transform_to_authority"],
        "outline_size_mm": authority["outline"]["size_mm"],
        "holes_lower_left_y_up_mm": {
            hole["reference"]: hole["xy_mm"] for hole in authority["mounting"]["holes"]
        },
        "j1_service_box_mm": [
            authority["connector_service_volumes"]["J1"]["mating_box_xyz_min_mm"],
            authority["connector_service_volumes"]["J1"]["mating_box_xyz_max_mm"],
        ],
        "j2_service_box_mm": [
            authority["connector_service_volumes"]["J2"]["mating_box_xyz_min_mm"],
            authority["connector_service_volumes"]["J2"]["mating_box_xyz_max_mm"],
        ],
        "step_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "independent_fit_review": "PENDING",
        "manufacturing_release": False,
    }
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({"step": str(args.output), "sha256": report["step_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
