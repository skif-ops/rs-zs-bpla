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
SUCCESSOR_SHA = "bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e"


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict:
    active_sha = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    assert active_sha in {CANDIDATE_SHA, SUCCESSOR_SHA}
    application_board = BOARD if active_sha == CANDIDATE_SHA else CANDIDATE
    assert hashlib.sha256(application_board.read_bytes()).hexdigest() == CANDIDATE_SHA
    assert application_board.read_bytes() == CANDIDATE.read_bytes()
    assert hashlib.sha256(APPROVAL.read_bytes()).hexdigest() == APPROVAL_SHA
    board = Board.from_file(str(application_board), encoding="utf-8")
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
    assert gate["required_unconnected"] == [108, 107]
    assert gate["required_drc_fingerprint_delta"] == 0
    if gate["status"] == "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE":
        assert gate["board_application_commit_sha"] == "74f30700f9c31aa6a6b12e87e7570d4648c70170"
        assert gate["application_source_commit_sha"] == "0fb40f38239dea1fe258eedc8f438d6d99db88b4"
        assert gate["application_source_tree_sha"] == "09ec7a36fbfd19ccdd49c5a3a5b8824f56b2fc34"
        assert gate["ci_run_number"] == 725 and gate["ci_run_id"] == 35907619762
        assert gate["pcb_pwr_schematic_run_number"] == 110
        assert gate["pcb_pwr_schematic_run_id"] == 35906891522
        assert gate["pcb_native_run_number"] == 370
        assert gate["pcb_native_run_id"] == 35907619671
        assert gate["pcb_native_job_id"] == 107339139353
        assert gate["artifact_id"] == 10772316282
        assert gate["artifact_digest"] == (
            "sha256:b0772876b2e00848b7120bb450b38d3204eb49815d7ddcf5bd6729d3786dd07b"
        )
        assert gate["comparative_drc"] == (
            "PASS_85_TO_85_VIOLATIONS_108_TO_107_UNCONNECTED_ZERO_DRC_FINGERPRINT_DELTA"
        )
        assert route["status"] == (
            "APPROVED_APPLIED_EXACT_VBAT_SYS_SHUNT_BULK_ROUTING_007_COMMIT_BOUND_KICAD9_GATE_PASS"
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
