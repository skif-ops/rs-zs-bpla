#!/usr/bin/env python3
"""Audit the bounded public JLCPCB numeric routing basis for PCB-MAIN."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.json"
RECORD = ROOT / "hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.md"
RESPONSE = ROOT / "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_RESPONSE_REV_A.csv"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def audit() -> dict[str, object]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    require(contract["schema"] == "dioneya-pcb-main-routing-design-basis-v1", "schema drift")
    require(contract["configuration"] == "EVT-PRE-20 Rev.A", "configuration drift")
    require(contract["board"] == "PCB-MAIN", "board drift")
    require(contract["retrieval_utc_date"] == "2026-09-19", "retrieval date drift")
    require(contract["fabricator"] == "JLCPCB", "fabricator drift")
    require(contract["official_sources"] == [
        "https://jlcpcb.com/impedance",
        "https://jlcpcb.com/pcb-impedance-calculator",
    ], "official source drift")

    require(contract["calculator_inputs"] == {
        "board_type": "Rigid",
        "copper_layers": 6,
        "nominal_board_thickness_mm": 1.6,
        "inner_copper_weight_oz": 0.5,
        "outer_copper_weight_oz": 1.0,
        "unit": "mm",
    }, "calculator input drift")

    standard = contract["selected_public_standard"]
    require(standard["stackup_id"] == "JLC06161H-3313", "stackup ID drift")
    require(standard["page_label"] == "Standard", "stackup label drift")
    require(standard["page_recommendation"] == "recommend", "recommendation drift")
    require(standard["displayed_finished_thickness_mm"] == 1.54, "finished thickness drift")
    require(standard["displayed_finished_thickness_tolerance_percent"] == 10.0,
            "displayed thickness tolerance drift")
    require(standard["layers"] == [
        {"name": "L1", "kind": "copper", "thickness_mm": 0.0350},
        {"name": "PP1", "kind": "prepreg", "material": "3313 RC57%", "thickness_mm": 0.0994},
        {"name": "L2", "kind": "copper", "thickness_mm": 0.0152},
        {"name": "CORE1", "kind": "core", "material": "H/H without copper", "thickness_mm": 0.5500},
        {"name": "L3", "kind": "copper", "thickness_mm": 0.0152},
        {"name": "PP2", "kind": "prepreg", "material": "2116 RC54%", "thickness_mm": 0.1088},
        {"name": "L4", "kind": "copper", "thickness_mm": 0.0152},
        {"name": "CORE2", "kind": "core", "material": "H/H without copper", "thickness_mm": 0.5500},
        {"name": "L5", "kind": "copper", "thickness_mm": 0.0152},
        {"name": "PP3", "kind": "prepreg", "material": "3313 RC57%", "thickness_mm": 0.0994},
        {"name": "L6", "kind": "copper", "thickness_mm": 0.0350},
    ], "stackup construction drift")

    geometry = contract["numeric_geometry"]
    require(geometry["rf_50ohm"] == {
        "target_ohm": 50.0,
        "type": "Single Ended (Non coplanar)",
        "signal_layer": "L1",
        "reference_layer": "L2",
        "trace_width_mm": 0.1509,
    }, "50-ohm geometry drift")
    require(geometry["usb_90ohm"] == {
        "target_ohm": 90.0,
        "type": "Differential Pair (Non coplanar)",
        "signal_layer": "L1",
        "reference_layer": "L2",
        "trace_width_mm": 0.1537,
        "pair_gap_mm": 0.2032,
    }, "90-ohm geometry drift")

    boundary = contract["acceptance_boundary"]
    require(boundary["numeric_input_for_engineering_routing_candidate"] is True,
            "engineering numeric input is not released")
    require(boundary["published_standard_selected_as_final_job_stackup"] is False,
            "public standard was incorrectly promoted to final job stackup")
    require(boundary["production_impedance_tolerance_percent"] is None,
            "production impedance tolerance was invented")
    for field in ("coupon_plan_accepted", "review_b_complete", "manufacturing_release"):
        require(boundary[field] is False, f"{field} was incorrectly promoted")
    require(boundary["job_specific_fabricator_response_required"] is True,
            "job-specific fabricator response interlock removed")
    require(boundary["job_specific_dfm_required"] is True,
            "job-specific DFM interlock removed")

    rows = list(csv.DictReader(RESPONSE.open(encoding="utf-8-sig", newline="")))
    require(len(rows) == 22, "stackup response row count drift")
    require(all(row["Disposition"] == "PENDING_EXTERNAL_RESPONSE" for row in rows),
            "public basis incorrectly accepted a fabricator response row")
    require(all(not row["Response_Value"].strip() for row in rows),
            "pending fabricator response unexpectedly populated")

    record = RECORD.read_text(encoding="utf-8")
    for token in (
        "0.1509 mm", "0.1537 mm", "0.2032 mm",
        "Final production impedance tolerance: `OPEN`",
        "Manufacturing release: `false`",
    ):
        require(token in record, f"record token missing: {token}")

    return {
        "schema": "dioneya-pcb-main-routing-design-basis-audit-v1",
        "configuration": contract["configuration"],
        "board": contract["board"],
        "status": contract["status"],
        "stackup_id": standard["stackup_id"],
        "rf_50ohm_trace_width_mm": geometry["rf_50ohm"]["trace_width_mm"],
        "usb_90ohm_trace_width_mm": geometry["usb_90ohm"]["trace_width_mm"],
        "usb_90ohm_pair_gap_mm": geometry["usb_90ohm"]["pair_gap_mm"],
        "pending_fabricator_response_rows": len(rows),
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(
        "PCB-MAIN JLC06161H-3313 public routing basis PASS: "
        "RF width 0.1509 mm; USB width/gap 0.1537/0.2032 mm; "
        "final fabricator acceptance remains pending"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
