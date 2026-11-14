#!/usr/bin/env python3
"""Audit PCB-PWR dual buck switch-node routing candidate 005."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kiutils.board import Board

from audit_pcb_pwr_routing_authority_rev_a import ref_of, semantic_board_sha256
from generate_pcb_pwr_buck_switch_node_routing_005_candidate_rev_a import ROUTES


from pcb_pwr_hot_loop_006_board import historical_basis_board

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-SWITCH-NODE-ROUTING-005/PCB-PWR_BUCK_SWITCH_NODE_ROUTING_005_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-SWITCH-NODE-ROUTING-005/PCB-PWR_BUCK_SWITCH_NODE_ROUTING_005_CANDIDATE_REV_A.kicad_pcb"
ACTIVE = historical_basis_board(ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb")
REVIEW = ROOT / "hardware/reviews/PCB_PWR_BUCK_SWITCH_NODE_ROUTING_005_CANDIDATE_REV_A.json"
GENERATOR = ROOT / "tools/generate_pcb_pwr_buck_switch_node_routing_005_candidate_rev_a.py"
ROUTING_RULES = ROOT / "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv"
STACKUP_BASIS = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"

BASE_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
CANDIDATE_SHA256 = "5d135a38774c4e223c1db8d6a3fc0e8c9c492fe3ba24f5e2ec4c1b00ab2166d7"
BASE_SEMANTIC_SHA256 = "f7a659d0740e78d40eddae7016724bd8e616baf9fb425f06ace70ec9acca4d3d"
CANDIDATE_SEMANTIC_SHA256 = "465f5b41265a7f8ccb80a6f7edbb937b2eebad0333730e7586e8f76e3d1d8391"
GENERATOR_SHA256 = "965c722290d47d662d9a4d6f08c09ca01d1fa1d50f9d64928f3809e819afbd57"
ACTIVE_GENERATOR_SHA256 = "1465130e19177f593f2013f32ae23a9a330fb592ef8e8cf6286c58d07214d621"
ROUTING_RULES_SHA256 = "551a9691d51fd9451bf60193d79b8ed244d6b61fd5ec9c844a15050710f48988"
STACKUP_BASIS_SHA256 = "41733d7d27e2c3ab831e602ee81b072146944da0a5efe8a2c805eeed46ecd1ca"
ECO_002_SUCCESSOR_SHA256 = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"
ECO_002_STACKUP_BASIS_SHA256 = "c417669cab385eb702c53a1912ad5973bda3ca0fec8cbc5c3e331a511178afad"
MINIMUM_EDGE_CLEARANCE_MM = 0.4


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point(value: Any) -> tuple[float, float]:
    return float(value.X), float(value.Y)


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
        and min(start[1], end[1]) - 1e-9
        <= value[1]
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


def rotate(value: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    x, y = value
    return (
        x * math.cos(angle) - y * math.sin(angle),
        x * math.sin(angle) + y * math.cos(angle),
    )


def pad_rectangle(footprint: Any, pad: Any) -> tuple[float, float, float, float]:
    angle = float(footprint.position.angle or 0.0)
    center = rotate((float(pad.position.X), float(pad.position.Y)), angle)
    center_x = float(footprint.position.X) + center[0]
    center_y = float(footprint.position.Y) + center[1]
    pad_angle = angle + float(pad.position.angle or 0.0)
    half_x, half_y = float(pad.size.X) / 2.0, float(pad.size.Y) / 2.0
    corners = [
        rotate((x, y), pad_angle)
        for x in (-half_x, half_x)
        for y in (-half_y, half_y)
    ]
    xs = [center_x + item[0] for item in corners]
    ys = [center_y + item[1] for item in corners]
    return min(xs), min(ys), max(xs), max(ys)


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
    base: Board, candidate: Board, added: list[Any], net_names: dict[int, str]
) -> dict[str, object]:
    minimum = math.inf
    limiting_object = ""
    for item in added:
        net_name = net_names[int(item.net)]
        start, end, width = point(item.start), point(item.end), float(item.width)
        for footprint in candidate.footprints:
            for pad in footprint.pads:
                layers = {str(layer) for layer in pad.layers}
                if not ({"F.Cu", "*.Cu"} & layers):
                    continue
                pad_net = str(pad.net.name) if pad.net is not None else ""
                if pad_net == net_name:
                    continue
                distance = segment_rectangle_distance(
                    start, end, pad_rectangle(footprint, pad)
                )
                edge_clearance = distance - width / 2.0
                if edge_clearance < minimum:
                    minimum = edge_clearance
                    limiting_object = f"{ref_of(footprint)}.{pad.number}"
        for predecessor in base.traceItems:
            predecessor_net = net_names[int(predecessor.net)]
            if predecessor_net == net_name:
                continue
            distance = segment_distance(
                start, end, point(predecessor.start), point(predecessor.end)
            )
            edge_clearance = distance - (width + float(predecessor.width)) / 2.0
            if edge_clearance < minimum:
                minimum = edge_clearance
                limiting_object = f"accepted trace {predecessor_net}"
    require(
        minimum + 1e-9 >= MINIMUM_EDGE_CLEARANCE_MM,
        f"switch-node copper clearance {minimum:.6f} mm is below 0.4 mm",
    )
    return {
        "status": "PASS_MINIMUM_0P4_MM_FOREIGN_COPPER_EDGE_CLEARANCE",
        "minimum_edge_clearance_mm": round(minimum, 6),
        "limiting_object": limiting_object,
    }


def drc_inventory(path: Path) -> tuple[Counter[tuple[str, str]], int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fingerprints = Counter(
        (str(item.get("severity")), str(item.get("type")))
        for item in payload.get("violations", [])
    )
    return (
        fingerprints,
        len(payload.get("violations", [])),
        len(payload.get("unconnected_items", [])),
    )


def audit_drc(base_path: Path, candidate_path: Path) -> dict[str, object]:
    base_fp, base_violations, base_unconnected = drc_inventory(base_path)
    candidate_fp, candidate_violations, candidate_unconnected = drc_inventory(
        candidate_path
    )
    require(not (candidate_fp - base_fp), "candidate introduces DRC fingerprints")
    require(not (base_fp - candidate_fp), "candidate removes unrelated DRC fingerprints")
    require(
        (base_violations, candidate_violations) == (86, 86),
        "candidate must preserve 86 DRC violations",
    )
    require(
        (base_unconnected, candidate_unconnected) == (121, 117),
        "candidate must close exactly four unconnected items",
    )
    return {
        "status": "PASS_ZERO_DRC_FINGERPRINT_DELTA_EXACT_FOUR_CONNECTION_REDUCTION",
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
        and sha256(ACTIVE) in {
            BASE_SHA256, CANDIDATE_SHA256, ECO_002_SUCCESSOR_SHA256},
        "candidate-005 base or controlled authoritative board drift",
    )
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "candidate-005 SHA-256 drift")
    require(
        sha256(GENERATOR) in {GENERATOR_SHA256, ACTIVE_GENERATOR_SHA256}
        and sha256(ROUTING_RULES) == ROUTING_RULES_SHA256
        and sha256(STACKUP_BASIS) in {
            STACKUP_BASIS_SHA256, ECO_002_STACKUP_BASIS_SHA256},
        "candidate-005 source binding drift",
    )
    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    require(
        semantic_board_sha256(base) == BASE_SEMANTIC_SHA256
        and semantic_board_sha256(candidate) == CANDIDATE_SEMANTIC_SHA256,
        "candidate-005 semantic identity drift",
    )
    require(
        len(base.traceItems) == 8
        and len(candidate.traceItems) == 22
        and len(base.zones) == len(candidate.zones) == 0,
        "candidate-005 copper inventory drift",
    )
    require(
        candidate.traceItems[:8] == base.traceItems,
        "candidate-005 modifies accepted predecessor copper",
    )

    net_names = {int(net.number): str(net.name) for net in candidate.nets}
    added = candidate.traceItems[8:]
    expected = [
        (net_name, start, end, float(width))
        for net_name, route in ROUTES.items()
        for start, end, width in route["segments"]
    ]
    width_lengths: dict[str, dict[float, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    route_lengths: dict[str, float] = defaultdict(float)
    for index, (item, identity) in enumerate(zip(added, expected, strict=True), start=1):
        expected_net, expected_start, expected_end, expected_width = identity
        start, end = point(item.start), point(item.end)
        require(
            net_names[int(item.net)] == expected_net
            and str(item.layer) == "F.Cu"
            and math.isclose(float(item.width), expected_width, abs_tol=1e-9)
            and start == expected_start
            and end == expected_end,
            f"candidate-005 segment {index} identity or geometry drift",
        )
        length = math.dist(start, end)
        width_lengths[expected_net][expected_width] += length
        route_lengths[expected_net] += length

    for net_name in ROUTES:
        require(
            math.isclose(route_lengths[net_name], 7.469896050985, abs_tol=1e-9)
            and math.isclose(width_lengths[net_name][0.5], 4.578426732689, abs_tol=1e-9)
            and math.isclose(width_lengths[net_name][1.0], 0.35, abs_tol=1e-9)
            and math.isclose(width_lengths[net_name][1.5], 0.851469318296, abs_tol=1e-9)
            and math.isclose(width_lengths[net_name][2.1], 1.69, abs_tol=1e-9),
            f"{net_name}: route length or progressive-width profile drift",
        )

    clearance = copper_clearance_screen(base, candidate, added, net_names)
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    require(
        review["creation_authorization"]
        == "ACCEPT_PCB_PWR_ROUTING_CANDIDATE_005_CREATION_SUBGATE"
        and review["candidate"]["sha256"] == CANDIDATE_SHA256
        and review["source_binding"]["generator_sha256"] == GENERATOR_SHA256
        and review["pad_entry_disposition"]["hidden_uniform_narrow_substitute"]
        is False
        and review["pad_entry_disposition"]["thermal_and_current_density_qualified"]
        is False
        and review["deferred_boundary"]["application_authorized"] is False
        and review["invariants"]["authoritative_board_modified"] is False
        and review["machine_gate"]["status"]
        in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_COMPARATIVE_DRC",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_COMPARATIVE_DRC",
        }
        and review["routing_complete"] is False
        and review["review_b_complete"] is False
        and review["cam_or_manufacturing_release"] is False,
        "candidate-005 proposal boundary drift",
    )

    report: dict[str, object] = {
        "status": "PASS_STATIC_PCB_PWR_BUCK_SWITCH_NODE_ROUTING_005_CANDIDATE",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "routed_nets": list(ROUTES),
        "connections": [str(route["connection"]) for route in ROUTES.values()],
        "trace_items": 22,
        "added_trace_items": 14,
        "per_net_route_length_mm": round(route_lengths["SW_3V8"], 6),
        "per_net_width_length_mm": {
            str(width): round(length, 6)
            for width, length in sorted(width_lengths["SW_3V8"].items())
        },
        "copper_clearance_screen": clearance,
        "vias": 0,
        "authoritative_board_modified": False,
        "pad_entry_thermal_qualified": False,
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
    print(
        "PCB-PWR buck switch-node routing 005 candidate audit:", report["status"]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
