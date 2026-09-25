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
SHUNT_BULK_007_SHA = "bb17dbead2445bcf4464960a83e13302347ce90463928ab09563afb3f0a3876b"
C13_C12_008_SHA = "bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e"
C13_C11_009_SHA = "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"
OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"
J2_PLACEMENT_ECO_003_SHA = "b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6"
AUTOROUTE_011_SHA = "cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578"
ECO_005_SHA = "81f44a7068de6c8d7b3ae1a6951bc9d7a4bc6c2646cdbc4eccea4d9c79e35610"  # exact committed ECO-005 board (Review B R1 remediation)
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
        assert digest(BOARD) in {CANDIDATE_SHA, SHUNT_BULK_007_SHA, C13_C12_008_SHA, C13_C11_009_SHA, OUTPUT_BULK_010_SHA, J2_PLACEMENT_ECO_003_SHA, AUTOROUTE_011_SHA, ECO_005_SHA}, \
            "authoritative board is not the approved candidate or controlled successor"
    else:
        assert BOARD.read_bytes() == BASE.read_bytes(), "authoritative predecessor differs"
        BOARD.write_bytes(payload)
    print("PCB-PWR hot-loop 006 exact application: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
