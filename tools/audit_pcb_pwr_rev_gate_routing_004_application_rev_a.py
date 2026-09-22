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
APPROVAL_SHA256 = "de211f42bf5a0256f89f06b93e5bd0715dca4609fd5c113312e1b01a139671cb"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict[str, object]:
    require(sha256(BOARD) == BOARD_SHA256 and
            BOARD.read_bytes() == candidate_audit.CANDIDATE.read_bytes(),
            "authoritative PCB-PWR is not exact accepted REV_GATE candidate")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "REV_GATE approval drift")
    board = Board.from_file(str(BOARD), encoding="utf-8")
    require(semantic_board_sha256(board) == SEMANTIC_SHA256,
            "applied REV_GATE semantic identity drift")
    require(len(board.traceItems) == 8 and len(board.zones) == 0,
            "applied REV_GATE copper inventory drift")
    proposal = candidate_audit.audit()
    require(proposal["status"] ==
            "PASS_STATIC_PCB_PWR_REV_GATE_ROUTING_004_CANDIDATE",
            "historical REV_GATE proposal audit drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    route = status["native_layout"]["rev_gate_routing_004"]
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
        and application["machine_gate"]["status"] in {
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
        and route["active_board_sha256"] == BOARD_SHA256
        and route["active_board_semantic_sha256"] == SEMANTIC_SHA256
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
    report: dict[str, object] = {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_REV_GATE_ROUTING_004_APPLICATION",
        "board_sha256": BOARD_SHA256,
        "trace_items": 8,
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
    print("PCB-PWR REV_GATE routing 004 application audit:", report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
