#!/usr/bin/env python3
"""Replay immutable candidate-007 evidence after exact 007 application."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import audit_pcb_pwr_vbat_sys_shunt_bulk_routing_007_candidate_rev_a as candidate_audit
import generate_pcb_pwr_vbat_sys_shunt_bulk_routing_007_candidate_rev_a as generator


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
CANDIDATE_SHA = "bb17dbead2445bcf4464960a83e13302347ce90463928ab09563afb3f0a3876b"
SUCCESSOR = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-SYS-C13-C12-ROUTING-008/PCB-PWR_VBAT_SYS_C13_C12_ROUTING_008_CANDIDATE_REV_A.kicad_pcb"
SUCCESSOR_SHA = "bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e"


def historical_candidate_audit(
    drc_base: Path | None = None, drc_candidate: Path | None = None
) -> dict:
    payload = ACTIVE.read_bytes()
    active_sha = hashlib.sha256(payload).hexdigest()
    assert active_sha in {CANDIDATE_SHA, SUCCESSOR_SHA}
    assert hashlib.sha256(generator.CANDIDATE.read_bytes()).hexdigest() == CANDIDATE_SHA
    if active_sha == CANDIDATE_SHA:
        assert payload == generator.CANDIDATE.read_bytes()
    else:
        assert payload == SUCCESSOR.read_bytes()
    # Candidate generator and audit are owner-reviewed immutable evidence. Route
    # their source pointer to the archived 006 predecessor without editing them.
    generator.SOURCE = generator.BASE
    candidate_audit.SOURCE = candidate_audit.BASE
    generator.generate(generator.BASE, generator.CANDIDATE, check=True)
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
    print("PCB-PWR shunt-bulk 007 historical candidate:", result["status"])
