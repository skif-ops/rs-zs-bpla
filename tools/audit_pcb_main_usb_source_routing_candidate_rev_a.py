#!/usr/bin/env python3
"""Independently audit PCB-MAIN USB MCU source-routing candidate 001."""

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
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-SOURCE-ROUTING-001/"
    "PCB-MAIN_USB_SOURCE_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-SOURCE-ROUTING-001/"
    "PCB-MAIN_USB_SOURCE_CANDIDATE_REV_A.kicad_pcb"
)
ACTIVE = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
REVIEW = ROOT / "hardware/reviews/PCB_MAIN_USB_SOURCE_ROUTING_001_CANDIDATE_REV_A.json"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_USB_SOURCE_ROUTING_001_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_SOURCE_ROUTING_001_APPLICATION_REV_A.json"
CELL_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_MODEM_ROUTING_001_APPLICATION_REV_A.json"
CELL_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-MODEM-ROUTING-001/"
    "PCB-MAIN_USB_CELL_MODEM_CANDIDATE_REV_A.kicad_pcb"
)

BASE_SHA256 = "d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e"
CANDIDATE_SHA256 = "76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5"
CELL_SUCCESSOR_SHA256 = "4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5"
TRACE_WIDTH_MM = 0.1537
PAIR_GAP_MM = 0.2032
GROUND_SEGMENT_TSTAMP = "fb9ade5d-8496-4617-9d20-390d44c347c4"
GROUND_VIA_TSTAMP = "bbd350c1-609d-43b7-9dd0-824ee009466f"
PROPOSAL_COMMIT = "f4ed1a4d0365ce19ff7e68799662ed9886cc49e3"
CI_RUN_ID = 35530524569
PCB_NATIVE_RUN_ID = 35530524588
ARTIFACT_ID = 10611360741
ARTIFACT_DIGEST = (
    "sha256:9cf6e29f613e84f1cea0234987bc14e82467567e042d53c67d97abae761b7cfb"
)

