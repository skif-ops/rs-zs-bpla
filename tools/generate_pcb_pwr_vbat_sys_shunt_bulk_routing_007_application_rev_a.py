#!/usr/bin/env python3
"""Apply or verify the exact PCB-PWR shunt-to-bulk 007 candidate accepted by Скиф."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-SYS-SHUNT-BULK-ROUTING-007"
BASE = DIRECTORY / "PCB-PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_BASE_REV_A.kicad_pcb"
CANDIDATE = DIRECTORY / "PCB-PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_CANDIDATE_REV_A.kicad_pcb"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_APPROVAL_REV_A.json"
BASE_SHA = "9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0"
CANDIDATE_SHA = "bb17dbead2445bcf4464960a83e13302347ce90463928ab09563afb3f0a3876b"
SUCCESSOR_SHA = "bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e"
ACTIVE_SUCCESSOR_SHA = "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"
OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"
J2_PLACEMENT_ECO_003_SHA = "b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6"
AUTOROUTE_011_SHA = "cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578"
ECO_005_SHA = "81f44a7068de6c8d7b3ae1a6951bc9d7a4bc6c2646cdbc4eccea4d9c79e35610"  # exact committed ECO-005 board (Review B R1 remediation)
ECO_006_SHA = "b8c1da6ca80b9e5d2795c4fee5b6926e4ab6169086795295e8e517a18def6ca7"  # exact committed ECO-006 board (Review B R2 DFM: TP mask 0.1 mm, legend 1.0/0.15 mm; copper unchanged)
APPROVAL_SHA = "ad5a6f459cd80eebac05d622e361b8e8ea9e9b453176f2f4dc454abc982a87db"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    assert digest(BASE) == BASE_SHA, "approved 006 predecessor changed"
    assert digest(CANDIDATE) == CANDIDATE_SHA, "approved 007 candidate changed"
    assert digest(APPROVAL) == APPROVAL_SHA, "owner approval changed"
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval["authorization"]
    assert approval["decision"] == "ACCEPT_PCB_PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_SUBGATE"
    assert approval["reviewed_candidate_board_sha256"] == CANDIDATE_SHA
    assert authorization["expected_authoritative_predecessor_sha256"] == BASE_SHA
    assert authorization["authorized_applied_board_sha256"] == CANDIDATE_SHA
    assert authorization["apply_exact_hash_bound_shunt_bulk_routing_candidate"] is True
    assert authorization["preserve_all_predecessor_objects"] is True
    assert authorization["add_only_the_reviewed_two_vbat_sys_segments"] is True
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
        assert digest(BOARD) in {CANDIDATE_SHA, SUCCESSOR_SHA, ACTIVE_SUCCESSOR_SHA, OUTPUT_BULK_010_SHA, J2_PLACEMENT_ECO_003_SHA, AUTOROUTE_011_SHA, ECO_005_SHA, ECO_006_SHA}, \
            "authoritative PCB-PWR is not accepted 007 or controlled successor"
    else:
        assert BOARD.read_bytes() == BASE.read_bytes(), "authoritative 006 predecessor differs"
        BOARD.write_bytes(payload)
    print("PCB-PWR shunt-to-bulk 007 exact application: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
