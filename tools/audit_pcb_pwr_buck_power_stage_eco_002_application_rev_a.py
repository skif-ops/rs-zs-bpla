#!/usr/bin/env python3
"""Audit exact application of PCB-PWR buck power-stage ECO-002."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kiutils.board import Board

import audit_pcb_pwr_buck_power_stage_eco_002_candidate_rev_a as candidate_audit
from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_BUCK_POWER_STAGE_ECO_002_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_PWR_BUCK_POWER_STAGE_ECO_002_APPLICATION_REV_A.json"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
BOARD_SHA256 = candidate_audit.CANDIDATE_SHA256
SEMANTIC_SHA256 = candidate_audit.CANDIDATE_SEMANTIC_SHA256
APPROVAL_SHA256 = "c1f5e11c6587c01d9b3f386e2316470029c2b7ba1566a9e3f7c91fd948ee08ae"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict[str, object]:
    require(
        sha256(BOARD) == BOARD_SHA256
        and BOARD.read_bytes() == candidate_audit.CANDIDATE.read_bytes(),
        "authoritative PCB-PWR is not exact accepted ECO-002 candidate",
    )
    require(sha256(APPROVAL) == APPROVAL_SHA256, "ECO-002 approval drift")
    board = Board.from_file(str(BOARD), encoding="utf-8")
    require(semantic_board_sha256(board) == SEMANTIC_SHA256,
            "applied ECO-002 semantic identity drift")
    require(len(board.traceItems) == 14 and len(board.zones) == 0,
            "applied ECO-002 copper inventory drift")

    proposal = candidate_audit.audit()
    require(proposal["status"] == "PASS_ACCEPTED_ECO_002_EXACT_APPLICATION_PENDING",
            "historical ECO-002 proposal audit drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    route = status["native_layout"]["buck_power_stage_eco_002"]
    gate = application["machine_gate"]
    require(
        approval["decision"] == "ACCEPT_PCB_PWR_BUCK_POWER_STAGE_ECO_002_SUBGATE"
        and application["decision"] == approval["decision"]
        and application["approval_commit_sha"] ==
        "100f81230df8310d1d52e606aadb058b9179282a"
        and application["approval_sha256"] == APPROVAL_SHA256
        and application["predecessor_board_sha256"] == candidate_audit.BASE_SHA256
        and application["applied_board_sha256"] == BOARD_SHA256
        and application["applied_board_semantic_sha256"] == SEMANTIC_SHA256
        and application["exact_candidate_byte_identity"] is True
        and application["moved_footprints"] ==
        ["C20", "C21", "C4", "C6", "L1", "L2", "U3", "U4"]
        and application["silkscreen_reference_anchors_changed"] == ["C4", "C6", "R2"]
        and application["routed_nets"] == ["BOOT_3V8", "BOOT_3V3", "SW_3V8", "SW_3V3"]
        and application["trace_items"] == 14
        and application["removed_bootstrap_trace_items"] == 2
        and application["retained_unrelated_predecessor_trace_items"] == 6
        and application["added_trace_items"] == 8
        and application["minimum_external_sw_routed_width_mm"] == 2.1
        and application["vias"] == 0
        and application["zones"] == 0
        and application["pad_geometry_or_nets_changed"] is False
        and application["drc_rules_relaxed"] is False
        and gate["status"] == "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE"
        and gate["required_violations"] == [86, 85]
        and gate["required_unconnected"] == [121, 117]
        and gate["required_new_drc_fingerprint_counts"] == 0
        and gate["comparative_drc"] ==
        "PENDING_EXACT_86_TO_85_VIOLATIONS_121_TO_117_UNCONNECTED_ZERO_NEW_FINGERPRINT_COUNTS"
        and all(gate[key] is None for key in (
            "application_source_commit_sha", "application_source_tree_sha",
            "board_application_commit_sha", "ci_run_number", "ci_run_id",
            "pcb_pwr_schematic_run_number", "pcb_pwr_schematic_run_id",
            "pcb_native_run_number", "pcb_native_run_id", "pcb_native_job_id",
            "artifact_id", "artifact_digest", "evidence_sha256",
        ))
        and application["physical_plus70c_first_article_validation_required"] is True
        and application["routing_complete"] is False
        and application["review_b_complete"] is False
        and application["cam_or_manufacturing_release"] is False
        and route["status"] ==
        "APPROVED_APPLIED_EXACT_BUCK_POWER_STAGE_ECO_002_APPLICATION_GATE_PENDING"
        and route["application"] ==
        "hardware/reviews/PCB_PWR_BUCK_POWER_STAGE_ECO_002_APPLICATION_REV_A.json"
        and route["application_generator"] ==
        "tools/generate_pcb_pwr_buck_power_stage_eco_002_application_rev_a.py"
        and route["application_audit"] ==
        "tools/audit_pcb_pwr_buck_power_stage_eco_002_application_rev_a.py"
        and route["active_board_sha256"] == BOARD_SHA256
        and route["active_board_semantic_sha256"] == SEMANTIC_SHA256
        and route["exact_candidate_byte_identity"] is True
        and route["human_acceptance_complete"] is True
        and route["application_authorized"] is True
        and route["application_machine_gate"] ==
        "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE"
        and route["authoritative_board_modified"] is True
        and route["physical_plus70c_first_article_validation_required"] is True
        and route["routing_complete"] is False
        and route["review_b_complete"] is False
        and route["manufacturing_release"] is False,
        "ECO-002 application boundary drift",
    )

    report: dict[str, object] = {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_POWER_STAGE_ECO_002_APPLICATION",
        "board_sha256": BOARD_SHA256,
        "board_semantic_sha256": SEMANTIC_SHA256,
        "trace_items": 14,
        "vias": 0,
        "zones": 0,
        "machine_gate": gate["status"],
        "physical_plus70c_first_article_validation_required": True,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_active is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_active is not None:
        report["comparative_drc"] = candidate_audit.audit_drc(drc_base, drc_active)
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
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR buck power-stage ECO-002 application audit:", report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
