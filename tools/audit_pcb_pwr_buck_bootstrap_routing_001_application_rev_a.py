#!/usr/bin/env python3
"""Audit exact application of PCB-PWR bootstrap routing candidate 001."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from kiutils.board import Board

import audit_pcb_pwr_buck_bootstrap_routing_001_candidate_rev_a as candidate_audit
from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


from pcb_pwr_hot_loop_006_board import historical_basis_board

ROOT = Path(__file__).resolve().parents[1]
BOARD = historical_basis_board(ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb")
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_APPLICATION_REV_A.json"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
BOARD_SHA256 = "a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236"
SEMANTIC_SHA256 = "d90ef0332ed5da798029a5cb580a0f3a5f68387068811eeb9e4c06d0681500ae"
SUCCESSOR_SHA256 = "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5"
SUCCESSOR_SEMANTIC_SHA256 = "07ce41bb361e68dd3a5310a6879030f097e4498e9397f2506ea5b78f49c47234"
VBAT_RAW_SUCCESSOR_SHA256 = "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3"
VBAT_RAW_SUCCESSOR_SEMANTIC_SHA256 = "4472097781d9dc58231a14c0fea67ad102e2e25b1e9e05e98481e7d6d3f3a93d"
REV_GATE_SUCCESSOR_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
REV_GATE_SUCCESSOR_SEMANTIC_SHA256 = "f7a659d0740e78d40eddae7016724bd8e616baf9fb425f06ace70ec9acca4d3d"
ECO_002_SUCCESSOR_SHA256 = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"
ECO_002_SUCCESSOR_SEMANTIC_SHA256 = "0e52d4cbc80104691e3793a579c7c7a8570e3640fabc2fb02bd7ea2e65643555"
APPROVAL_SHA256 = "30b26ade4edf0a2f357fb93e1ce95dea7628a7c382003578ebf07c74a7465e0b"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict[str, object]:
    require(sha256(BOARD) in {
                BOARD_SHA256, SUCCESSOR_SHA256, VBAT_RAW_SUCCESSOR_SHA256,
                REV_GATE_SUCCESSOR_SHA256, ECO_002_SUCCESSOR_SHA256},
            "authoritative PCB-PWR is not accepted bootstrap or controlled successor")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "bootstrap approval drift")
    board = Board.from_file(str(BOARD), encoding="utf-8")
    require(semantic_board_sha256(board) in {
                SEMANTIC_SHA256,
                SUCCESSOR_SEMANTIC_SHA256,
                VBAT_RAW_SUCCESSOR_SEMANTIC_SHA256,
                REV_GATE_SUCCESSOR_SEMANTIC_SHA256,
                ECO_002_SUCCESSOR_SEMANTIC_SHA256,
            },
            "applied bootstrap semantic identity drift")
    require(len(board.traceItems) in {2, 3, 4, 8, 14} and len(board.zones) == 0,
            "applied bootstrap copper inventory drift")
    proposal = candidate_audit.audit()
    require(proposal["status"] ==
            "PASS_STATIC_PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_CANDIDATE",
            "historical bootstrap proposal audit drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    route = status["native_layout"]["buck_bootstrap_routing_001"]
    require(
        approval["decision"] == "ACCEPT_PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_SUBGATE"
        and application["decision"] == approval["decision"]
        and application["predecessor_board_sha256"] == candidate_audit.BASE_SHA256
        and application["applied_board_sha256"] == BOARD_SHA256
        and application["trace_items"] == 2
        and application["vias"] == 0
        and application["machine_gate"]["status"] in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_APPLICATION_GATE",
        }
        and application["routing_complete"] is False
        and application["review_b_complete"] is False
        and application["cam_or_manufacturing_release"] is False
        and route["active_board_sha256"] in {
            BOARD_SHA256, SUCCESSOR_SHA256, VBAT_RAW_SUCCESSOR_SHA256,
            REV_GATE_SUCCESSOR_SHA256, ECO_002_SUCCESSOR_SHA256}
        and route["authoritative_board_modified"] is True
        and route["routing_complete"] is False
        and route["review_b_complete"] is False
        and route["manufacturing_release"] is False,
        "bootstrap application boundary drift",
    )
    report: dict[str, object] = {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_APPLICATION",
        "board_sha256": BOARD_SHA256,
        "trace_items": 2,
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
    print("PCB-PWR bootstrap routing 001 application audit:", report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
