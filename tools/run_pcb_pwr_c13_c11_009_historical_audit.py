#!/usr/bin/env python3
"""Replay accepted candidate-009 audit after authoritative board advances."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import audit_pcb_pwr_vbat_sys_c13_c11_routing_009_candidate_rev_a as audit_module
import generate_pcb_pwr_vbat_sys_c13_c11_routing_009_candidate_rev_a as generator_module


def historical_candidate_audit(drc_base: Path | None = None, drc_candidate: Path | None = None) -> dict:
    original_audit_source = audit_module.SOURCE
    original_generator_source = generator_module.SOURCE
    try:
        audit_module.SOURCE = audit_module.BASE
        generator_module.SOURCE = generator_module.BASE
        return audit_module.audit(drc_base, drc_candidate)
    finally:
        audit_module.SOURCE = original_audit_source
        generator_module.SOURCE = original_generator_source


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = historical_candidate_audit(args.drc_base, args.drc_candidate)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR C13-to-C11 009 historical candidate:", report["status"])
