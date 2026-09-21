#!/usr/bin/env python3
"""Apply/check the exact accepted PCB-PWR LM74700 VCAP routing candidate 002."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/candidates/PCB-PWR-LM74700-VCAP-ROUTING-002/PCB-PWR_LM74700_VCAP_ROUTING_002_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-PWR-LM74700-VCAP-ROUTING-002/PCB-PWR_LM74700_VCAP_ROUTING_002_CANDIDATE_REV_A.kicad_pcb"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_LM74700_VCAP_ROUTING_002_APPROVAL_REV_A.json"

BASE_SHA256 = "a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236"
CANDIDATE_SHA256 = "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5"
APPROVAL_SHA256 = "b9578a4d6691a1a5d7f0bfaafc08d6939af70acf1b4d86add1c00c0b816099ea"
APPROVAL_COMMIT = "b4b1ca81ffca63b389c3e34b3ba1be17ac9a590f"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    require(sha256(BASE) == BASE_SHA256, "VCAP predecessor SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "VCAP candidate SHA-256 drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "VCAP approval SHA-256 drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval["authorization"]
    require(
        approval["decision"] == "ACCEPT_PCB_PWR_LM74700_VCAP_ROUTING_002_SUBGATE"
        and approval["reviewed_candidate_board_sha256"] == CANDIDATE_SHA256
        and authorization["apply_exact_hash_bound_vcap_routing_candidate"] is True
        and authorization["expected_authoritative_predecessor_sha256"] == BASE_SHA256
        and authorization["authorized_applied_board_sha256"] == CANDIDATE_SHA256
        and authorization["add_only_the_reviewed_vcap_segment"] is True
        and authorization["authorize_narrow_switch_node_substitution"] is False
        and authorization["routing_complete"] is False
        and authorization["review_b_complete"] is False
        and authorization["cam_or_manufacturing_release"] is False,
        "VCAP approval identity or boundary drift",
    )
    return CANDIDATE.read_bytes()


def apply(output: Path, check: bool) -> dict[str, object]:
    payload = accepted_payload()
    if check:
        require(output.read_bytes() == payload,
                "authoritative PCB-PWR is not the exact accepted VCAP candidate")
    else:
        require(output.read_bytes() == BASE.read_bytes() and sha256(output) == BASE_SHA256,
                "authoritative PCB-PWR is not the approved predecessor")
        output.write_bytes(payload)
    return {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_LM74700_VCAP_ROUTING_002_APPLICATION",
        "approval_commit": APPROVAL_COMMIT,
        "approval_sha256": APPROVAL_SHA256,
        "predecessor_sha256": BASE_SHA256,
        "applied_sha256": CANDIDATE_SHA256,
        "trace_items": 3,
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
