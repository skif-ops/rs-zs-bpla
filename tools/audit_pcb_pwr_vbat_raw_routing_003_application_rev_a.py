#!/usr/bin/env python3
"""Audit exact application of PCB-PWR VBAT_RAW routing candidate 003."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kiutils.board import Board

import audit_pcb_pwr_vbat_raw_routing_003_candidate_rev_a as candidate_audit
from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_VBAT_RAW_ROUTING_003_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_PWR_VBAT_RAW_ROUTING_003_APPLICATION_REV_A.json"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
BOARD_SHA256 = candidate_audit.CANDIDATE_SHA256
SEMANTIC_SHA256 = candidate_audit.CANDIDATE_SEMANTIC_SHA256
REV_GATE_SUCCESSOR_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
REV_GATE_SUCCESSOR_SEMANTIC_SHA256 = "f7a659d0740e78d40eddae7016724bd8e616baf9fb425f06ace70ec9acca4d3d"
REV_GATE_SUCCESSOR = ROOT / "hardware/kicad/candidates/PCB-PWR-REV-GATE-ROUTING-004/PCB-PWR_REV_GATE_ROUTING_004_CANDIDATE_REV_A.kicad_pcb"
APPROVAL_SHA256 = "c7064ff198b4668aa486ce76a0552c7c76f67193d3a63d25c99019d5d03d5bc5"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict[str, object]:
    active_sha256 = sha256(BOARD)
    require(active_sha256 in {BOARD_SHA256, REV_GATE_SUCCESSOR_SHA256},
            "authoritative PCB-PWR is not accepted VBAT_RAW or controlled successor")
    expected_active = {
        BOARD_SHA256: candidate_audit.CANDIDATE,
        REV_GATE_SUCCESSOR_SHA256: REV_GATE_SUCCESSOR,
    }[active_sha256]
    require(BOARD.read_bytes() == expected_active.read_bytes(),
            "authoritative PCB-PWR VBAT_RAW successor byte identity drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "VBAT_RAW approval drift")
    board = Board.from_file(str(BOARD), encoding="utf-8")
    require(semantic_board_sha256(board) in {
                SEMANTIC_SHA256, REV_GATE_SUCCESSOR_SEMANTIC_SHA256},
            "applied VBAT_RAW semantic identity drift")
    require(len(board.traceItems) in {4, 8} and len(board.zones) == 0,
            "applied VBAT_RAW copper inventory drift")
    proposal = candidate_audit.audit()
    require(proposal["status"] ==
            "PASS_STATIC_PCB_PWR_VBAT_RAW_ROUTING_003_CANDIDATE",
            "historical VBAT_RAW proposal audit drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    route = status["native_layout"]["vbat_raw_routing_003"]
    gate = application["machine_gate"]
    require(
        approval["decision"] == "ACCEPT_PCB_PWR_VBAT_RAW_ROUTING_003_SUBGATE"
        and application["decision"] == approval["decision"]
        and application["predecessor_board_sha256"] == candidate_audit.BASE_SHA256
        and application["applied_board_sha256"] == BOARD_SHA256
        and application["trace_items"] == 4
        and application["width_mm"] == 4.0
        and application["vias"] == 0
        and application["machine_gate"]["status"] in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
        }
        and application["routing_complete"] is False
        and application["review_b_complete"] is False
        and application["cam_or_manufacturing_release"] is False
        and route["active_board_sha256"] in {
            BOARD_SHA256, REV_GATE_SUCCESSOR_SHA256}
        and route["authoritative_board_modified"] is True
        and route["routing_complete"] is False
        and route["review_b_complete"] is False
        and route["manufacturing_release"] is False,
        "VBAT_RAW application boundary drift",
    )
    if gate["status"] == "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE":
        require(
            gate["application_source_commit_sha"] ==
            "514696e87540cac1c92012fc06711d74e5d2ed59"
            and gate["application_source_tree_sha"] ==
            "3c64a57fb8c95e89024021dd6d030433088d4785"
            and gate["board_application_commit_sha"] ==
            "514696e87540cac1c92012fc06711d74e5d2ed59"
            and gate["ci_run_number"] == 621
            and gate["ci_run_id"] == 35640984924
            and gate["pcb_pwr_schematic_run_number"] == 89
            and gate["pcb_pwr_schematic_run_id"] == 35640984910
            and gate["pcb_native_run_number"] == 342
            and gate["pcb_native_run_id"] == 35640984921
            and gate["artifact_id"] == 10657859914
            and gate["artifact_digest"] ==
            "sha256:9992df866d70396d758c838897ae315aff312ff6c6263bf37da4560f8c3cfbc1"
            and gate["required_violations"] == [86, 86]
            and gate["required_unconnected"] == [123, 122]
            and gate["required_drc_fingerprint_delta"] == 0
            and gate["comparative_drc"] ==
            "PASS_86_TO_86_VIOLATIONS_123_TO_122_UNCONNECTED_ZERO_FINGERPRINT_DELTA"
            and route["status"] ==
            "APPROVED_APPLIED_EXACT_VBAT_RAW_ROUTING_COMMIT_BOUND_KICAD9_GATE_PASS"
            and route["application_machine_gate"] ==
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE"
            and route["application_source_commit_sha"] ==
            gate["application_source_commit_sha"]
            and route["application_source_tree_sha"] ==
            gate["application_source_tree_sha"]
            and route["application_board_commit_sha"] ==
            gate["board_application_commit_sha"]
            and route["application_ci_run_number"] == gate["ci_run_number"]
            and route["application_pcb_pwr_schematic_run_number"] ==
            gate["pcb_pwr_schematic_run_number"]
            and route["application_pcb_native_run_number"] ==
            gate["pcb_native_run_number"]
            and route["application_artifact_id"] == gate["artifact_id"]
            and route["application_artifact_digest"] == gate["artifact_digest"]
            and route["application_comparative_drc"] == gate["comparative_drc"],
            "VBAT_RAW commit-bound application evidence drift",
        )
    report: dict[str, object] = {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_VBAT_RAW_ROUTING_003_APPLICATION",
        "board_sha256": active_sha256,
        "trace_items": 4,
        "vias": 0,
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
    print("PCB-PWR VBAT_RAW routing 003 application audit:", report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
