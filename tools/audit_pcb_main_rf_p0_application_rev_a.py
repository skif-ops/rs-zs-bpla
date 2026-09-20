#!/usr/bin/env python3
"""Audit application of the accepted PCB-MAIN RF P0 routing subgate."""

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
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-P0-001/"
    "PCB-MAIN_RF_P0_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-P0-001/"
    "PCB-MAIN_RF_P0_CANDIDATE_REV_A.kicad_pcb"
)
PROPOSAL = ROOT / "hardware/reviews/PCB_MAIN_RF_P0_ROUTING_CANDIDATE_REV_A.json"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_RF_P0_ROUTING_APPROVAL_REV_A.json"
MAPPING = ROOT / "hardware/reviews/PCB_MAIN_RF_P0_ROUTING_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_RF_P0_ROUTING_APPLICATION_REV_A.json"
OCTOSPI_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_OCTOSPI_R8_ECO_002_APPLICATION_REV_A.json"
)
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"

BASE_SHA256 = "04a0c7e37068d00fbe53b48fd19063b015b6b5c04e9aaafb3b01bbced0d7a99f"
CANDIDATE_SHA256 = "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
APPROVAL_SHA256 = "9c015c966c642afc9b2b2b174a7b059ffe3ecb00116eb171c18f94a8a0418b57"
REVIEWED_COMMIT = "ae92a08a1a530e9d10eb6294481842ed68008469"
REVIEWED_TREE = "7eee7230005bddae5b3e389110d2204cac43ad8e"
APPROVAL_COMMIT = "af4f8dc88ac442bcf2d46d1409467e8086c4b4d8"
DECISION = "ACCEPT_RF_P0_ROUTING_SUBGATE"
APPLICATION_STATUS = (
    "APPLIED_ACCEPTED_RF_P0_ROUTING_SUBGATE_REMAINING_ROUTING_AND_REVIEWS_OPEN"
)
RF_WIDTH_MM = 0.1509
EXPECTED = {
    "CELL_RF": (38, 33.067387862532),
    "CELL_RF_ANT": (37, 18.436106588963),
    "GNSS_RF_ANT_BIASED": (17, 10.205266952966),
    "GNSS_RF_DC_BLOCK": (1, 1.000000000000),
    "GNSS_RF_FILTERED": (6, 25.325357133747),
    "LORA_RF_ANT": (26, 14.538138937276),
    "LORA_RF_MODULE": (13, 9.035535027254),
}
ROUTED_NETS = sorted(EXPECTED)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trace_uuid(item: object) -> str:
    return str(item.tstamp)


