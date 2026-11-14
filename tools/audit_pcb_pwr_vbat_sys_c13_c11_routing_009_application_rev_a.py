#!/usr/bin/env python3
"""Independent hash, scope and release audit of accepted PCB-PWR 009 application."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kiutils.board import Board

from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256
from run_pcb_pwr_c13_c11_009_historical_audit import historical_candidate_audit
from generate_pcb_pwr_vbat_sys_c13_c11_routing_009_application_rev_a import (
    APPROVAL, APPROVAL_SHA, BASE_SHA, BOARD, CANDIDATE, CANDIDATE_SHA, ROOT,
)

APPLICATION = ROOT / "hardware/reviews/PCB_PWR_VBAT_SYS_C13_C11_ROUTING_009_APPLICATION_REV_A.json"
SEMANTIC_SHA = "047dca85bb31d926bbd2228c985aa0a1c318b266fa8d68762613a9eec80f9550"


def audit() -> dict:
    assert hashlib.sha256(BOARD.read_bytes()).hexdigest() == CANDIDATE_SHA
    assert BOARD.read_bytes() == CANDIDATE.read_bytes()
    assert hashlib.sha256(APPROVAL.read_bytes()).hexdigest() == APPROVAL_SHA
    board = Board.from_file(str(BOARD), encoding="utf-8")
    assert semantic_board_sha256(board) == SEMANTIC_SHA
    assert len(board.traceItems) == 43 and len(board.zones) == 2
    assert historical_candidate_audit()["status"] == "PASS_STATIC_PCB_PWR_VBAT_SYS_C13_C11_ROUTING_009_CANDIDATE"
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    assert approval["decision"] == application["decision"] == "ACCEPT_PCB_PWR_VBAT_SYS_C13_C11_ROUTING_009_SUBGATE"
    assert application["approval_sha256"] == APPROVAL_SHA
    assert application["predecessor_board_sha256"] == BASE_SHA
    assert application["applied_board_sha256"] == CANDIDATE_SHA
    assert application["applied_board_semantic_sha256"] == SEMANTIC_SHA
    assert application["exact_candidate_byte_identity"] is True
    assert application["trace_items"] == 43 and application["predecessor_trace_items"] == 39
    assert application["added_segments"] == 4
    assert application["added_vias"] == application["added_zones"] == 0
    assert application["routed_nets"] == ["VBAT_SYS"]
    assert application["connections"] == ["C13.1-C11.1"]
    gate = application["machine_gate"]
    assert gate["status"] in {"PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
                              "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE"}
    assert gate["required_violations"] == [85, 85]
    assert gate["required_unconnected"] == [106, 105]
    assert gate["required_drc_fingerprint_delta"] == 0
    assert application["routing_complete"] is application["review_b_complete"] is application["manufacturing_release"] is False
    return {"status": "PASS_EXACT_ACCEPTED_PCB_PWR_VBAT_SYS_C13_C11_ROUTING_009_APPLICATION",
            "active_board_sha256": CANDIDATE_SHA, "machine_gate": gate["status"],
            "routing_complete": False, "review_b_complete": False,
            "manufacturing_release": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR C13-to-C11 009 application:", report["status"])
