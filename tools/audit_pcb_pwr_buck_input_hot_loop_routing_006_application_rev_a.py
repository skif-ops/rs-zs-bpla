#!/usr/bin/env python3
"""Independent hash, scope and release audit of accepted hot-loop 006 application."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kiutils.board import Board

import audit_pcb_pwr_buck_input_hot_loop_routing_006_candidate_rev_a as proposal_audit
from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256
from pcb_pwr_hot_loop_006_board import hot_loop_application_board, is_exact_application
from run_pcb_pwr_hot_loop_006_historical_candidate_audit import historical_candidate_audit


ROOT = Path(__file__).resolve().parents[1]
BOARD = hot_loop_application_board(ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb")
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_APPLICATION_REV_A.json"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
APPROVAL_SHA = "3738c1235f805acb01fccda413a379eac13b60d5d6f7ebaae12c72969c53ae1f"


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict[str, object]:
    assert is_exact_application(BOARD), "active board differs from approved candidate 006"
    assert hashlib.sha256(APPROVAL.read_bytes()).hexdigest() == APPROVAL_SHA
    board = Board.from_file(str(BOARD), encoding="utf-8")
    assert semantic_board_sha256(board) == proposal_audit.CANDIDATE_SEMANTIC_SHA256
    assert len(board.traceItems) == 35 and len(board.zones) == 2
    proposal = historical_candidate_audit()
    assert proposal["status"] == "PASS_STATIC_PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_CANDIDATE"
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    route = json.loads(STATUS.read_text(encoding="utf-8"))["native_layout"]["buck_input_hot_loop_routing_006"]
    assert approval["decision"] == application["decision"] == "ACCEPT_PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_SUBGATE"
    assert application["approval_sha256"] == APPROVAL_SHA
    assert application["predecessor_board_sha256"] == proposal_audit.BASE_SHA256
    assert application["applied_board_sha256"] == proposal_audit.CANDIDATE_SHA256
    assert application["applied_board_semantic_sha256"] == proposal_audit.CANDIDATE_SEMANTIC_SHA256
    assert application["exact_candidate_byte_identity"] is True
    assert application["trace_items"] == 35 and application["added_segments"] == 13
    assert application["added_vias"] == 8 and application["added_local_in1_cu_planes"] == 2
    assert application["routed_nets"] == ["VBAT_SYS", "GND_PWR"]
    assert application["generic_twelve_via_rule_satisfied"] is False
    assert application["via_current_capacity_qualified"] is False
    assert application["via_under_pad_process_qualified"] is False
    assert application["routing_complete"] is False
    assert application["review_b_complete"] is False
    assert application["manufacturing_release"] is False
    assert route["active_board_sha256"] == proposal_audit.CANDIDATE_SHA256
    assert route["active_board_semantic_sha256"] == proposal_audit.CANDIDATE_SEMANTIC_SHA256
    assert route["authoritative_board_modified"] is True
    assert route["application"] == str(APPLICATION.relative_to(ROOT))
    assert route["application_machine_gate"] == application["machine_gate"]["status"]
    assert route["routing_complete"] is False
    assert route["review_b_complete"] is False
    assert route["manufacturing_release"] is False
    gate = application["machine_gate"]
    assert gate["status"] in {
        "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
        "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
    }
    assert gate["required_violations"] == [85, 85]
    assert gate["required_unconnected"] == [117, 108]
    assert gate["required_drc_fingerprint_delta"] == 0
    if gate["status"] == "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE":
        assert gate["board_application_commit_sha"] == "4875f63f86d0eb2cd00a8a43dcdd97bdd89d7a93"
        assert gate["application_source_commit_sha"] == "0b821758bc073326594154039f5631e4f5a784f5"
        assert gate["application_source_tree_sha"] == "05478176fc80ae9e33d8dcbcc11469705a2588e4"
        assert gate["ci_run_number"] == 715 and gate["ci_run_id"] == 35897520174
        assert gate["pcb_pwr_schematic_run_number"] == 108
        assert gate["pcb_native_run_number"] == 364
        assert gate["pcb_native_run_id"] == 35897520103
        assert gate["pcb_native_job_id"] == 107305041180
        assert gate["artifact_id"] == 10766709699
        assert gate["artifact_digest"] == (
            "sha256:1e5c6e1a0aa4571a86b05694cbb1b448029995e60edef15a31744d896080f7e0"
        )
        assert gate["comparative_drc"] == (
            "PASS_85_TO_85_VIOLATIONS_117_TO_108_UNCONNECTED_ZERO_DRC_FINGERPRINT_DELTA"
        )
        assert route["status"] == (
            "APPROVED_APPLIED_EXACT_BUCK_INPUT_HOT_LOOP_ROUTING_006_COMMIT_BOUND_KICAD9_GATE_PASS"
        )
        for key in ("source_commit_sha", "source_tree_sha", "board_commit_sha",
                    "ci_run_number", "pcb_pwr_schematic_run_number",
                    "pcb_native_run_number", "artifact_id", "artifact_digest",
                    "comparative_drc"):
            assert route["application_" + key] == gate[
                ("board_application_commit_sha" if key == "board_commit_sha"
                 else "application_" + key if key in
                 ("source_commit_sha", "source_tree_sha") else key)
            ]
    assert (drc_base is None) == (drc_active is None)
    result: dict[str, object] = {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_APPLICATION",
        "active_board_sha256": proposal_audit.CANDIDATE_SHA256,
        "machine_gate": gate["status"],
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    if drc_base is not None and drc_active is not None:
        result["comparative_drc"] = proposal_audit.audit_drc(drc_base, drc_active)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-active", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.drc_base, args.drc_active)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR hot-loop 006 application audit:", result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
