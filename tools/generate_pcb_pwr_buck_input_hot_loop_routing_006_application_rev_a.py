#!/usr/bin/env python3
"""Apply or verify the exact PCB-PWR hot-loop 006 board accepted by Скиф."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-INPUT-HOT-LOOP-ROUTING-006"
BASE = DIR / "PCB-PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_BASE_REV_A.kicad_pcb"
CANDIDATE = DIR / "PCB-PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_CANDIDATE_REV_A.kicad_pcb"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_APPROVAL_REV_A.json"
BASE_SHA = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"
CANDIDATE_SHA = "9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0"
APPROVAL_SHA = "3738c1235f805acb01fccda413a379eac13b60d5d6f7ebaae12c72969c53ae1f"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    assert digest(BASE) == BASE_SHA, "approved predecessor changed"
    assert digest(CANDIDATE) == CANDIDATE_SHA, "approved candidate changed"
    assert digest(APPROVAL) == APPROVAL_SHA, "owner approval changed"
    a = json.loads(APPROVAL.read_text(encoding="utf-8"))
    b = a["authorization"]
    assert a["decision"] == "ACCEPT_PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_SUBGATE"
    assert a["reviewed_candidate_board_sha256"] == CANDIDATE_SHA
    assert b["expected_authoritative_predecessor_sha256"] == BASE_SHA
    assert b["authorized_applied_board_sha256"] == CANDIDATE_SHA
    assert b["apply_exact_hash_bound_hot_loop_routing_candidate"] is True
    assert b["preserve_all_predecessor_objects"] is True
    assert b["alter_reviewed_candidate_without_new_controlled_review"] is False
    assert b["routing_complete"] is False
    assert b["review_b_complete"] is False
    assert b["cam_or_manufacturing_release"] is False
    return CANDIDATE.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = accepted_payload()
    if args.check:
        assert BOARD.read_bytes() == payload, "authoritative board differs from approved candidate"
    else:
        assert BOARD.read_bytes() == BASE.read_bytes(), "authoritative predecessor differs"
        BOARD.write_bytes(payload)
    print("PCB-PWR hot-loop 006 exact application: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
