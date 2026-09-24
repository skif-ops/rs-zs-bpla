#!/usr/bin/env python3
"""Replay accepted application-009 audit after authoritative board advances."""

from __future__ import annotations

import argparse
import json

import audit_pcb_pwr_vbat_sys_c13_c11_routing_009_application_rev_a as audit_module
import generate_pcb_pwr_vbat_sys_c13_c11_routing_009_application_rev_a as generator_module


def historical_application_audit() -> dict:
    original_audit_board = audit_module.BOARD
    original_generator_board = generator_module.BOARD
    try:
        audit_module.BOARD = audit_module.CANDIDATE
        generator_module.BOARD = generator_module.CANDIDATE
        return audit_module.audit()
    finally:
        audit_module.BOARD = original_audit_board
        generator_module.BOARD = original_generator_board


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    report = historical_application_audit()
    if args.output:
        from pathlib import Path
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR C13-to-C11 009 historical application:", report["status"])
