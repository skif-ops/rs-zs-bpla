#!/usr/bin/env python3
"""Audit the EVT-PRE-20 hardware design and purchase-release gates only.

This gate intentionally excludes application, server, Android and other software
deliverables. Software is relevant here only when a hardware interface, pinout,
power sequence or production-test dependency explicitly requires it.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOT_SIZES = (4, 10, 20)
BOARD_FILES = {
    board: {
        "schematic": ROOT / f"hardware/kicad/native/{board}/{board}.kicad_sch",
        "board": ROOT / f"hardware/kicad/native/{board}/{board}.kicad_pcb",
        "project": ROOT / f"hardware/kicad/native/{board}/{board}.kicad_pro",
    }
    for board in ("PCB-MAIN", "PCB-MIC", "PCB-PWR")
}


def read_csv(relative_path: str) -> list[dict[str, str]]:
    with (ROOT / relative_path).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def read_json(relative_path: str) -> dict[str, object]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def board_copper_counts(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    return {
        "segments": len(re.findall(r"\(segment\b", text)),
        "vias": len(re.findall(r"\(via\b", text)),
        "zones": len(re.findall(r"\(zone\b", text)),
    }


def run_bom_qg2() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="evt-pre-20-hw-qg2-") as temp_dir:
        output = Path(temp_dir) / "bom_qg2.json"
        process = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/audit_evt_pre_20_bom_qg2.py"),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if process.returncode != 0 or not output.is_file():
            return {
                "status": "ERROR",
                "production_bom_complete": False,
                "blockers": [
                    "BOM QG-2 audit could not be executed reproducibly: "
                    + (process.stderr.strip() or process.stdout.strip() or f"exit {process.returncode}")
                ],
            }
        return json.loads(output.read_text(encoding="utf-8"))


def audit() -> dict[str, object]:
    checks: list[dict[str, object]] = []
    design_blockers: list[str] = []
    purchase_blockers: list[str] = []

    def check(
        name: str,
        passed: bool,
        detail: str,
        blocker: str,
        *,
        design: bool = True,
        purchase: bool = True,
    ) -> None:
        checks.append(
            {
                "name": name,
                "pass": passed,
                "detail": detail,
                "blocks_hardware_design_release": design and not passed,
                "blocks_purchase_release": purchase and not passed,
            }
        )
        if not passed and design:
            design_blockers.append(blocker)
        if not passed and purchase:
            purchase_blockers.append(blocker)

    baseline = (ROOT / "config/EVT_PRE_20_BASELINE.yaml").read_text(encoding="utf-8")
    lot_options_ok = (
        "supported_procurement_quantities: [4, 10, 20]" in baseline
        and "maximum_station_quantity: 20" in baseline
    )
    check(
        "controlled_procurement_scenarios",
        lot_options_ok,
        "procurement quantities 4, 10 and 20 with maximum serial capacity 20",
        "hardware baseline does not control all 4/10/20 procurement scenarios",
    )

    bom_qg2 = run_bom_qg2()
    qg2_ok = bom_qg2.get("production_bom_complete") is True
    qg2_blockers = [str(item) for item in bom_qg2.get("blockers", [])]
    check(
        "production_bom_qg2",
        qg2_ok,
        "production BOM QG-2 PASS" if qg2_ok else f"production BOM QG-2 BLOCKED ({len(qg2_blockers)} findings)",
        "production BOM QG-2 remains BLOCKED: " + " | ".join(qg2_blockers),
    )

    board_results: dict[str, object] = {}
    for board, files in BOARD_FILES.items():
        missing = [name for name, path in files.items() if not path.is_file()]
        copper = board_copper_counts(files["board"])
        routing_present = copper["segments"] > 0
        board_results[board] = {
            "files": {name: str(path.relative_to(ROOT)) for name, path in files.items()},
            "missing": missing,
            "copper": copper,
            "routing_present": routing_present,
        }
        check(
            f"{board.lower()}_native_source",
            not missing,
            "complete native schematic/board/project set" if not missing else "missing: " + ", ".join(missing),
            f"{board} native source set is incomplete: {', '.join(missing)}",
        )
        check(
            f"{board.lower()}_routing_presence",
            routing_present,
            f"segments={copper['segments']} vias={copper['vias']} zones={copper['zones']}",
            f"{board} routing is absent",
        )

    main_status = read_json("hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json")
    main_review_b = main_status.get("review_b", {})
    main_clearance = (
        main_review_b.get("evidence", {}).get("placement_clearance_control", {})
        if isinstance(main_review_b, dict) else {}
    )
    main_clearance_pass = (
        isinstance(main_clearance, dict)
        and main_clearance.get("state") == "PASS"
        and main_clearance.get("confirmed_component_collisions") == 0
        and main_clearance.get("screening_component_collisions") == 0
        and main_clearance.get("confirmed_mounting_clearance_conflicts") == 0
        and main_clearance.get("screening_mounting_clearance_conflicts") == 0
        and main_clearance.get("confirmed_tool_clearance_conflicts") == 0
        and main_clearance.get("screening_tool_clearance_conflicts") == 0
        and main_clearance.get("locked_authority_component_conflicts") == []
        and main_clearance.get("locked_authority_mounting_conflicts") == []
        and main_clearance.get("locked_authority_tool_conflicts") == []
    )
    check(
        "pcb_main_placement_clearance",
        main_clearance_pass,
        (
            f"state={main_clearance.get('state', 'MISSING')} "
            f"confirmed={main_clearance.get('confirmed_component_collisions', 'MISSING')} "
            f"screening={main_clearance.get('screening_component_collisions', 'MISSING')} "
            f"mounting_confirmed={main_clearance.get('confirmed_mounting_clearance_conflicts', 'MISSING')} "
            f"mounting_screening={main_clearance.get('screening_mounting_clearance_conflicts', 'MISSING')} "
            f"tool_confirmed={main_clearance.get('confirmed_tool_clearance_conflicts', 'MISSING')} "
            f"tool_screening={main_clearance.get('screening_tool_clearance_conflicts', 'MISSING')}"
        ) if isinstance(main_clearance, dict) else "MISSING",
        "PCB-MAIN placement has unresolved courtyard/pad-envelope, mounting-exclusion or U.FL tool/service conflicts",
    )
    main_released = (
        main_status.get("manufacturing_release") is True
        and isinstance(main_review_b, dict)
        and main_review_b.get("complete") is True
        and main_review_b.get("status") == "PASS"
    )
    check(
        "pcb_main_review_b_release",
        main_released,
        str(main_review_b.get("status", "MISSING")) if isinstance(main_review_b, dict) else "MISSING",
        "PCB-MAIN Review B/DRC/CAM/DFM release is not complete",
    )

    pwr_status = read_json("hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json")
    pwr_review_b = pwr_status.get("review_b", {})
    pwr_released = (
        pwr_status.get("manufacturing_release") is True
        and isinstance(pwr_review_b, dict)
        and pwr_review_b.get("complete") is True
        and pwr_review_b.get("status") == "PASS"
    )
    check(
        "pcb_pwr_review_b_release",
        pwr_released,
        str(pwr_review_b.get("status", "MISSING")) if isinstance(pwr_review_b, dict) else "MISSING",
        "PCB-PWR DIM-003/routing/DRC/CAM/DFM Review B release is not complete",
    )

    mic_status = read_json("hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json")
    mic_review_a = mic_status.get("review_a", {})
    mic_review_b = mic_status.get("review_b", {})
    mic_status_ok = (
        mic_status.get("schema_version") == 1
        and mic_status.get("configuration") == "EVT-PRE-20 Rev.A"
        and mic_status.get("assembly") == "PCB-MIC"
    )
    check(
        "pcb_mic_release_status_control",
        mic_status_ok,
        str(mic_status.get("release_state", "MISSING")),
        "PCB-MIC controlled release-status record is missing or invalid",
    )

    mic_metadata = read_json("hardware/kicad/native/PCB-MIC/fabrication_metadata.json")
    expected_mic_authority = "hardware/kicad/REV_A_CAPTURE_ADDENDUM_003_PCB_MIC_MECH.md"
    mic_authority = str(mic_metadata.get("authority", ""))
    mic_authority_ok = mic_authority == expected_mic_authority and (ROOT / mic_authority).is_file()
    check(
        "pcb_mic_mechanical_authority_traceability",
        mic_authority_ok,
        mic_authority or "MISSING",
        "PCB-MIC fabrication metadata does not resolve to the controlled mechanical authority",
    )
    mic_handoff = mic_review_b.get("manufacturing_handoff", {})
    mic_handoff_ready = (
        isinstance(mic_handoff, dict)
        and mic_handoff.get("status") == "PACKET_READY_EXTERNAL_ACCEPTANCE_REQUIRED"
        and mic_handoff.get("internal_packet_complete") is True
        and mic_handoff.get("complete") is False
        and mic_handoff.get("fabricator_dfm_acceptance") is False
        and mic_handoff.get("assembler_dfm_acceptance") is False
        and mic_handoff.get("panelization_acceptance") is False
        and mic_handoff.get("depanel_acceptance") is False
        and mic_handoff.get("assembler_process_keepout_acceptance") is False
    )
    check(
        "pcb_mic_manufacturing_handoff_packet",
        mic_handoff_ready,
        str(mic_handoff.get("status", "MISSING")) if isinstance(mic_handoff, dict) else "MISSING",
        "PCB-MIC controlled manufacturing handoff packet is not ready",
    )
    mic_released = (
        mic_status_ok
        and mic_status.get("manufacturing_release") is True
        and isinstance(mic_review_a, dict)
        and mic_review_a.get("complete") is True
        and mic_review_a.get("status") == "PASS"
        and isinstance(mic_review_b, dict)
        and mic_review_b.get("complete") is True
        and mic_review_b.get("status") == "PASS"
        and mic_metadata.get("status") == "FOR_MANUFACTURE"
    )
    check(
        "pcb_mic_fabrication_release",
        mic_released,
        (
            f"status={mic_status.get('release_state', 'MISSING')}; "
            f"Review A={mic_review_a.get('status', 'MISSING') if isinstance(mic_review_a, dict) else 'MISSING'}; "
            f"Review B={mic_review_b.get('status', 'MISSING') if isinstance(mic_review_b, dict) else 'MISSING'}"
        ),
        "PCB-MIC Review B/CAM/DFM and manufacturing release are not complete",
    )

    dimensions = read_csv("mechanics/common/OPEN_DIMENSIONS.csv")
    open_dimensions = [
        row["ID"]
        for row in dimensions
        if row["Status"] not in {"CLOSED", "CLOSED_AUTHORITY_INPUT"}
    ]
    check(
        "mechanical_dimensions",
        not open_dimensions,
        "all hardware dimensions closed" if not open_dimensions else "open: " + ", ".join(open_dimensions),
        "mechanical release inputs remain open: " + ", ".join(open_dimensions),
    )

    scenarios = read_csv("manufacturing/EVT_LOT_SELECTION_REV_A.csv")
    scenario_quantities = [int(row["Station_Qty"]) for row in scenarios]
    selected = [row for row in scenarios if row["Selection_Status"] == "SELECTED"]
    selection_ok = scenario_quantities == list(LOT_SIZES) and len(selected) == 1
    selected_quantity = int(selected[0]["Station_Qty"]) if selection_ok else None
    check(
        "purchase_lot_selection",
        selection_ok,
        f"selected quantity {selected_quantity}" if selection_ok else "no single selected scenario",
        "purchase quantity is not selected from 4, 10 or 20",
        design=False,
        purchase=True,
    )

    rfq_rows = read_csv("hardware/CHINA_PROCUREMENT_RFQ.csv")
    required_rfq = [row for row in rfq_rows if row["Status"] == "RFQ_REQUIRED"]
    quote_fields = ("Quote_date", "Supplier", "URL", "MOQ", "Lead_time_days", "Stock_claim")
    incomplete_rfq = [
        row["RFQ_ID"]
        for row in required_rfq
        if any(not row[field].strip() for field in quote_fields)
    ]
    check(
        "supplier_rfq_release",
        not incomplete_rfq,
        "all required RFQs contain supplier evidence" if not incomplete_rfq else "incomplete: " + ", ".join(incomplete_rfq),
        "supplier RFQ evidence is incomplete: " + ", ".join(incomplete_rfq),
        design=False,
        purchase=True,
    )

    design_ready = not design_blockers
    purchase_ready = design_ready and not purchase_blockers
    return {
        "schema": "dioneya-hardware-production-release-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "scope": {
            "included": ["BOM", "PCB-MAIN", "PCB-MIC", "PCB-PWR", "mechanics", "harness", "supplier_DFM", "purchase_lot"],
            "excluded": ["application_firmware", "server", "Android"],
            "software_rule": "software is included only when an explicit hardware interface or production-test dependency requires it",
        },
        "hardware_design_release": {
            "ready": design_ready,
            "status": "PASS" if design_ready else "BLOCKED",
            "blockers": design_blockers,
        },
        "purchase_release": {
            "ready": purchase_ready,
            "status": "PASS" if purchase_ready else "BLOCKED",
            "selected_station_quantity": selected_quantity,
            "blockers": purchase_blockers,
        },
        "boards": board_results,
        "bom_qg2": bom_qg2,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="return non-zero until hardware purchase release is ready")
    parser.add_argument("--output", default="artifacts/evt_pre_20_hardware_release_audit.json")
    args = parser.parse_args()

    result = audit()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    design = result["hardware_design_release"]
    purchase = result["purchase_release"]
    print(f"EVT-PRE-20 hardware-only production audit: {purchase['status']}")
    print(f"- hardware design release: {design['status']}")
    for blocker in design["blockers"]:
        print(f"  - {blocker}")
    print(f"- purchase release: {purchase['status']}")
    for blocker in purchase["blockers"]:
        if blocker not in design["blockers"]:
            print(f"  - {blocker}")
    print("- software scope: excluded unless an explicit hardware dependency requires it")
    try:
        display_output = output.relative_to(ROOT)
    except ValueError:
        display_output = output
    print(f"report: {display_output}")
    return 1 if args.strict and not purchase["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
