#!/usr/bin/env python3
"""Audit DIM-003 Rev B coordinates, source board pose, mirror guard and STEP.

Run from the repository after generation. The board is read automatically when
available. The checked-in evidence record also permits an isolated candidate
package to be checked before it is staged in the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "hardware/reviews/PCB_PWR_DIM_003_EVT_AUTHORITY_REV_B.json"
EVIDENCE = ROOT / "hardware/reviews/PCB_PWR_DIM_003_BOARD_POSE_EVIDENCE_REV_B.json"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
STEP = ROOT / "mechanics/pcb_pwr/PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_B.step"
REPORT = ROOT / "mechanics/pcb_pwr/PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_B.json"
REFS = ("H1", "H2", "H3", "H4", "J1", "J2")
REV_E_METADATA_BOARD_SHA256 = "de2a723bbbc0d37b9f4fc5f55e24bfa287f892a081925daf4a24b8a7fa6c901d"


def strip_rev_e_metadata(board_text: str) -> str:
    """Remove only Rev E title and stackup blocks to prove ECO-006 geometry identity."""
    text, title_count = re.subn(r'\t\(title_block\n(?:\t.*\n)*?\t\)\n', '', board_text, count=1)
    text, stack_count = re.subn(r'\t\t\(stackup\n(?:\t\t\t.*\n)*?\t\t\)\n', '', text, count=1)
    if (title_count, stack_count) != (1, 1):
        raise AssertionError("Rev E metadata blocks missing or altered")
    return text


def close(actual: float, expected: float, label: str, tolerance: float = 0.001) -> None:
    if not math.isclose(actual, expected, abs_tol=tolerance):
        raise AssertionError(f"{label}: {actual} != {expected}")


def xy_close(actual: list[float], expected: list[float], label: str) -> None:
    for axis, a, e in zip("xy", actual, expected):
        close(a, e, f"{label}.{axis}")


def bracket_block(text: str, start: int) -> str:
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise ValueError("Unclosed KiCad expression")


def read_board_poses(board: Path) -> tuple[dict, dict]:
    text = board.read_text(encoding="utf-8")
    poses = {}
    courtyards = {}
    for match in re.finditer(r"(?m)^\s*\(footprint\s+", text):
        block = bracket_block(text, match.start() + len(match.group()) - len(match.group().lstrip()))
        ref = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
        if not ref or ref.group(1) not in REFS:
            continue
        name = ref.group(1)
        at = re.search(r"(?m)^\s{2,}\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\)", block)
        if not at:
            raise AssertionError(f"Missing at for {name}")
        poses[name] = {"at_kicad_mm": [float(at.group(1)), float(at.group(2))],
                       "rotation_kicad_deg": float(at.group(3) or 0)}
        if name in ("J1", "J2"):
            for rect_match in re.finditer(r"\(fp_rect\s+", block):
                rect = bracket_block(block, rect_match.start())
                if '(layer "F.CrtYd")' not in rect:
                    continue
                start = re.search(r"\(start\s+(-?[\d.]+)\s+(-?[\d.]+)\)", rect)
                end = re.search(r"\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)", rect)
                if start and end:
                    courtyards[name] = {"start": [float(start.group(1)), float(start.group(2))],
                                        "end": [float(end.group(1)), float(end.group(2))]}
    if set(poses) != set(REFS) or set(courtyards) != {"J1", "J2"}:
        raise AssertionError(f"Board pose coverage: {sorted(poses)}; courtyards={sorted(courtyards)}")
    return poses, courtyards


def transform_courtyard(pose: dict, rect: dict, board_height: float) -> dict:
    x0, y0 = pose["at_kicad_mm"]
    angle = math.radians(pose["rotation_kicad_deg"])
    xs = []
    ys = []
    for u in (rect["start"][0], rect["end"][0]):
        for v in (rect["start"][1], rect["end"][1]):
            # KiCad rotations are counterclockwise in physical XY, where screen Y points down.
            x_kicad = x0 + u * math.cos(angle) + v * math.sin(angle)
            y_kicad = y0 - u * math.sin(angle) + v * math.cos(angle)
            xs.append(x_kicad)
            ys.append(board_height - y_kicad)
    return {"x": [min(xs), max(xs)], "y": [min(ys), max(ys)]}


def audit_step(step: Path, authority: dict) -> dict:
    import cadquery as cq
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    solids = cq.importers.importStep(str(step)).solids().vals()
    if len(solids) != 4:
        raise AssertionError(f"STEP solid count: {len(solids)} != 4")
    expected_boxes = ((0, 90, 0, 60, 0, 1.6), (0, 90, 0, 60, -3, 18),
                      (0, 12, 20, 40, 1.6, 40), (80, 130, 0, 25, 1.6, 22))
    actual_boxes = []
    for solid in solids:
        box = solid.BoundingBox()
        actual_boxes.append((box.xmin, box.xmax, box.ymin, box.ymax, box.zmin, box.zmax))
    for index, (actual, expected) in enumerate(zip(actual_boxes, expected_boxes)):
        for axis, a, e in zip("xXyYzZ", actual, expected):
            close(a, e, f"solid {index} {axis}")
    cylinders = []
    for face in solids[0].Faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        if surface.GetType() == GeomAbs_Cylinder:
            cylinder = surface.Cylinder()
            cylinders.append((round(cylinder.Location().X(), 3),
                              round(cylinder.Location().Y(), 3),
                              round(cylinder.Radius(), 3)))
    expected_holes = sorted((x, y, authority["mounting"]["nominal_drill_mm"] / 2)
                            for x, y in (item["xy_mm"] for item in authority["mounting"]["holes"]))
    if sorted(cylinders) != expected_holes:
        raise AssertionError(f"STEP cylinders: {sorted(cylinders)} != {expected_holes}")
    return {"solid_count": len(solids), "board_hole_cylinders": sorted(cylinders)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, default=BOARD)
    parser.add_argument("--step-geometry", action="store_true", help="Import STEP with CadQuery/OCP")
    args = parser.parse_args()
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if authority["source_board_sha256"] != evidence["source_board_sha256"]:
        raise AssertionError("Source board hash differs between authority and evidence")
    if authority["coordinate_system"]["board_source"]["height_mm"] != evidence["board_height_mm"]:
        raise AssertionError("Board height differs")
    board_height = evidence["board_height_mm"]
    board_status = "EVIDENCE_ONLY_BOARD_FILE_UNAVAILABLE"
    poses = {name: {"at_kicad_mm": entry["at_kicad_mm"],
                    "rotation_kicad_deg": entry.get("rotation_kicad_deg", 0)}
             for name, entry in evidence["footprints"].items()}
    courtyards = {name: evidence[f"{name.lower()}_front_courtyard_local_mm"]
                  for name in ("J1", "J2")}
    if args.board.exists():
        digest = hashlib.sha256(args.board.read_bytes()).hexdigest()
        if digest != authority["source_board_sha256"]:
            if digest != REV_E_METADATA_BOARD_SHA256:
                raise AssertionError(f"Board SHA-256 mismatch: {digest}")
            stripped = strip_rev_e_metadata(args.board.read_text(encoding="utf-8"))
            if hashlib.sha256(stripped.encode("utf-8")).hexdigest() != authority["source_board_sha256"]:
                raise AssertionError("Rev E board differs from ECO-006 beyond title and stackup")
            board_status = "REV_E_METADATA_ONLY_EQUIVALENCE_AND_POSES_VERIFIED"
        else:
            board_status = "SOURCE_BOARD_SHA_AND_POSES_VERIFIED"
        poses, courtyards = read_board_poses(args.board)
    holes = {item["reference"]: item["xy_mm"] for item in authority["mounting"]["holes"]}
    for name in REFS:
        expected = evidence["footprints"][name]
        xy_close(poses[name]["at_kicad_mm"], expected["at_kicad_mm"], f"{name} KiCad")
        x_kicad, y_kicad = poses[name]["at_kicad_mm"]
        transformed = [x_kicad, board_height - y_kicad]
        xy_close(transformed, expected["at_dim_mm"], f"{name} DIM")
        if name.startswith("H"):
            xy_close(transformed, holes[name], f"{name} authority")
        else:
            xy_close(transformed, authority["connector_service_volumes"][name]["footprint_origin_xy_mm"],
                     f"{name} authority")
    # Deliberately perform the wrong direct mapping as a negative mirror test.
    if all(poses[name]["at_kicad_mm"] == holes[name] for name in holes):
        raise AssertionError("Mirror guard did not detect the Rev A coordinate error")
    mirror_guard = "PASS_DIRECT_MAPPING_REJECTED"
    bounds = {}
    for name in ("J1", "J2"):
        rect = courtyards[name]
        reference_rect = evidence[f"{name.lower()}_front_courtyard_local_mm"]
        for endpoint in ("start", "end"):
            xy_close(rect[endpoint], reference_rect[endpoint], f"{name} courtyard {endpoint}")
        bounds[name] = transform_courtyard(poses[name], rect, board_height)
        for axis in ("x", "y"):
            for index in (0, 1):
                close(bounds[name][axis][index],
                      evidence[f"{name.lower()}_front_courtyard_dim_bounds_mm"][axis][index],
                      f"{name} courtyard {axis}{index}")
    j2 = authority["connector_service_volumes"]["J2"]
    if bounds["J2"]["y"][0] < j2["mating_box_xyz_min_mm"][1] or bounds["J2"]["y"][1] > j2["mating_box_xyz_max_mm"][1]:
        raise AssertionError("J2 service box does not span footprint courtyard Y")
    j1 = authority["connector_service_volumes"]["J1"]
    if not all(j1["mating_box_xyz_min_mm"][i] <= bounds["J1"][axis][0] and
               bounds["J1"][axis][1] <= j1["mating_box_xyz_max_mm"][i]
               for i, axis in enumerate(("x", "y"))):
        raise AssertionError("J1 footprint courtyard outside service box")
    step_hash = hashlib.sha256(STEP.read_bytes()).hexdigest()
    if step_hash != authority["frozen_step"]["sha256"] or step_hash != report["step_sha256"]:
        raise AssertionError("STEP SHA-256 differs between file, authority and report")
    result = {"board_source": board_status, "mirror_guard": mirror_guard,
              "j1_courtyard_dim_bounds_mm": bounds["J1"],
              "j2_courtyard_dim_bounds_mm": bounds["J2"], "step_sha256": step_hash,
              "step_geometry": audit_step(STEP, authority) if args.step_geometry else "HASH_VERIFIED"}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
