#!/usr/bin/env python3
"""Independent audit of the bounded PCB-PWR J2 placement ECO-003 candidate.

Geometry follows KiCad's y-down convention: a footprint rotated by angle a maps a
local point (x, y) to (X + x*cos a + y*sin a, Y - x*sin a + y*cos a).  This is the
convention KiCad DRC reports pad positions in; the historical placement audits
use the opposite sign, which is why J2 passed them while lying outside the board.

Checks:
- base is the authoritative routing-010 board and the candidate regenerates to
  its pinned SHA-256;
- the textual delta is exactly the nine accepted footprint placement lines;
- every pad and NPTH lies inside the 90 x 60 mm outline;
- J2 body is inside the accepted DIM-003 service box, front face flush at x = 90;
- fitted courtyards keep >= 0.20 mm, no courtyard overlaps at all (DNP and PCB
  features included, circles honoured), fitted bodies keep >= 0.20 mm outside the
  D10 mounting exclusions;
- no track or via lies within 0.20 mm of a moved footprint courtyard;
- optional KiCad 9 comparative DRC: the J2 edge errors and H3/R13 courtyard error
  disappear, no new error fingerprint appears, unconnected items do not grow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import generate_pcb_pwr_j2_placement_eco_003_candidate_rev_a as generator  # noqa: E402

BOARD_X_MM = 90.0
BOARD_Y_MM = 60.0
REQUIRED_CLEARANCE_MM = 0.20
MOUNTING_EXCLUSION_RADIUS_MM = 5.0
DIM_003_J2_BOX = (80.0, 35.0, 130.0, 60.0)
EXPECTED_REMOVED_ERRORS = Counter({"copper_edge_clearance": 3, "courtyards_overlap": 1})
MOVED = tuple(generator.PLACEMENT_REPLACEMENTS)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_of(footprint) -> str:
    properties = footprint.properties
    if isinstance(properties, dict):
        return properties.get("Reference", "?")
    return next((p.value for p in properties if getattr(p, "key", None) == "Reference"), "?")


def population_of(footprint) -> str:
    description = footprint.description or ""
    marker = "population="
    if marker not in description:
        return "UNKNOWN"
    return description.split(marker, 1)[1].split("|", 1)[0]


def to_board(footprint, x: float, y: float) -> tuple[float, float]:
    angle = math.radians(float(footprint.position.angle or 0.0))
    return (
        float(footprint.position.X) + x * math.cos(angle) + y * math.sin(angle),
        float(footprint.position.Y) - x * math.sin(angle) + y * math.cos(angle),
    )


def layer_shapes(footprint, layer: str):
    """Yield ('box', x0, y0, x1, y1) or ('circle', cx, cy, r) in board coordinates."""
    for item in footprint.graphicItems:
        if getattr(item, "layer", "") != layer:
            continue
        kind = type(item).__name__
        if kind == "FpCircle":
            cx, cy = to_board(footprint, item.center.X, item.center.Y)
            radius = math.hypot(item.center.X - item.end.X, item.center.Y - item.end.Y)
            yield ("circle", cx, cy, radius)
            continue
        points = []
        if kind == "FpRect":
            for x, y in ((item.start.X, item.start.Y), (item.end.X, item.start.Y),
                         (item.end.X, item.end.Y), (item.start.X, item.end.Y)):
                points.append(to_board(footprint, x, y))
        elif kind == "FpPoly":
            points = [to_board(footprint, p.X, p.Y) for p in item.coordinates]
        else:
            for attribute in ("start", "end"):
                point = getattr(item, attribute, None)
                if point is not None:
                    points.append(to_board(footprint, point.X, point.Y))
        if points:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            yield ("box", min(xs), min(ys), max(xs), max(ys))


def courtyard(footprint):
    """Union bounding box of rectangular courtyard parts plus any circle."""
    side = "F.CrtYd" if footprint.layer == "F.Cu" else "B.CrtYd"
    boxes = []
    circle = None
    for shape in layer_shapes(footprint, side):
        if shape[0] == "circle":
            circle = shape[1:]
        else:
            boxes.append(shape[1:])
    box = None
    if boxes:
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
               max(b[2] for b in boxes), max(b[3] for b in boxes))
    return box, circle


def box_gap(first, second) -> float:
    gap_x = max(first[0] - second[2], second[0] - first[2], 0.0)
    gap_y = max(first[1] - second[3], second[1] - first[3], 0.0)
    overlap = gap_x == 0.0 and gap_y == 0.0 and (
        first[0] < second[2] and second[0] < first[2] and first[1] < second[3] and second[1] < first[3]
    )
    return -1.0 if overlap else math.hypot(gap_x, gap_y)


def circle_box_gap(circle, box) -> float:
    cx, cy, radius = circle
    dx = max(box[0] - cx, 0.0, cx - box[2])
    dy = max(box[1] - cy, 0.0, cy - box[3])
    return math.hypot(dx, dy) - radius


def pad_extents(footprint):
    for pad in footprint.pads:
        x, y = to_board(footprint, pad.position.X, pad.position.Y)
        radius = max(float(pad.size.X), float(pad.size.Y)) / 2.0
        yield pad.number or "NPTH", x, y, radius


def geometry(board_path: Path) -> dict[str, object]:
    from kiutils.board import Board

    board = Board.from_file(str(board_path))
    footprints = {reference_of(f): f for f in board.footprints}
    require(len(footprints) == len(board.footprints) == 66, "PCB-PWR reference set drift")

    outside = sorted(
        f"{ref}:{number}"
        for ref, fp in footprints.items()
        for number, x, y, r in pad_extents(fp)
        if x - r < 0.0 or y - r < 0.0 or x + r > BOARD_X_MM or y + r > BOARD_Y_MM
    )

    body = [s for s in layer_shapes(footprints["J2"], "F.Fab") if s[0] == "box"]
    require(body, "J2 has no F.Fab body")
    j2_body = (min(b[1] for b in body), min(b[2] for b in body), max(b[3] for b in body), max(b[4] for b in body))
    j2_in_box = (
        j2_body[0] >= DIM_003_J2_BOX[0] - 1e-6 and j2_body[1] >= DIM_003_J2_BOX[1] - 1e-6
        and j2_body[2] <= DIM_003_J2_BOX[2] + 1e-6 and j2_body[3] <= DIM_003_J2_BOX[3] + 1e-6
    )
    j2_front_flush = abs(j2_body[2] - BOARD_X_MM) <= 0.01

    yards = {ref: courtyard(fp) for ref, fp in footprints.items()}
    overlaps = []
    fitted_conflicts = []
    fitted_minimum = math.inf
    references = sorted(yards)
    for index, first in enumerate(references):
        for second in references[index + 1:]:
            (box_a, circle_a), (box_b, circle_b) = yards[first], yards[second]
            gaps = []
            if box_a and box_b:
                gaps.append(box_gap(box_a, box_b))
            if circle_a and box_b:
                gaps.append(circle_box_gap(circle_a, box_b))
            if circle_b and box_a:
                gaps.append(circle_box_gap(circle_b, box_a))
            if not gaps:
                continue
            gap = min(gaps)
            if gap < 0.0:
                overlaps.append([first, second])
            both_fitted = population_of(footprints[first]) == population_of(footprints[second]) == "FITTED"
            if both_fitted and box_a and box_b:
                distance = max(box_gap(box_a, box_b), 0.0)
                fitted_minimum = min(fitted_minimum, distance)
                if distance + 1e-6 < REQUIRED_CLEARANCE_MM:
                    fitted_conflicts.append([first, second, round(distance, 3)])

    mounting = []
    for hole in ("H1", "H2", "H3", "H4"):
        cx, cy = float(footprints[hole].position.X), float(footprints[hole].position.Y)
        for ref, fp in footprints.items():
            if population_of(fp) != "FITTED" or not yards[ref][0]:
                continue
            margin = circle_box_gap((cx, cy, MOUNTING_EXCLUSION_RADIUS_MM), yards[ref][0])
            if margin + 1e-6 < REQUIRED_CLEARANCE_MM:
                mounting.append([hole, ref, round(margin, 3)])

    copper_touch = []
    for ref in MOVED:
        box = yards[ref][0]
        if not box:
            continue
        for item in board.traceItems:
            for attribute in ("start", "end", "position"):
                point = getattr(item, attribute, None)
                if point is None:
                    continue
                if (box[0] - REQUIRED_CLEARANCE_MM <= point.X <= box[2] + REQUIRED_CLEARANCE_MM
                        and box[1] - REQUIRED_CLEARANCE_MM <= point.Y <= box[3] + REQUIRED_CLEARANCE_MM):
                    copper_touch.append([ref, type(item).__name__, point.X, point.Y])

    return {
        "pads_outside_outline": outside,
        "j2_body_mm": [round(v, 3) for v in j2_body],
        "j2_body_inside_dim_003_box": j2_in_box,
        "j2_front_face_flush_east_edge": j2_front_flush,
        "courtyard_overlaps": overlaps,
        "fitted_clearance_conflicts": fitted_conflicts,
        "fitted_minimum_clearance_mm": round(fitted_minimum, 3),
        "mounting_exclusion_conflicts": mounting,
        "copper_near_moved_footprints": copper_touch,
        "trace_items": len(board.traceItems),
        "zones": len(board.zones),
    }


def drc_errors(path: Path) -> tuple[Counter, Counter, int]:
    report = json.loads(path.read_text(encoding="utf-8"))
    by_type: Counter = Counter()
    fingerprints: Counter = Counter()
    for violation in report.get("violations", []):
        if violation.get("severity") != "error":
            continue
        by_type[violation["type"]] += 1
        items = tuple(sorted(item.get("description", "") for item in violation.get("items", [])))
        fingerprints[(violation["type"], items)] += 1
    return by_type, fingerprints, len(report.get("unconnected_items", []))


def audit(drc_base: Path | None, drc_candidate: Path | None) -> dict[str, object]:
    workdir = Path(tempfile.mkdtemp(prefix="pcb-pwr-eco-003-"))
    base_path, candidate_path = generator.materialize(workdir)
    require(sha256(base_path) == generator.BASE_SHA256, "ECO-003 base is not the routing-010 authoritative board")
    require(sha256(candidate_path) == generator.CANDIDATE_SHA256, "ECO-003 candidate SHA-256 drift")

    base_lines = base_path.read_text(encoding="utf-8").split("\n")
    candidate_lines = candidate_path.read_text(encoding="utf-8").split("\n")
    require(len(base_lines) == len(candidate_lines), "ECO-003 changes line structure")
    changed = [(a, b) for a, b in zip(base_lines, candidate_lines) if a != b]
    expected = sorted((old.strip("\n"), new.strip("\n")) for old, new in generator.PLACEMENT_REPLACEMENTS.values())
    require(sorted(changed) == expected, "ECO-003 delta is not exactly the accepted placement lines")

    base_geometry = geometry(base_path)
    candidate_geometry = geometry(candidate_path)
    require(candidate_geometry["trace_items"] == base_geometry["trace_items"] == 53, "trace item drift")
    require(candidate_geometry["zones"] == base_geometry["zones"] == 2, "zone drift")

    blockers = []
    if candidate_geometry["pads_outside_outline"]:
        blockers.append("pads outside outline")
    if not candidate_geometry["j2_body_inside_dim_003_box"]:
        blockers.append("J2 body outside DIM-003 service box")
    if not candidate_geometry["j2_front_face_flush_east_edge"]:
        blockers.append("J2 front face not flush with east edge")
    for key in ("courtyard_overlaps", "fitted_clearance_conflicts", "mounting_exclusion_conflicts",
                "copper_near_moved_footprints"):
        if candidate_geometry[key]:
            blockers.append(key)

    drc = None
    if drc_base and drc_candidate:
        base_types, base_prints, base_unconnected = drc_errors(drc_base)
        candidate_types, candidate_prints, candidate_unconnected = drc_errors(drc_candidate)
        new_prints = sorted(str(k) for k in candidate_prints if k not in base_prints)
        removed = base_types - candidate_types
        drc = {
            "base_errors": dict(base_types),
            "candidate_errors": dict(candidate_types),
            "removed_errors": dict(removed),
            "new_error_fingerprints": new_prints,
            "unconnected": [base_unconnected, candidate_unconnected],
        }
        if new_prints:
            blockers.append("new DRC error fingerprints")
        if removed != EXPECTED_REMOVED_ERRORS:
            blockers.append(f"DRC removed errors {dict(removed)} != expected {dict(EXPECTED_REMOVED_ERRORS)}")
        if candidate_unconnected > base_unconnected:
            blockers.append("unconnected items grew")

    status = "PASS_BOUNDED_J2_PLACEMENT_ECO_003_CANDIDATE" if not blockers else "BLOCKED"
    if drc is None and not blockers:
        status += "_KICAD_DRC_PENDING"
    return {
        "schema": "dioneya-pcb-pwr-j2-placement-eco-003-candidate-audit-v1",
        "status": status,
        "base_sha256": generator.BASE_SHA256,
        "candidate_sha256": sha256(candidate_path),
        "moved_references": list(MOVED),
        "geometry_convention": "KiCad y-down: X+x*cos(a)+y*sin(a), Y-x*sin(a)+y*cos(a)",
        "base_geometry": base_geometry,
        "candidate_geometry": candidate_geometry,
        "kicad_drc": drc,
        "blockers": blockers,
        "application_authorized": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-candidate", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/pcb_pwr_j2_placement_eco_003_candidate.json")
    args = parser.parse_args()
    result = audit(args.drc_base, args.drc_candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PCB-PWR J2 placement ECO-003 candidate: {result['status']}")
    for blocker in result["blockers"]:
        print(f"  - {blocker}")
    return 0 if not result["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
