#!/usr/bin/env python3
"""Apply or verify the exact accepted PCB-PWR 3V8 output bulk candidate 010."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "hardware/kicad/candidates/PCB-PWR-3V8-OUTPUT-BULK-ROUTING-010"
BASE = DIRECTORY / "PCB-PWR_3V8_OUTPUT_BULK_ROUTING_010_BASE_REV_A.kicad_pcb"
CANDIDATE = DIRECTORY / "PCB-PWR_3V8_OUTPUT_BULK_ROUTING_010_CANDIDATE_REV_A.kicad_pcb"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_3V8_OUTPUT_BULK_ROUTING_010_APPROVAL_REV_A.json"
BASE_SHA = "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"
CANDIDATE_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"
APPROVAL_SHA = "f7e0fb5f7bddc8fdca644cb125ff58900a187bfd36831c6ea9215e18687cad6b"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    assert digest(BASE) == BASE_SHA
    assert digest(CANDIDATE) == CANDIDATE_SHA
    assert digest(APPROVAL) == APPROVAL_SHA
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval["authorization"]
    assert approval["decision"] == "ACCEPT_PCB_PWR_3V8_OUTPUT_BULK_ROUTING_010_SUBGATE"
    assert approval["reviewed_candidate_board_sha256"] == CANDIDATE_SHA
    assert authorization["expected_authoritative_predecessor_sha256"] == BASE_SHA
    assert authorization["authorized_applied_board_sha256"] == CANDIDATE_SHA
    assert authorization["apply_exact_hash_bound_3v8_output_bulk_routing_candidate"] is True
    assert authorization["preserve_all_predecessor_objects"] is True
    assert authorization["add_only_the_reviewed_ten_3v8_modem_segments"] is True
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
        from pcb_pwr_hot_loop_006_board import is_autoroute_011, is_eco_005, is_eco_006, is_j2_placement_eco_003

        active = BOARD.read_bytes()
        assert active == payload or is_j2_placement_eco_003(active) or (is_autoroute_011(active) or (is_eco_005(active) or is_eco_006(active))), \
            "authoritative PCB-PWR is not exact accepted 010 or its ECO-003 / autoroute 011 successor"
    else:
        assert BOARD.read_bytes() == BASE.read_bytes(), "authoritative 009 predecessor differs"
        BOARD.write_bytes(payload)
    print("PCB-PWR 3V8 output bulk 010 exact application: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
