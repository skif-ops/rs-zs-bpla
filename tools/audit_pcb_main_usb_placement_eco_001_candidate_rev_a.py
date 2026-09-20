#!/usr/bin/env python3
"""Audit PCB-MAIN USB source-termination placement ECO-001 candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from kiutils.board import Board

import audit_pcb_main_placement_clearance_rev_a as placement_clearance


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-PLACEMENT-ECO-001/PCB-MAIN_USB_PLACEMENT_ECO_001_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-PLACEMENT-ECO-001/PCB-MAIN_USB_PLACEMENT_ECO_001_CANDIDATE_REV_A.kicad_pcb"
REVIEW = ROOT / "hardware/reviews/PCB_MAIN_USB_PLACEMENT_ECO_001_CANDIDATE_REV_A.json"
ACTIVE = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_USB_PLACEMENT_ECO_001_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_PLACEMENT_ECO_001_APPLICATION_REV_A.json"
AUTHORITY = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
BASE_SHA256 = "f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9"
CANDIDATE_SHA256 = "d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e"
EXPECTED_POSES = {
    "R91": ((49.0, 18.25, 180.0), (64.0, 25.25, 0.0)),
    "R92": ((55.0, 18.25, 180.0), (64.0, 26.25, 0.0)),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref_of(footprint: Any) -> str:
    refs = [str(item.text) for item in footprint.graphicItems
            if getattr(item, "type", None) == "reference"]
    require(len(refs) == 1 and refs[0], "footprint reference missing or duplicated")
    return refs[0]


def pose_of(footprint: Any) -> tuple[float, float, float]:
    return (float(footprint.position.X), float(footprint.position.Y),
            float(footprint.position.angle or 0.0) % 360.0)


def without_pose(footprint: Any) -> dict[str, Any]:
    return {key: value for key, value in footprint.__dict__.items() if key != "position"}


def rotate(local: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    x, y = local
    return (x * math.cos(angle) + y * math.sin(angle),
            -x * math.sin(angle) + y * math.cos(angle))


def pad_position(board: Board, reference: str, number: str) -> tuple[float, float]:
    footprint = next(item for item in board.footprints if ref_of(item) == reference)
    pad = next(item for item in footprint.pads if str(item.number) == number)
    local = rotate((float(pad.position.X), float(pad.position.Y)),
                   float(footprint.position.angle or 0.0))
    return (float(footprint.position.X) + local[0],
            float(footprint.position.Y) + local[1])


def drc_inventory(path: Path) -> tuple[Counter[str], int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = Counter(item.get("type", "UNKNOWN") for item in data.get("violations", [])
                     if item.get("severity") == "error")
    return errors, len(data.get("violations", [])), len(data.get("unconnected_items", []))


def audit_drc(base_path: Path, candidate_path: Path) -> dict[str, object]:
    base_errors, base_violations, base_unconnected = drc_inventory(base_path)
    candidate_errors, candidate_violations, candidate_unconnected = drc_inventory(candidate_path)
    added = {kind: candidate_errors[kind] - base_errors[kind]
             for kind in candidate_errors if candidate_errors[kind] > base_errors[kind]}
    require(not added, f"USB placement ECO introduces KiCad 9 errors: {added}")
    require(candidate_unconnected <= base_unconnected,
            "USB placement ECO increases unconnected items")
    return {
        "base_violations": base_violations,
        "candidate_violations": candidate_violations,
        "base_unconnected": base_unconnected,
        "candidate_unconnected": candidate_unconnected,
        "new_errors": 0,
    }


def audit(drc_base: Path | None = None, drc_candidate: Path | None = None) -> dict[str, object]:
    require(sha256(BASE) == BASE_SHA256, "USB ECO base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "USB ECO candidate SHA-256 drift")
    require(sha256(ACTIVE) == CANDIDATE_SHA256 and
            ACTIVE.read_bytes() == CANDIDATE.read_bytes(),
            "authoritative PCB-MAIN is not the exact accepted USB ECO candidate")

    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    base_footprints = {ref_of(item): item for item in base.footprints}
    candidate_footprints = {ref_of(item): item for item in candidate.footprints}
    require(base_footprints.keys() == candidate_footprints.keys(), "footprint set drift")
    changed = set()
    for reference in base_footprints:
        first, second = base_footprints[reference], candidate_footprints[reference]
        require(without_pose(first) == without_pose(second),
                f"{reference}: non-placement footprint data changed")
        if pose_of(first) != pose_of(second):
            changed.add(reference)
    require(changed == set(EXPECTED_POSES), f"unexpected moved footprints: {changed}")
    for reference, (old, new) in EXPECTED_POSES.items():
        require(pose_of(base_footprints[reference]) == old, f"{reference}: base pose drift")
        require(pose_of(candidate_footprints[reference]) == new, f"{reference}: candidate pose drift")

    for field in ("nets", "traceItems", "zones", "graphicItems", "groups", "setup"):
        require(getattr(base, field) == getattr(candidate, field),
                f"candidate changes non-placement board field {field}")

    clearance = placement_clearance.audit(CANDIDATE, AUTHORITY)
    summary = clearance["summary"]
    require(summary["state"] == "PASS" and
            summary["confirmed_component_collisions"] == 0 and
            summary["confirmed_mounting_clearance_conflicts"] == 0 and
            summary["confirmed_tool_clearance_conflicts"] == 0,
            "USB placement candidate is not clearance-clean")

    dp_length = math.dist(pad_position(candidate, "U1", "71"),
                          pad_position(candidate, "R91", "1"))
    dm_length = math.dist(pad_position(candidate, "U1", "70"),
                          pad_position(candidate, "R92", "1"))
    require(abs(dp_length - dm_length) < 0.075,
            "USB source-side direct-length mismatch exceeds placement bound")
    require(max(dp_length, dm_length) < 4.0,
            "USB source-side termination distance exceeds placement bound")
    require(pad_position(candidate, "R91", "1")[0] < pad_position(candidate, "R91", "2")[0] and
            pad_position(candidate, "R92", "1")[0] < pad_position(candidate, "R92", "2")[0],
            "U1-side resistor pads do not face U1")

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    require(review["candidate_board_sha256"] == CANDIDATE_SHA256 and
            review["status"] == "KICAD9_COMPARATIVE_DRC_PASS_PENDING_HUMAN_REVIEW" and
            review["authoritative_board_modified"] is False and
            review["manufacturing_release"] is False,
            "USB placement ECO proposal boundary drift")
    gate = review.get("machine_gate", {})
    require(gate.get("source_commit") ==
            "ad3745e719c7c21dade8d0120075d20d629274c8" and
            gate.get("source_tree") ==
            "92c4da4694cda9a545765a6bec10f86d47a49d4f" and
            gate.get("pcb_native_run_id") == 35523547766 and
            gate.get("pcb_native_run_number") == 281 and
            gate.get("ci_run_id") == 35523547763 and
            gate.get("ci_run_number") == 554 and
            gate.get("artifact_id") == 10609108665 and
            gate.get("artifact_digest") ==
            "sha256:2d450a717585fcba580851059ed278a0db8f8a3974d3f911993df31e08d6e24f" and
            gate.get("base_unconnected") == 429 and
            gate.get("candidate_unconnected") == 429 and
            gate.get("new_errors") == 0,
            "USB placement ECO commit-bound machine evidence drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    require(
        approval.get("decision") ==
        "ACCEPT_USB_SOURCE_TERMINATION_PLACEMENT_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and approval.get("authorization", {}).get(
            "apply_exact_hash_bound_r91_r92_placement_delta"
        ) is True
        and approval.get("authorization", {}).get(
            "cam_or_manufacturing_release"
        ) is False,
        "USB placement ECO approval identity or boundary drift",
    )
    require(
        application.get("decision") ==
        "ACCEPT_USB_SOURCE_TERMINATION_PLACEMENT_SUBGATE"
        and application.get("applied", {}).get("board_sha256") ==
        CANDIDATE_SHA256
        and application.get("applied", {}).get("exact_candidate_byte_identity")
        is True
        and application.get("machine_gate", {}).get("status") in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE",
        }
        and application.get("usb_pair_routing_complete") is False
        and application.get("review_b_complete") is False
        and application.get("cam_or_manufacturing_release") is False,
        "USB placement ECO application identity or release boundary drift",
    )

    report: dict[str, object] = {
        "status": "PASS_STATIC_ACCEPTED_AND_APPLIED",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "moved_footprints": sorted(changed),
        "source_side_direct_lengths_mm": {
            "USB_DP_U1": round(dp_length, 9),
            "USB_DM_U1": round(dm_length, 9),
        },
        "source_side_length_mismatch_mm": round(abs(dp_length - dm_length), 9),
        "placement_clearance_state": summary["state"],
        "historical_proposal_authoritative_board_modified": False,
        "active_successor_sha256": CANDIDATE_SHA256,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_candidate is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_candidate is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_candidate)
        report["status"] = "PASS_KICAD9_COMPARATIVE_PROPOSAL_ONLY"
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
    print("PCB-MAIN USB placement ECO-001 candidate audit:", report["status"])
    print(f"candidate_sha256={CANDIDATE_SHA256} moved={report['moved_footprints']} ")
    print(f"source_side_direct_lengths_mm={report['source_side_direct_lengths_mm']} "
          f"mismatch_mm={report['source_side_length_mismatch_mm']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
