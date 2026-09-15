#!/usr/bin/env python3
"""Audit the bounded PCB-PWR Rev.A fitted-component 2D clearance subgate.

This is deliberately narrower than mechanical Review B.  It verifies that the
42 simultaneously fitted assembly bodies have controlled courtyards and at
least 0.20 mm separation on the provisional placement canvas.  DNP footprints,
PCB-only net-ties/test targets, mounting geometry, connector service volumes,
3D envelopes and all routed-copper checks remain outside this subgate.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from kiutils.board import Board

from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
DEFAULT_PLACEMENT = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv"
DEFAULT_STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"

REQUIRED_CLEARANCE_MM = 0.20
GEOMETRY_TOLERANCE_MM = 0.005
BOARD_X_MM = 90.0
BOARD_Y_MM = 60.0
EXPECTED_POPULATION = Counter({"FITTED": 42, "PCB_FEATURE": 13, "DNP": 5})
EXPECTED_PROVISIONAL_EDGE_OVERHANGS = ["J2"]


@dataclass(frozen=True)
class Envelope:
    ref: str
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def bounds(self) -> list[float]:
        return [rounded(self.xmin), rounded(self.ymin),
                rounded(self.xmax), rounded(self.ymax)]


def rounded(value: float) -> float:
    return round(value, 6)


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def ref_of(footprint: Any) -> str:
    property_ref = str(footprint.properties.get("Reference", ""))
    graphic_refs = [str(item.text) for item in footprint.graphicItems
                    if getattr(item, "type", None) == "reference"]
    require(len(graphic_refs) <= 1,
            f"footprint has duplicate reference graphics: {graphic_refs}")
    if property_ref:
        require(not graphic_refs or graphic_refs[0] == property_ref,
                f"reference field/graphic mismatch: {property_ref!r} / {graphic_refs}")
        return property_ref
    require(len(graphic_refs) == 1 and graphic_refs[0],
            "footprint has no non-blank reference")
    return graphic_refs[0]


def population_of(footprint: Any) -> str:
    values = [item.split("=", 1)[1] for item in str(footprint.description).split("|")
              if item.startswith("population=")]
    require(len(values) == 1 and values[0] in EXPECTED_POPULATION,
            f"{ref_of(footprint)}: invalid population metadata {values}")
    return values[0]


def rotate(point: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    cosine, sine = math.cos(angle), math.sin(angle)
    x, y = point
    return x * cosine - y * sine, x * sine + y * cosine


def courtyard_points(footprint: Any) -> list[tuple[float, float]]:
    layer = "F.CrtYd" if footprint.layer == "F.Cu" else "B.CrtYd"
    items = [item for item in footprint.graphicItems
             if getattr(item, "layer", None) == layer]
    require(items, f"{ref_of(footprint)}: fitted footprint has no {layer} geometry")

    points: list[tuple[float, float]] = []
    for item in items:
        item_type = type(item).__name__
        if item_type in {"FpLine", "FpRect"}:
            for field in ("start", "end"):
                point = getattr(item, field, None)
                require(point is not None,
                        f"{ref_of(footprint)}: incomplete {item_type} courtyard")
                points.append((float(point.X), float(point.Y)))
        elif item_type == "FpCircle":
            center = item.center
            radius = math.hypot(float(item.end.X) - float(center.X),
                                float(item.end.Y) - float(center.Y))
            require(radius > 0.0, f"{ref_of(footprint)}: degenerate courtyard circle")
            # A bounding square remains conservative after any footprint rotation.
            points.extend([
                (float(center.X) - radius, float(center.Y) - radius),
                (float(center.X) - radius, float(center.Y) + radius),
                (float(center.X) + radius, float(center.Y) - radius),
                (float(center.X) + radius, float(center.Y) + radius),
            ])
        else:
            raise AssertionError(
                f"{ref_of(footprint)}: unsupported courtyard primitive {item_type}"
            )
    return points


def envelope_of(footprint: Any) -> Envelope:
    ref = ref_of(footprint)
    require(footprint.layer in {"F.Cu", "B.Cu"},
            f"{ref}: unsupported footprint side {footprint.layer}")
    angle = float(footprint.position.angle or 0.0)
    transformed: list[tuple[float, float]] = []
    for local_x, local_y in courtyard_points(footprint):
        if footprint.layer == "B.Cu":
            local_x = -local_x
        x, y = rotate((local_x, local_y), angle)
        transformed.append((x + float(footprint.position.X),
                            y + float(footprint.position.Y)))
    xs = [point[0] for point in transformed]
    ys = [point[1] for point in transformed]
    return Envelope(ref, min(xs), min(ys), max(xs), max(ys))


def rectangle_distance(first: Envelope, second: Envelope) -> tuple[float, float, float]:
    gap_x = max(first.xmin - second.xmax, second.xmin - first.xmax, 0.0)
    gap_y = max(first.ymin - second.ymax, second.ymin - first.ymax, 0.0)
    return math.hypot(gap_x, gap_y), gap_x, gap_y


def expected_control(report: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    return {
        "state": summary["state"],
        "board_semantic_sha256": report["board"]["semantic_sha256"],
        "placement_authority_sha256": report["placement_authority"]["sha256"],
        "fitted_footprints": summary["fitted_footprints"],
        "courtyard_footprints": summary["courtyard_footprints"],
        "excluded_dnp_footprints": summary["excluded_dnp_footprints"],
        "excluded_pcb_feature_footprints": summary["excluded_pcb_feature_footprints"],
        "required_clearance_mm": summary["required_clearance_mm"],
        "minimum_observed_clearance_mm": summary["minimum_observed_clearance_mm"],
        "clearance_conflicts": summary["clearance_conflicts"],
        "provisional_edge_overhangs": summary["provisional_edge_overhangs"],
        "mounting_pattern": "OPEN_DIM_003",
        "connector_and_probe_service_clearance": "OPEN_DIM_003_AND_FIXTURE_REVIEW",
        "routing_complete": False,
        "manufacturing_release": False,
    }


def verify_status(status_path: Path, report: dict[str, Any]) -> None:
    status = json.loads(status_path.read_text(encoding="utf-8"))
    require(status.get("manufacturing_release") is False,
            "PCB-PWR manufacturing release unexpectedly true")
    require(status.get("review_b", {}).get("complete") is False,
            "PCB-PWR Review B unexpectedly complete")
    placement = status.get("native_layout", {}).get("placement_clearance", {})
    require(placement.get("audit") ==
            "tools/audit_pcb_pwr_placement_clearance_rev_a.py",
            "PCB-PWR clearance audit is not bound in capture status")
    require(placement.get("record") ==
            "hardware/reviews/PCB_PWR_PLACEMENT_CLEARANCE_REV_A.md",
            "PCB-PWR clearance record is not bound in capture status")
    require(placement.get("control") == expected_control(report),
            "PCB-PWR placement-clearance control differs from audit")


def audit(board_path: Path, placement_path: Path) -> dict[str, Any]:
    board = Board.from_file(str(board_path), encoding="utf-8")
    footprints = {ref_of(footprint): footprint for footprint in board.footprints}
    require(len(footprints) == len(board.footprints) == 60,
            "PCB-PWR board must contain 60 unique references")

    rows = read_csv(placement_path)
    by_ref = {row["RefDes"]: row for row in rows}
    require(len(rows) == len(by_ref) == 60 and set(by_ref) == set(footprints),
            "PCB-PWR placement authority/reference set differs from board")
    for ref, footprint in footprints.items():
        row = by_ref[ref]
        require(abs(float(footprint.position.X) - float(row["X_mm"])) <= 0.002 and
                abs(float(footprint.position.Y) - float(row["Y_mm"])) <= 0.002 and
                abs((float(footprint.position.angle or 0.0) % 360.0) -
                    (float(row["Rotation_deg"]) % 360.0)) <= 0.01,
                f"{ref}: board position differs from placement authority")

    populations = Counter(population_of(footprint) for footprint in footprints.values())
    require(populations == EXPECTED_POPULATION,
            f"PCB-PWR population set drift: {dict(populations)}")
    fitted = [envelope_of(footprint) for footprint in footprints.values()
              if population_of(footprint) == "FITTED"]
    fitted.sort(key=lambda item: item.ref)

    findings: list[dict[str, Any]] = []
    observed: list[float] = []
    for first, second in combinations(fitted, 2):
        distance, gap_x, gap_y = rectangle_distance(first, second)
        observed.append(distance)
        if distance + GEOMETRY_TOLERANCE_MM >= REQUIRED_CLEARANCE_MM:
            continue
        findings.append({
            "pair": [first.ref, second.ref],
            "distance_mm": rounded(distance),
            "axis_gap_x_mm": rounded(gap_x),
            "axis_gap_y_mm": rounded(gap_y),
            "required_clearance_mm": REQUIRED_CLEARANCE_MM,
            "clearance_deficit_mm": rounded(REQUIRED_CLEARANCE_MM - distance),
            "bounds_mm": [first.bounds(), second.bounds()],
        })

    overhangs = sorted(item.ref for item in fitted if
                       item.xmin < 0.0 or item.ymin < 0.0 or
                       item.xmax > BOARD_X_MM or item.ymax > BOARD_Y_MM)
    require(overhangs == EXPECTED_PROVISIONAL_EDGE_OVERHANGS,
            f"unexpected provisional edge-overhang set: {overhangs}")
    require(len(board.traceItems) == 0 and len(board.zones) == 0,
            "PCB-PWR placement-clearance candidate contains routed copper")

    minimum = min(observed)
    passed = not findings and len(fitted) == 42
    summary = {
        "state": ("PASS_FITTED_2D_PLACEMENT_CLEARANCE_DIM_003_OPEN"
                  if passed else "BLOCKED_FITTED_2D_PLACEMENT_CLEARANCE"),
        "fitted_footprints": len(fitted),
        "courtyard_footprints": len(fitted),
        "excluded_dnp_footprints": populations["DNP"],
        "excluded_pcb_feature_footprints": populations["PCB_FEATURE"],
        "required_clearance_mm": REQUIRED_CLEARANCE_MM,
        "minimum_observed_clearance_mm": rounded(minimum),
        "clearance_conflicts": len(findings),
        "provisional_edge_overhangs": overhangs,
    }
    return {
        "schema": "dioneya-pcb-pwr-placement-clearance-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "board": {
            "path": display_path(board_path),
            "sha256": sha256(board_path),
            "semantic_sha256": semantic_board_sha256(board),
            "trace_items": len(board.traceItems),
            "copper_zones": len(board.zones),
        },
        "placement_authority": {
            "path": display_path(placement_path),
            "sha256": sha256(placement_path),
            "row_count": len(rows),
        },
        "method": {
            "scope": "SIMULTANEOUSLY_FITTED_ASSEMBLY_BODIES_ONLY",
            "courtyard_geometry": "CONSERVATIVE_AXIS_ALIGNED_ENVELOPE_AFTER_TRANSFORM",
            "distance_metric": "EUCLIDEAN_NEAREST_RECTANGLE_DISTANCE",
            "geometry_tolerance_mm": GEOMETRY_TOLERANCE_MM,
            "dnp_and_pcb_features": "EXCLUDED_BODY_SERVICE_AND_FIXTURE_REVIEW_OPEN",
            "j2_edge_overhang": "PROVISIONAL_INTENT_NOT_SERVICE_CLEARANCE_PASS",
        },
        "summary": summary,
        "clearance_conflicts": findings,
        "open_boundaries": [
            "DIM-003 outline mounting pattern terminal and tool zones",
            "J1/J2 mating and harness bend service volumes",
            "TP1-TP10 fixture datum probe access and wear",
            "assembled STEP height enclosure and thermal interface",
            "routing DRC CAM DFM physical evidence and independent Review B",
        ],
        "release_disposition": (
            "PASS_2D_FITTED_CLEARANCE_MECHANICS_ROUTING_AND_REVIEW_B_OPEN"
            if passed else "HOLD_PLACEMENT_CLEARANCE_REWORK_REQUIRED"
        ),
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--placement", type=Path, default=DEFAULT_PLACEMENT)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-status-check", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    board_path = args.board.resolve()
    placement_path = args.placement.resolve()
    status_path = args.status.resolve()
    require(board_path.is_file(), f"board not found: {board_path}")
    require(placement_path.is_file(), f"placement authority not found: {placement_path}")
    require(status_path.is_file(), f"capture status not found: {status_path}")

    report = audit(board_path, placement_path)
    if not args.no_status_check:
        verify_status(status_path, report)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")

    summary = report["summary"]
    print(f"PCB-PWR fitted 2D placement-clearance audit: {summary['state']}")
    print(
        f"fitted={summary['fitted_footprints']} "
        f"courtyard={summary['courtyard_footprints']} "
        f"required_gap_mm={summary['required_clearance_mm']:.2f} "
        f"minimum_gap_mm={summary['minimum_observed_clearance_mm']:.3f} "
        f"conflicts={summary['clearance_conflicts']} "
        f"provisional_edge_overhangs={summary['provisional_edge_overhangs']}"
    )
    print("DIM-003/service/fixture/3D/routing/DRC/CAM/DFM/Review B remain open")
    if args.strict and summary["state"] != \
            "PASS_FITTED_2D_PLACEMENT_CLEARANCE_DIM_003_OPEN":
        print("strict PCB-PWR fitted placement-clearance gate: FAIL", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
