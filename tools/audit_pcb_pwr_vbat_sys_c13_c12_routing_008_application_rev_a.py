#!/usr/bin/env python3
"""Independent hash, scope and release audit of accepted PCB-PWR 008 application."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kiutils.board import Board

import audit_pcb_pwr_vbat_sys_c13_c12_routing_008_candidate_rev_a as candidate_audit
from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256
from generate_pcb_pwr_vbat_sys_c13_c12_routing_008_application_rev_a import (
    APPROVAL_SHA, BASE_SHA, BOARD, CANDIDATE, CANDIDATE_SHA,
)
from run_pcb_pwr_c13_c12_008_historical_audit import historical_candidate_audit

ROOT = Path(__file__).resolve().parents[1]
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_VBAT_SYS_C13_C12_ROUTING_008_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_PWR_VBAT_SYS_C13_C12_ROUTING_008_APPLICATION_REV_A.json"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
SEMANTIC_SHA = "1278dcdc1c752e34132af5ac6472525c5012774ff864aa2210bee40c8c2284e3"
SUCCESSOR_SHA = "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"
OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"
J2_PLACEMENT_ECO_003_SHA = "b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6"
AUTOROUTE_011_SHA = "cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578"
ECO_005_SHA = "81f44a7068de6c8d7b3ae1a6951bc9d7a4bc6c2646cdbc4eccea4d9c79e35610"  # exact committed ECO-005 board (Review B R1 remediation)
ECO_006_SHA = "b8c1da6ca80b9e5d2795c4fee5b6926e4ab6169086795295e8e517a18def6ca7"  # exact committed ECO-006 board (Review B R2 DFM: TP mask 0.1 mm, legend 1.0/0.15 mm; copper unchanged)


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict:
    board_sha = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    assert board_sha in {CANDIDATE_SHA, SUCCESSOR_SHA, OUTPUT_BULK_010_SHA, J2_PLACEMENT_ECO_003_SHA, AUTOROUTE_011_SHA, ECO_005_SHA, ECO_006_SHA}
    assert hashlib.sha256(APPROVAL.read_bytes()).hexdigest() == APPROVAL_SHA
    board = Board.from_file(str(CANDIDATE if board_sha in {SUCCESSOR_SHA, OUTPUT_BULK_010_SHA, J2_PLACEMENT_ECO_003_SHA, AUTOROUTE_011_SHA, ECO_005_SHA, ECO_006_SHA} else BOARD), encoding="utf-8")
    assert semantic_board_sha256(board) == SEMANTIC_SHA
    assert len(board.traceItems) == 39 and len(board.zones) == 2
    proposal = historical_candidate_audit()
    assert proposal["status"] == "PASS_STATIC_PCB_PWR_VBAT_SYS_C13_C12_ROUTING_008_CANDIDATE"
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    route = json.loads(STATUS.read_text(encoding="utf-8"))["native_layout"]["vbat_sys_c13_c12_routing_008"]
    decision = "ACCEPT_PCB_PWR_VBAT_SYS_C13_C12_ROUTING_008_SUBGATE"
    assert approval["decision"] == application["decision"] == decision
    assert application["approval_sha256"] == APPROVAL_SHA
    assert application["predecessor_board_sha256"] == BASE_SHA
    assert application["applied_board_sha256"] == CANDIDATE_SHA
    assert application["applied_board_semantic_sha256"] == SEMANTIC_SHA
    assert application["exact_candidate_byte_identity"] is True
    assert application["trace_items"] == 39 and application["predecessor_trace_items"] == 37
    assert application["added_segments"] == 2
    assert application["added_vias"] == application["added_zones"] == 0
    assert application["routed_nets"] == ["VBAT_SYS"]
    assert application["connections"] == ["C13.1-C12.1"]
    assert application["routing_complete"] is False
    assert application["review_b_complete"] is False
    assert application["manufacturing_release"] is False
    assert route["active_board_sha256"] == CANDIDATE_SHA
    assert route["active_board_semantic_sha256"] == SEMANTIC_SHA
    assert route["authoritative_board_modified"] is True
    assert route["exact_candidate_byte_identity"] is True
    assert route["application"] == str(APPLICATION.relative_to(ROOT))
    assert route["routing_complete"] is False
    assert route["review_b_complete"] is False
    assert route["manufacturing_release"] is False
    gate = application["machine_gate"]
    assert route["application_machine_gate"] == gate["status"]
    assert gate["status"] in {
        "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
        "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
    }
    assert gate["required_violations"] == [85, 85]
    assert gate["required_unconnected"] == [107, 106]
    assert gate["required_drc_fingerprint_delta"] == 0
    if gate["status"] == "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE":
        assert gate["application_source_commit_sha"] == "dcf67e5057d13acc21d9dcf761433a6533c55a2a"
        assert gate["application_source_tree_sha"] == "9367008d84ded02456f15a4b96fe456f0b721cf1"
        assert gate["board_application_commit_sha"] == "055e1a04f6143930b0187be01354e959210396cc"
        assert gate["ci_run_number"] == 736 and gate["ci_run_id"] == 35960317596
        assert gate["pcb_pwr_schematic_run_number"] == 115
        assert gate["pcb_pwr_schematic_run_id"] == 35959612219
        assert gate["pcb_native_run_number"] == 377 and gate["pcb_native_run_id"] == 35960317609
        assert gate["pcb_native_job_id"] == 107507288098
        assert gate["artifact_id"] == 10791463571
        assert gate["artifact_digest"] == "sha256:b121be95290b9912d179756292fa522ce7047388cd0aa6b8d0a743eae2e18333"
        assert gate["comparative_drc"] == "PASS_85_TO_85_VIOLATIONS_107_TO_106_UNCONNECTED_ZERO_DRC_FINGERPRINT_DELTA"
    assert (drc_base is None) == (drc_active is None)
    result = {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_VBAT_SYS_C13_C12_ROUTING_008_APPLICATION",
        "active_board_sha256": CANDIDATE_SHA,
        "machine_gate": gate["status"],
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    if drc_base is not None:
        result["comparative_drc"] = candidate_audit.comparative_drc(drc_base, drc_active)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-active", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.drc_base, args.drc_active)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR C13-to-C12 008 application:", report["status"])
