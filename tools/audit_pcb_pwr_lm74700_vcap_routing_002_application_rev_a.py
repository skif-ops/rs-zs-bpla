#!/usr/bin/env python3
"""Audit exact application of PCB-PWR LM74700 VCAP routing candidate 002."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kiutils.board import Board

import audit_pcb_pwr_lm74700_vcap_routing_002_candidate_rev_a as candidate_audit
from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_LM74700_VCAP_ROUTING_002_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_PWR_LM74700_VCAP_ROUTING_002_APPLICATION_REV_A.json"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
BOARD_SHA256 = candidate_audit.CANDIDATE_SHA256
SEMANTIC_SHA256 = candidate_audit.CANDIDATE_SEMANTIC_SHA256
VBAT_RAW_SUCCESSOR_SHA256 = "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3"
VBAT_RAW_SUCCESSOR_SEMANTIC_SHA256 = "4472097781d9dc58231a14c0fea67ad102e2e25b1e9e05e98481e7d6d3f3a93d"
VBAT_RAW_SUCCESSOR = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-RAW-ROUTING-003/PCB-PWR_VBAT_RAW_ROUTING_003_CANDIDATE_REV_A.kicad_pcb"
REV_GATE_SUCCESSOR_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
REV_GATE_SUCCESSOR_SEMANTIC_SHA256 = "f7a659d0740e78d40eddae7016724bd8e616baf9fb425f06ace70ec9acca4d3d"
REV_GATE_SUCCESSOR = ROOT / "hardware/kicad/candidates/PCB-PWR-REV-GATE-ROUTING-004/PCB-PWR_REV_GATE_ROUTING_004_CANDIDATE_REV_A.kicad_pcb"
APPROVAL_SHA256 = "b9578a4d6691a1a5d7f0bfaafc08d6939af70acf1b4d86add1c00c0b816099ea"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict[str, object]:
    active_sha256 = sha256(BOARD)
    require(active_sha256 in {
                BOARD_SHA256, VBAT_RAW_SUCCESSOR_SHA256,
                REV_GATE_SUCCESSOR_SHA256},
            "authoritative PCB-PWR is not accepted VCAP or controlled successor")
    expected_active = {
        BOARD_SHA256: candidate_audit.CANDIDATE,
        VBAT_RAW_SUCCESSOR_SHA256: VBAT_RAW_SUCCESSOR,
        REV_GATE_SUCCESSOR_SHA256: REV_GATE_SUCCESSOR,
    }[active_sha256]
    require(BOARD.read_bytes() == expected_active.read_bytes(),
            "authoritative PCB-PWR VCAP successor byte identity drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "VCAP approval drift")
    board = Board.from_file(str(BOARD), encoding="utf-8")
    require(semantic_board_sha256(board) in {
                SEMANTIC_SHA256, VBAT_RAW_SUCCESSOR_SEMANTIC_SHA256,
                REV_GATE_SUCCESSOR_SEMANTIC_SHA256},
            "applied VCAP semantic identity drift")
    require(len(board.traceItems) in {3, 4, 8} and len(board.zones) == 0,
            "applied VCAP copper inventory drift")
    proposal = candidate_audit.audit()
    require(proposal["status"] ==
            "PASS_STATIC_PCB_PWR_LM74700_VCAP_ROUTING_002_CANDIDATE",
            "historical VCAP proposal audit drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    route = status["native_layout"]["lm74700_vcap_routing_002"]
    require(
        approval["decision"] == "ACCEPT_PCB_PWR_LM74700_VCAP_ROUTING_002_SUBGATE"
        and application["decision"] == approval["decision"]
        and application["predecessor_board_sha256"] == candidate_audit.BASE_SHA256
        and application["applied_board_sha256"] == BOARD_SHA256
        and application["trace_items"] == 3
        and application["vias"] == 0
        and application["machine_gate"]["status"] in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
        }
        and application["routing_complete"] is False
        and application["review_b_complete"] is False
        and application["cam_or_manufacturing_release"] is False
        and route["active_board_sha256"] in {
            BOARD_SHA256, VBAT_RAW_SUCCESSOR_SHA256,
            REV_GATE_SUCCESSOR_SHA256}
        and route["authoritative_board_modified"] is True
        and route["routing_complete"] is False
        and route["review_b_complete"] is False
        and route["manufacturing_release"] is False,
        "VCAP application boundary drift",
    )
    report: dict[str, object] = {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_LM74700_VCAP_ROUTING_002_APPLICATION",
        "board_sha256": BOARD_SHA256,
        "trace_items": 3,
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
    print("PCB-PWR LM74700 VCAP routing 002 application audit:", report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