EXPECTED_ROUTES: dict[str, tuple[tuple[float, float], ...]] = {
    "USB_DP_U1": (
        (59.75, 26.0),
        (60.7, 26.0),
        (61.2, 25.85),
        (63.0, 25.85),
        (63.45, 25.4),
        (63.675, 25.25),
    ),
    "USB_DM_U1": (
        (59.75, 26.5),
        (60.7, 26.5),
        (61.2, 26.35),
        (61.6, 26.2069),
        (61.7, 26.2069),
        (61.95, 26.454798070497958),
        (62.2, 26.2069),
        (63.35, 26.2069),
        (63.675, 26.25),
    ),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref_of(footprint: Any) -> str:
    values = [str(item.text) for item in footprint.graphicItems
              if getattr(item, "type", None) == "reference"]
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
        if ((y1 > y) != (y2 > y)):
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
    require(not added, f"USB source candidate introduces KiCad 9 errors: {added}")
    require(candidate_unconnected == base_unconnected - 2,
            "USB source candidate must close exactly two pad connections")
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
    require(sha256(BASE) == BASE_SHA256, "USB source base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "USB source candidate SHA-256 drift")
    active_sha256 = sha256(ACTIVE)
    require(active_sha256 in {BASE_SHA256, CANDIDATE_SHA256, CELL_SUCCESSOR_SHA256},
            "authoritative PCB-MAIN USB source-routing lineage drift")
    if active_sha256 == BASE_SHA256:
        require(ACTIVE.read_bytes() == BASE.read_bytes(),
                "authoritative PCB-MAIN proposal base byte identity drift")
        application_state = "PROPOSAL_NOT_APPLIED"
    else:
        approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
        application = json.loads(APPLICATION.read_text(encoding="utf-8"))
        require(
            approval.get("decision") == "ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE"
            and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
            and application.get("decision") == "ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE"
            and application.get("applied", {}).get("board_sha256") == CANDIDATE_SHA256
            and application.get("applied", {}).get("exact_candidate_byte_identity") is True
            and application.get("review_b_complete") is False
            and application.get("manufacturing_release") is False,
            "accepted USB source-routing application boundary drift",
        )
        if active_sha256 == CANDIDATE_SHA256:
            require(ACTIVE.read_bytes() == CANDIDATE.read_bytes(),
                    "authoritative PCB-MAIN USB source candidate byte drift")
            application_state = "ACCEPTED_EXACT_CANDIDATE_APPLIED"
        else:
            require(ACTIVE.read_bytes() == CELL_CANDIDATE.read_bytes(),
                    "authoritative PCB-MAIN cellular USB successor byte drift")
            cell_application = json.loads(
                CELL_APPLICATION.read_text(encoding="utf-8")
            )
            require(
                cell_application.get("decision") ==
                "ACCEPT_USB_CELL_MODEM_ROUTING_SUBGATE"
                and cell_application.get("predecessor", {}).get(
                    "board_sha256"
                ) == CANDIDATE_SHA256
                and cell_application.get("applied", {}).get("board_sha256") ==
                CELL_SUCCESSOR_SHA256
                and cell_application.get("review_b_complete") is False
                and cell_application.get("manufacturing_release") is False,
                "cellular USB modem successor boundary drift",
            )
            application_state = "ACCEPTED_EXACT_CANDIDATE_WITH_CELL_MODEM_SUCCESSOR"

    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    for field in (
        "general", "layers", "setup", "properties", "graphicItems", "dimensions",
        "groups", "targets", "nets", "footprints", "zones",
    ):
        require(getattr(base, field) == getattr(candidate, field),
                f"USB source candidate changes non-routing field: {field}")

    base_items = {item.tstamp: item for item in base.traceItems}
    candidate_items = {item.tstamp: item for item in candidate.traceItems}
    require(set(base_items) <= set(candidate_items), "candidate removes accepted copper")
    changed = {
        key for key in base_items if base_items[key] != candidate_items[key]
    }
    require(changed == {GROUND_SEGMENT_TSTAMP, GROUND_VIA_TSTAMP},
            f"unexpected modified accepted copper: {sorted(changed)}")
    ground_segment = candidate_items[GROUND_SEGMENT_TSTAMP]
    ground_via = candidate_items[GROUND_VIA_TSTAMP]
    require(type(ground_segment).__name__ == "Segment"
            and point(ground_segment.start) == (62.1, 27.225)
            and point(ground_segment.end) == (62.5, 26.75)
            and ground_segment.layer == "F.Cu" and ground_segment.net == 45,
            "bounded GND_DIGITAL fanout segment drift")
    require(type(ground_via).__name__ == "Via"
            and point(ground_via.position) == (62.5, 26.75)
            and math.isclose(float(ground_via.size), 0.5)
            and math.isclose(float(ground_via.drill), 0.3)
            and list(ground_via.layers) == ["F.Cu", "B.Cu"]
            and ground_via.net == 45,
            "bounded GND_DIGITAL fanout via drift")

    net_names = {item.number: item.name for item in candidate.nets}
    additions = [
        item for key, item in candidate_items.items() if key not in base_items
    ]
    require(len(additions) == 13 and all(type(item).__name__ == "Segment" for item in additions),
            "USB source added-copper inventory drift")
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
        "USB_DP_U1": pad_position(candidate, "U1", "71"),
        "USB_DM_U1": pad_position(candidate, "U1", "70"),
    }
    ends = {
        "USB_DP_U1": pad_position(candidate, "R91", "1"),
        "USB_DM_U1": pad_position(candidate, "R92", "1"),
    }
    for name, points in EXPECTED_ROUTES.items():
        require(points[0] == starts[name] and points[-1] == ends[name],
                f"{name}: route does not terminate on controlled pads")

    lengths = {name: polyline_length(points) for name, points in EXPECTED_ROUTES.items()}
    mismatch = abs(lengths["USB_DP_U1"] - lengths["USB_DM_U1"])
    require(mismatch < 1e-9, "USB source pair is not exactly length matched")
    pair_distance = min(
        segment_distance(dp_start, dp_end, dm_start, dm_end)
        for dp_start, dp_end in zip(EXPECTED_ROUTES["USB_DP_U1"],
                                    EXPECTED_ROUTES["USB_DP_U1"][1:])
        for dm_start, dm_end in zip(EXPECTED_ROUTES["USB_DM_U1"],
                                    EXPECTED_ROUTES["USB_DM_U1"][1:])
    )
    edge_gap = pair_distance - TRACE_WIDTH_MM
    require(edge_gap + 1e-9 >= PAIR_GAP_MM,
            f"USB source pair edge gap below engineering basis: {edge_gap}")

    reference_zones = [
        item for item in candidate.zones
        if item.netName == "GND_DIGITAL" and list(item.layers) == ["In1.Cu"]
    ]
    require(len(reference_zones) == 1 and len(reference_zones[0].polygons) == 1,
            "unique GND_DIGITAL L2 reference polygon missing")
    polygon = [(float(item.X), float(item.Y))
               for item in reference_zones[0].polygons[0].coordinates]
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
                        f"USB source route leaves GND_DIGITAL L2 reference: {sample}")
                reference_samples += 1

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    machine_gate = review.get("machine_gate", {})
    recorded_ci = machine_gate.get("commit_bound_ci")
    recorded_drc = machine_gate.get("commit_bound_kicad9_comparative_drc")
    require(review.get("candidate_board_sha256") == CANDIDATE_SHA256
            and review.get("base_board_sha256") == BASE_SHA256
            and review.get("status") == "KICAD9_COMPARATIVE_PASS_HUMAN_REVIEW_PENDING"
            and machine_gate.get("static_regeneration") == "PASS"
            and machine_gate.get("independent_static_audit") == "PASS"
            and recorded_ci == {
                "status": "PASS",
                "commit": PROPOSAL_COMMIT,
                "run_number": 559,
                "run_id": CI_RUN_ID,
            }
            and recorded_drc == {
                "status": "PASS_NO_NEW_ERRORS_EXACT_TWO_CONNECTION_REDUCTION",
                "commit": PROPOSAL_COMMIT,
                "run_number": 286,
                "run_id": PCB_NATIVE_RUN_ID,
                "artifact_name": "evt-pre-20-kicad-native-gate",
                "artifact_id": ARTIFACT_ID,
                "artifact_digest": ARTIFACT_DIGEST,
                "base_violations": 232,
                "candidate_violations": 232,
                "base_unconnected": 429,
                "candidate_unconnected": 427,
                "new_errors": 0,
                "unconnected_reduction": 2,
            }
            and review.get("authoritative_board_modified") is False
            and review.get("human_acceptance") == "PENDING"
            and review.get("review_b_complete") is False
            and review.get("manufacturing_release") is False,
            "USB source proposal review boundary drift")

    report: dict[str, object] = {
        "schema": "dioneya.pcb-main-usb-source-routing-001-audit.v1",
        "status": "PASS_STATIC_RECORDED_KICAD9_EVIDENCE_ACCEPTED_AND_APPLIED",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "routed_nets": sorted(EXPECTED_ROUTES),
        "added_segments": len(additions),
        "moved_ground_items": sorted(changed),
        "lengths_mm": {name: round(value, 12) for name, value in lengths.items()},
        "pair_length_mismatch_mm": round(mismatch, 12),
        "minimum_pair_edge_gap_mm": round(edge_gap, 12),
        "reference_samples": reference_samples,
        "authoritative_board_modified": False,
        "human_acceptance": "ACCEPTED",
        "active_board_sha256": active_sha256,
        "application_state": application_state,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_candidate is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_candidate is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_candidate)
        report["status"] = "PASS_KICAD9_COMPARATIVE_ACCEPTED_AND_APPLIED"
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
    print(f"PCB-MAIN USB source routing candidate audit: {report['status']}")
    print(
        f"candidate_sha256={CANDIDATE_SHA256} segments={report['added_segments']} "
        f"length_mismatch_mm={report['pair_length_mismatch_mm']} "
        f"minimum_pair_edge_gap_mm={report['minimum_pair_edge_gap_mm']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
