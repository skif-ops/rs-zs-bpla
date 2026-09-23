#!/usr/bin/env python3
"""Independent hash, scope and release audit of accepted PCB-PWR 007 application."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kiutils.board import Board

import audit_pcb_pwr_vbat_sys_shunt_bulk_routing_007_candidate_rev_a as candidate_audit
from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256
from generate_pcb_pwr_vbat_sys_shunt_bulk_routing_007_application_rev_a import (
    APPROVAL_SHA, BASE_SHA, BOARD, CANDIDATE, CANDIDATE_SHA,
)
from run_pcb_pwr_shunt_bulk_007_historical_audit import historical_candidate_audit

ROOT = Path(__file__).resolve().parents[1]
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_APPLICATION_REV_A.json"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
SEMANTIC_SHA = "a3f4e65be713c3ed2518ffab78b1adad2fc0cf7814e0069b50b08fbe64d8d613"


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict:
    assert hashlib.sha256(BOARD.read_bytes()).hexdigest() == CANDIDATE_SHA
    assert BOARD.read_bytes() == CANDIDATE.read_bytes()
    assert hashlib.sha256(APPROVAL.read_bytes()).hexdigest() == APPROVAL_SHA
    board = Board.from_file(str(BOARD), encoding="utf-8")
    assert semantic_board_sha256(board) == SEMANTIC_SHA
    assert len(board.traceItems) == 37 and len(board.zones) == 2
    proposal = historical_candidate_audit()
    assert proposal["status"] == "PASS_STATIC_PCB_PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_CANDIDATE"
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    route = json.loads(STATUS.read_text(encoding="utf-8"))["native_layout"]["vbat_sys_shunt_bulk_routing_007"]
    decision = "ACCEPT_PCB_PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_SUBGATE"
    assert approval["decision"] == application["decision"] == decision
    assert application["approval_sha256"] == APPROVAL_SHA
    assert application["predecessor_board_sha256"] == BASE_SHA
    assert application["applied_board_sha256"] == CANDIDATE_SHA
    assert application["applied_board_semantic_sha256"] == SEMANTIC_SHA
    assert application["exact_candidate_byte_identity"] is True
    assert application["trace_items"] == 37 and application["predecessor_trace_items"] == 35
    assert application["added_segments"] == 2
    assert application["added_vias"] == application["added_zones"] == 0
    assert application["routed_nets"] == ["VBAT_SYS"]
    assert application["connections"] == ["RSH1.2-C13.1"]
    assert application["routing_complete"] is False
    assert application["review_b_complete"] is False
    assert application["manufacturing_release"] is False
    assert route["active_board_sha256"] == CANDIDATE_SHA
    assert route["active_board_semantic_sha256"] == SEMANTIC_SHA
    assert route["authoritative_board_modified"] is True
    assert route["exact_candidate_byte_identity"] is True
    assert route["routing_complete"] is False
    assert route["review_b_complete"] is False
    assert route["manufacturing_release"] is False
    gate = application["machine_gate"]
    assert gate["status"] in {
        "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
        "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
    }
    assert gate["required_violations"] == [85, 85]
    assert gate["required_unconnected"] == [108, 107]
    assert gate["required_drc_fingerprint_delta"] == 0
    assert (drc_base is None) == (drc_active is None)
    result = {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_APPLICATION",
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
    print("PCB-PWR shunt-to-bulk 007 application:", report["status"])
