#!/usr/bin/env python3
"""Replay immutable candidate-008 evidence after exact 008 application."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import audit_pcb_pwr_vbat_sys_c13_c12_routing_008_candidate_rev_a as candidate_audit
import generate_pcb_pwr_vbat_sys_c13_c12_routing_008_candidate_rev_a as generator


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
CANDIDATE_SHA = "bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e"
ACTIVE_SUCCESSOR_SHA = "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"


def historical_candidate_audit(
    drc_base: Path | None = None, drc_candidate: Path | None = None
) -> dict:
    payload = ACTIVE.read_bytes()
    assert hashlib.sha256(payload).hexdigest() in {CANDIDATE_SHA, ACTIVE_SUCCESSOR_SHA}
    assert hashlib.sha256(generator.CANDIDATE.read_bytes()).hexdigest() == CANDIDATE_SHA
    generator.SOURCE = generator.BASE
    candidate_audit.SOURCE = candidate_audit.BASE
    generator.generate(generator.BASE, generator.CANDIDATE, check=True)
    # Preserve the owner-reviewed candidate audit byte-for-byte. Replay its
    # candidate-time status boundary from a temporary snapshot after application.
    status = json.loads(candidate_audit.STATUS.read_text(encoding="utf-8"))
    route = status["native_layout"]["vbat_sys_c13_c12_routing_008"]
    route["status"] = "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_COMPARATIVE_DRC_HUMAN_REVIEW_PENDING"
    route["authoritative_board_modified"] = False
    route["application_authorized"] = False
    with tempfile.TemporaryDirectory() as directory:
        snapshot = Path(directory) / "PCB_PWR_CAPTURE_STATUS_REV_A.json"
        snapshot.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        candidate_audit.STATUS = snapshot
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
    print("PCB-PWR C13-to-C12 008 historical candidate:", result["status"])
