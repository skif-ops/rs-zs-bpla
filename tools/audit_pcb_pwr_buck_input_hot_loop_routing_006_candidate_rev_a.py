#!/usr/bin/env python3
"""Audit PCB-PWR dual buck input hot-loop routing candidate 006."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from kiutils.board import Board

from audit_pcb_pwr_routing_authority_rev_a import ref_of, semantic_board_sha256
from generate_pcb_pwr_buck_input_hot_loop_routing_006_candidate_rev_a import (
    CHANNELS,
    routes,
    vias,
    zones,
)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-INPUT-HOT-LOOP-ROUTING-006/PCB-PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-INPUT-HOT-LOOP-ROUTING-006/PCB-PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_CANDIDATE_REV_A.kicad_pcb"
ACTIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
REVIEW = ROOT / "hardware/reviews/PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_CANDIDATE_REV_A.json"
GENERATOR = ROOT / "tools/generate_pcb_pwr_buck_input_hot_loop_routing_006_candidate_rev_a.py"
ROUTING_RULES = ROOT / "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv"
STACKUP_BASIS = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"

BASE_SHA256 = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"
CANDIDATE_SHA256 = "9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0"
BASE_SEMANTIC_SHA256 = "0e52d4cbc80104691e3793a579c7c7a8570e3640fabc2fb02bd7ea2e65643555"
CANDIDATE_SEMANTIC_SHA256 = "4da495603ca0c4ed2f7c4a3cb1197a133856408ac6f262ac976c1dab5667f687"
GENERATOR_SHA256 = "97dc3b8f0051482370771cc22b133bef8bef05c7f320a210ce5c9c803695dd72"
ROUTING_RULES_SHA256 = "551a9691d51fd9451bf60193d79b8ed244d6b61fd5ec9c844a15050710f48988"
STACKUP_BASIS_SHA256 = "c417669cab385eb702c53a1912ad5973bda3ca0fec8cbc5c3e331a511178afad"
MINIMUM_EDGE_CLEARANCE_MM = 0.3


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point(value: Any) -> tuple[float, float]:
    return float(value.X), float(value.Y)


def rotate_clockwise(
    value: tuple[float, float], angle_deg: float
) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    x, y = value
    return (
        x * math.cos(angle) + y * math.sin(angle),
        -x * math.sin(angle) + y * math.cos(angle),
    )


def pad_rectangle(footprint: Any, pad: Any) -> tuple[float, float, float, float]:
    local = rotate_clockwise(
        (float(pad.position.X), float(pad.position.Y)),
        float(footprint.position.angle or 0.0),
    )
    center_x = float(footprint.position.X) + local[0]
    center_y = float(footprint.position.Y) + local[1]
    # KiCad 9 serializes child pad angles in board coordinates after the
    # controlled ECO-002 rotation; do not add the parent angle a second time.
    pad_angle = float(pad.position.angle or 0.0)
    half_x, half_y = float(pad.size.X) / 2.0, float(pad.size.Y) / 2.0
    corners = [
        rotate_clockwise((x, y), pad_angle)
        for x in (-half_x, half_x)
        for y in (-half_y, half_y)
    ]
    xs = [center_x + item[0] for item in corners]
    ys = [center_y + item[1] for item in corners]
    return min(xs), min(ys), max(xs), max(ys)


def cross(
    start: tuple[float, float],
    end: tuple[float, float],
    value: tuple[float, float],
) -> float:
    return (
        (end[0] - start[0]) * (value[1] - start[1])
        - (end[1] - start[1]) * (value[0] - start[0])
    )


def on_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    value: tuple[float, float],
) -> bool:
    return (
        min(start[0], end[0]) - 1e-9 <= value[0] <= max(start[0], end[0]) + 1e-9
        and min(start[1], end[1]) - 1e-9 <= value[1]
        <= max(start[1], end[1]) + 1e-9
        and abs(cross(start, end, value)) < 1e-9
    )


def segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    values = (cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b))
    proper = (
        ((values[0] > 0 > values[1]) or (values[1] > 0 > values[0]))
        and ((values[2] > 0 > values[3]) or (values[3] > 0 > values[2]))
    )
    return proper or any(
        (
            abs(values[0]) < 1e-9 and on_segment(a, b, c),
            abs(values[1]) < 1e-9 and on_segment(a, b, d),
            abs(values[2]) < 1e-9 and on_segment(c, d, a),
            abs(values[3]) < 1e-9 and on_segment(c, d, b),
        )
    )


def point_segment_distance(
    value: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    magnitude = dx * dx + dy * dy
    if magnitude == 0:
        return math.dist(value, start)
    ratio = max(
        0.0,
        min(
            1.0,
            ((value[0] - start[0]) * dx + (value[1] - start[1]) * dy)
            / magnitude,
        ),
    )
    projection = (start[0] + ratio * dx, start[1] + ratio * dy)
    return math.dist(value, projection)


def segment_distance(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> float:
    if segments_intersect(a, b, c, d):
        return 0.0
    return min(
        point_segment_distance(a, c, d),
        point_segment_distance(b, c, d),
        point_segment_distance(c, a, b),
        point_segment_distance(d, a, b),
    )


def point_rectangle_distance(
    value: tuple[float, float], rectangle: tuple[float, float, float, float]
) -> float:
    xmin, ymin, xmax, ymax = rectangle
    dx = max(xmin - value[0], 0.0, value[0] - xmax)
    dy = max(ymin - value[1], 0.0, value[1] - ymax)
    return math.hypot(dx, dy)


def segment_rectangle_distance(
    start: tuple[float, float],
    end: tuple[float, float],
    rectangle: tuple[float, float, float, float],
) -> float:
    xmin, ymin, xmax, ymax = rectangle
    if any(
        xmin <= value[0] <= xmax and ymin <= value[1] <= ymax
        for value in (start, end)
    ):
        return 0.0
    corners = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
    edges = list(zip(corners, corners[1:] + corners[:1]))
    return min(segment_distance(start, end, first, second) for first, second in edges)


def copper_clearance_screen(
    base: Board, candidate: Board, added_segments: list[Any], added_vias: list[Any]
) -> dict[str, object]:
    net_names = {int(net.number): str(net.name) for net in candidate.nets}
    minimum = math.inf
    limiting_object = ""
    for item in added_segments:
        net_name = net_names[int(item.net)]
        start, end, width = point(item.start), point(item.end), float(item.width)
        for footprint in candidate.footprints:
            for pad in footprint.pads:
                if not ({"F.Cu", "*.Cu"} & {str(layer) for layer in pad.layers}):
                    continue
                pad_net = str(pad.net.name) if pad.net is not None else ""
                if pad_net == net_name:
                    continue
                clearance = (
                    segment_rectangle_distance(start, end, pad_rectangle(footprint, pad))
                    - width / 2.0
                )
                if clearance < minimum:
                    minimum = clearance
                    limiting_object = f"{net_name} segment to {ref_of(footprint)}.{pad.number}"
        for predecessor in base.traceItems:
            if type(predecessor).__name__ != "Segment":
                continue
            predecessor_net = net_names[int(predecessor.net)]
            if predecessor_net == net_name:
                continue
            clearance = segment_distance(
                start, end, point(predecessor.start), point(predecessor.end)
            ) - (width + float(predecessor.width)) / 2.0
            if clearance < minimum:
                minimum = clearance
                limiting_object = f"{net_name} segment to accepted {predecessor_net} trace"

    for index, first in enumerate(added_segments):
        first_net = net_names[int(first.net)]
        for second in added_segments[index + 1 :]:
            second_net = net_names[int(second.net)]
            if first_net == second_net:
                continue
            clearance = segment_distance(
                point(first.start), point(first.end), point(second.start), point(second.end)
            ) - (float(first.width) + float(second.width)) / 2.0
            if clearance < minimum:
                minimum = clearance
                limiting_object = f"new {first_net} segment to new {second_net} segment"

    for via in added_vias:
        net_name = net_names[int(via.net)]
        center, radius = point(via.position), float(via.size) / 2.0
        for footprint in candidate.footprints:
            for pad in footprint.pads:
                if not ({"F.Cu", "*.Cu"} & {str(layer) for layer in pad.layers}):
                    continue
                pad_net = str(pad.net.name) if pad.net is not None else ""
                if pad_net == net_name:
                    continue
                clearance = point_rectangle_distance(
                    center, pad_rectangle(footprint, pad)
                ) - radius
                if clearance < minimum:
                    minimum = clearance
                    limiting_object = f"{net_name} via to {ref_of(footprint)}.{pad.number}"

    require(
        minimum + 1e-9 >= MINIMUM_EDGE_CLEARANCE_MM,
        f"candidate-006 conservative copper clearance {minimum:.6f} mm is below 0.3 mm",
    )
    return {
        "status": "PASS_MINIMUM_0P3_MM_FOREIGN_COPPER_EDGE_CLEARANCE",
        "minimum_edge_clearance_mm": round(minimum, 6),
        "limiting_object": limiting_object,
    }


def drc_inventory(path: Path) -> tuple[Counter[tuple[str, str]], int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fingerprints = Counter(
        (str(item.get("severity")), str(item.get("type")))
        for item in payload.get("violations", [])
    )
    return fingerprints, len(payload.get("violations", [])), len(
        payload.get("unconnected_items", [])
    )


def audit_drc(base_path: Path, candidate_path: Path) -> dict[str, object]:
    base_fp, base_violations, base_unconnected = drc_inventory(base_path)
    candidate_fp, candidate_violations, candidate_unconnected = drc_inventory(
        candidate_path
    )
    require(not (candidate_fp - base_fp), "candidate introduces DRC fingerprints")
    require(not (base_fp - candidate_fp), "candidate removes unrelated DRC fingerprints")
    require(
        (base_violations, candidate_violations) == (85, 85),
        "candidate must preserve 85 DRC violations",
    )
    require(
        (base_unconnected, candidate_unconnected) == (117, 108),
        "candidate must close exactly nine unconnected items",
    )
    return {
        "status": "PASS_ZERO_DRC_FINGERPRINT_DELTA_EXACT_NINE_CONNECTION_REDUCTION",
        "base_violations": base_violations,
        "candidate_violations": candidate_violations,
        "base_unconnected": base_unconnected,
        "candidate_unconnected": candidate_unconnected,
        "new_drc_fingerprints": 0,
        "removed_drc_fingerprints": 0,
    }


def audit(
    drc_base: Path | None = None, drc_candidate: Path | None = None
) -> dict[str, object]:
    require(
        sha256(BASE) == BASE_SHA256
        and sha256(ACTIVE) in {BASE_SHA256, CANDIDATE_SHA256}
        and ACTIVE.read_bytes() in {BASE.read_bytes(), CANDIDATE.read_bytes()},
        "candidate-006 base or authoritative PCB-PWR drift",
    )
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "candidate-006 SHA-256 drift")
    require(
        sha256(GENERATOR) == GENERATOR_SHA256
        and sha256(ROUTING_RULES) == ROUTING_RULES_SHA256
        and sha256(STACKUP_BASIS) == STACKUP_BASIS_SHA256,
        "candidate-006 source binding drift",
    )
    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    require(
        semantic_board_sha256(base) == BASE_SEMANTIC_SHA256
        and semantic_board_sha256(candidate) == CANDIDATE_SEMANTIC_SHA256,
        "candidate-006 semantic identity drift",
    )
    require(
        len(base.traceItems) == 14
        and len(candidate.traceItems) == 35
        and len(base.zones) == 0
        and len(candidate.zones) == 2,
        "candidate-006 copper inventory drift",
    )
    require(
        candidate.traceItems[:14] == base.traceItems,
        "candidate-006 modifies accepted predecessor copper",
    )
    require(
        len(candidate.footprints) == len(base.footprints) == 66,
        "candidate-006 footprint inventory drift",
    )

    net_names = {int(net.number): str(net.name) for net in candidate.nets}
    added_segments = [
        item for item in candidate.traceItems[14:] if type(item).__name__ == "Segment"
    ]
    added_vias = [
        item for item in candidate.traceItems[14:] if type(item).__name__ == "Via"
    ]
    require(
        len(added_segments) == len(routes()) == 13
        and len(added_vias) == len(vias()) == 8,
        "candidate-006 segment or via inventory drift",
    )
    for index, (item, expected) in enumerate(
        zip(added_segments, routes(), strict=True), start=1
    ):
        require(
            net_names[int(item.net)] == expected["net"]
            and str(item.layer) == "F.Cu"
            and point(item.start) == expected["start"]
            and point(item.end) == expected["end"]
            and math.isclose(float(item.width), float(expected["width"]), abs_tol=1e-9),
            f"candidate-006 segment {index} identity drift",
        )
    for index, (item, expected) in enumerate(
        zip(added_vias, vias(), strict=True), start=1
    ):
        require(
            net_names[int(item.net)] == "GND_PWR"
            and point(item.position) == expected["at"]
            and math.isclose(float(item.size), 0.6, abs_tol=1e-9)
            and math.isclose(float(item.drill), 0.3, abs_tol=1e-9)
            and list(item.layers) == ["F.Cu", "B.Cu"],
            f"candidate-006 via {index} identity drift",
        )

    expected_zones = zones()
    require(
        [str(item.name) for item in candidate.zones]
        == [str(item["name"]) for item in expected_zones]
        and all(int(item.net) == 13 for item in candidate.zones)
        and all(list(item.layers) == ["In1.Cu"] for item in candidate.zones),
        "candidate-006 local-plane identity drift",
    )

    clearance = copper_clearance_screen(base, candidate, added_segments, added_vias)
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    require(
        review["creation_authorization"]
        == "ACCEPT_PCB_PWR_ROUTING_CANDIDATE_006_CREATION_SUBGATE"
        and review["scope_revision_authorization"]
        == "ACCEPT_PCB_PWR_ROUTING_CANDIDATE_006_VIA_PLANE_SCOPE_REVISION_SUBGATE"
        and review["candidate"]["sha256"] == CANDIDATE_SHA256
        and review["source_binding"]["generator_sha256"] == GENERATOR_SHA256
        and review["via_plane_disposition"]["generic_twelve_via_rule_satisfied"]
        is False
        and review["via_plane_disposition"]["physical_evt_validation_required"]
        is True
        and review["deferred_boundary"]["application_authorized"] is False
        and review["invariants"]["authoritative_board_modified"] is False
        and review["routing_complete"] is False
        and review["review_b_complete"] is False
        and review["cam_or_manufacturing_release"] is False,
        "candidate-006 proposal boundary drift",
    )

    report: dict[str, object] = {
        "status": "PASS_STATIC_PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_CANDIDATE",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "routed_nets": ["VBAT_SYS", "GND_PWR"],
        "connections": [
            "C11-C20-U3 VIN/PGND",
            "C12-C21-U4 VIN/PGND and U4.EN",
        ],
        "trace_items": 35,
        "added_segments": 13,
        "added_vias": 8,
        "added_local_planes": 2,
        "local_plane_layer": "In1.Cu",
        "via_geometry_mm": {"diameter": 0.6, "drill": 0.3},
        "copper_clearance_screen": clearance,
        "generic_twelve_via_rule_satisfied": False,
        "physical_evt_validation_required": True,
        "authoritative_board_modified": False,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require(
        (drc_base is None) == (drc_candidate is None),
        "both comparative DRC paths are required together",
    )
    if drc_base is not None and drc_candidate is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_candidate)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.drc_base, args.drc_candidate)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR buck input hot-loop routing 006 candidate audit:", report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