def audit() -> dict[str, Any]:
    for path in (
        BOARD, BASE, CANDIDATE, PROPOSAL, APPROVAL, MAPPING, APPLICATION,
        OCTOSPI_APPLICATION, STATUS,
    ):
        require(path.is_file() and path.stat().st_size > 0,
                f"missing RF application input: {path}")

    require(sha256(BASE) == BASE_SHA256, "reviewed RF base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "reviewed RF candidate SHA-256 drift")
    require(sha256(BOARD) == CANDIDATE_SHA256 and
            BOARD.read_bytes() == CANDIDATE.read_bytes(),
            "authoritative PCB-MAIN is not the exact accepted RF candidate")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "signed RF approval SHA-256 drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    require(
        approval.get("proposal_id") == "PCB-MAIN-RF-P0-001"
        and approval.get("reviewer") == "Скиф"
        and approval.get("decision_date") == "2026-09-20"
        and approval.get("decision") == DECISION
        and approval.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and approval.get("reviewed_tree_sha") == REVIEWED_TREE
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and approval.get("machine_gate", {}).get("pcb_native_run_id") == 35503671184
        and approval.get("machine_gate", {}).get("pcb_native_conclusion") == "success"
        and approval.get("machine_gate", {}).get("ci_run_id") == 35503671273
        and approval.get("machine_gate", {}).get("ci_conclusion") == "success"
        and approval.get("authorization", {}).get(
            "apply_exact_hash_bound_seven_net_rf_routes"
        ) is True
        and approval.get("authorization", {}).get(
            "alter_reviewed_rf_geometry_without_new_controlled_review"
        ) is False
        and approval.get("authorization", {}).get("routing_complete") is False
        and approval.get("authorization", {}).get("review_b_complete") is False
        and approval.get("authorization", {}).get("cam_or_manufacturing_release") is False,
        "RF approval identity, scope, or release boundary drift",
    )

    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    require(
        mapping.get("proposal_id") == "PCB-MAIN-RF-P0-001"
        and mapping.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and mapping.get("reviewed_tree_sha") == REVIEWED_TREE
        and mapping.get("proposal_blob_sha") ==
        "943e8b215fdcac7cafe4b18979e4ff93f1ce5757"
        and mapping.get("proposal_record_blob_sha") ==
        "b89a750b175938b6023ace846265a4dfb56fc31b"
        and mapping.get("candidate_board_blob_sha") ==
        "86759a47926903d2edbd0bb1d749e15b06cc619d"
        and mapping.get("candidate_board_sha256") == CANDIDATE_SHA256
        and mapping.get("equivalence") == "EXACT_REVIEWED_TREE_AND_BLOBS"
        and mapping.get("review_b_complete") is False
        and mapping.get("manufacturing_release") is False,
        "RF review-commit mapping drift",
    )

    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    applied = application.get("applied", {})
    historical = application.get("historical_baseline", {})
    require(
        application.get("proposal_id") == "PCB-MAIN-RF-P0-001"
        and application.get("approval") == str(APPROVAL.relative_to(ROOT))
        and application.get("reviewed_proposal_commit_sha") == REVIEWED_COMMIT
        and application.get("approval_commit_sha") == APPROVAL_COMMIT
        and application.get("approval_sha256") == APPROVAL_SHA256
        and application.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and application.get("decision") == DECISION
        and application.get("scope") == "EXACT_SEVEN_NET_RF_P0_ROUTING_ONLY"
        and application.get("routed_nets") == ROUTED_NETS
        and application.get("status") == APPLICATION_STATUS
        and application.get("routing_complete") is False
        and application.get("rf_return_path_review_complete") is False
        and application.get("si_review_complete") is False
        and application.get("pi_review_complete") is False
        and application.get("final_job_stackup_accepted") is False
        and application.get("production_impedance_tolerance_accepted") is False
        and application.get("coupon_plan_accepted") is False
        and application.get("review_b_complete") is False
        and application.get("cam_or_manufacturing_release") is False,
        "RF application binding or release boundary drift",
    )
    require(
        historical.get("board_sha256") == BASE_SHA256
        and historical.get("trace_items") == 838
        and historical.get("track_segments") == 553
        and historical.get("vias") == 285
        and historical.get("filled_connectivity") == 444
        and applied.get("board") == "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
        and applied.get("board_sha256") == CANDIDATE_SHA256
        and applied.get("exact_candidate_byte_identity") is True
        and applied.get("trace_items") == 976
        and applied.get("track_segments") == 691
        and applied.get("vias") == 285
        and applied.get("added_segments") == 138
        and applied.get("added_vias") == 0
        and applied.get("rf_width_mm") == RF_WIDTH_MM
        and applied.get("native_filled_connectivity_baseline_to_candidate") == [444, 429]
        and applied.get("kicad9_comparative_drc_violations_baseline_to_candidate") ==
        [226, 226]
        and applied.get("kicad9_comparative_drc_errors_baseline_to_candidate") == [0, 0]
        and applied.get("new_comparative_drc_error_counts") == {},
        "RF applied geometry or comparative-gate evidence drift",
    )

    octospi = json.loads(OCTOSPI_APPLICATION.read_text(encoding="utf-8"))
    require(
        octospi.get("applied", {}).get("board_sha256") == BASE_SHA256
        and octospi.get("applied", {}).get("exact_candidate_byte_identity") is True
        and octospi.get("routing_complete") is False
        and octospi.get("review_b_complete") is False,
        "accepted OctoSPI predecessor evidence drift",
    )

    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    active = Board.from_file(str(BOARD), encoding="utf-8")
    for field in (
        "general", "layers", "setup", "properties", "graphicItems",
        "dimensions", "groups", "targets", "nets", "footprints", "zones",
    ):
        require(getattr(base, field) == getattr(candidate, field),
                f"RF application changes non-routing field: {field}")
        require(getattr(candidate, field) == getattr(active, field),
                f"authoritative RF application field drift: {field}")

    base_items = {trace_uuid(item): item for item in base.traceItems}
    candidate_items = {trace_uuid(item): item for item in candidate.traceItems}
    active_items = {trace_uuid(item): item for item in active.traceItems}
    require(candidate_items == active_items,
            "authoritative RF copper is not the exact accepted candidate")
    require(set(base_items) <= set(candidate_items), "RF application removes accepted copper")
    require(all(base_items[key] == candidate_items[key] for key in base_items),
            "RF application modifies accepted predecessor copper")
    added = [candidate_items[key] for key in set(candidate_items) - set(base_items)]

    names = {int(net.number): net.name for net in candidate.nets}
    segments: Counter[str] = Counter()
    lengths: defaultdict[str, float] = defaultdict(float)
    for item in added:
        name = names[int(item.net)]
        require(name in EXPECTED, f"out-of-scope RF copper applied on {name}")
        require(type(item).__name__ == "Segment", f"{name}: RF signal via was applied")
        require(item.layer == "F.Cu", f"{name}: applied RF route leaves F.Cu")
        require(math.isclose(float(item.width), RF_WIDTH_MM, abs_tol=1e-9),
                f"{name}: applied RF width drift")
        segments[name] += 1
        lengths[name] += math.hypot(
            float(item.end.X) - float(item.start.X),
            float(item.end.Y) - float(item.start.Y),
        )
    require(len(added) == 138 and sum(segments.values()) == 138,
            "RF applied-copper inventory drift")
    for name, (expected_segments, expected_length) in EXPECTED.items():
        require(segments[name] == expected_segments, f"{name}: applied segment-count drift")
        require(math.isclose(lengths[name], expected_length, abs_tol=1e-6),
                f"{name}: applied route-length drift")

    all_segments = [
        item for item in active.traceItems if type(item).__name__ == "Segment"
    ]
    all_vias = [item for item in active.traceItems if type(item).__name__ == "Via"]
    total_length = sum(
        math.hypot(
            float(item.end.X) - float(item.start.X),
            float(item.end.Y) - float(item.start.Y),
        )
        for item in all_segments
    )
    require(
        len(active.traceItems) == 976
        and len(all_segments) == 691
        and len(all_vias) == 285
        and len(active.zones) == 7
        and math.isclose(total_length, 886.332347987082, abs_tol=1e-9),
        "authoritative RF board aggregate inventory drift",
    )

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    review_b = status.get("review_b", {})
    evidence = review_b.get("evidence", {})
    placement = evidence.get("placement_clearance_control", {})
    control = evidence.get("routing_constraint_control", {})
    require(
        review_b.get("complete") is False
        and review_b.get("status") ==
        "OPEN_HIERARCHY_ACCEPTED_PLACEMENT_CLEARANCE_PASS_RF_P0_SUBGATE_"
        "APPLIED_REMAINING_ROUTING_PENDING"
        and evidence.get("rf_p0_routing_application") == str(APPLICATION.relative_to(ROOT))
        and evidence.get("rf_p0_routing_status") ==
        "APPROVED_APPLIED_EXACT_SEVEN_NET_RF_ROUTING_SUBGATE_"
        "REMAINING_ROUTING_AND_REVIEWS_OPEN"
        and placement.get("board_sha256") == CANDIDATE_SHA256
        and control.get("state") ==
        "PASS_CONSTRAINT_COVERAGE_AND_ACCEPTED_RF_P0_SUBGATE"
        and control.get("board_sha256") == CANDIDATE_SHA256
        and control.get("trace_items") == 976
        and control.get("rf_p0_subgate") == "APPLIED_EXACT_ACCEPTED_CANDIDATE"
        and control.get("routing_complete") is False
        and control.get("manufacturing_release") is False
        and status.get("manufacturing_release") is False,
        "PCB-MAIN capture-status RF application boundary drift",
    )

    return {
        "schema_version": "dioneya.pcb-main-rf-p0-routing-application-audit.v1",
        "proposal_id": "PCB-MAIN-RF-P0-001",
        "status": "PASS_EXACT_ACCEPTED_RF_CANDIDATE_APPLIED",
        "board_sha256": CANDIDATE_SHA256,
        "trace_items": len(active.traceItems),
        "track_segments": len(all_segments),
        "vias": len(all_vias),
        "routed_nets": ROUTED_NETS,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print("PCB-MAIN RF P0 routing application audit: PASS")
    print("trace_items=976 routed_nets=7 added_segments=138 added_vias=0")
    print("release_boundary=ROUTING_AND_RF_SI_RETURN_PATH_REVIEW_B_OPEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
