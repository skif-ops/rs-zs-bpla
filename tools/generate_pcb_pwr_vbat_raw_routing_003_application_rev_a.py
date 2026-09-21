#!/usr/bin/env python3
"""Apply/check the exact accepted PCB-PWR VBAT_RAW routing candidate 003."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-RAW-ROUTING-003/PCB-PWR_VBAT_RAW_ROUTING_003_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-RAW-ROUTING-003/PCB-PWR_VBAT_RAW_ROUTING_003_CANDIDATE_REV_A.kicad_pcb"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_VBAT_RAW_ROUTING_003_APPROVAL_REV_A.json"

BASE_SHA256 = "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5"
CANDIDATE_SHA256 = "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3"
APPROVAL_SHA256 = "c7064ff198b4668aa486ce76a0552c7c76f67193d3a63d25c99019d5d03d5bc5"
APPROVAL_COMMIT = "4356f40dd80e7fb183db13bd3844d3bf30dd40b3"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    require(sha256(BASE) == BASE_SHA256, "VBAT_RAW predecessor SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "VBAT_RAW candidate SHA-256 drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "VBAT_RAW approval SHA-256 drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval["authorization"]
    require(
        approval["decision"] == "ACCEPT_PCB_PWR_VBAT_RAW_ROUTING_003_SUBGATE"
        and approval["reviewed_candidate_board_sha256"] == CANDIDATE_SHA256
        and authorization["apply_exact_hash_bound_vbat_raw_routing_candidate"] is True
        and authorization["expected_authoritative_predecessor_sha256"] == BASE_SHA256
        and authorization["authorized_applied_board_sha256"] == CANDIDATE_SHA256
        and authorization["add_only_the_reviewed_vbat_raw_segment"] is True
        and authorization["authorize_buck_hot_loop_or_switch_node_routing"] is False
        and authorization["routing_complete"] is False
        and authorization["review_b_complete"] is False
        and authorization["cam_or_manufacturing_release"] is False,
        "VBAT_RAW approval identity or boundary drift",
    )
    return CANDIDATE.read_bytes()


def apply(output: Path, check: bool) -> dict[str, object]:
    payload = accepted_payload()
    if check:
        require(output.read_bytes() == payload,
                "authoritative PCB-PWR is not the exact accepted VBAT_RAW candidate")
    else:
        require(output.read_bytes() == BASE.read_bytes() and sha256(output) == BASE_SHA256,
                "authoritative PCB-PWR is not the approved predecessor")
        output.write_bytes(payload)
    return {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_VBAT_RAW_ROUTING_003_APPLICATION",
        "approval_commit": APPROVAL_COMMIT,
        "approval_sha256": APPROVAL_SHA256,
        "predecessor_sha256": BASE_SHA256,
        "applied_sha256": CANDIDATE_SHA256,
        "trace_items": 4,
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
