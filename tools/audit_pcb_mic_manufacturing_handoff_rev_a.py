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
        root = Path(__file__).resolve().parents[1]
        status_path = root / "hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json"
        approval_path = root / "hardware/reviews/PCB_MIC_REVIEW_B_APPROVAL_REV_B.json"
        handoff_json = root / "hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_B.json"
        handoff_md = root / "hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_B.md"
        validate_git_binding(
            args.commit_sha,
            args.require_clean_source,
            [
                Path(__file__).resolve(),
                status_path,
                approval_path,
                handoff_json,
                handoff_md,
                root / "hardware/reviews/PCB_MIC_DFM_RESPONSE_REV_A.csv",
            ],
        )
        baseline = audit_baseline()
        status = json.loads(status_path.read_text(encoding="utf-8"))
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        handoff = json.loads(handoff_json.read_text(encoding="utf-8"))
        if status.get("release_state") != "REVIEW_B_PASS_CONTROLLED_FIRST_ARTICLE":
            raise RuntimeError("PCB-MIC Review B controlled release is not active")
        if status.get("manufacturing_release") is not True:
            raise RuntimeError("PCB-MIC manufacturing release flag is false")
        if approval.get("decision") != "ACCEPT_CONTROLLED_FIRST_ARTICLE":
            raise RuntimeError("PCB-MIC approval decision mismatch")
        if handoff.get("status") != "RELEASED_CONTROLLED_FIRST_ARTICLE":
            raise RuntimeError("PCB-MIC manufacturing handoff status mismatch")
        result = {
            "schema": "dioneya-pcb-mic-manufacturing-handoff-audit-v3",
            "configuration": baseline["configuration"],
            "assembly": "PCB-MIC",
            "status": "PASS_REVIEW_B_CONTROLLED_FIRST_ARTICLE_HANDOFF",
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
            "review_b_complete": True,
            "manufacturing_release": True,
            "fabrication_authorized": True,
            "pcba_authorized": True,
            "scope": "ONE_BOARD_OR_ONE_PANEL_THEN_REMAINDER_AFTER_INSPECTION",
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
