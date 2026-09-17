#!/usr/bin/env python3
"""Inventory PCB-MAIN Rev.A placement, mounting and U.FL service clearances.

The committed board is still an unrouted engineering placement candidate. This
audit has two modes:

* the default controlled-baseline mode inventories the placement and verifies
  that its summary matches PCB_MAIN_CAPTURE_STATUS_REV_A.json;
* ``--strict`` additionally fails while any collision remains and is the
  machine-enforced 2D placement-clearance subgate.

Manufacturer/drawing courtyards are treated as confirmed assembly envelopes.
Footprints without a courtyard use their pad bounds plus a conservative 0.25 mm
screening margin; those findings must be resolved or replaced by controlled
courtyard data before Review B, but are labelled separately from confirmed
courtyard collisions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from kiutils.board import Board

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
DEFAULT_AUTHORITY = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
DEFAULT_STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"

PAD_SCREENING_MARGIN_MM = 0.25
GEOMETRY_TOLERANCE_MM = 0.02
COURTYARD_SOURCE = "COURTYARD"
PAD_SOURCE = "PAD_ENVELOPE_PLUS_0_25_MM"
FIXTURE_PACKAGE_PREFIX = "POGO_FIXTURE_"
TOOL_GEOMETRY_PATTERN = re.compile(
    r"(?:^|_)TOOL_D([0-9]+(?:\.[0-9]+)?)_Z([0-9]+(?:\.[0-9]+)?)(?:_|$)"
)


@dataclass(frozen=True)
class Envelope:
    ref: str
    side: str
    source: str
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    authority_locked: bool

    def bounds(self) -> list[float]:
        return [rounded(self.xmin), rounded(self.ymin),
                rounded(self.xmax), rounded(self.ymax)]


def rounded(value: float) -> float:
    return round(value, 6)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def ref_of(footprint: Any) -> str:
    graphic_refs = [str(item.text) for item in footprint.graphicItems
                    if getattr(item, "type", None) == "reference"]
    require(len(graphic_refs) <= 1,
            f"footprint has duplicate reference graphics: {graphic_refs}")
    property_ref = str(footprint.properties.get("Reference", ""))
    if property_ref:
        require(not graphic_refs or graphic_refs[0] == property_ref,
                "footprint reference field and graphic disagree: "
                f"field={property_ref!r} graphic={graphic_refs}")
        return property_ref
    require(len(graphic_refs) == 1 and graphic_refs[0],
            "footprint has no non-blank Reference field or reference graphic")
    return graphic_refs[0]


def rotate(point: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    cosine, sine = math.cos(angle), math.sin(angle)
    x, y = point
    return x * cosine - y * sine, x * sine + y * cosine


def rectangle_corners(xmin: float, ymin: float, xmax: float, ymax: float) -> list[tuple[float, float]]:
    return [(xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax)]


def courtyard_points(footprint: Any) -> list[tuple[float, float]]:
    layer = "F.CrtYd" if footprint.layer == "F.Cu" else "B.CrtYd"
    items = [item for item in footprint.graphicItems
             if getattr(item, "layer", None) == layer]
    if not items:
        return []

    points: list[tuple[float, float]] = []
    for item in items:
        item_type = type(item).__name__
        require(item_type in {"FpLine", "FpRect"},
                f"{ref_of(footprint)}: unsupported courtyard primitive {item_type}")
        for field in ("start", "end"):
            point = getattr(item, field, None)
            require(point is not None,
                    f"{ref_of(footprint)}: incomplete {item_type} courtyard primitive")
            points.append((float(point.X), float(point.Y)))

    xmin = min(point[0] for point in points)
    ymin = min(point[1] for point in points)
    xmax = max(point[0] for point in points)
    ymax = max(point[1] for point in points)
    require(xmax > xmin and ymax > ymin,
            f"{ref_of(footprint)}: degenerate courtyard envelope")
    return rectangle_corners(xmin, ymin, xmax, ymax)


def pad_screening_points(footprint: Any) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for pad in footprint.pads:
        half_x = float(pad.size.X) / 2.0 + PAD_SCREENING_MARGIN_MM
        half_y = float(pad.size.Y) / 2.0 + PAD_SCREENING_MARGIN_MM
        local_angle = float(pad.position.angle or 0.0)
        for corner in rectangle_corners(-half_x, -half_y, half_x, half_y):
            x, y = rotate(corner, local_angle)
            points.append((x + float(pad.position.X), y + float(pad.position.Y)))
    require(points, f"{ref_of(footprint)}: no courtyard and no pads for screening envelope")
    return points


def envelope_of(footprint: Any, locked_refs: set[str]) -> Envelope:
    ref = ref_of(footprint)
    require(footprint.layer in {"F.Cu", "B.Cu"},
            f"{ref}: unsupported footprint side {footprint.layer}")
    local_points = courtyard_points(footprint)
    source = COURTYARD_SOURCE if local_points else PAD_SOURCE
    if not local_points:
        local_points = pad_screening_points(footprint)

    footprint_angle = float(footprint.position.angle or 0.0)
    transformed: list[tuple[float, float]] = []
    for local_x, local_y in local_points:
        if footprint.layer == "B.Cu":
            local_x = -local_x
        x, y = rotate((local_x, local_y), footprint_angle)
        transformed.append((x + float(footprint.position.X),
                            y + float(footprint.position.Y)))
    xs = [point[0] for point in transformed]
    ys = [point[1] for point in transformed]
    return Envelope(
        ref=ref,
        side="TOP" if footprint.layer == "F.Cu" else "BOTTOM",
        source=source,
        xmin=min(xs),
        ymin=min(ys),
        xmax=max(xs),
        ymax=max(ys),
        authority_locked=ref in locked_refs,
    )


def load_authority(path: Path) -> tuple[set[str], list[dict[str, Any]]]:
    locked_refs: set[str] = set()
    mounting_holes: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(rows, "mechanical placement authority is empty")
    for row in rows:
        feature = row["Feature_Type"]
        if feature in {"CONNECTOR_PLACEMENT", "MODULE_PLACEMENT"}:
            locked_refs.add(row["RefDes"])
        elif feature == "MOUNTING_HOLE":
            match = re.search(r"NO_COMPONENT_D([0-9.]+)", row["Clearance_Rule"])
            require(match is not None,
                    f"{row['RefDes']}: component-exclusion diameter is not encoded")
            mounting_holes.append({
                "ref": row["RefDes"],
                "x_mm": float(row["X_mm"]),
                "y_mm": float(row["Y_mm"]),
                "component_exclusion_diameter_mm": float(match.group(1)),
            })
    require(len(locked_refs) == 17, f"expected 17 locked connector/module refs, got {len(locked_refs)}")
    require(len(mounting_holes) == 4, f"expected four mounting holes, got {len(mounting_holes)}")
    return locked_refs, mounting_holes


def load_tool_clearances(path: Path) -> list[dict[str, Any]]:
    clearances: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        match = TOOL_GEOMETRY_PATTERN.search(row["Clearance_Rule"])
        if match is None:
            continue
        require(row["Feature_Type"] == "CONNECTOR_PLACEMENT" and
                row["Side"] == "TOP" and row["Access_Direction"] == "UP_Z",
                f"{row['Record_ID']}: tool clearance owner must be a top connector with UP_Z access")
        clearances.append({
            "ref": row["RefDes"],
            "x_mm": float(row["X_mm"]),
            "y_mm": float(row["Y_mm"]),
            "diameter_mm": float(match.group(1)),
            "height_mm": float(match.group(2)),
            "access_direction": row["Access_Direction"],
            "clearance_rule": row["Clearance_Rule"],
        })
    require([item["ref"] for item in clearances] == ["J8", "J9", "J10"],
            "expected J8/J9/J10 U.FL tool-clearance set")
    require({(item["diameter_mm"], item["height_mm"]) for item in clearances} ==
            {(8.0, 15.0)}, "expected D8 x Z15 U.FL tool-clearance geometry")
    return clearances


def component_collision(first: Envelope, second: Envelope) -> dict[str, Any] | None:
    if first.side != second.side:
        return None
    overlap_x = min(first.xmax, second.xmax) - max(first.xmin, second.xmin)
    overlap_y = min(first.ymax, second.ymax) - max(first.ymin, second.ymin)
    if overlap_x <= GEOMETRY_TOLERANCE_MM or overlap_y <= GEOMETRY_TOLERANCE_MM:
        return None
    confirmed = first.source == COURTYARD_SOURCE and second.source == COURTYARD_SOURCE
    return {
        "pair": [first.ref, second.ref],
        "side": first.side,
        "classification": (
            "CONFIRMED_COURTYARD_COLLISION" if confirmed
            else "SCREENING_PAD_ENVELOPE_COLLISION"
        ),
        "envelope_sources": [first.source, second.source],
        "overlap_x_mm": rounded(overlap_x),
        "overlap_y_mm": rounded(overlap_y),
        "overlap_area_mm2": rounded(overlap_x * overlap_y),
        "authority_locked_pair": first.authority_locked and second.authority_locked,
        "bounds_mm": [first.bounds(), second.bounds()],
    }


def mounting_conflict(hole: dict[str, Any], envelope: Envelope) -> dict[str, Any] | None:
    nearest_x = max(envelope.xmin, min(hole["x_mm"], envelope.xmax))
    nearest_y = max(envelope.ymin, min(hole["y_mm"], envelope.ymax))
    distance = math.hypot(nearest_x - hole["x_mm"], nearest_y - hole["y_mm"])
    radius = hole["component_exclusion_diameter_mm"] / 2.0
    if distance >= radius - GEOMETRY_TOLERANCE_MM:
        return None
    confirmed = envelope.source == COURTYARD_SOURCE
    return {
        "pair": [hole["ref"], envelope.ref],
        "side": envelope.side,
        "classification": (
            "CONFIRMED_COURTYARD_TO_MOUNTING_EXCLUSION_CONFLICT" if confirmed
            else "SCREENING_PAD_ENVELOPE_TO_MOUNTING_EXCLUSION_CONFLICT"
        ),
        "envelope_source": envelope.source,
        "hole_center_mm": [rounded(hole["x_mm"]), rounded(hole["y_mm"])],
        "required_radius_mm": rounded(radius),
        "actual_nearest_distance_mm": rounded(distance),
        "clearance_deficit_mm": rounded(radius - distance),
        "authority_locked_component": envelope.authority_locked,
        "component_bounds_mm": envelope.bounds(),
    }


def tool_clearance_conflict(clearance: dict[str, Any], envelope: Envelope) -> dict[str, Any] | None:
    if envelope.side != "TOP" or envelope.ref == clearance["ref"]:
        return None
    nearest_x = max(envelope.xmin, min(clearance["x_mm"], envelope.xmax))
    nearest_y = max(envelope.ymin, min(clearance["y_mm"], envelope.ymax))
    distance = math.hypot(nearest_x - clearance["x_mm"],
                          nearest_y - clearance["y_mm"])
    radius = clearance["diameter_mm"] / 2.0
    if distance >= radius - GEOMETRY_TOLERANCE_MM:
        return None
    confirmed = envelope.source == COURTYARD_SOURCE
    return {
        "pair": [clearance["ref"], envelope.ref],
        "side": envelope.side,
        "classification": (
            "CONFIRMED_TOOL_CLEARANCE_TO_COURTYARD_CONFLICT" if confirmed
            else "SCREENING_TOOL_CLEARANCE_TO_PAD_ENVELOPE_CONFLICT"
        ),
        "envelope_source": envelope.source,
        "tool_center_mm": [rounded(clearance["x_mm"]), rounded(clearance["y_mm"])],
        "required_radius_mm": rounded(radius),
        "required_height_mm": rounded(clearance["height_mm"]),
        "actual_nearest_distance_mm": rounded(distance),
        "clearance_deficit_mm": rounded(radius - distance),
        "access_direction": clearance["access_direction"],
        "clearance_rule": clearance["clearance_rule"],
        "authority_locked_component": envelope.authority_locked,
        "component_bounds_mm": envelope.bounds(),
    }


def expected_control(report: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    return {
        "state": summary["state"],
        "board_sha256": report["board_sha256"],
        "authority_sha256": report["authority_sha256"],
        "assembly_footprints": summary["assembly_footprints"],
        "courtyard_footprints": summary["courtyard_footprints"],
        "pad_screening_footprints": summary["pad_screening_footprints"],
        "confirmed_component_collisions": summary["confirmed_component_collisions"],
        "screening_component_collisions": summary["screening_component_collisions"],
        "confirmed_mounting_clearance_conflicts": summary["confirmed_mounting_clearance_conflicts"],
        "screening_mounting_clearance_conflicts": summary["screening_mounting_clearance_conflicts"],
        "confirmed_tool_clearance_conflicts": summary["confirmed_tool_clearance_conflicts"],
        "screening_tool_clearance_conflicts": summary["screening_tool_clearance_conflicts"],
        "locked_authority_component_conflicts": summary["locked_authority_component_conflicts"],
        "locked_authority_mounting_conflicts": summary["locked_authority_mounting_conflicts"],
        "locked_authority_tool_conflicts": summary["locked_authority_tool_conflicts"],
    }


def verify_controlled_status(status_path: Path, report: dict[str, Any]) -> None:
    status = json.loads(status_path.read_text(encoding="utf-8"))
    review_b = status.get("review_b", {})
    require(review_b.get("complete") is False, "PCB-MAIN Review B unexpectedly complete")
    evidence = review_b.get("evidence", {})
    require(evidence.get("placement_clearance_audit") ==
            "tools/audit_pcb_main_placement_clearance_rev_a.py",
            "PCB-MAIN placement-clearance audit is not bound in capture status")
    require(evidence.get("placement_clearance_record") ==
            "hardware/reviews/PCB_MAIN_PLACEMENT_CLEARANCE_ERRATA_REV_A.md",
            "PCB-MAIN placement-clearance record is not bound in capture status")
    actual = evidence.get("placement_clearance_control")
    expected = expected_control(report)
    require(actual == expected,
            "PCB-MAIN placement-clearance controlled baseline drift: "
            f"status={actual!r} actual={expected!r}")


def audit(board_path: Path, authority_path: Path) -> dict[str, Any]:
    locked_refs, mounting_holes = load_authority(authority_path)
    tool_clearances = load_tool_clearances(authority_path)
    board = Board.from_file(str(board_path), encoding="utf-8")
    footprints = {ref_of(footprint): footprint for footprint in board.footprints}
    require(len(footprints) == len(board.footprints), "duplicate footprint reference")

    assembly = []
    for ref, footprint in sorted(footprints.items()):
        if footprint.properties.get("DIONEA_POPULATION") != "FITTED":
            continue
        package = footprint.properties.get("DIONEA_PACKAGE", "")
        if package.startswith(FIXTURE_PACKAGE_PREFIX):
            continue
        assembly.append(envelope_of(footprint, locked_refs))

    collisions = []
    for first, second in combinations(assembly, 2):
        finding = component_collision(first, second)
        if finding is not None:
            collisions.append(finding)
    collisions.sort(key=lambda finding: tuple(finding["pair"]))

    mounting = []
    for hole in mounting_holes:
        for envelope in assembly:
            finding = mounting_conflict(hole, envelope)
            if finding is not None:
                mounting.append(finding)
    mounting.sort(key=lambda finding: tuple(finding["pair"]))

    tool_findings = []
    for clearance in tool_clearances:
        for envelope in assembly:
            finding = tool_clearance_conflict(clearance, envelope)
            if finding is not None:
                tool_findings.append(finding)
    tool_findings.sort(key=lambda finding: tuple(finding["pair"]))

    confirmed_collisions = [finding for finding in collisions
                            if finding["classification"] == "CONFIRMED_COURTYARD_COLLISION"]
    screening_collisions = [finding for finding in collisions
                            if finding["classification"] == "SCREENING_PAD_ENVELOPE_COLLISION"]
    confirmed_mounting = [finding for finding in mounting
                          if finding["classification"].startswith("CONFIRMED_")]
    screening_mounting = [finding for finding in mounting
                          if finding["classification"].startswith("SCREENING_")]
    confirmed_tool = [finding for finding in tool_findings
                      if finding["classification"].startswith("CONFIRMED_")]
    screening_tool = [finding for finding in tool_findings
                      if finding["classification"].startswith("SCREENING_")]
    locked_component_pairs = sorted(
        finding["pair"] for finding in confirmed_collisions
        if finding["authority_locked_pair"]
    )
    locked_mounting_pairs = sorted(
        finding["pair"] for finding in confirmed_mounting
        if finding["authority_locked_component"]
    )
    locked_tool_pairs = sorted(
        finding["pair"] for finding in confirmed_tool
        if finding["authority_locked_component"]
    )
    blocked = bool(collisions or mounting or tool_findings)
    summary = {
        "state": "BLOCKED_PLACEMENT_CLEARANCE" if blocked else "PASS",
        "assembly_footprints": len(assembly),
        "courtyard_footprints": sum(item.source == COURTYARD_SOURCE for item in assembly),
        "pad_screening_footprints": sum(item.source == PAD_SOURCE for item in assembly),
        "confirmed_component_collisions": len(confirmed_collisions),
        "screening_component_collisions": len(screening_collisions),
        "confirmed_mounting_clearance_conflicts": len(confirmed_mounting),
        "screening_mounting_clearance_conflicts": len(screening_mounting),
        "confirmed_tool_clearance_conflicts": len(confirmed_tool),
        "screening_tool_clearance_conflicts": len(screening_tool),
        "locked_authority_component_conflicts": locked_component_pairs,
        "locked_authority_mounting_conflicts": locked_mounting_pairs,
        "locked_authority_tool_conflicts": locked_tool_pairs,
    }
    return {
        "schema_version": "dioneya.pcb-main-placement-clearance.v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "board": display_path(board_path),
        "board_sha256": sha256(board_path),
        "authority": display_path(authority_path),
        "authority_sha256": sha256(authority_path),
        "method": {
            "same_side_only": True,
            "courtyard_geometry": "AXIS_ALIGNED_ENVELOPE_AFTER_FOOTPRINT_TRANSFORM",
            "missing_courtyard_screening": f"PAD_BOUNDS_PLUS_{PAD_SCREENING_MARGIN_MM:.2f}_MM",
            "ufl_tool_geometry": "TOP_SIDE_CIRCLE_FROM_TOOL_D_RULE",
            "service_edge_overhang": "ALLOWED_BUT_REQUIRES_ENCLOSURE_SWEEP",
            "positive_overlap_tolerance_mm": GEOMETRY_TOLERANCE_MM,
            "fixture_pogo_footprints_excluded": True,
        },
        "summary": summary,
        "confirmed_component_collisions": confirmed_collisions,
        "screening_component_collisions": screening_collisions,
        "confirmed_mounting_clearance_conflicts": confirmed_mounting,
        "screening_mounting_clearance_conflicts": screening_mounting,
        "confirmed_tool_clearance_conflicts": confirmed_tool,
        "screening_tool_clearance_conflicts": screening_tool,
        "release_disposition": (
            "HOLD_PLACEMENT_CLEARANCE_REWORK_REQUIRED"
            if blocked else "PASS_2D_PLACEMENT_CLEARANCE_ROUTING_AND_3D_REVIEW_PENDING"
        ),
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-status-check", action="store_true",
                        help="inventory an experimental board without comparing the committed control")
    parser.add_argument("--strict", action="store_true",
                        help="return non-zero while any placement-clearance finding remains")
    args = parser.parse_args()

    board_path = args.board.resolve()
    authority_path = args.authority.resolve()
    status_path = args.status.resolve()
    require(board_path.is_file(), f"board not found: {board_path}")
    require(authority_path.is_file(), f"authority not found: {authority_path}")
    require(status_path.is_file(), f"capture status not found: {status_path}")

    report = audit(board_path, authority_path)
    if not args.no_status_check:
        verify_controlled_status(status_path, report)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = report["summary"]
    print(f"PCB-MAIN placement-clearance audit: {summary['state']}")
    print(
        f"assembly={summary['assembly_footprints']} "
        f"courtyard={summary['courtyard_footprints']} "
        f"pad_screening={summary['pad_screening_footprints']} "
        f"confirmed_collisions={summary['confirmed_component_collisions']} "
        f"screening_collisions={summary['screening_component_collisions']} "
        f"confirmed_mounting={summary['confirmed_mounting_clearance_conflicts']} "
        f"screening_mounting={summary['screening_mounting_clearance_conflicts']} "
        f"confirmed_tool={summary['confirmed_tool_clearance_conflicts']} "
        f"screening_tool={summary['screening_tool_clearance_conflicts']}"
    )
    print(
        "locked_authority_component_conflicts="
        f"{summary['locked_authority_component_conflicts']} "
        "locked_authority_mounting_conflicts="
        f"{summary['locked_authority_mounting_conflicts']} "
        "locked_authority_tool_conflicts="
        f"{summary['locked_authority_tool_conflicts']}"
    )
    if args.strict and summary["state"] != "PASS":
        print("strict placement-clearance gate: FAIL", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
