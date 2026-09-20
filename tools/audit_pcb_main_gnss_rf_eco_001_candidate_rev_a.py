#!/usr/bin/env python3
"""Audit the bounded PCB-MAIN GNSS RF placement/routeability ECO-001."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kiutils.board import Board

import audit_pcb_main_placement_clearance_rev_a as placement_clearance


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-GNSS-RF-ECO-001"
    / "PCB-MAIN_GNSS_RF_ECO_001_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-GNSS-RF-ECO-001"
    / "PCB-MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.kicad_pcb"
)
GENERATOR = ROOT / "tools/generate_pcb_main_gnss_rf_eco_001_candidate_rev_a.py"
PROPOSAL = ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.json"
PROPOSAL_RECORD = ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.md"
REVIEW = ROOT / "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_REV_A.json"
CAPTURE_STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
PLACEMENT_AUTHORITY = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"

BASE_SHA256 = "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
CANDIDATE_SHA256 = "d4c0eaa95bb62c7b9ae15b110fb3a76e6a056f462f0a36a734b3fa63730d2aee"
GENERATOR_SHA256 = "da949bfd6acd35876af7cd97837801354c101d351438cc620153cf50884716f0"
RF_WIDTH_MM = 0.1509
GND_ZONE_NAME = "PCB_MAIN_GND_DIGITAL_In1_Cu"
SAMPLE_PITCH_MM = 0.1
GNSS_RF_NETS = {
    "GNSS_RF_ANT_BIASED",
    "GNSS_RF_DC_BLOCK",
    "GNSS_RF_FILTERED",
}
EXPECTED_POSES = {
    "FL1": ((60.5, 68.0, 0.0), (56.8, 51.6, 270.0)),
    "C64": ((58.75, 68.0, 0.0), (58.3, 51.6, 180.0)),
}
EXPECTED_BASE_ROUTES = {
    "GNSS_RF_ANT_BIASED": (17, 10.205266952966369),
    "GNSS_RF_DC_BLOCK": (1, 1.0),
    "GNSS_RF_FILTERED": (6, 25.325357133746827),
}
EXPECTED_CANDIDATE_ROUTES = {
    "GNSS_RF_ANT_BIASED": (22, 34.11475179074332),
    "GNSS_RF_DC_BLOCK": (2, 1.3869101147436909),
    "GNSS_RF_FILTERED": (2, 1.3269968101992187),
}
FILTERED_PAD_DISTANCE_MM = 1.299278646018627
FILTERED_STRETCH_RATIO = 1.02133350245194
REMOVED_TRACE_TSTAMPS = {
    "1dfbdae1-2515-4a74-ac93-32252bfff0bc",
    "0de81ed9-e21d-4a77-8665-1c6f9f233bb5",
    "0ecb7fd9-e7ca-4939-a2e0-d2d1cc20afb6",
    "cb4b0680-668d-47ac-82bb-4687dca027de",
    "cc1858ee-b635-4ec2-93f2-83b945f8f7e6",
    "d421cfb1-108c-4d9a-a0a2-3f4dd0795a9c",
    "f66c9606-454e-4415-aa49-7c8e66ab2659",
    "8bb16eba-0c23-436c-83cb-15711942aa13",
    "97b4ffd7-640c-458b-a674-df70012edd9e",
    "e4d5b871-eae5-40c8-bc94-33070afaccfd",
    "ed333547-457e-4a27-b04c-76eefac1703b",
    "f0cf6fbe-b2d3-49cb-ac31-38e0b70d131a",
    "1b0fbb03-8a78-4e3f-b887-5b3096c609de",
    "3b6e7ac6-f2af-49e1-bbb9-dd1c158f1517",
    "72553cba-285e-40e8-afa0-669c5c279833",
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(first: float, second: float, tolerance: float = 1e-6) -> bool:
    return math.isclose(float(first), float(second), rel_tol=0.0,
                        abs_tol=tolerance)


def ref_of(footprint: Any) -> str:
    property_ref = str(footprint.properties.get("Reference", ""))
    graphic_refs = [
        str(item.text) for item in footprint.graphicItems
        if getattr(item, "type", None) == "reference"
    ]
    if property_ref:
        require(not graphic_refs or graphic_refs == [property_ref],
                "footprint reference mismatch")
        return property_ref
    require(len(graphic_refs) == 1 and graphic_refs[0],
            "footprint reference missing")
    return graphic_refs[0]


def pose_of(footprint: Any) -> tuple[float, float, float]:
    return (
        float(footprint.position.X),
        float(footprint.position.Y),
        float(footprint.position.angle or 0.0) % 360.0,
    )


def pose_matches(actual: tuple[float, float, float],
                 expected: tuple[float, float, float]) -> bool:
    return all(close(first, second) for first, second in zip(actual, expected))


def footprint_without_pose(footprint: Any) -> dict[str, Any]:
    return {
        key: value for key, value in footprint.__dict__.items()
        if key != "position"
    }


def net_code(item: Any) -> int:
    value = getattr(item, "net", 0)
    return int(getattr(value, "number", value) or 0)


def trace_map(board: Board) -> dict[str, Any]:
    result = {str(item.tstamp): item for item in board.traceItems}
    require(len(result) == len(board.traceItems), "duplicate trace UUID")
    return result


def point(value: Any) -> tuple[float, float]:
    return float(value.X), float(value.Y)


def added_trace_signature(item: Any, net_names: dict[int, str]) -> tuple[Any, ...]:
    name = net_names[net_code(item)]
    if type(item).__name__ == "Segment":
        return (
            "segment", name, point(item.start), point(item.end),
            float(item.width), item.layer,
        )
    require(type(item).__name__ == "Via", "unexpected added trace-item type")
    return (
        "via", name, point(item.position), float(item.size),
        float(item.drill), tuple(item.layers),
    )


EXPECTED_ADDED_TRACE_SIGNATURES = Counter({
    ("segment", "GNSS_RF_ANT_BIASED", (58.4125, 67.975), (61.95, 68.25), RF_WIDTH_MM, "F.Cu"): 1,
    ("segment", "GNSS_RF_ANT_BIASED", (61.95, 68.25), (63.2, 67.0), RF_WIDTH_MM, "F.Cu"): 1,
    ("segment", "GNSS_RF_ANT_BIASED", (63.2, 67.0), (63.2, 54.7), RF_WIDTH_MM, "F.Cu"): 1,
    ("segment", "GNSS_RF_ANT_BIASED", (63.2, 54.7), (59.5, 51.0), RF_WIDTH_MM, "F.Cu"): 1,
    ("segment", "GNSS_RF_ANT_BIASED", (59.5, 51.0), (58.625, 51.6), RF_WIDTH_MM, "F.Cu"): 1,
    ("segment", "GNSS_RF_DC_BLOCK", (57.975, 51.6), (57.45, 51.1), RF_WIDTH_MM, "F.Cu"): 1,
    ("segment", "GNSS_RF_DC_BLOCK", (57.45, 51.1), (56.8, 51.225), RF_WIDTH_MM, "F.Cu"): 1,
    ("segment", "GNSS_RF_FILTERED", (56.8, 53.25), (56.8, 52.55), RF_WIDTH_MM, "F.Cu"): 1,
    ("segment", "GNSS_RF_FILTERED", (56.8, 52.55), (56.55, 51.975), RF_WIDTH_MM, "F.Cu"): 1,
    ("segment", "GND_DIGITAL", (56.55, 51.6), (55.725, 51.85), 0.15, "F.Cu"): 1,
    ("segment", "GND_DIGITAL", (57.05, 51.975), (57.05, 51.6), 0.15, "F.Cu"): 1,
    ("segment", "GND_DIGITAL", (57.05, 51.6), (57.45, 51.95), 0.15, "F.Cu"): 1,
    ("segment", "GND_DIGITAL", (57.45, 51.95), (57.75, 52.55), 0.15, "F.Cu"): 1,
    ("via", "GND_DIGITAL", (57.75, 52.55), 0.5, 0.3, ("F.Cu", "B.Cu")): 1,
})


def route_stats(board: Board) -> dict[str, tuple[int, float]]:
    net_names = {int(net.number): net.name for net in board.nets}
    counts: Counter[str] = Counter()
    lengths: defaultdict[str, float] = defaultdict(float)
    for item in board.traceItems:
        name = net_names.get(net_code(item), "")
        if name not in GNSS_RF_NETS:
            continue
        require(type(item).__name__ == "Segment" and item.layer == "F.Cu" and
                close(float(item.width), RF_WIDTH_MM, 1e-9),
                f"{name}: RF geometry drift")
        counts[name] += 1
        lengths[name] += math.dist(point(item.start), point(item.end))
    return {name: (counts[name], lengths[name]) for name in GNSS_RF_NETS}


def rotate(local: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    x, y = local
    return (
        x * math.cos(angle) + y * math.sin(angle),
        -x * math.sin(angle) + y * math.cos(angle),
    )


def pad_position(board: Board, reference: str, number: str) -> tuple[float, float]:
    footprint = next(item for item in board.footprints if ref_of(item) == reference)
    pad = next(item for item in footprint.pads if str(item.number) == number)
    local = rotate(
        (float(pad.position.X), float(pad.position.Y)),
        float(footprint.position.angle or 0.0),
    )
    return (
        float(footprint.position.X) + local[0],
        float(footprint.position.Y) + local[1],
    )


def audit_no_signal_under_u9(board: Board) -> int:
    net_names = {int(net.number): net.name for net in board.nets}
    body = (48.45, 53.15, 58.55, 62.85)
    rf_pad = (56.4, 52.35, 57.2, 54.15)
    samples = 0
    for item in board.traceItems:
        if (net_names.get(net_code(item), "") not in GNSS_RF_NETS or
                type(item).__name__ != "Segment"):
            continue
        start, end = point(item.start), point(item.end)
        intervals = max(1, math.ceil(math.dist(start, end) / 0.025))
        for index in range(intervals + 1):
            ratio = index / intervals
            x = start[0] + (end[0] - start[0]) * ratio
            y = start[1] + (end[1] - start[1]) * ratio
            samples += 1
            inside_body = body[0] < x < body[2] and body[1] < y < body[3]
            inside_rf_pad = rf_pad[0] <= x <= rf_pad[2] and rf_pad[1] <= y <= rf_pad[3]
            require(not inside_body or inside_rf_pad,
                    f"GNSS signal copper runs under U9 body at {(x, y)}")
    return samples


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
            f"GNSS RF ECO introduces KiCad 9 errors: {added_errors}")
    require(candidate_unconnected <= base_unconnected,
            "GNSS RF ECO increases unconnected items")
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


def point_on_segment(point_xy: tuple[float, float], start: tuple[float, float],
                     end: tuple[float, float], tolerance: float = 1e-7) -> bool:
    px, py = point_xy
    ax, ay = start
    bx, by = end
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > tolerance:
        return False
    return (px - ax) * (px - bx) + (py - ay) * (py - by) <= tolerance


def point_in_polygon(point_xy: tuple[float, float],
                     polygon: list[tuple[float, float]]) -> bool:
    inside = False
    px, py = point_xy
    previous = polygon[-1]
    for current in polygon:
        if point_on_segment(point_xy, previous, current):
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
    board = Board().from_file(str(path), encoding="utf-8")
    zones = [zone for zone in board.zones if zone.name == GND_ZONE_NAME]
    require(len(zones) == 1, "filled candidate is missing GND_DIGITAL L2 zone")
    zone = zones[0]
    require(zone.netName == "GND_DIGITAL" and zone.layers == ["In1.Cu"],
            "filled GND_DIGITAL L2-zone identity drift")
    polygons = [
        [point(item) for item in polygon.coordinates]
        for polygon in zone.filledPolygons
        if polygon.layer == "In1.Cu" and not polygon.island
    ]
    require(polygons, "KiCad 9 did not materialize connected GND_DIGITAL L2 copper")

    net_names = {int(net.number): net.name for net in board.nets}
    sample_counts: Counter[str] = Counter()
    uncovered: list[dict[str, object]] = []
    for item in board.traceItems:
        name = net_names.get(net_code(item), "")
        if name not in GNSS_RF_NETS or type(item).__name__ != "Segment":
            continue
        start, end = point(item.start), point(item.end)
        intervals = max(1, math.ceil(math.dist(start, end) / SAMPLE_PITCH_MM))
        for index in range(intervals + 1):
            ratio = index / intervals
            sample = (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
            sample_counts[name] += 1
            if not any(point_in_polygon(sample, polygon) for polygon in polygons):
                uncovered.append({"net": name, "point_mm": sample})
    require(set(sample_counts) == GNSS_RF_NETS,
            f"filled-board GNSS RF net inventory drift: {sample_counts}")
    require(not uncovered,
            f"GNSS RF centreline lacks filled GND_DIGITAL L2 reference: {uncovered[:5]}")
    return {
        "status": "PASS_FILLED_GND_DIGITAL_L2_UNDER_GNSS_RF_CENTRELINES",
        "filled_polygon_count": len(polygons),
        "sample_pitch_mm_max": SAMPLE_PITCH_MM,
        "samples_by_net": dict(sample_counts),
        "uncovered_samples": 0,
    }


def static_audit() -> dict[str, object]:
    for path in (BASE, CANDIDATE, GENERATOR, PROPOSAL, PROPOSAL_RECORD,
                 REVIEW, CAPTURE_STATUS, PLACEMENT_AUTHORITY):
        require(path.is_file() and path.stat().st_size > 0,
                f"missing GNSS ECO input: {path}")
    require(sha256(BASE) == BASE_SHA256, "GNSS ECO base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "GNSS ECO candidate SHA-256 drift")
    require(sha256(GENERATOR) == GENERATOR_SHA256,
            "GNSS ECO generator SHA-256 drift")

    base = Board().from_file(str(BASE), encoding="utf-8")
    candidate = Board().from_file(str(CANDIDATE), encoding="utf-8")
    require(base.nets == candidate.nets, "GNSS ECO net table drift")
    for field in ("general", "layers", "setup", "properties", "graphicItems",
                  "dimensions", "groups", "targets", "zones"):
        require(getattr(base, field) == getattr(candidate, field),
                f"GNSS ECO board-level field drift: {field}")

    base_footprints = {ref_of(item): item for item in base.footprints}
    candidate_footprints = {ref_of(item): item for item in candidate.footprints}
    require(len(base_footprints) == len(candidate_footprints) == 251 and
            base_footprints.keys() == candidate_footprints.keys(),
            "GNSS ECO footprint inventory drift")
    changed = {
        ref for ref in base_footprints
        if base_footprints[ref] != candidate_footprints[ref]
    }
    require(changed == set(EXPECTED_POSES),
            f"GNSS ECO unexpected footprint delta: {sorted(changed)}")
    for ref, (before, after) in EXPECTED_POSES.items():
        source, target = base_footprints[ref], candidate_footprints[ref]
        require(pose_matches(pose_of(source), before) and
                pose_matches(pose_of(target), after),
                f"{ref}: GNSS ECO pose drift")
        require(footprint_without_pose(source) == footprint_without_pose(target),
                f"{ref}: non-placement footprint data drift")
        require(target.locked is False and
                target.properties.get("DIONEA_PLACEMENT_CLASS") ==
                "UNLOCKED_LAYOUT_CANDIDATE",
                f"{ref}: placement class drift")

    base_traces = trace_map(base)
    candidate_traces = trace_map(candidate)
    removed = set(base_traces) - set(candidate_traces)
    added = set(candidate_traces) - set(base_traces)
    require(removed == REMOVED_TRACE_TSTAMPS,
            f"GNSS ECO removed trace inventory drift: {removed}")
    require(len(added) == 14 and len(base.traceItems) == 976 and
            len(candidate.traceItems) == 975,
            "GNSS ECO trace-item count drift")
    for tstamp in set(base_traces) & set(candidate_traces):
        require(base_traces[tstamp] == candidate_traces[tstamp],
                f"GNSS ECO modified unrelated trace item {tstamp}")
    net_names = {int(net.number): net.name for net in candidate.nets}
    actual_added = Counter(
        added_trace_signature(candidate_traces[tstamp], net_names)
        for tstamp in added
    )
    require(actual_added == EXPECTED_ADDED_TRACE_SIGNATURES,
            f"GNSS ECO added trace geometry drift: {actual_added}")

    for board, expected, label in (
        (base, EXPECTED_BASE_ROUTES, "base"),
        (candidate, EXPECTED_CANDIDATE_ROUTES, "candidate"),
    ):
        actual = route_stats(board)
        for name, (expected_count, expected_length) in expected.items():
            count, length = actual[name]
            require(count == expected_count and close(length, expected_length, 1e-9),
                    f"{label} {name}: route inventory drift")

    direct = math.dist(
        pad_position(candidate, "U9", "11"),
        pad_position(candidate, "FL1", "A"),
    )
    filtered_length = route_stats(candidate)["GNSS_RF_FILTERED"][1]
    require(close(direct, FILTERED_PAD_DISTANCE_MM, 1e-9) and
            close(filtered_length / direct, FILTERED_STRETCH_RATIO, 1e-9),
            "GNSS filtered routeability metric drift")
    under_u9_samples = audit_no_signal_under_u9(candidate)

    placement = placement_clearance.audit(CANDIDATE, PLACEMENT_AUTHORITY)
    require(placement["summary"] == {
        "state": "PASS",
        "assembly_footprints": 227,
        "courtyard_footprints": 227,
        "pad_screening_footprints": 0,
        "confirmed_component_collisions": 0,
        "screening_component_collisions": 0,
        "confirmed_mounting_clearance_conflicts": 0,
        "screening_mounting_clearance_conflicts": 0,
        "confirmed_tool_clearance_conflicts": 0,
        "screening_tool_clearance_conflicts": 0,
        "locked_authority_component_conflicts": [],
        "locked_authority_mounting_conflicts": [],
        "locked_authority_tool_conflicts": [],
    }, "GNSS ECO strict 2D placement-clearance drift")

    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    boundary = proposal.get("decision_boundary", {})
    require(proposal.get("proposal_id") == "PCB-MAIN-GNSS-RF-ECO-001" and
            proposal.get("status") ==
            "PROPOSAL_KICAD9_COMPARATIVE_DRC_PASS_PENDING_HUMAN_REVIEW" and
            proposal.get("base", {}).get("board_sha256") == BASE_SHA256 and
            proposal.get("candidate", {}).get("board_sha256") == CANDIDATE_SHA256 and
            proposal.get("candidate", {}).get("generator_sha256") == GENERATOR_SHA256 and
            proposal.get("static_validation", {}).get("strict_2d_placement_clearance") == "PASS" and
            proposal.get("static_validation", {}).get("gnss_signal_copper_under_u9_body") is False and
            proposal.get("required_machine_gate", {}).get(
                "filled_gnd_digital_l2_gnss_rf_centreline_coverage_required"
            ) is True,
            "GNSS ECO proposal identity or machine-gate contract drift")
    require(proposal.get("commit_bound_machine_gate") == {
        "head_commit_sha": "67538ba5dfea4cde08c06738cc6b537847a25398",
        "head_tree_sha": "f45c0923461b299eb3ccfaa97eb9ca2cf069a285",
        "pcb_native_run_id": 35511383587,
        "pcb_native_run_number": 273,
        "pcb_native_conclusion": "success",
        "comparative_drc_step": "success",
        "ci_run_id": 35511383579,
        "ci_run_number": 546,
        "ci_conclusion": "success",
        "artifact_id": 10605856993,
        "artifact_name": "evt-pre-20-kicad-native-gate",
        "artifact_digest": (
            "sha256:3e08973033e263876c833abc220196daf1b6cbfc60d2476924032131c96b9056"
        ),
        "baseline_drc_sha256": (
            "0ed9ee12912d34c5fedbb0bcd2dd5d3069d62dc26bff6d705f6dbff5b071a157"
        ),
        "candidate_drc_sha256": (
            "58c39848989df2a4eb96cd4b69358811fd04d6e66f8434ca9cd02c2ab58573f7"
        ),
        "comparative_audit_sha256": (
            "c8e72c07e9e51f2f7617baf604e79256b03b8bb360c1cf69d6a91f43831c2bf8"
        ),
        "filled_candidate_sha256": (
            "085a750207f5a2de668d986c210ed348884afa84eb5229a163161b355550b839"
        ),
        "placement_clearance_sha256": (
            "49af2a5051748183d91399feaf32b73ceb06e3ee540f437d1e4dd20d2251ac28"
        ),
    }, "GNSS ECO commit-bound machine-gate evidence drift")
    require(proposal.get("comparative_kicad9_drc") == {
        "status": "PASS_NO_NEW_KICAD9_DRC_ERRORS_OR_UNCONNECTED_REGRESSION",
        "base_violations": 226,
        "candidate_violations": 227,
        "base_errors": 0,
        "candidate_errors": 0,
        "base_unconnected_items": 429,
        "candidate_unconnected_items": 429,
        "new_error_counts": {},
    } and proposal.get("filled_reference") == {
        "status": "PASS_FILLED_GND_DIGITAL_L2_UNDER_GNSS_RF_CENTRELINES",
        "filled_polygon_count": 1,
        "maximum_sample_pitch_mm": 0.1,
        "gnss_rf_ant_biased_samples": 372,
        "gnss_rf_dc_block_samples": 17,
        "gnss_rf_filtered_samples": 17,
        "uncovered_samples": 0,
    }, "GNSS ECO KiCad 9 DRC or filled-reference evidence drift")
    require(boundary == {
        "proposal_only": True,
        "applied_to_authoritative_board": False,
        "cellular_l2_return_subgate_complete": False,
        "gnss_rf_placement_routeability_complete": False,
        "rf_si_return_path_review_complete": False,
        "routing_complete": False,
        "review_b_complete": False,
        "cam_or_manufacturing_release": False,
    }, "GNSS ECO decision boundary drift")

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    remediation = {item["proposal_id"]: item for item in review["required_remediation"]}
    require("PCB-MAIN-GNSS-RF-ECO-001" in remediation and
            review.get("decision") == "ECO_REQUIRED" and
            review.get("decision_boundary", {}).get(
                "gnss_rf_placement_routeability_complete"
            ) is False,
            "GNSS ECO return-path review linkage drift")

    capture = json.loads(CAPTURE_STATUS.read_text(encoding="utf-8"))
    evidence = capture.get("review_b", {}).get("evidence", {})
    require(
        evidence.get("gnss_rf_eco_001_candidate") == str(CANDIDATE.relative_to(ROOT))
        and evidence.get("gnss_rf_eco_001_candidate_record") == str(PROPOSAL.relative_to(ROOT))
        and evidence.get("gnss_rf_eco_001_candidate_review") == str(PROPOSAL_RECORD.relative_to(ROOT))
        and evidence.get("gnss_rf_eco_001_status") ==
        "PROPOSAL_KICAD9_COMPARATIVE_DRC_PASS_PENDING_HUMAN_REVIEW_NOT_APPLIED"
        and capture.get("manufacturing_release") is False,
        "GNSS ECO capture-status traceability or release boundary drift",
    )

    return {
        "schema_version": "dioneya.pcb-main-gnss-rf-eco-001-audit.v1",
        "status": "PASS_STATIC_GNSS_RF_PLACEMENT_ROUTEABILITY_PROPOSAL_CONTROLLED",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "generator_sha256": GENERATOR_SHA256,
        "changed_footprints": sorted(changed),
        "base_trace_items": len(base.traceItems),
        "candidate_trace_items": len(candidate.traceItems),
        "filtered_pad_distance_mm": direct,
        "filtered_route_length_mm": filtered_length,
        "filtered_stretch_ratio": filtered_length / direct,
        "under_u9_audit_samples": under_u9_samples,
        "strict_2d_placement_clearance": "PASS",
        "kicad9_comparative_drc": (
            "PASS_NO_NEW_KICAD9_DRC_ERRORS_OR_UNCONNECTED_REGRESSION"
        ),
        "gnss_rf_placement_routeability_complete": False,
        "rf_si_return_path_review_complete": False,
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
    print("PCB-MAIN GNSS RF ECO-001 audit: PASS_STATIC_PROPOSAL_CONTROLLED")
    print(
        "changed_footprints=['C64', 'FL1'] "
        f"filtered_route={report['filtered_route_length_mm']:.6f}_mm"
    )
    print("release_boundary=HUMAN_REVIEW_RF_SI_REVIEW_B_AND_MANUFACTURING_OPEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
