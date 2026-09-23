#!/usr/bin/env python3
"""Audit exact application of PCB-PWR REV_GATE routing candidate 004."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kiutils.board import Board

import audit_pcb_pwr_rev_gate_routing_004_candidate_rev_a as candidate_audit
from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_REV_GATE_ROUTING_004_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_PWR_REV_GATE_ROUTING_004_APPLICATION_REV_A.json"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
BOARD_SHA256 = candidate_audit.CANDIDATE_SHA256
SEMANTIC_SHA256 = candidate_audit.CANDIDATE_SEMANTIC_SHA256
ECO_002_SUCCESSOR_SHA256 = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"
ECO_002_SUCCESSOR_SEMANTIC_SHA256 = "0e52d4cbc80104691e3793a579c7c7a8570e3640fabc2fb02bd7ea2e65643555"
ECO_002_SUCCESSOR = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-POWER-STAGE-ECO-002/PCB-PWR_BUCK_POWER_STAGE_ECO_002_CANDIDATE_REV_A.kicad_pcb"
APPROVAL_SHA256 = "de211f42bf5a0256f89f06b93e5bd0715dca4609fd5c113312e1b01a139671cb"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict[str, object]:
    active_sha256 = sha256(BOARD)
    require(active_sha256 in {BOARD_SHA256, ECO_002_SUCCESSOR_SHA256},
            "authoritative PCB-PWR is not accepted REV_GATE or controlled successor")
    expected_active = {
        BOARD_SHA256: candidate_audit.CANDIDATE,
        ECO_002_SUCCESSOR_SHA256: ECO_002_SUCCESSOR,
    }[active_sha256]
    require(BOARD.read_bytes() == expected_active.read_bytes(),
            "authoritative PCB-PWR REV_GATE successor byte identity drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "REV_GATE approval drift")
    board = Board.from_file(str(BOARD), encoding="utf-8")
    require(semantic_board_sha256(board) in {
                SEMANTIC_SHA256, ECO_002_SUCCESSOR_SEMANTIC_SHA256},
            "applied REV_GATE semantic identity drift")
    require(len(board.traceItems) in {8, 14} and len(board.zones) == 0,
            "applied REV_GATE copper inventory drift")
    proposal = candidate_audit.audit()
    require(proposal["status"] ==
            "PASS_STATIC_PCB_PWR_REV_GATE_ROUTING_004_CANDIDATE",
            "historical REV_GATE proposal audit drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    route = status["native_layout"]["rev_gate_routing_004"]
    gate = application["machine_gate"]
    require(
        approval["decision"] == "ACCEPT_PCB_PWR_REV_GATE_ROUTING_004_SUBGATE"
        and application["decision"] == approval["decision"]
        and application["predecessor_board_sha256"] == candidate_audit.BASE_SHA256
        and application["applied_board_sha256"] == BOARD_SHA256
        and application["trace_items"] == 8
        and application["added_trace_items"] == 4
        and application["added_route_length_mm"] == 12.565
        and application["width_mm"] == 0.5
        and application["vias"] == 0
        and gate["status"] in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
        }
        and application["routing_complete"] is False
        and application["review_b_complete"] is False
        and application["cam_or_manufacturing_release"] is False
        and route["status"] in {
            "APPROVED_APPLIED_EXACT_REV_GATE_ROUTING_APPLICATION_GATE_PENDING",
            "APPROVED_APPLIED_EXACT_REV_GATE_ROUTING_COMMIT_BOUND_KICAD9_GATE_PASS",
        }
        and route["active_board_sha256"] in {
            BOARD_SHA256, ECO_002_SUCCESSOR_SHA256}
        and route["active_board_semantic_sha256"] in {
            SEMANTIC_SHA256, ECO_002_SUCCESSOR_SEMANTIC_SHA256}
        and route["exact_candidate_byte_identity"] is True
        and route["human_acceptance_complete"] is True
        and route["application_machine_gate"] in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE",
        }
        and route["authoritative_board_modified"] is True
        and route["routing_complete"] is False
        and route["review_b_complete"] is False
        and route["manufacturing_release"] is False,
        "REV_GATE application boundary drift",
    )
    if gate["status"] == "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE":
        require(
            gate["application_source_commit_sha"] ==
            "b33de67652bafb07f059d8c5dfa69d056a44a6bd"
            and gate["application_source_tree_sha"] ==
            "57011fb59e9d2e3ed05b9edf4f97cad6dec754bd"
            and gate["board_application_commit_sha"] ==
            "b33de67652bafb07f059d8c5dfa69d056a44a6bd"
            and gate["ci_run_number"] == 641
            and gate["ci_run_id"] == 35692517016
            and gate["pcb_pwr_schematic_run_number"] == 94
            and gate["pcb_pwr_schematic_run_id"] == 35692517010
            and gate["pcb_native_run_number"] == 347
            and gate["pcb_native_run_id"] == 35692517037
            and gate["pcb_native_job_id"] == 106632325949
            and gate["artifact_id"] == 10678553469
            and gate["artifact_digest"] ==
            "sha256:6c5fe93ecb13ffb07706c5af8f5f90364a61ce2bdca42e10b612f5624b78b7ee"
            and gate["required_violations"] == [86, 86]
            and gate["required_unconnected"] == [122, 121]
            and gate["required_drc_fingerprint_delta"] == 0
            and gate["comparative_drc"] ==
            "PASS_86_TO_86_VIOLATIONS_122_TO_121_UNCONNECTED_ZERO_FINGERPRINT_DELTA"
            and gate["evidence_sha256"] == {
                "application_audit.json":
                "130da37dc91b3c225e21dfdaba1711bc4b412e48c05d2044b67c36a173e5ee04",
                "baseline_drc.json":
                "6dce93d4bef62172a187bbded7e39138d137915234edd3a8357fe3904ad208bd",
                "candidate_drc.json":
                "721fbb50f991cd4f3932b74354cac1857573a640aac5f75bd8b64566d987fd35",
                "comparative_audit.json":
                "7efbf21ba0072d957992430d40c91fa3389fe43644f2f8f297583c6b9de771fc",
            }
            and route["status"] ==
            "APPROVED_APPLIED_EXACT_REV_GATE_ROUTING_COMMIT_BOUND_KICAD9_GATE_PASS"
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
            and route["application_artifact_digest"] ==
            gate["artifact_digest"]
            and route["application_comparative_drc"] ==
            gate["comparative_drc"],
            "REV_GATE commit-bound application evidence drift",
        )
    report: dict[str, object] = {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_REV_GATE_ROUTING_004_APPLICATION",
        "board_sha256": BOARD_SHA256,
        "trace_items": 8,
        "vias": 0,
        "machine_gate": gate["status"],
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
    print("PCB-PWR REV_GATE routing 004 application audit:", report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
