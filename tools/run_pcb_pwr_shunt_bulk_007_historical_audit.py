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
ACTIVE_SUCCESSOR_SHA = "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"
OUTPUT_BULK_010_SHA = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"
J2_PLACEMENT_ECO_003_SHA = "b12f445dd87799745635c289b271dda1781a85245dcfee2b61f1c989c893a7e6"
AUTOROUTE_011_SHA = "cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578"
ECO_005_SHA = "81f44a7068de6c8d7b3ae1a6951bc9d7a4bc6c2646cdbc4eccea4d9c79e35610"  # exact committed ECO-005 board (Review B R1 remediation)


def historical_candidate_audit(
    drc_base: Path | None = None, drc_candidate: Path | None = None
) -> dict:
    payload = ACTIVE.read_bytes()
    active_sha = hashlib.sha256(payload).hexdigest()
    assert active_sha in {CANDIDATE_SHA, SUCCESSOR_SHA, ACTIVE_SUCCESSOR_SHA, OUTPUT_BULK_010_SHA,
                          J2_PLACEMENT_ECO_003_SHA, AUTOROUTE_011_SHA, ECO_005_SHA}
    assert hashlib.sha256(generator.CANDIDATE.read_bytes()).hexdigest() == CANDIDATE_SHA
    if active_sha == CANDIDATE_SHA:
        assert payload == generator.CANDIDATE.read_bytes()
    elif active_sha == SUCCESSOR_SHA:
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
