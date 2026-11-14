#!/usr/bin/env python3
"""Apply or verify the exact PCB-PWR C13-to-C11 routing 009 candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-SYS-C13-C11-ROUTING-009"
BASE = DIRECTORY / "PCB-PWR_VBAT_SYS_C13_C11_ROUTING_009_BASE_REV_A.kicad_pcb"
CANDIDATE = DIRECTORY / "PCB-PWR_VBAT_SYS_C13_C11_ROUTING_009_CANDIDATE_REV_A.kicad_pcb"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_VBAT_SYS_C13_C11_ROUTING_009_APPROVAL_REV_A.json"
BASE_SHA = "bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e"
CANDIDATE_SHA = "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"
APPROVAL_SHA = "41edd423f57d5b4651cadb76edfeb9cfb72240582d680993d9d832e183f431b2"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    assert digest(BASE) == BASE_SHA
    assert digest(CANDIDATE) == CANDIDATE_SHA
    assert digest(APPROVAL) == APPROVAL_SHA
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval["authorization"]
    assert approval["decision"] == "ACCEPT_PCB_PWR_VBAT_SYS_C13_C11_ROUTING_009_SUBGATE"
    assert approval["reviewed_candidate_board_sha256"] == CANDIDATE_SHA
    assert authorization["expected_authoritative_predecessor_sha256"] == BASE_SHA
    assert authorization["authorized_applied_board_sha256"] == CANDIDATE_SHA
    assert authorization["apply_exact_hash_bound_c13_c11_routing_candidate"] is True
    assert authorization["preserve_all_predecessor_objects"] is True
    assert authorization["add_only_the_reviewed_four_vbat_sys_segments"] is True
    assert authorization["alter_reviewed_candidate_without_new_controlled_review"] is False
    assert authorization["routing_complete"] is False
    assert authorization["review_b_complete"] is False
    assert authorization["cam_or_manufacturing_release"] is False
    return CANDIDATE.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = accepted_payload()
    if args.check:
        assert BOARD.read_bytes() == payload, "authoritative PCB-PWR is not exact accepted 009"
    else:
        assert BOARD.read_bytes() == BASE.read_bytes(), "authoritative 008 predecessor differs"
        BOARD.write_bytes(payload)
    print("PCB-PWR C13-to-C11 009 exact application: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
