#!/usr/bin/env python3
"""Audit the bounded PCB-MAIN BG95 USB modem-segment candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from kiutils.board import Board


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-MODEM-ROUTING-001/"
    "PCB-MAIN_USB_CELL_MODEM_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-MODEM-ROUTING-001/"
    "PCB-MAIN_USB_CELL_MODEM_CANDIDATE_REV_A.kicad_pcb"
)
ACTIVE = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
REVIEW = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_MODEM_ROUTING_001_CANDIDATE_REV_A.json"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_MODEM_ROUTING_001_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_MODEM_ROUTING_001_APPLICATION_REV_A.json"

BASE_SHA256 = "76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5"
CANDIDATE_SHA256 = "4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5"
TRACE_WIDTH_MM = 0.1537
PAIR_GAP_MM = 0.2032
PROPOSAL_COMMIT = "5c73ffe5b9eae3f623f7336c705f939a2a5af2fd"
CI_RUN_ID = 35536788206
PCB_NATIVE_RUN_ID = 35536788193
ARTIFACT_ID = 10613537447
ARTIFACT_DIGEST = (
    "sha256:fa9f1ab6357ad4ad2e356194e05ae999a6a8358641082a860228e0e4cfe04e90"
)

EXPECTED_ROUTES: dict[str, tuple[tuple[float, float], ...]] = {
    "CELL_USB_DP_U8": (
        (14.85, 51.1),
        (14.15, 51.324286504055095),
        (11.025, 51.324286504055095),
        (10.325, 50.75),
    ),
    "CELL_USB_DM_U8": (
        (14.85, 52.2),
        (14.15, 51.68118650405509),
        (11.025, 51.68118650405509),
        (10.325, 52.0),
    ),
}


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


def pad_position(board: Board, reference: str, number: str) -> tuple[float, float]:
    footprint = next(item for item in board.footprints if ref_of(item) == reference)
    pad = next(item for item in footprint.pads if str(item.number) == number)
    angle = math.radians(float(footprint.position.angle or 0.0))
    x, y = float(pad.position.X), float(pad.position.Y)
    return (
        float(footprint.position.X) + x * math.cos(angle) + y * math.sin(angle),
        float(footprint.position.Y) - x * math.sin(angle) + y * math.cos(angle),
    )


def point(value: Any) -> tuple[float, float]:
    return float(value.X), float(value.Y)


def segment_signature(item: Any) -> tuple[object, ...]:
    endpoints = tuple(sorted((point(item.start), point(item.end))))
    return endpoints + (float(item.width), str(item.layer), int(item.net))


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


def segments_intersect(a: tuple[float, float], b: tuple[float, float],
                       c: tuple[float, float], d: tuple[float, float]) -> bool:
    values = (cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b))
    proper = (
        ((values[0] > 0 > values[1]) or (values[1] > 0 > values[0]))
        and ((values[2] > 0 > values[3]) or (values[3] > 0 > values[2]))
    )
    return proper or any((
        abs(values[0]) < 1e-9 and on_segment(a, b, c),
        abs(values[1]) < 1e-9 and on_segment(a, b, d),
        abs(values[2]) < 1e-9 and on_segment(c, d, a),
        abs(values[3]) < 1e-9 and on_segment(c, d, b),
    ))


def segment_distance(a: tuple[float, float], b: tuple[float, float],
                     c: tuple[float, float], d: tuple[float, float]) -> float:
    if segments_intersect(a, b, c, d):
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
    require(not added, f"cellular USB modem candidate introduces KiCad 9 errors: {added}")
    require(candidate_unconnected == base_unconnected - 2,
            "cellular USB modem candidate must close exactly two pad connections")
    return {
        "status": "PASS_NO_NEW_ERRORS_EXACT_TWO_CONNECTION_REDUCTION",
        "base_violations": base_violations,
        "candidate_violations": candidate_violations,
        "base_unconnected": base_unconnected,
        "candidate_unconnected": candidate_unconnected,
        "new_errors": 0,
        "unconnected_reduction": 2,
    }


def audit(drc_base: Path | None = None, drc_candidate: Path | None = None) -> dict[str, object]:
    require(sha256(BASE) == BASE_SHA256, "cellular USB modem base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "cellular USB modem candidate SHA-256 drift")
    active_sha256 = sha256(ACTIVE)
    require(active_sha256 in {BASE_SHA256, CANDIDATE_SHA256},
            "authoritative PCB-MAIN cellular USB modem lineage drift")

    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    for field in (
        "general", "layers", "setup", "properties", "graphicItems", "dimensions",
        "groups", "targets", "nets", "footprints", "zones",
    ):
        require(getattr(base, field) == getattr(candidate, field),
                f"cellular USB modem candidate changes non-routing field: {field}")

    base_items = {item.tstamp: item for item in base.traceItems}
    candidate_items = {item.tstamp: item for item in candidate.traceItems}
    require(set(base_items) <= set(candidate_items), "candidate removes accepted copper")
    require(all(base_items[key] == candidate_items[key] for key in base_items),
            "candidate modifies accepted copper")

    net_names = {item.number: item.name for item in candidate.nets}
    additions = [item for key, item in candidate_items.items() if key not in base_items]
    require(len(additions) == 6 and all(type(item).__name__ == "Segment" for item in additions),
            "cellular USB modem added-copper inventory drift")
    actual: dict[str, Counter[tuple[object, ...]]] = {
        name: Counter() for name in EXPECTED_ROUTES
    }
    for item in additions:
        name = net_names[item.net]
        require(name in actual, f"candidate routes unauthorized net: {name}")
        require(item.layer == "F.Cu" and math.isclose(float(item.width), TRACE_WIDTH_MM),
                f"{name}: geometry drift")
        actual[name][segment_signature(item)] += 1
    for name, points in EXPECTED_ROUTES.items():
        code = next(number for number, net_name in net_names.items() if net_name == name)
        expected = Counter(
            tuple(sorted((start, end))) + (TRACE_WIDTH_MM, "F.Cu", code)
            for start, end in zip(points, points[1:])
        )
        require(actual[name] == expected, f"{name}: exact route topology drift")

    starts = {
        "CELL_USB_DP_U8": pad_position(candidate, "U8", "9"),
        "CELL_USB_DM_U8": pad_position(candidate, "U8", "10"),
    }
    ends = {
        "CELL_USB_DP_U8": pad_position(candidate, "R39", "1"),
        "CELL_USB_DM_U8": pad_position(candidate, "R40", "1"),
    }
    for name, points in EXPECTED_ROUTES.items():
        require(points[0] == starts[name] and points[-1] == ends[name],
                f"{name}: route does not terminate on controlled pads")

    lengths = {name: polyline_length(points) for name, points in EXPECTED_ROUTES.items()}
    mismatch = abs(lengths["CELL_USB_DP_U8"] - lengths["CELL_USB_DM_U8"])
    require(mismatch < 1e-9, "cellular USB modem pair is not exactly length matched")
    pair_distance = min(
        segment_distance(dp_start, dp_end, dm_start, dm_end)
        for dp_start, dp_end in zip(EXPECTED_ROUTES["CELL_USB_DP_U8"],
                                    EXPECTED_ROUTES["CELL_USB_DP_U8"][1:])
        for dm_start, dm_end in zip(EXPECTED_ROUTES["CELL_USB_DM_U8"],
                                    EXPECTED_ROUTES["CELL_USB_DM_U8"][1:])
    )
    edge_gap = pair_distance - TRACE_WIDTH_MM
    require(edge_gap + 1e-9 >= PAIR_GAP_MM,
            f"cellular USB modem pair edge gap below engineering basis: {edge_gap}")

    reference_zones = [
        item for item in candidate.zones
        if item.netName == "GND_MODEM" and list(item.layers) == ["In1.Cu"]
    ]
    require(len(reference_zones) == 1 and len(reference_zones[0].polygons) == 1,
            "unique GND_MODEM L2 reference polygon missing")
    polygon = [
        (float(item.X), float(item.Y))
        for item in reference_zones[0].polygons[0].coordinates
    ]
    reference_samples = 0
    for points in EXPECTED_ROUTES.values():
        for start, end in zip(points, points[1:]):
            for index in range(21):
                ratio = index / 20
                sample = (
                    start[0] + ratio * (end[0] - start[0]),
                    start[1] + ratio * (end[1] - start[1]),
                )
                require(point_in_polygon(sample, polygon),
                        f"cellular USB modem route leaves GND_MODEM L2 reference: {sample}")
                reference_samples += 1

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    machine_gate = review.get("machine_gate", {})
    require(
        review.get("candidate_board_sha256") == CANDIDATE_SHA256
        and review.get("base_board_sha256") == BASE_SHA256
        and review.get("status") == "ACCEPTED_APPLIED_COMMIT_BOUND_GATE_PENDING"
        and machine_gate.get("static_regeneration") == "PASS"
        and machine_gate.get("independent_static_audit") == "PASS"
        and machine_gate.get("commit_bound_ci") == {
            "status": "PASS",
            "commit": PROPOSAL_COMMIT,
            "run_number": 564,
            "run_id": CI_RUN_ID,
        }
        and machine_gate.get("commit_bound_kicad9_comparative_drc") == {
            "status": "PASS_NO_NEW_ERRORS_EXACT_TWO_CONNECTION_REDUCTION",
            "commit": PROPOSAL_COMMIT,
            "run_number": 291,
            "run_id": PCB_NATIVE_RUN_ID,
            "artifact_name": "evt-pre-20-kicad-native-gate",
            "artifact_id": ARTIFACT_ID,
            "artifact_digest": ARTIFACT_DIGEST,
            "base_violations": 232,
            "candidate_violations": 232,
            "base_unconnected": 427,
            "candidate_unconnected": 425,
            "new_errors": 0,
            "unconnected_reduction": 2,
        }
        and review.get("authoritative_board_modified") is True
        and review.get("human_acceptance") == "ACCEPTED"
        and approval.get("decision") == "ACCEPT_USB_CELL_MODEM_ROUTING_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and application.get("decision") == "ACCEPT_USB_CELL_MODEM_ROUTING_SUBGATE"
        and application.get("applied", {}).get("board_sha256") == CANDIDATE_SHA256
        and application.get("applied", {}).get("exact_candidate_byte_identity") is True
        and review.get("review_b_complete") is False
        and review.get("manufacturing_release") is False,
        "cellular USB modem proposal review boundary drift",
    )

    report: dict[str, object] = {
        "schema": "dioneya.pcb-main-usb-cell-modem-routing-001-audit.v1",
        "status": "PASS_STATIC_RECORDED_KICAD9_EVIDENCE_ACCEPTED_AND_APPLIED",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "routed_nets": sorted(EXPECTED_ROUTES),
        "added_segments": len(additions),
        "lengths_mm": {name: round(value, 12) for name, value in lengths.items()},
        "pair_length_mismatch_mm": round(mismatch, 12),
        "minimum_pair_edge_gap_mm": round(edge_gap, 12),
        "reference_samples": reference_samples,
        "authoritative_board_modified": active_sha256 == CANDIDATE_SHA256,
        "human_acceptance": "ACCEPTED",
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_candidate is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_candidate is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_candidate)
        report["status"] = "PASS_KICAD9_COMPARATIVE_PENDING_APPLICATION"
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
    print(f"PCB-MAIN cellular USB modem routing audit: {report['status']}")
    print(
        f"candidate_sha256={CANDIDATE_SHA256} segments={report['added_segments']} "
        f"length_mismatch_mm={report['pair_length_mismatch_mm']} "
        f"minimum_pair_edge_gap_mm={report['minimum_pair_edge_gap_mm']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
