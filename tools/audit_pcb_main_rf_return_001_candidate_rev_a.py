#!/usr/bin/env python3
"""Audit PCB-MAIN RF/SI finding 001 and cellular L2 return candidate 001."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kiutils.board import Board


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
BASE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-RF-RETURN-001"
    / "PCB-MAIN_RF_RETURN_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-RF-RETURN-001"
    / "PCB-MAIN_RF_RETURN_CANDIDATE_REV_A.kicad_pcb"
)
GENERATOR = ROOT / "tools/generate_pcb_main_rf_return_001_candidate_rev_a.py"
REVIEW = ROOT / "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_REV_A.json"
PROPOSAL = ROOT / "hardware/reviews/PCB_MAIN_RF_RETURN_001_CANDIDATE_REV_A.json"
BASIS = ROOT / "hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.json"
CAPTURE_STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"

BASE_SHA256 = "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
CANDIDATE_SHA256 = "22ddd8c56ceabf397ed033a44235b439625d3104fa2cf798bb57b782d24b1352"
GENERATOR_SHA256 = "9c37ce07c1bfe5881e4d239772b9e3aeb8d48fe10abf1fd4acbd14e6b3476e11"
ZONE_NAME = "PCB_MAIN_GND_MODEM_CELL_In1_Cu"
ZONE_TSTAMP = "474ddbc4-d099-4dd3-9f8f-bc95779ae00a"
ZONE_POLYGON = [(10.0, 34.0), (36.0, 34.0), (36.0, 74.0), (10.0, 74.0)]
GND_DIGITAL_POLYGON = [
    (109.35, 74.35), (36.2, 74.35), (36.2, 33.8), (9.8, 33.8),
    (9.8, 74.35), (0.65, 74.35), (0.65, 0.65), (109.35, 0.65),
]
RF_EXPECTED = {
    "CELL_RF": (38, 33.067387862532, "GND_MODEM"),
    "CELL_RF_ANT": (37, 18.436106588963, "GND_MODEM"),
    "GNSS_RF_ANT_BIASED": (17, 10.205266952966, "GND_DIGITAL"),
    "GNSS_RF_DC_BLOCK": (1, 1.0, "GND_DIGITAL"),
    "GNSS_RF_FILTERED": (6, 25.325357133747, "GND_DIGITAL"),
    "LORA_RF_ANT": (26, 14.538138937276, "GND_DIGITAL"),
    "LORA_RF_MODULE": (13, 9.035535027254, "GND_DIGITAL"),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def coordinates(zone: Any) -> list[tuple[float, float]]:
    require(len(zone.polygons) == 1, f"{zone.name}: expected one outline polygon")
    return [(float(point.X), float(point.Y)) for point in zone.polygons[0].coordinates]


def ref_of(footprint: Any) -> str:
    refs = [str(item.text) for item in footprint.graphicItems
            if getattr(item, "type", None) == "reference"]
    property_ref = str(footprint.properties.get("Reference", ""))
    if property_ref:
        require(not refs or refs == [property_ref], "footprint reference mismatch")
        return property_ref
    require(len(refs) == 1 and refs[0], "footprint reference missing")
    return refs[0]


def rotate(point: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    cosine, sine = math.cos(angle), math.sin(angle)
    x, y = point
    return x * cosine + y * sine, -x * sine + y * cosine


def pad_position(board: Board, reference: str, number: str) -> tuple[float, float]:
    footprints = [footprint for footprint in board.footprints
                  if ref_of(footprint) == reference]
    require(len(footprints) == 1, f"missing or duplicate footprint {reference}")
    footprint = footprints[0]
    pads = [pad for pad in footprint.pads if str(pad.number) == number]
    require(len(pads) == 1, f"missing or duplicate pad {reference}.{number}")
    pad = pads[0]
    x, y = rotate(
        (float(pad.position.X), float(pad.position.Y)),
        float(footprint.position.angle or 0.0),
    )
    return x + float(footprint.position.X), y + float(footprint.position.Y)


def drc_inventory(path: Path) -> tuple[Counter[str], int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = Counter(
        violation.get("type", "UNKNOWN")
        for violation in data.get("violations", [])
        if violation.get("severity") == "error"
    )
    return errors, len(data.get("violations", [])), len(data.get("unconnected_items", []))


def audit_drc(base_path: Path, candidate_path: Path) -> dict[str, object]:
    base_errors, base_violations, base_unconnected = drc_inventory(base_path)
    candidate_errors, candidate_violations, candidate_unconnected = drc_inventory(candidate_path)
    added_errors = {
        key: candidate_errors[key] - base_errors[key]
        for key in candidate_errors
        if candidate_errors[key] > base_errors[key]
    }
    require(not added_errors,
            f"cellular L2 return candidate introduces KiCad 9 errors: {added_errors}")
    require(candidate_unconnected <= base_unconnected,
            "cellular L2 return candidate increases unconnected items")
    return {
        "status": "PASS_NO_NEW_KICAD9_DRC_ERRORS_OR_UNCONNECTED_REGRESSION",
        "base_violations": base_violations,
        "candidate_violations": candidate_violations,
        "base_errors": dict(base_errors),
        "candidate_errors": dict(candidate_errors),
        "base_unconnected_items": base_unconnected,
        "candidate_unconnected_items": candidate_unconnected,
        "new_error_counts": added_errors,
    }


def point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
    tolerance: float = 1e-7,
) -> bool:
    px, py = point
    ax, ay = start
    bx, by = end
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > tolerance:
        return False
    dot = (px - ax) * (px - bx) + (py - ay) * (py - by)
    return dot <= tolerance


def point_in_polygon(
    point: tuple[float, float], polygon: list[tuple[float, float]]
) -> bool:
    require(len(polygon) >= 3, "filled-zone polygon has fewer than three points")
    inside = False
    px, py = point
    previous = polygon[-1]
    for current in polygon:
        if point_on_segment(point, previous, current):
            return True
        x1, y1 = previous
        x2, y2 = current
        if (y1 > py) != (y2 > py):
            crossing_x = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            if px < crossing_x:
                inside = not inside
        previous = current
    return inside


def audit_filled_reference(path: Path) -> dict[str, object]:
    """Prove the KiCad-filled local L2 plane exists below both cellular RF routes."""
    board = Board().from_file(str(path), encoding="utf-8")
    # KiCad 9 rewrites the zone identifier token on save, while kiutils 1.4.8
    # does not expose that rewritten UUID as ``tstamp``.  The committed source
    # identity is already locked by static_audit(); select the post-fill copy by
    # its unique controlled name and then re-check its electrical identity.
    zones = [zone for zone in board.zones if zone.name == ZONE_NAME]
    require(len(zones) == 1, "filled candidate is missing the controlled L2 zone")
    zone = zones[0]
    require(
        zone.name == ZONE_NAME
        and zone.netName == "GND_MODEM"
        and zone.layers == ["In1.Cu"],
        "filled candidate L2-zone identity drift",
    )
    polygons = [
        [(float(point.X), float(point.Y)) for point in polygon.coordinates]
        for polygon in zone.filledPolygons
        if polygon.layer == "In1.Cu" and not polygon.island
    ]
    require(polygons,
            "KiCad 9 did not materialize a connected local GND_MODEM L2 zone")

    net_names = {int(net.number): net.name for net in board.nets}
    sample_pitch_mm = 0.1
    sample_counts: Counter[str] = Counter()
    uncovered: list[dict[str, object]] = []
    segment_counts: Counter[str] = Counter()
    for item in board.traceItems:
        name = net_names.get(int(item.net), "")
        if name not in {"CELL_RF", "CELL_RF_ANT"} or type(item).__name__ != "Segment":
            continue
        require(item.layer == "F.Cu" and
                math.isclose(float(item.width), 0.1509, abs_tol=1e-9),
                f"{name}: filled-board RF geometry drift")
        start = (float(item.start.X), float(item.start.Y))
        end = (float(item.end.X), float(item.end.Y))
        length = math.dist(start, end)
        intervals = max(1, math.ceil(length / sample_pitch_mm))
        segment_counts[name] += 1
        for index in range(intervals + 1):
            ratio = index / intervals
            point = (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
            sample_counts[name] += 1
            if not any(point_in_polygon(point, polygon) for polygon in polygons):
                uncovered.append({
                    "net": name,
                    "x_mm": round(point[0], 6),
                    "y_mm": round(point[1], 6),
                })
    require(segment_counts == Counter({"CELL_RF": 38, "CELL_RF_ANT": 37}),
            f"filled-board cellular RF inventory drift: {segment_counts}")
    require(not uncovered,
            f"cellular RF centreline lacks filled GND_MODEM L2 reference: {uncovered[:5]}")
    return {
        "status": "PASS_FILLED_GND_MODEM_L2_UNDER_CELLULAR_RF_CENTRELINES",
        "filled_polygon_count": len(polygons),
        "sample_pitch_mm_max": sample_pitch_mm,
        "samples_by_net": dict(sample_counts),
        "uncovered_samples": 0,
    }


def static_audit() -> dict[str, object]:
    require(sha256(ACTIVE) == BASE_SHA256 and ACTIVE.read_bytes() == BASE.read_bytes(),
            "active PCB-MAIN no longer matches the controlled RF-return baseline")
    require(sha256(BASE) == BASE_SHA256, "RF-return base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "RF-return candidate SHA-256 drift")
    require(sha256(GENERATOR) == GENERATOR_SHA256,
            "RF-return generator SHA-256 drift")

    base = Board().from_file(str(BASE), encoding="utf-8")
    candidate = Board().from_file(str(CANDIDATE), encoding="utf-8")
    for field in (
        "general", "layers", "setup", "properties", "graphicItems",
        "dimensions", "groups", "targets", "nets", "footprints", "traceItems",
    ):
        require(getattr(base, field) == getattr(candidate, field),
                f"RF-return candidate changes accepted field: {field}")

    require(len(base.zones) == 7 and len(candidate.zones) == 8,
            "RF-return zone inventory drift")
    base_zones = {str(zone.tstamp): zone for zone in base.zones}
    candidate_zones = {str(zone.tstamp): zone for zone in candidate.zones}
    require(len(base_zones) == len(base.zones) and
            len(candidate_zones) == len(candidate.zones), "duplicate zone UUID")
    require(set(candidate_zones) - set(base_zones) == {ZONE_TSTAMP},
            "RF-return candidate does not add exactly the controlled zone")
    require(all(base_zones[key] == candidate_zones[key] for key in base_zones),
            "RF-return candidate modifies an accepted zone or rule area")

    zone = candidate_zones[ZONE_TSTAMP]
    require(zone.name == ZONE_NAME and int(zone.net) == 47 and
            zone.netName == "GND_MODEM" and zone.layers == ["In1.Cu"],
            "cellular L2 return zone identity drift")
    require(math.isclose(float(zone.clearance), 0.1, abs_tol=1e-9) and
            math.isclose(float(zone.minThickness), 0.15, abs_tol=1e-9),
            "cellular L2 return zone geometry-rule drift")
    require(coordinates(zone) == ZONE_POLYGON,
            "cellular L2 return zone polygon drift")
    require(not zone.filledPolygons and not zone.fillSegments,
            "candidate must commit the controlled zone unfilled")

    digital = [item for item in candidate.zones
               if item.name == "PCB_MAIN_GND_DIGITAL_In1_Cu"]
    require(len(digital) == 1 and digital[0].netName == "GND_DIGITAL" and
            digital[0].layers == ["In1.Cu"] and
            coordinates(digital[0]) == GND_DIGITAL_POLYGON,
            "accepted GND_DIGITAL L2 cut-out drift")
    require(min(x for x, _ in ZONE_POLYGON) - 9.8 >= 0.2 - 1e-9 and
            36.2 - max(x for x, _ in ZONE_POLYGON) >= 0.2 - 1e-9 and
            min(y for _, y in ZONE_POLYGON) - 33.8 >= 0.2 - 1e-9,
            "cellular L2 zone no longer retains the controlled domain gap")

    net_names = {int(net.number): net.name for net in candidate.nets}
    segments: Counter[str] = Counter()
    lengths: defaultdict[str, float] = defaultdict(float)
    widths: defaultdict[str, set[float]] = defaultdict(set)
    rf_points: defaultdict[str, list[tuple[float, float]]] = defaultdict(list)
    signal_vias: Counter[str] = Counter()
    modem_vias_in_zone = 0
    for item in candidate.traceItems:
        name = net_names.get(int(item.net), "")
        if type(item).__name__ == "Via":
            if name in RF_EXPECTED:
                signal_vias[name] += 1
            if name == "GND_MODEM":
                x, y = float(item.position.X), float(item.position.Y)
                if 10.0 <= x <= 36.0 and 34.0 <= y <= 74.0:
                    modem_vias_in_zone += 1
            continue
        if name not in RF_EXPECTED:
            continue
        require(item.layer == "F.Cu", f"{name}: RF route leaves F.Cu")
        segments[name] += 1
        widths[name].add(float(item.width))
        start = (float(item.start.X), float(item.start.Y))
        end = (float(item.end.X), float(item.end.Y))
        rf_points[name].extend((start, end))
        lengths[name] += math.dist(start, end)
    require(not signal_vias, f"RF signal via inventory drift: {signal_vias}")
    require(sum(segments.values()) == 138, "accepted RF segment total drift")
    for name, (expected_segments, expected_length, _) in RF_EXPECTED.items():
        require(segments[name] == expected_segments, f"{name}: segment-count drift")
        require(math.isclose(lengths[name], expected_length, abs_tol=1e-6),
                f"{name}: routed-length drift")
        require(widths[name] == {0.1509}, f"{name}: RF width drift")

    require(modem_vias_in_zone == 50,
            "unexpected GND_MODEM via count inside cellular L2 zone")
    cell_margins: dict[str, float] = {}
    for name in ("CELL_RF", "CELL_RF_ANT"):
        margins = [
            min(x - 10.0, 36.0 - x, y - 34.0, 74.0 - y)
            for x, y in rf_points[name]
        ]
        require(min(margins) >= 2.525 - 1e-9,
                f"{name}: route leaves controlled cellular L2 reference margin")
        cell_margins[name] = min(margins)

    u9_rf = pad_position(candidate, "U9", "11")
    fl1_rf = pad_position(candidate, "FL1", "A")
    direct = math.dist(u9_rf, fl1_rf)
    stretch = lengths["GNSS_RF_FILTERED"] / direct
    require(math.isclose(direct, 15.543668325077, abs_tol=1e-9),
            "GNSS RF pad-to-pad geometry drift")
    require(math.isclose(stretch, 1.629303752763, abs_tol=1e-9),
            "GNSS RF route stretch drift")

    basis = json.loads(BASIS.read_text(encoding="utf-8"))
    rf_basis = basis["numeric_geometry"]["rf_50ohm"]
    require(basis["selected_public_standard"]["stackup_id"] == "JLC06161H-3313" and
            rf_basis == {
                "target_ohm": 50.0,
                "type": "Single Ended (Non coplanar)",
                "signal_layer": "L1",
                "reference_layer": "L2",
                "trace_width_mm": 0.1509,
            }, "public RF routing basis drift")

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    require(review.get("review_id") == "PCB-MAIN-RF-SI-RETURN-001" and
            review.get("reviewed_board_sha256") == BASE_SHA256 and
            review.get("decision") == "ECO_REQUIRED" and
            review.get("gnss_routeability_finding", {}).get("result") ==
            "FAIL_PLACEMENT_ROUTING_ECO_REQUIRED" and
            review.get("decision_boundary", {}).get("cellular_l2_return_subgate_complete") is False and
            review.get("decision_boundary", {}).get("gnss_rf_placement_routeability_complete") is False and
            review.get("decision_boundary", {}).get("rf_si_return_path_review_complete") is False and
            review.get("decision_boundary", {}).get("cam_or_manufacturing_release") is False,
            "RF/SI review identity or decision boundary drift")
    findings = {item["finding_id"]: item for item in review["return_domain_findings"]}
    require(findings["RF-RP-002"]["result"] ==
            "FAIL_L1_OVER_L2_GEOMETRY_HAS_NO_GND_MODEM_L2_REFERENCE",
            "cellular return-path finding drift")

    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    require(proposal.get("proposal_id") == "PCB-MAIN-RF-RETURN-001" and
            proposal.get("status") ==
            "PROPOSAL_KICAD9_COMPARATIVE_DRC_PASS_PENDING_HUMAN_REVIEW" and
            proposal.get("base", {}).get("board_sha256") == BASE_SHA256 and
            proposal.get("candidate", {}).get("board_sha256") == CANDIDATE_SHA256 and
            proposal.get("added_zone", {}).get("gnd_modem_vias_inside_polygon") == 50 and
            proposal.get("static_validation", {}).get("cross_domain_join_added") is False and
            proposal.get("required_machine_gate") == {
                "kicad_version": "9.x",
                "refill_base_and_candidate": True,
                "comparative_drc_new_error_count": 0,
                "unconnected_item_regression_allowed": False,
                "filled_gnd_modem_l2_cellular_rf_centreline_coverage_required": True,
                "maximum_coverage_sample_pitch_mm": 0.1,
            } and
            proposal.get("decision_boundary", {}).get("proposal_only") is True and
            proposal.get("decision_boundary", {}).get("gnss_rf_placement_routeability_complete") is False and
            proposal.get("decision_boundary", {}).get("review_b_complete") is False and
            proposal.get("decision_boundary", {}).get("cam_or_manufacturing_release") is False,
            "RF-return proposal identity or release boundary drift")
    require(
        proposal.get("commit_bound_machine_gate") == {
            "head_commit_sha": "239016fdd295426766cc88209822be39610297db",
            "head_tree_sha": "7a6e0c226318bd85e6456d17bae119b489d2aff1",
            "pcb_native_run_id": 35508574131,
            "pcb_native_run_number": 267,
            "pcb_native_conclusion": "success",
            "comparative_drc_step": "success",
            "ci_run_id": 35508574124,
            "ci_run_number": 540,
            "ci_conclusion": "success",
            "artifact_id": 10603873750,
            "artifact_name": "evt-pre-20-kicad-native-gate",
            "artifact_digest": (
                "sha256:65adbdc2a6f9b2803645fe6df17cd8ee2b6eb6d4ab0b03be76322626ec814ded"
            ),
            "baseline_drc_sha256": (
                "36c07ab710f2b9ac429b2b2e76369be3fe9235b67abd3532e946411310570a2d"
            ),
            "candidate_drc_sha256": (
                "d1d337fe2dccf6818e9e1e76a869d25b345bd2d0a93c4e3e6b0177f1aad4a9ea"
            ),
            "comparative_audit_sha256": (
                "73bf1b365b06c4091e3dae18cab6412b1b4c90705d609c8659da1ac64c45a3db"
            ),
            "filled_candidate_sha256": (
                "c0b1aa4555a754420e2002a07f25bb0639c5f2c886e11948e0b243671d175e78"
            ),
        },
        "RF-return commit-bound machine-gate evidence drift",
    )
    require(
        proposal.get("comparative_kicad9_drc") == {
            "status": "PASS_NO_NEW_KICAD9_DRC_ERRORS_OR_UNCONNECTED_REGRESSION",
            "base_violations": 226,
            "candidate_violations": 226,
            "base_errors": 0,
            "candidate_errors": 0,
            "base_unconnected_items": 429,
            "candidate_unconnected_items": 429,
            "new_error_counts": {},
        }
        and proposal.get("filled_reference") == {
            "status": "PASS_FILLED_GND_MODEM_L2_UNDER_CELLULAR_RF_CENTRELINES",
            "filled_polygon_count": 1,
            "maximum_sample_pitch_mm": 0.1,
            "cell_rf_samples": 385,
            "cell_rf_ant_samples": 238,
            "uncovered_samples": 0,
        },
        "RF-return KiCad 9 DRC or filled-reference evidence drift",
    )

    capture_status = json.loads(CAPTURE_STATUS.read_text(encoding="utf-8"))
    evidence = capture_status.get("review_b", {}).get("evidence", {})
    require(
        evidence.get("rf_si_return_path_review") == str(REVIEW.relative_to(ROOT))
        and evidence.get("rf_si_return_path_review_record") ==
        "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_REV_A.md"
        and evidence.get("rf_si_return_path_review_audit") ==
        "tools/audit_pcb_main_rf_return_001_candidate_rev_a.py"
        and evidence.get("rf_si_return_path_status") ==
        "ECO_REQUIRED_CELLULAR_L2_RETURN_AND_GNSS_PLACEMENT_ROUTING_OPEN"
        and evidence.get("rf_return_001_candidate") ==
        str(CANDIDATE.relative_to(ROOT))
        and evidence.get("rf_return_001_candidate_record") ==
        str(PROPOSAL.relative_to(ROOT))
        and evidence.get("rf_return_001_candidate_review") ==
        "hardware/reviews/PCB_MAIN_RF_RETURN_001_CANDIDATE_REV_A.md"
        and evidence.get("rf_return_001_status") ==
        "PROPOSAL_KICAD9_COMPARATIVE_DRC_PASS_PENDING_HUMAN_REVIEW_NOT_APPLIED"
        and capture_status.get("manufacturing_release") is False,
        "PCB-MAIN capture-status RF/SI ECO traceability or release boundary drift",
    )

    return {
        "schema_version": "dioneya.pcb-main-rf-return-001-candidate-audit.v1",
        "status": "PASS_STATIC_ECO_REQUIRED_AND_CELLULAR_L2_RETURN_PROPOSAL_CONTROLLED",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "generator_sha256": GENERATOR_SHA256,
        "accepted_rf_segments": sum(segments.values()),
        "accepted_rf_signal_vias": sum(signal_vias.values()),
        "added_zones": 1,
        "gnd_modem_vias_inside_added_zone": modem_vias_in_zone,
        "cell_rf_minimum_zone_edge_margin_mm": cell_margins,
        "gnss_rf_filtered_length_mm": lengths["GNSS_RF_FILTERED"],
        "gnss_rf_filtered_pad_distance_mm": direct,
        "gnss_rf_filtered_stretch_ratio": stretch,
        "decision": "ECO_REQUIRED",
        "kicad9_comparative_drc": (
            "PASS_NO_NEW_KICAD9_DRC_ERRORS_OR_UNCONNECTED_REGRESSION"
        ),
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-candidate", type=Path)
    parser.add_argument("--filled-candidate", type=Path)
    args = parser.parse_args()
    report = static_audit()
    if args.drc_base or args.drc_candidate:
        require(bool(args.drc_base and args.drc_candidate),
                "both comparative DRC reports are required")
        report["comparative_drc"] = audit_drc(
            args.drc_base.resolve(), args.drc_candidate.resolve()
        )
        report["kicad9_comparative_drc"] = report["comparative_drc"]["status"]
    if args.filled_candidate:
        require(bool(args.drc_base and args.drc_candidate),
                "filled-reference audit requires both comparative DRC reports")
        report["filled_reference"] = audit_filled_reference(
            args.filled_candidate.resolve()
        )
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    print("PCB-MAIN RF/SI return review and cellular L2 candidate audit: PASS")
    print("decision=ECO_REQUIRED cellular_l2_candidate=CONTROLLED gnss_eco=OPEN")
    print("release_boundary=RF_SI_REVIEW_B_AND_MANUFACTURING_RELEASE_OPEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
