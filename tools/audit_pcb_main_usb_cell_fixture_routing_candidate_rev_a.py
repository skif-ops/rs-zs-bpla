#!/usr/bin/env python3
"""Audit the bounded PCB-MAIN cellular USB fixture-routing candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
import sys
from pathlib import Path
from typing import Any

from kiutils.board import Board

from generate_pcb_main_usb_cell_fixture_routing_candidate_rev_a import (
    BASE_SHA256,
    B_ROUTES,
    CANDIDATE_SHA256,
    F_ROUTES,
    PAIR_GAP_MM,
    TRACE_WIDTH_MM,
    VIA_DRILL_MM,
    VIA_SIZE_MM,
    VIAS,
)


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")) if str(ROOT / "tools") not in sys.path else None
import pcb_main_lineage_rev_a as _lineage  # noqa: E402  (PCB-MAIN 003: earlier sub-gates read the predecessor)
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-FIXTURE-ROUTING-001/"
    "PCB-MAIN_USB_CELL_FIXTURE_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-FIXTURE-ROUTING-001/"
    "PCB-MAIN_USB_CELL_FIXTURE_CANDIDATE_REV_A.kicad_pcb"
)
ACTIVE = _lineage.historical_board()
REVIEW = (
    ROOT / "hardware/reviews/"
    "PCB_MAIN_USB_CELL_FIXTURE_ROUTING_001_CANDIDATE_REV_A.json"
)

COPPER_CLEARANCE_MM = 0.2
EXPECTED_UNCONNECTED_REDUCTION = 4
PROPOSAL_COMMIT = "11af5c9df9ac8e4fd68ba78dbbd5c067bd3fe23f"
CI_RUN_ID = 35540146804
PCB_NATIVE_RUN_ID = 35540146802
ARTIFACT_ID = 10614043819
ARTIFACT_DIGEST = (
    "sha256:0a2bd9269a99a517716182f84fa280f3807c1f56045731a6a2253f4f434b7680"
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref_of(footprint: Any) -> str:
    values = [
        str(item.text) for item in footprint.graphicItems
        if getattr(item, "type", None) == "reference"
    ]
    require(len(values) == 1 and values[0], "footprint reference missing")
    return values[0]


def net_name(value: Any, names: dict[int, str]) -> str:
    if value is None:
        return ""
    name = getattr(value, "name", "")
    if name:
        return str(name)
    number = getattr(value, "number", value)
    return "" if number is None else str(names.get(int(number), ""))


def pad_position(footprint: Any, pad: Any) -> tuple[float, float]:
    angle = math.radians(float(footprint.position.angle or 0.0))
    x, y = float(pad.position.X), float(pad.position.Y)
    return (
        float(footprint.position.X) + x * math.cos(angle) + y * math.sin(angle),
        float(footprint.position.Y) - x * math.sin(angle) + y * math.cos(angle),
    )


def controlled_pad(board: Board, reference: str, number: str) -> tuple[float, float]:
    footprint = next(item for item in board.footprints if ref_of(item) == reference)
    pad = next(item for item in footprint.pads if str(item.number) == number)
    return pad_position(footprint, pad)


def point(value: Any) -> tuple[float, float]:
    return float(value.X), float(value.Y)


def segment_signature(item: Any) -> tuple[object, ...]:
    endpoints = tuple(sorted((point(item.start), point(item.end))))
    return endpoints + (float(item.width), str(item.layer), int(item.net))


def via_signature(item: Any) -> tuple[object, ...]:
    return (
        point(item.position),
        float(item.size),
        float(item.drill),
        tuple(item.layers),
        int(item.net),
    )


def polyline_length(points: tuple[tuple[float, float], ...]) -> float:
    return sum(math.dist(start, end) for start, end in zip(points, points[1:]))


def point_segment_distance(
    value: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    magnitude = dx * dx + dy * dy
    if magnitude == 0:
        return math.dist(value, start)
    ratio = max(0.0, min(1.0, (
        (value[0] - start[0]) * dx + (value[1] - start[1]) * dy
    ) / magnitude))
    projection = (start[0] + ratio * dx, start[1] + ratio * dy)
    return math.dist(value, projection)


def cross(
    start: tuple[float, float],
    end: tuple[float, float],
    value: tuple[float, float],
) -> float:
    return ((end[0] - start[0]) * (value[1] - start[1])
            - (end[1] - start[1]) * (value[0] - start[0]))


def on_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    value: tuple[float, float],
) -> bool:
    return (
        min(start[0], end[0]) - 1e-9 <= value[0] <= max(start[0], end[0]) + 1e-9
        and min(start[1], end[1]) - 1e-9 <= value[1] <= max(start[1], end[1]) + 1e-9
        and abs(cross(start, end, value)) < 1e-9
    )


def segment_distance(a: tuple[float, float], b: tuple[float, float],
                     c: tuple[float, float], d: tuple[float, float]) -> float:
    values = (cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b))
    proper = (
        ((values[0] > 0 > values[1]) or (values[1] > 0 > values[0]))
        and ((values[2] > 0 > values[3]) or (values[3] > 0 > values[2]))
    )
    touching = any((
        abs(values[0]) < 1e-9 and on_segment(a, b, c),
        abs(values[1]) < 1e-9 and on_segment(a, b, d),
        abs(values[2]) < 1e-9 and on_segment(c, d, a),
        abs(values[3]) < 1e-9 and on_segment(c, d, b),
    ))
    if proper or touching:
        return 0.0
    return min(
        point_segment_distance(a, c, d),
        point_segment_distance(b, c, d),
        point_segment_distance(c, a, b),
        point_segment_distance(d, a, b),
    )


def point_in_polygon(value: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    inside = False
    x, y = value
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > y) != (y2 > y):
            intersection = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection:
                inside = not inside
        previous = current
    return inside


def drc_inventory(path: Path) -> tuple[Counter[str], int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = Counter(
        item.get("type", "UNKNOWN")
        for item in payload.get("violations", [])
        if item.get("severity") == "error"
    )
    return errors, len(payload.get("violations", [])), len(payload.get("unconnected_items", []))


def audit_drc(base_path: Path, candidate_path: Path) -> dict[str, object]:
    base_errors, base_violations, base_unconnected = drc_inventory(base_path)
    candidate_errors, candidate_violations, candidate_unconnected = drc_inventory(candidate_path)
    added = {
        kind: candidate_errors[kind] - base_errors[kind]
        for kind in candidate_errors
        if candidate_errors[kind] > base_errors[kind]
    }
    require(not added, f"cellular USB fixture candidate introduces KiCad 9 errors: {added}")
    require(candidate_unconnected == base_unconnected - EXPECTED_UNCONNECTED_REDUCTION,
            "cellular USB fixture candidate must close exactly four pad connections")
    return {
        "status": "PASS_NO_NEW_ERRORS_EXACT_FOUR_CONNECTION_REDUCTION",
        "base_violations": base_violations,
        "candidate_violations": candidate_violations,
        "base_unconnected": base_unconnected,
        "candidate_unconnected": candidate_unconnected,
        "new_errors": 0,
        "unconnected_reduction": EXPECTED_UNCONNECTED_REDUCTION,
    }


def expected_segment_counter(net_code: int, layer: str,
                             points: tuple[tuple[float, float], ...]) -> Counter[tuple[object, ...]]:
    return Counter(
        tuple(sorted((start, end))) + (TRACE_WIDTH_MM, layer, net_code)
        for start, end in zip(points, points[1:])
    )


def candidate_obstacle_clearance(base: Board) -> float:
    names = {item.number: item.name for item in base.nets}
    obstacles: dict[str, list[tuple[str, str, object, float]]] = {"F.Cu": [], "B.Cu": []}
    for item in base.traceItems:
        item_type = type(item).__name__
        name = names[int(item.net)]
        if item_type == "Segment" and item.layer in obstacles:
            obstacles[item.layer].append((
                "segment", name, (point(item.start), point(item.end)), float(item.width) / 2,
            ))
        elif item_type == "Via":
            entry = ("point", name, point(item.position), float(item.size) / 2)
            obstacles["F.Cu"].append(entry)
            obstacles["B.Cu"].append(entry)
    for footprint in base.footprints:
        for pad in footprint.pads:
            layers = set(pad.layers)
            radius = max(float(pad.size.X), float(pad.size.Y)) / 2
            entry = ("point", net_name(pad.net, names), pad_position(footprint, pad), radius)
            for layer in obstacles:
                if layer in layers or "*.Cu" in layers:
                    obstacles[layer].append(entry)

    minimum = math.inf
    for layer, routes in (("F.Cu", F_ROUTES), ("B.Cu", B_ROUTES)):
        for name, points in routes.items():
            for start, end in zip(points, points[1:]):
                for kind, obstacle_name, geometry, radius in obstacles[layer]:
                    if obstacle_name == name:
                        continue
                    distance = (
                        point_segment_distance(geometry, start, end)
                        if kind == "point"
                        else segment_distance(start, end, *geometry)
                    )
                    minimum = min(minimum, distance - radius - TRACE_WIDTH_MM / 2)
    for name, position in VIAS.items():
        for layer in ("F.Cu", "B.Cu"):
            for kind, obstacle_name, geometry, radius in obstacles[layer]:
                if obstacle_name == name:
                    continue
                distance = (
                    math.dist(position, geometry)
                    if kind == "point"
                    else point_segment_distance(position, *geometry)
                )
                minimum = min(minimum, distance - radius - VIA_SIZE_MM / 2)
    require(minimum + 1e-9 >= COPPER_CLEARANCE_MM,
            f"candidate conservative obstacle clearance below 0.2 mm: {minimum}")
    return minimum


def audit(drc_base: Path | None = None, drc_candidate: Path | None = None) -> dict[str, object]:
    require(sha256(BASE) == BASE_SHA256, "cellular USB fixture base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "cellular USB fixture candidate SHA-256 drift")
    active_sha256 = sha256(ACTIVE)
    require(active_sha256 in {BASE_SHA256, CANDIDATE_SHA256},
            "authoritative PCB-MAIN cellular USB fixture proposal lineage drift")

    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    for field in (
        "general", "layers", "setup", "properties", "graphicItems", "dimensions",
        "groups", "targets", "nets", "footprints", "zones",
    ):
        require(getattr(base, field) == getattr(candidate, field),
                f"cellular USB fixture candidate changes non-routing field: {field}")

    base_items = {str(item.tstamp): item for item in base.traceItems}
    candidate_items = {str(item.tstamp): item for item in candidate.traceItems}
    require(set(base_items) <= set(candidate_items), "candidate removes accepted copper")
    require(all(base_items[key] == candidate_items[key] for key in base_items),
            "candidate modifies accepted copper")
    additions = [item for key, item in candidate_items.items() if key not in base_items]

    names = {item.number: item.name for item in candidate.nets}
    codes = {name: number for number, name in names.items()}
    segments = [item for item in additions if type(item).__name__ == "Segment"]
    vias = [item for item in additions if type(item).__name__ == "Via"]
    require(len(segments) == 27 and len(vias) == 2 and len(additions) == 29,
            "cellular USB fixture added-copper inventory drift")

    actual_segments: Counter[tuple[object, ...]] = Counter(segment_signature(item) for item in segments)
    expected_segments: Counter[tuple[object, ...]] = Counter()
    for name, points in F_ROUTES.items():
        expected_segments.update(expected_segment_counter(codes[name], "F.Cu", points))
    for name, points in B_ROUTES.items():
        expected_segments.update(expected_segment_counter(codes[name], "B.Cu", points))
    require(actual_segments == expected_segments, "cellular USB fixture exact segment topology drift")
    expected_vias = Counter(
        (position, VIA_SIZE_MM, VIA_DRILL_MM, ("F.Cu", "B.Cu"), codes[name])
        for name, position in VIAS.items()
    )
    require(Counter(via_signature(item) for item in vias) == expected_vias,
            "cellular USB fixture exact via topology drift")

    endpoints = {
        "CELL_USB_DP_TP": (
            controlled_pad(candidate, "R39", "2"),
            controlled_pad(candidate, "U26", "1"),
            controlled_pad(candidate, "TP_CELL_USB", "2"),
        ),
        "CELL_USB_DM_TP": (
            controlled_pad(candidate, "R40", "2"),
            controlled_pad(candidate, "U26", "2"),
            controlled_pad(candidate, "TP_CELL_USB", "3"),
        ),
    }
    for name, (series_pad, esd_pad, fixture_pad) in endpoints.items():
        require(F_ROUTES[name][0] == series_pad, f"{name}: series endpoint drift")
        require(F_ROUTES[name][-1] == esd_pad, f"{name}: ESD endpoint drift")
        require(F_ROUTES[name][-2] == VIAS[name] == B_ROUTES[name][0],
                f"{name}: layer transition discontinuity")
        require(B_ROUTES[name][-1] == fixture_pad, f"{name}: fixture endpoint drift")

    primary_lengths = {
        name: polyline_length(F_ROUTES[name][:-1]) + polyline_length(B_ROUTES[name])
        for name in F_ROUTES
    }
    stub_lengths = {
        name: math.dist(F_ROUTES[name][-2], F_ROUTES[name][-1])
        for name in F_ROUTES
    }
    primary_mismatch = abs(primary_lengths["CELL_USB_DP_TP"]
                           - primary_lengths["CELL_USB_DM_TP"])
    stub_mismatch = abs(stub_lengths["CELL_USB_DP_TP"]
                        - stub_lengths["CELL_USB_DM_TP"])
    require(primary_mismatch < 1e-9, "cellular USB fixture primary pair is not length matched")
    require(stub_mismatch < 1e-9, "cellular USB fixture ESD shunts are not length matched")

    layer_pair_gaps: list[float] = []
    for routes in (F_ROUTES, B_ROUTES):
        dp = routes["CELL_USB_DP_TP"]
        dm = routes["CELL_USB_DM_TP"]
        layer_pair_gaps.extend(
            segment_distance(dp_start, dp_end, dm_start, dm_end) - TRACE_WIDTH_MM
            for dp_start, dp_end in zip(dp, dp[1:])
            for dm_start, dm_end in zip(dm, dm[1:])
        )
    layer_pair_gaps.append(
        math.dist(VIAS["CELL_USB_DP_TP"], VIAS["CELL_USB_DM_TP"]) - VIA_SIZE_MM
    )
    minimum_pair_gap = min(layer_pair_gaps)
    require(minimum_pair_gap + 1e-9 >= PAIR_GAP_MM,
            f"cellular USB fixture pair edge gap below engineering basis: {minimum_pair_gap}")

    reference_zones = [
        item for item in candidate.zones
        if item.netName == "GND_MODEM" and list(item.layers) == ["In4.Cu"]
    ]
    require(len(reference_zones) == 1 and len(reference_zones[0].polygons) == 1,
            "unique GND_MODEM L5 reference polygon missing")
    polygon = [
        (float(item.X), float(item.Y))
        for item in reference_zones[0].polygons[0].coordinates
    ]
    reference_samples = 0
    for points in B_ROUTES.values():
        for start, end in zip(points, points[1:]):
            for index in range(21):
                ratio = index / 20
                sample = (
                    start[0] + ratio * (end[0] - start[0]),
                    start[1] + ratio * (end[1] - start[1]),
                )
                require(point_in_polygon(sample, polygon),
                        f"cellular USB fixture route leaves GND_MODEM L5 reference: {sample}")
                reference_samples += 1

    base_names = {item.number: item.name for item in base.nets}
    return_vias = [
        point(item.position) for item in base.traceItems
        if type(item).__name__ == "Via" and base_names[int(item.net)] == "GND_MODEM"
    ]
    nearest_returns = {
        name: min(math.dist(position, return_via) for return_via in return_vias)
        for name, position in VIAS.items()
    }
    require(all(value <= 1.1 for value in nearest_returns.values()),
            "cellular USB fixture layer transition lacks adjacent GND_MODEM return via")
    obstacle_clearance = candidate_obstacle_clearance(base)

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    machine_gate = review.get("machine_gate", {})
    require(
        review.get("candidate_board_sha256") == CANDIDATE_SHA256
        and review.get("base_board_sha256") == BASE_SHA256
        and review.get("status") in {
            "STATIC_PASS_KICAD9_GATE_PENDING",
            "ACCEPTED_APPLIED_COMMIT_BOUND_GATE_PENDING",
            "ACCEPTED_APPLIED_COMMIT_BOUND_GATE_PASS",
        }
        and review.get("authoritative_board_modified") is (active_sha256 == CANDIDATE_SHA256)
        and review.get("human_acceptance") in {"PENDING", "ACCEPTED"}
        and review.get("review_b_complete") is False
        and review.get("manufacturing_release") is False,
        "cellular USB fixture proposal review boundary drift",
    )
    if review.get("human_acceptance") == "ACCEPTED":
        require(
            machine_gate.get("static_regeneration") == "PASS"
            and machine_gate.get("independent_static_audit") == "PASS"
            and machine_gate.get("commit_bound_ci") == {
                "status": "PASS",
                "commit": PROPOSAL_COMMIT,
                "run_number": 568,
                "run_id": CI_RUN_ID,
            }
            and machine_gate.get("commit_bound_kicad9_comparative_drc") == {
                "status": "PASS_NO_NEW_ERRORS_EXACT_FOUR_CONNECTION_REDUCTION",
                "commit": PROPOSAL_COMMIT,
                "run_number": 295,
                "run_id": PCB_NATIVE_RUN_ID,
                "artifact_name": "evt-pre-20-kicad-native-gate",
                "artifact_id": ARTIFACT_ID,
                "artifact_digest": ARTIFACT_DIGEST,
                "base_violations": 232,
                "candidate_violations": 232,
                "base_unconnected": 425,
                "candidate_unconnected": 421,
                "new_errors": 0,
                "unconnected_reduction": 4,
            },
            "cellular USB fixture proposal commit-bound evidence drift",
        )

    report: dict[str, object] = {
        "schema": "dioneya.pcb-main-usb-cell-fixture-routing-001-audit.v1",
        "status": (
            "PASS_STATIC_RECORDED_KICAD9_EVIDENCE_ACCEPTED_AND_APPLIED"
            if review.get("human_acceptance") == "ACCEPTED"
            else "PASS_STATIC_KICAD9_GATE_PENDING"
        ),
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "routed_nets": sorted(F_ROUTES),
        "added_segments": len(segments),
        "added_signal_vias": len(vias),
        "primary_lengths_mm": {
            name: round(value, 12) for name, value in primary_lengths.items()
        },
        "primary_pair_length_mismatch_mm": round(primary_mismatch, 12),
        "esd_stub_lengths_mm": {
            name: round(value, 12) for name, value in stub_lengths.items()
        },
        "esd_stub_length_mismatch_mm": round(stub_mismatch, 12),
        "minimum_pair_edge_gap_mm": round(minimum_pair_gap, 12),
        "minimum_conservative_obstacle_edge_gap_mm": round(obstacle_clearance, 12),
        "reference_samples": reference_samples,
        "nearest_return_via_mm": {
            name: round(value, 12) for name, value in nearest_returns.items()
        },
        "authoritative_board_modified": active_sha256 == CANDIDATE_SHA256,
        "human_acceptance": review.get("human_acceptance"),
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_candidate is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_candidate is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_candidate)
        report["status"] = (
            "PASS_KICAD9_COMPARATIVE_ACCEPTED_AND_APPLIED"
            if review.get("human_acceptance") == "ACCEPTED"
            else "PASS_KICAD9_COMPARATIVE_PENDING_APPLICATION"
        )
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
    print(f"PCB-MAIN cellular USB fixture routing audit: {report['status']}")
    print(
        f"candidate_sha256={CANDIDATE_SHA256} segments={report['added_segments']} "
        f"vias={report['added_signal_vias']} "
        f"length_mismatch_mm={report['primary_pair_length_mismatch_mm']} "
        f"minimum_pair_edge_gap_mm={report['minimum_pair_edge_gap_mm']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
