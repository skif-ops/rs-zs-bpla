#!/usr/bin/env python3
"""Audit PCB-PWR Rev.A fitted-body and accepted EVT mounting clearance.

This verifies that the 44 simultaneously fitted assembly bodies retain at least
0.20 mm courtyard separation and that the four DIM-003 mounting exclusions do
not intersect a fitted body or existing copper pad.  DNP body population and all
routed-copper checks remain outside this bounded subgate.
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
EXPECTED_POPULATION = Counter({"FITTED": 44, "PCB_FEATURE": 13, "DNP": 5})
EXPECTED_PROVISIONAL_EDGE_OVERHANGS = ["J2"]
EXPECTED_MOUNTING_HOLES = {
    "H1": (5.0, 5.0),
    "H2": (82.0, 5.0),
    "H3": (68.0, 55.0),
    "H4": (5.0, 55.0),
}
MOUNTING_DRILL_MM = 3.4
MOUNTING_COPPER_EXCLUSION_RADIUS_MM = 4.0
MOUNTING_FITTED_EXCLUSION_RADIUS_MM = 5.0
ECO_002_SHA256 = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"
ECO_002_POSES = {
    "U3": (55.0, 14.0, 90.0),
    "U4": (55.0, 42.0, 90.0),
    "C4": (57.8, 14.03, 270.0),
    "C6": (57.8, 42.03, 270.0),
    "C20": (52.35, 14.0, 90.0),
    "C21": (52.35, 42.0, 90.0),
    "L1": (62.5, 14.0, 180.0),
    "L2": (62.5, 42.0, 180.0),
}


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


def point_rectangle_distance(x: float, y: float, envelope: Envelope) -> float:
    gap_x = max(envelope.xmin - x, x - envelope.xmax, 0.0)
    gap_y = max(envelope.ymin - y, y - envelope.ymax, 0.0)
    return math.hypot(gap_x, gap_y)


def pad_envelope(footprint: Any, pad: Any) -> Envelope:
    fp_angle = float(footprint.position.angle or 0.0)
    local_x = float(pad.position.X)
    local_y = float(pad.position.Y)
    center_x, center_y = rotate((local_x, local_y), fp_angle)
    center_x += float(footprint.position.X)
    center_y += float(footprint.position.Y)
    pad_angle = fp_angle + float(pad.position.angle or 0.0)
    half_x = float(pad.size.X) / 2.0
    half_y = float(pad.size.Y) / 2.0
    corners = [
        rotate((dx, dy), pad_angle)
        for dx in (-half_x, half_x)
        for dy in (-half_y, half_y)
    ]
    xs = [center_x + point[0] for point in corners]
    ys = [center_y + point[1] for point in corners]
    return Envelope(ref_of(footprint), min(xs), min(ys), max(xs), max(ys))


def validate_mounting_hole(footprint: Any, reference: str,
                           expected_xy: tuple[float, float]) -> None:
    require(str(footprint.libId) == "DioneyaPWR:MountingHole_M3_3.4_EVT",
            f"{reference}: mounting footprint binding differs")
    require(abs(float(footprint.position.X) - expected_xy[0]) <= 0.002 and
            abs(float(footprint.position.Y) - expected_xy[1]) <= 0.002,
            f"{reference}: mounting coordinate differs")
    attributes = footprint.attributes
    require(bool(attributes.boardOnly) and bool(attributes.excludeFromPosFiles)
            and bool(attributes.excludeFromBom),
            f"{reference}: mounting footprint release attributes differ")
    require(len(footprint.pads) == 1, f"{reference}: expected one NPTH pad")
    pad = footprint.pads[0]
    require(str(pad.type) == "np_thru_hole" and str(pad.shape) == "circle",
            f"{reference}: mounting pad type/shape differs")
    require(abs(float(pad.size.X) - MOUNTING_DRILL_MM) <= 0.001 and
            abs(float(pad.size.Y) - MOUNTING_DRILL_MM) <= 0.001 and
            pad.drill is not None and
            abs(float(pad.drill.diameter) - MOUNTING_DRILL_MM) <= 0.001,
            f"{reference}: mounting drill differs")
    require(abs(float(pad.clearance) - 2.3) <= 0.001,
            f"{reference}: D8 all-copper exclusion differs")


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
        "mounting_holes": summary["mounting_holes"],
        "mounting_pattern": "EVT_DIM_003_ACCEPTED_H1_H4_NPTH_3P4",
        "mounting_fitted_exclusion_diameter_mm": 10.0,
        "minimum_mounting_to_fitted_body_margin_mm":
            summary["minimum_mounting_to_fitted_body_margin_mm"],
        "mounting_to_fitted_body_conflicts":
            summary["mounting_to_fitted_body_conflicts"],
        "mounting_to_existing_pad_conflicts":
            summary["mounting_to_existing_pad_conflicts"],
        "connector_and_probe_service_clearance": "EVT_DIM_003_ACCEPTED_SERIAL_REVALIDATION_REQUIRED",
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
    board_sha256 = sha256(board_path)
    footprints = {ref_of(footprint): footprint for footprint in board.footprints}
    require(len(footprints) == len(board.footprints) == 66,
            "PCB-PWR board must contain 62 electrical and four mounting references")

    rows = read_csv(placement_path)
    by_ref = {row["RefDes"]: row for row in rows}
    require(len(rows) == len(by_ref) == 62 and
            set(footprints) == set(by_ref) | set(EXPECTED_MOUNTING_HOLES),
            "PCB-PWR electrical/mounting reference set differs from authority")
    for ref, row in by_ref.items():
        footprint = footprints[ref]
        expected = (
            ECO_002_POSES[ref]
            if board_sha256 == ECO_002_SHA256 and ref in ECO_002_POSES
            else (float(row["X_mm"]), float(row["Y_mm"]),
                  float(row["Rotation_deg"]) % 360.0)
        )
        require(abs(float(footprint.position.X) - expected[0]) <= 0.002 and
                abs(float(footprint.position.Y) - expected[1]) <= 0.002 and
                abs((float(footprint.position.angle or 0.0) % 360.0) -
                    expected[2]) <= 0.01,
                f"{ref}: board position differs from placement authority or exact ECO-002 override")

    for ref, xy in EXPECTED_MOUNTING_HOLES.items():
        validate_mounting_hole(footprints[ref], ref, xy)

    electrical = [footprints[ref] for ref in by_ref]
    populations = Counter(population_of(footprint) for footprint in electrical)
    require(populations == EXPECTED_POPULATION,
            f"PCB-PWR population set drift: {dict(populations)}")
    fitted = [envelope_of(footprint) for footprint in electrical
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

    mounting_body_findings: list[dict[str, Any]] = []
    mounting_margins: list[float] = []
    for hole, (x, y) in EXPECTED_MOUNTING_HOLES.items():
        for body in fitted:
            margin = point_rectangle_distance(x, y, body) - \
                MOUNTING_FITTED_EXCLUSION_RADIUS_MM
            mounting_margins.append(margin)
            if margin + GEOMETRY_TOLERANCE_MM < REQUIRED_CLEARANCE_MM:
                mounting_body_findings.append({
                    "hole": hole,
                    "reference": body.ref,
                    "margin_mm": rounded(margin),
                    "required_margin_mm": REQUIRED_CLEARANCE_MM,
                    "body_bounds_mm": body.bounds(),
                })

    mounting_pad_findings: list[dict[str, Any]] = []
    for hole, (x, y) in EXPECTED_MOUNTING_HOLES.items():
        for footprint in electrical:
            for pad in footprint.pads:
                envelope = pad_envelope(footprint, pad)
                margin = point_rectangle_distance(x, y, envelope) - \
                    MOUNTING_COPPER_EXCLUSION_RADIUS_MM
                if margin + GEOMETRY_TOLERANCE_MM < 0.0:
                    mounting_pad_findings.append({
                        "hole": hole,
                        "reference": ref_of(footprint),
                        "pad": str(pad.number),
                        "margin_mm": rounded(margin),
                        "pad_bounds_mm": envelope.bounds(),
                    })

    require(len(board.traceItems) in {0, 2, 3, 4, 8, 14} and len(board.zones) == 0,
            "PCB-PWR copper exceeds the accepted ECO-002 successor boundary")

    minimum = min(observed)
    passed = (not findings and not mounting_body_findings and
              not mounting_pad_findings and len(fitted) == 44)
    summary = {
        "state": ("PASS_FITTED_2D_AND_EVT_MOUNTING_CLEARANCE_DIM_003_ACCEPTED"
                  if passed else "BLOCKED_FITTED_2D_PLACEMENT_CLEARANCE"),
        "fitted_footprints": len(fitted),
        "courtyard_footprints": len(fitted),
        "excluded_dnp_footprints": populations["DNP"],
        "excluded_pcb_feature_footprints": populations["PCB_FEATURE"],
        "required_clearance_mm": REQUIRED_CLEARANCE_MM,
        "minimum_observed_clearance_mm": rounded(minimum),
        "clearance_conflicts": len(findings),
        "provisional_edge_overhangs": overhangs,
        "mounting_holes": len(EXPECTED_MOUNTING_HOLES),
        "minimum_mounting_to_fitted_body_margin_mm": rounded(min(mounting_margins)),
        "mounting_to_fitted_body_conflicts": len(mounting_body_findings),
        "mounting_to_existing_pad_conflicts": len(mounting_pad_findings),
    }
    return {
        "schema": "dioneya-pcb-pwr-placement-clearance-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "board": {
            "path": display_path(board_path),
            "sha256": board_sha256,
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
        "mounting_to_fitted_body_conflicts": mounting_body_findings,
        "mounting_to_existing_pad_conflicts": mounting_pad_findings,
        "open_boundaries": [
            "serial enclosure and exact vendor component STEP revalidation",
            "fabricator stackup copper weights and numeric power geometry",
            "routing DRC CAM DFM physical evidence and independent Review B",
        ],
        "release_disposition": (
            "PASS_EVT_2D_FITTED_AND_MOUNTING_CLEARANCE_ROUTING_AND_REVIEW_B_OPEN"
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
    print(f"PCB-PWR fitted 2D and EVT mounting-clearance audit: {summary['state']}")
    print(
        f"fitted={summary['fitted_footprints']} "
        f"courtyard={summary['courtyard_footprints']} "
        f"required_gap_mm={summary['required_clearance_mm']:.2f} "
        f"minimum_gap_mm={summary['minimum_observed_clearance_mm']:.3f} "
        f"conflicts={summary['clearance_conflicts']} "
        f"mounting_holes={summary['mounting_holes']} "
        f"mounting_margin_mm={summary['minimum_mounting_to_fitted_body_margin_mm']:.3f} "
        f"mounting_body_conflicts={summary['mounting_to_fitted_body_conflicts']} "
        f"mounting_pad_conflicts={summary['mounting_to_existing_pad_conflicts']} "
        f"provisional_edge_overhangs={summary['provisional_edge_overhangs']}"
    )
    print("DIM-003 EVT mechanics accepted; routing/DRC/CAM/DFM/Review B remain open")
    if args.strict and summary["state"] != \
            "PASS_FITTED_2D_AND_EVT_MOUNTING_CLEARANCE_DIM_003_ACCEPTED":
        print("strict PCB-PWR fitted placement-clearance gate: FAIL", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
