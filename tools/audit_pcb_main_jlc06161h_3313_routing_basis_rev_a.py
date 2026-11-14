#!/usr/bin/env python3
"""Audit the selected PCB-MAIN JLC06161H-3313 EVT routing basis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_evt_engineering_manufacturing_baseline_rev_a import audit as audit_baseline


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        baseline = audit_baseline()
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        assert contract["selected_public_standard"]["stackup_id"] == "JLC06161H-3313"
        assert contract["numeric_geometry"]["rf_50ohm"]["trace_width_mm"] == 0.1509
        assert contract["numeric_geometry"]["usb_90ohm"]["trace_width_mm"] == 0.1537
        assert contract["numeric_geometry"]["usb_90ohm"]["pair_gap_mm"] == 0.2032
        boundary = contract["acceptance_boundary"]
        assert boundary["published_standard_selected_as_final_job_stackup"] is True
        assert boundary["production_impedance_tolerance_percent"] == 10.0
        assert boundary["job_specific_fabricator_response_required"] is False
        assert boundary["order_checkout_dfm_must_pass"] is True
        assert boundary["manufacturing_release"] is False
        result = {
            "schema": "dioneya-pcb-main-routing-design-basis-audit-v2",
            "configuration": baseline["configuration"],
            "board": "PCB-MAIN",
            "status": "PASS_PUBLIC_STANDARD_SELECTED_AS_EVT_JOB_STACKUP_NOT_FOR_MANUFACTURE",
            "stackup_id": "JLC06161H-3313",
            "rf_50ohm_trace_width_mm": 0.1509,
            "usb_90ohm_trace_width_mm": 0.1537,
            "usb_90ohm_pair_gap_mm": 0.2032,
            "external_reply_required": False,
            "manufacturing_release": False,
        }
        exit_code = 0
    except Exception as exc:
        result = {"status": "FAIL_MAIN_ROUTING_BASIS_AUDIT", "error": str(exc),
                  "manufacturing_release": False}
        exit_code = 1
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(result["status"])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
