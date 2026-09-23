#!/usr/bin/env python3
"""Apply/check the exact accepted PCB-PWR bootstrap routing candidate 001."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-BOOTSTRAP-ROUTING-001/PCB-PWR_BUCK_BOOTSTRAP_ROUTING_001_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-BOOTSTRAP-ROUTING-001/PCB-PWR_BUCK_BOOTSTRAP_ROUTING_001_CANDIDATE_REV_A.kicad_pcb"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_APPROVAL_REV_A.json"

BASE_SHA256 = "b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957"
CANDIDATE_SHA256 = "a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236"
CONTROLLED_SUCCESSOR_SHA256 = "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5"
LATEST_SUCCESSOR_SHA256 = "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3"
REV_GATE_SUCCESSOR_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
ECO_002_SUCCESSOR_SHA256 = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"
APPROVAL_SHA256 = "30b26ade4edf0a2f357fb93e1ce95dea7628a7c382003578ebf07c74a7465e0b"
APPROVAL_COMMIT = "57d7b571ed2bb82feea7288fea1d7f4b99ac0ae8"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    require(sha256(BASE) == BASE_SHA256, "bootstrap predecessor SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "bootstrap candidate SHA-256 drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "bootstrap approval SHA-256 drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval["authorization"]
    require(
        approval["decision"] == "ACCEPT_PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_SUBGATE"
        and approval["reviewed_candidate_board_sha256"] == CANDIDATE_SHA256
        and authorization["apply_exact_hash_bound_bootstrap_routing_candidate"] is True
        and authorization["expected_authoritative_predecessor_sha256"] == BASE_SHA256
        and authorization["authorized_applied_board_sha256"] == CANDIDATE_SHA256
        and authorization["add_only_the_two_reviewed_bootstrap_segments"] is True
        and authorization["routing_complete"] is False
        and authorization["review_b_complete"] is False
        and authorization["cam_or_manufacturing_release"] is False,
        "bootstrap approval identity or boundary drift",
    )
    return CANDIDATE.read_bytes()


def apply(output: Path, check: bool) -> dict[str, object]:
    payload = accepted_payload()
    if check:
        output_sha256 = sha256(output)
        require(output_sha256 in {
                    CANDIDATE_SHA256,
                    CONTROLLED_SUCCESSOR_SHA256,
                    LATEST_SUCCESSOR_SHA256,
                    REV_GATE_SUCCESSOR_SHA256,
                    ECO_002_SUCCESSOR_SHA256,
                },
                "authoritative PCB-PWR is not accepted bootstrap or controlled successor")
    else:
        require(output.read_bytes() == BASE.read_bytes() and sha256(output) == BASE_SHA256,
                "authoritative PCB-PWR is not the approved predecessor")
        output.write_bytes(payload)
    return {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_APPLICATION",
        "approval_commit": APPROVAL_COMMIT,
        "approval_sha256": APPROVAL_SHA256,
        "predecessor_sha256": BASE_SHA256,
        "applied_sha256": CANDIDATE_SHA256,
        "trace_items": 2,
        "vias": 0,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=BOARD)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(apply(args.output.resolve(), args.check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
