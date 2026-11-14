#!/usr/bin/env python3
"""Independent hash, scope and release audit of accepted PCB-PWR 010 application."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kiutils.board import Board

from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256
from run_pcb_pwr_3v8_output_bulk_010_historical_audit import historical_candidate_audit
from generate_pcb_pwr_3v8_output_bulk_routing_010_application_rev_a import (
    APPROVAL, APPROVAL_SHA, BASE_SHA, BOARD, CANDIDATE, CANDIDATE_SHA, ROOT,
)

APPLICATION = ROOT / "hardware/reviews/PCB_PWR_3V8_OUTPUT_BULK_ROUTING_010_APPLICATION_REV_A.json"
SEMANTIC_SHA = "d6810b6ea293bfd931f09e73ff64698d18d0a64b465db7b71c712f64a36b2980"

# After the accepted J2 placement ECO-003 the authoritative board is the exact
# placement-only successor; replay the 010 application on its committed candidate.
from pcb_pwr_hot_loop_006_board import is_autoroute_011, is_eco_005, is_eco_006, is_j2_placement_eco_003  # noqa: E402

# ... and after the accepted autoroute 011 (successor of ECO-003) likewise.
if is_j2_placement_eco_003(BOARD.read_bytes()) or (is_autoroute_011(BOARD.read_bytes()) or (is_eco_005(BOARD.read_bytes()) or is_eco_006(BOARD.read_bytes()))):
    BOARD = CANDIDATE


def audit() -> dict:
    assert hashlib.sha256(BOARD.read_bytes()).hexdigest() == CANDIDATE_SHA
    assert BOARD.read_bytes() == CANDIDATE.read_bytes()
    assert hashlib.sha256(APPROVAL.read_bytes()).hexdigest() == APPROVAL_SHA
    board = Board.from_file(str(BOARD), encoding="utf-8")
    assert semantic_board_sha256(board) == SEMANTIC_SHA
    assert len(board.traceItems) == 53 and len(board.zones) == 2
    assert historical_candidate_audit()["status"] == "PASS_STATIC_PCB_PWR_3V8_OUTPUT_BULK_ROUTING_010_CANDIDATE"
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    assert approval["decision"] == application["decision"] == "ACCEPT_PCB_PWR_3V8_OUTPUT_BULK_ROUTING_010_SUBGATE"
    assert application["approval_commit_sha"] == "fd513d24baf18976ea640bcad875e529d4b73890"
    assert application["approval_sha256"] == APPROVAL_SHA
    assert application["predecessor_board_sha256"] == BASE_SHA
    assert application["applied_board_sha256"] == CANDIDATE_SHA
    assert application["applied_board_semantic_sha256"] == SEMANTIC_SHA
    assert application["exact_candidate_byte_identity"] is True
    assert application["trace_items"] == 53 and application["predecessor_trace_items"] == 43
    assert application["added_segments"] == 10
    assert application["added_vias"] == application["added_zones"] == 0
    assert application["routed_nets"] == ["3V8_MODEM"]
    assert application["connections"] == ["L1.2-C3.1-C14.1-C15.1-C16.1"]
    gate = application["machine_gate"]
    assert gate["status"] in {"PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
                              "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE"}
    assert gate["required_violations"] == [85, 85]
    assert gate["required_unconnected"] == [105, 101]
    assert gate["required_drc_fingerprint_delta"] == 0
    if gate["status"].startswith("PASS_"):
        assert gate["application_source_commit_sha"] == "8a2f48d2eeb4c427aa7708691dd8913800c208dc"
        assert gate["application_source_tree_sha"] == "a39f7050eb09e965e2faf0190eb21d398433fd01"
        assert gate["board_application_commit_sha"] == "8a2f48d2eeb4c427aa7708691dd8913800c208dc"
        assert gate["application_gate_commit_sha"] == "277b4a8d0409a915bc0119e4125676911180edf4"
        assert gate["application_gate_tree_sha"] == "128ad845e66fcc9515224f2a09706c7920b062f4"
        assert gate["ci_run_number"] == 760 and gate["ci_run_id"] == 35994738429
        assert gate["pcb_pwr_schematic_run_number"] == 124 and gate["pcb_pwr_schematic_run_id"] == 35992434448
        assert gate["pcb_native_run_number"] == 393 and gate["pcb_native_run_id"] == 35994738473
        assert gate["pcb_native_job_id"] == 107616887186
        assert gate["artifact_id"] == 10804869811
        assert gate["artifact_digest"] == "sha256:c649fa27acfc9e5399c0196587930c85f87b3ba275e5ef3fd001c310f6943161"
        assert gate["comparative_drc"] == "PASS_85_TO_85_VIOLATIONS_105_TO_101_UNCONNECTED_ZERO_DRC_FINGERPRINT_DELTA"
    assert application["routing_complete"] is application["review_b_complete"] is application["manufacturing_release"] is False
    return {"status": "PASS_EXACT_ACCEPTED_PCB_PWR_3V8_OUTPUT_BULK_ROUTING_010_APPLICATION",
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
    print("PCB-PWR 3V8 output bulk 010 application:", report["status"])
