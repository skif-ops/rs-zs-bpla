#!/usr/bin/env python3
"""Apply or verify the exact PCB-PWR C13-to-C12 candidate 008 accepted by Скиф."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-SYS-C13-C12-ROUTING-008"
BASE = DIRECTORY / "PCB-PWR_VBAT_SYS_C13_C12_ROUTING_008_BASE_REV_A.kicad_pcb"
CANDIDATE = DIRECTORY / "PCB-PWR_VBAT_SYS_C13_C12_ROUTING_008_CANDIDATE_REV_A.kicad_pcb"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_VBAT_SYS_C13_C12_ROUTING_008_APPROVAL_REV_A.json"
BASE_SHA = "bb17dbead2445bcf4464960a83e13302347ce90463928ab09563afb3f0a3876b"
CANDIDATE_SHA = "bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e"
SUCCESSOR_SHA = "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"
OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"
J2_PLACEMENT_ECO_003_SHA = "b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6"
AUTOROUTE_011_SHA = "cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578"
APPROVAL_SHA = "f90d95781a140300856b290b9958f0f814c5ef13e44da332e0a1311993be40f2"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    assert digest(BASE) == BASE_SHA, "approved 007 predecessor changed"
    assert digest(CANDIDATE) == CANDIDATE_SHA, "approved 008 candidate changed"
    assert digest(APPROVAL) == APPROVAL_SHA, "owner approval changed"
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval["authorization"]
    assert approval["decision"] == "ACCEPT_PCB_PWR_VBAT_SYS_C13_C12_ROUTING_008_SUBGATE"
    assert approval["reviewed_candidate_board_sha256"] == CANDIDATE_SHA
    assert authorization["expected_authoritative_predecessor_sha256"] == BASE_SHA
    assert authorization["authorized_applied_board_sha256"] == CANDIDATE_SHA
    assert authorization["apply_exact_hash_bound_c13_c12_routing_candidate"] is True
    assert authorization["preserve_all_predecessor_objects"] is True
    assert authorization["add_only_the_reviewed_two_vbat_sys_segments"] is True
    assert authorization["authorize_c13_to_c11_u2_global_ground_output_kelvin_or_feedback_routing"] is False
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
        assert digest(BOARD) in {CANDIDATE_SHA, SUCCESSOR_SHA, OUTPUT_BULK_010_SHA, J2_PLACEMENT_ECO_003_SHA, AUTOROUTE_011_SHA}, \
            "authoritative PCB-PWR is not accepted 008 or controlled successor"
    else:
        assert BOARD.read_bytes() == BASE.read_bytes(), "authoritative 007 predecessor differs"
        BOARD.write_bytes(payload)
    print("PCB-PWR C13-to-C12 008 exact application: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
