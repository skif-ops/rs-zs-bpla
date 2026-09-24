#!/usr/bin/env python3
"""Replay immutable candidate-006 audit after accepted 007 succeeds it."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import audit_pcb_pwr_buck_input_hot_loop_routing_006_candidate_rev_a as candidate_audit
from pcb_pwr_hot_loop_006_board import (
    C13_C12_008,
    C13_C12_008_SHA256,
    C13_C11_009,
    C13_C11_009_SHA256,
    OUTPUT_BULK_010,
    OUTPUT_BULK_010_SHA256,
    is_j2_placement_eco_003,
    CANDIDATE,
    SHUNT_BULK_007,
    SHUNT_BULK_007_SHA256,
)


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"


def historical_candidate_audit(
    drc_base: Path | None = None, drc_candidate: Path | None = None
) -> dict:
    payload = ACTIVE.read_bytes()
    active_sha = hashlib.sha256(payload).hexdigest()
    if is_j2_placement_eco_003(payload):
        payload, active_sha = OUTPUT_BULK_010.read_bytes(), OUTPUT_BULK_010_SHA256
    assert active_sha in {SHUNT_BULK_007_SHA256, C13_C12_008_SHA256, C13_C11_009_SHA256, OUTPUT_BULK_010_SHA256}
    assert payload == (SHUNT_BULK_007 if active_sha == SHUNT_BULK_007_SHA256
                       else C13_C12_008 if active_sha == C13_C12_008_SHA256
                       else C13_C11_009 if active_sha == C13_C11_009_SHA256
                       else OUTPUT_BULK_010).read_bytes()
    candidate_audit.ACTIVE = CANDIDATE
    return candidate_audit.audit(drc_base, drc_candidate)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = historical_candidate_audit(args.drc_base, args.drc_candidate)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR hot-loop 006 historical candidate:", result["status"])
