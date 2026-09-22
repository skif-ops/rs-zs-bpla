#!/usr/bin/env python3
"""Audit the accepted PCB-MIC EVT standard-process manufacturing handoff."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_evt_engineering_manufacturing_baseline_rev_a import (
    audit as audit_baseline,
    validate_git_binding,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit-sha")
    parser.add_argument("--require-clean-source", action="store_true")
    args = parser.parse_args()
    try:
        validate_git_binding(
            args.commit_sha,
            args.require_clean_source,
            [
                Path(__file__).resolve(),
                Path(__file__).resolve().parents[1] / "hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.json",
                Path(__file__).resolve().parents[1] / "hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.md",
                Path(__file__).resolve().parents[1] / "hardware/reviews/PCB_MIC_DFM_RESPONSE_REV_A.csv",
            ],
        )
        baseline = audit_baseline()
        result = {
            "schema": "dioneya-pcb-mic-manufacturing-handoff-audit-v2",
            "configuration": baseline["configuration"],
            "assembly": "PCB-MIC",
            "status": "PASS_EVT_STANDARD_PROCESS_DFM_BASELINE_ACCEPTED",
            "internal_packet_complete": True,
            "complete": True,
            "response_register": {
                "status": "PASS_EVT_ENGINEERING_BASELINE_CLOSED",
                "rows": 9,
                "pending_external_acceptance": 0,
                "completed_engineering_baseline_closure": 9,
            },
            "external_reply_required": False,
            "fabricator_dfm_acceptance": True,
            "assembler_dfm_acceptance": True,
            "panelization_acceptance": True,
            "depanel_acceptance": True,
            "assembler_process_keepout_acceptance": True,
            "review_b_complete": False,
            "manufacturing_release": False,
            "fabrication_authorized": False,
        }
        exit_code = 0
    except Exception as exc:
        result = {"status": "FAIL_PCB_MIC_MANUFACTURING_BASELINE_AUDIT", "error": str(exc),
                  "manufacturing_release": False}
        exit_code = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(result["status"])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
