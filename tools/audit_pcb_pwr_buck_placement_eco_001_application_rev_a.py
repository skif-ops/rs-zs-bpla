#!/usr/bin/env python3
"""Audit the accepted and exactly applied PCB-PWR buck placement ECO-001."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from kiutils.board import Board

import audit_pcb_pwr_buck_placement_eco_001_candidate_rev_a as candidate_audit
import audit_pcb_pwr_placement_clearance_rev_a as clearance_audit
from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
BASE = candidate_audit.BASE
CANDIDATE = candidate_audit.CANDIDATE
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_BUCK_PLACEMENT_ECO_001_APPROVAL_REV_A.json"
MAPPING = ROOT / "hardware/reviews/PCB_PWR_BUCK_PLACEMENT_ECO_001_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_PWR_BUCK_PLACEMENT_ECO_001_APPLICATION_REV_A.json"
GENERATOR = ROOT / "tools/generate_pcb_pwr_buck_placement_eco_001_application_rev_a.py"
PLACEMENT = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"

BASE_SHA256 = "fdd53e669a167df8925c38e289993c38b818c231eddd0be54de378b51538bf48"
CANDIDATE_SHA256 = "9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37"
BOARD_SEMANTIC_SHA256 = "5994f22cdce03bc60779fcf120177bb82f6ecb88b2afdbe9bf4c0c2819af7337"
APPROVAL_SHA256 = "03a3c499b785ffdbe331f5bb442aecde31411bb6b3e65c88e0eaf2e0a62c8c7e"
MAPPING_SHA256 = "26b4376b851d4dd5082bfd02182e243d7d0d9161a7b72c53a7112db9c21c2c85"
GENERATOR_SHA256 = "8ed0ebf6cf3aed26c7f6ef9d7746424defcb467674ce69e353c3b8f2c39f3752"
PLACEMENT_SHA256 = "257fee5898b5d44970115220a485d40b01c4fefad14b5c3b1a4ffb43b7b5b2d6"
REVIEWED_COMMIT = "38d629c2e7f9a9956a93c8b9666b17e69905eeb6"
REVIEWED_TREE = "b935ed765133297099dee6af4799f598df832ab2"
APPROVAL_COMMIT = "82dbcf2a0318d79c73ad4c59e1f58158b453605f"
EXPECTED_POSES = {
    "C4": (54.575, 16.4, 180.0),
    "C6": (54.575, 44.4, 180.0),
    "L1": (60.75, 14.0, 180.0),
    "L2": (60.75, 42.0, 180.0),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drc_inventory(path: Path) -> tuple[Counter[str], int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = Counter(
        item.get("type", "UNKNOWN")
        for item in data.get("violations", [])
        if item.get("severity") == "error"
    )
    return errors, len(data.get("violations", [])), \
        len(data.get("unconnected_items", []))


def audit_drc(base_path: Path, active_path: Path) -> dict[str, object]:
    base_errors, base_violations, base_unconnected = drc_inventory(base_path)
    active_errors, active_violations, active_unconnected = drc_inventory(active_path)
    added = {
        kind: active_errors[kind] - base_errors[kind]
        for kind in active_errors
        if active_errors[kind] > base_errors[kind]
    }
    require(not added,
            f"applied PCB-PWR buck placement adds KiCad 9 errors: {added}")
    require(active_unconnected == base_unconnected,
            "applied placement-only ECO changes unconnected-item count")
    return {
        "status": "PASS_NO_NEW_KICAD9_ERRORS_NO_CONNECTIVITY_REGRESSION",
        "base_violations": base_violations,
        "active_violations": active_violations,
        "base_unconnected": base_unconnected,
        "active_unconnected": active_unconnected,
        "new_error_counts": added,
    }


def audit(
    drc_base: Path | None = None,
    drc_active: Path | None = None,
) -> dict[str, object]:
    for path in (
        BOARD, BASE, CANDIDATE, APPROVAL, MAPPING, APPLICATION,
        GENERATOR, PLACEMENT, STATUS,
    ):
        require(path.is_file() and path.stat().st_size > 0,
                f"missing PCB-PWR buck placement application input: {path}")
    require(sha256(BASE) == BASE_SHA256,
            "PCB-PWR application predecessor SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256 and
            sha256(BOARD) == CANDIDATE_SHA256 and
            BOARD.read_bytes() == CANDIDATE.read_bytes(),
            "authoritative PCB-PWR is not the exact accepted candidate")
    board = Board.from_file(str(BOARD), encoding="utf-8")
    require(semantic_board_sha256(board) == BOARD_SEMANTIC_SHA256,
            "applied PCB-PWR semantic board identity drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256,
            "PCB-PWR buck placement approval SHA-256 drift")
    require(sha256(MAPPING) == MAPPING_SHA256,
            "PCB-PWR buck placement review mapping SHA-256 drift")
    require(sha256(GENERATOR) == GENERATOR_SHA256,
            "PCB-PWR buck placement application generator drift")
    require(sha256(PLACEMENT) == PLACEMENT_SHA256,
            "PCB-PWR placement manifest SHA-256 drift")

    historical = candidate_audit.audit()
    require(historical.get("status") == "PASS_STATIC_ACCEPTED_AND_APPLIED",
            "accepted PCB-PWR candidate historical audit drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    authorization = approval.get("authorization", {})
    require(
        approval.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and approval.get("reviewed_tree_sha") == REVIEWED_TREE
        and approval.get("decision") ==
        "ACCEPT_PCB_PWR_BUCK_PLACEMENT_ECO_001_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and authorization.get(
            "apply_exact_hash_bound_c4_c6_l1_l2_placement_delta"
        ) is True
        and authorization.get("routing_complete") is False
        and authorization.get("cam_or_manufacturing_release") is False,
        "PCB-PWR approval identity or boundary drift",
    )
    require(
        mapping.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and mapping.get("reviewed_tree_sha") == REVIEWED_TREE
        and mapping.get("candidate_board_sha256") == CANDIDATE_SHA256
        and mapping.get("equivalence") == "EXACT_REVIEWED_TREE_AND_BLOBS"
        and mapping.get("cam_or_manufacturing_release") is False,
        "PCB-PWR review commit mapping drift",
    )

    applied = application.get("applied", {})
    gate = application.get("machine_gate", {})
    warning_disposition = application.get("warning_disposition", {})
    require(
        application.get("approval_commit_sha") == APPROVAL_COMMIT
        and application.get("approval_sha256") == APPROVAL_SHA256
        and application.get("decision") ==
        "ACCEPT_PCB_PWR_BUCK_PLACEMENT_ECO_001_SUBGATE"
        and application.get("scope") ==
        "EXACT_C4_C6_L1_L2_PLACEMENT_DELTA_ONLY"
        and application.get("predecessor", {}).get("board_sha256") == BASE_SHA256
        and application.get("application_generator", {}).get("sha256") ==
        GENERATOR_SHA256
        and applied.get("board_sha256") == CANDIDATE_SHA256
        and applied.get("board_semantic_sha256") == BOARD_SEMANTIC_SHA256
        and applied.get("exact_candidate_byte_identity") is True
        and applied.get("changed_references") == ["C4", "C6", "L1", "L2"]
        and applied.get("trace_items") == 0
        and applied.get("copper_zones") == 0
        and applied.get("copper_changed") is False
        and applied.get("placement_manifest_sha256") == PLACEMENT_SHA256
        and gate.get("status") in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE",
        }
        and warning_disposition.get("lib_footprint_mismatch_C4_C6") ==
        "OPEN_WARNING_ONLY_MUST_CLOSE_BEFORE_REVIEW_B_OR_CAM"
        and warning_disposition.get("silk_overlap_L2_R10") ==
        "OPEN_WARNING_ONLY_MUST_CLOSE_BEFORE_REVIEW_B_OR_CAM"
        and application.get("routing_complete") is False
        and application.get("review_b_complete") is False
        and application.get("cam_or_manufacturing_release") is False,
        "PCB-PWR application identity, geometry, warning, or release boundary drift",
    )

    footprints = {candidate_audit.ref_of(item): item for item in board.footprints}
    for reference, expected in EXPECTED_POSES.items():
        actual = candidate_audit.pose_of(footprints[reference])
        require(all(candidate_audit.close(first, second)
                    for first, second in zip(actual, expected)),
                f"{reference}: applied pose drift")
    require(len(board.traceItems) == 0 and len(board.zones) == 0,
            "PCB-PWR buck placement application unexpectedly adds copper")

    with PLACEMENT.open(encoding="utf-8-sig", newline="") as stream:
        rows = {row["RefDes"]: row for row in csv.DictReader(stream)}
    for reference, expected in EXPECTED_POSES.items():
        row = rows[reference]
        actual = (
            float(row["X_mm"]),
            float(row["Y_mm"]),
            float(row["Rotation_deg"]) % 360.0,
        )
        require(all(candidate_audit.close(first, second)
                    for first, second in zip(actual, expected)),
                f"{reference}: placement manifest pose drift")

    clearance = clearance_audit.audit(BOARD, PLACEMENT)
    summary = clearance.get("summary", {})
    require(
        summary.get("state") ==
        "PASS_FITTED_2D_AND_EVT_MOUNTING_CLEARANCE_DIM_003_ACCEPTED"
        and summary.get("minimum_observed_clearance_mm") == 0.22
        and summary.get("clearance_conflicts") == 0
        and summary.get("mounting_to_fitted_body_conflicts") == 0
        and summary.get("mounting_to_existing_pad_conflicts") == 0,
        "applied PCB-PWR buck placement strict-clearance drift",
    )

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    layout = status.get("native_layout", {})
    eco = layout.get("buck_placement_eco_001", {})
    require(
        eco.get("status") in {
            "APPROVED_APPLIED_EXACT_C4_C6_L1_L2_PLACEMENT_PENDING_COMMIT_BOUND_KICAD9_GATE",
            "APPROVED_APPLIED_EXACT_C4_C6_L1_L2_PLACEMENT_COMMIT_BOUND_KICAD9_GATE_PASS",
        }
        and eco.get("active_board_sha256") == CANDIDATE_SHA256
        and eco.get("board_semantic_sha256") == BOARD_SEMANTIC_SHA256
        and eco.get("exact_candidate_byte_identity") is True
        and eco.get("routing_added") is False
        and eco.get("warning_only_items_closed") is False
        and layout.get("routing_present") is False
        and layout.get("copper_zones_present") is False
        and layout.get("cam_export_authorized") is False
        and status.get("review_b", {}).get("complete") is False
        and status.get("manufacturing_release") is False,
        "PCB-PWR capture-status application or release boundary drift",
    )

    report: dict[str, object] = {
        "schema_version":
        "dioneya.pcb-pwr-buck-placement-eco-001-application-audit.v1",
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_PLACEMENT_APPLICATION",
        "predecessor_sha256": BASE_SHA256,
        "active_board_sha256": CANDIDATE_SHA256,
        "board_semantic_sha256": BOARD_SEMANTIC_SHA256,
        "placement_manifest_sha256": PLACEMENT_SHA256,
        "changed_references": ["C4", "C6", "L1", "L2"],
        "copper_changed": False,
        "strict_placement_clearance": "PASS_MINIMUM_0P22_MM",
        "machine_gate": gate.get("status"),
        "warning_only_items_closed": False,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_active is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_active is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_active)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-active", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.drc_base, args.drc_active)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print("PCB-PWR buck placement ECO-001 application audit:", report["status"])
    print(
        f"active_board_sha256={CANDIDATE_SHA256} "
        "moved=['C4', 'C6', 'L1', 'L2'] minimum_clearance_mm=0.22"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
