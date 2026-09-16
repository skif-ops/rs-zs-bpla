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


def run_json_audit(script_name: str) -> dict[str, object]:
    """Run an internal hardware audit without leaving generated files in the tree."""
    with tempfile.TemporaryDirectory(prefix="evt-pre-20-hw-subgate-") as temp_dir:
        output = Path(temp_dir) / "audit.json"
        process = subprocess.run(
            [
                sys.executable,
                str(ROOT / f"tools/{script_name}"),
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
                "error": process.stderr.strip() or process.stdout.strip() or f"exit {process.returncode}",
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

    layer_authority = run_json_audit("audit_pcb_layer_count_authority_rev_a.py")
    layer_authority_ok = (
        layer_authority.get("status") == "PASS_CONTROLLED_LAYER_COUNTS_FINAL_STACKUPS_OPEN"
        and layer_authority.get("manufacturing_release") is False
        and layer_authority.get("controlled_counts") == {
            "PCB-MAIN": 6,
            "PCB-PWR": 4,
            "PCB-MIC": 2,
        }
    )
    check(
        "pcb_layer_count_authority",
        layer_authority_ok,
        str(layer_authority.get("status", "MISSING")),
        "PCB layer counts are inconsistent across native boards, BOM/RFQ or controlled authorities",
    )

    pwr_status = read_json("hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json")
    pwr_hierarchy = run_json_audit("audit_pcb_pwr_hierarchy_rev_a.py")
    pwr_hierarchy_internal_ok = (
        pwr_hierarchy.get("status") ==
        "PASS_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE"
        and pwr_hierarchy.get("pages") == 5
        and pwr_hierarchy.get("root_sheets") == 4
        and pwr_hierarchy.get("symbols") == 63
        and pwr_hierarchy.get("physical_symbols") == 60
        and pwr_hierarchy.get("wire_segments") == 185
        and pwr_hierarchy.get("cross_sheet_nets") == 9
        and pwr_hierarchy.get("hierarchical_labels") == 26
        and pwr_hierarchy.get("pin_net_semantic_sha256") ==
        "fb31a1880037c2d15873ef7a003b74967e0427ed767bc16de256a790b5320b5a"
        and pwr_hierarchy.get("pin_net_review_a") ==
        "RETAINED_BY_EXACT_ELECTRICAL_EQUIVALENCE"
        and pwr_hierarchy.get("manufacturing_release") is False
    )
    check(
        "pcb_pwr_human_readable_hierarchy_internal_equivalence",
        pwr_hierarchy_internal_ok,
        str(pwr_hierarchy.get("status", "MISSING")),
        "PCB-PWR five-page hierarchy or exact 60-position pad/net equivalence has regressed",
    )

    pwr_hierarchy_record = pwr_status.get("human_readable_hierarchy", {})
    pwr_hierarchy_control = (
        pwr_hierarchy_record.get("control", {})
        if isinstance(pwr_hierarchy_record, dict)
        else {}
    )
    pwr_hierarchy_native_evidence_complete = (
        pwr_hierarchy_internal_ok
        and isinstance(pwr_hierarchy_control, dict)
        and pwr_hierarchy_control.get("native_kicad_9_erc_pass") is True
        and pwr_hierarchy_control.get("committed_erc_evidence") is True
        and pwr_hierarchy_control.get("committed_pdf_evidence") is True
    )
    check(
        "pcb_pwr_hierarchy_native_erc_pdf_evidence",
        pwr_hierarchy_native_evidence_complete,
        "commit-bound KiCad 9 ERC/PDF evidence PASS",
        "PCB-PWR hierarchy still requires commit-bound KiCad 9 ERC/PDF evidence",
    )
    pwr_hierarchy_human_review_complete = (
        pwr_hierarchy_native_evidence_complete
        and pwr_hierarchy_control.get("independent_human_review_complete") is True
    )
    check(
        "pcb_pwr_hierarchy_independent_human_review",
        pwr_hierarchy_human_review_complete,
        "independent human hierarchy review PASS",
        "PCB-PWR hierarchy independent human acceptance remains open",
    )

    pwr_clearance = run_json_audit("audit_pcb_pwr_placement_clearance_rev_a.py")
    pwr_clearance_summary = pwr_clearance.get("summary", {})
    pwr_clearance_controlled = (
        isinstance(pwr_clearance_summary, dict)
        and pwr_clearance_summary.get("state") ==
        "PASS_FITTED_2D_PLACEMENT_CLEARANCE_DIM_003_OPEN"
        and pwr_clearance_summary.get("fitted_footprints") == 42
        and pwr_clearance_summary.get("courtyard_footprints") == 42
        and pwr_clearance_summary.get("required_clearance_mm") == 0.2
        and pwr_clearance_summary.get("minimum_observed_clearance_mm", 0) >= 0.2
        and pwr_clearance_summary.get("clearance_conflicts") == 0
        and pwr_clearance.get("board", {}).get("trace_items") == 0
        and pwr_clearance.get("board", {}).get("copper_zones") == 0
        and pwr_clearance.get("manufacturing_release") is False
    )
    check(
        "pcb_pwr_fitted_2d_placement_clearance",
        pwr_clearance_controlled,
        str(pwr_clearance_summary.get("state", "MISSING")),
        "PCB-PWR fitted-component 2D placement clearance has regressed",
    )

    pwr_routing_authority = run_json_audit("audit_pcb_pwr_routing_authority_rev_a.py")
    pwr_routing_controlled = (
        pwr_routing_authority.get("status") ==
        "PASS_PRE_ROUTE_CONSTRAINT_COVERAGE_ROUTING_OPEN"
        and pwr_routing_authority.get("authority", {}).get("row_count") == 31
        and pwr_routing_authority.get("board", {}).get("net_count") == 31
        and pwr_routing_authority.get("board", {}).get("trace_items") == 0
        and pwr_routing_authority.get("board", {}).get("copper_zones") == 0
        and pwr_routing_authority.get("dim_003") ==
        "CONTROLLED_REQUEST_READY_0_OF_18_ACCEPTED_REQUIRED_BEFORE_ROUTING"
        and pwr_routing_authority.get("routing_complete") is False
        and pwr_routing_authority.get("manufacturing_release") is False
    )
    check(
        "pcb_pwr_pre_route_constraint_coverage",
        pwr_routing_controlled,
        str(pwr_routing_authority.get("status", "MISSING")),
        "PCB-PWR pre-route constraint authority is incomplete or its no-routing interlock drifted",
    )

    pwr_dim_003 = run_json_audit("audit_pcb_pwr_dim_003_request_rev_a.py")
    pwr_dim_003_packet_ready = (
        pwr_dim_003.get("status") ==
        "PASS_INTERNAL_DIM_003_REQUEST_READY_EXTERNAL_RESPONSE_PENDING"
        and pwr_dim_003.get("internal_packet_complete") is True
        and pwr_dim_003.get("required_response_rows") == 18
        and pwr_dim_003.get("accepted_response_rows") == 0
        and pwr_dim_003.get("routing_authorized") is False
        and pwr_dim_003.get("harness_length_release_authorized") is False
        and pwr_dim_003.get("manufacturing_release") is False
    )
    check(
        "pcb_pwr_dim_003_request_packet",
        pwr_dim_003_packet_ready,
        str(pwr_dim_003.get("status", "MISSING")),
        "PCB-PWR controlled DIM-003 mechanical-freeze request packet is not ready",
    )
    accepted_response_rows = int(pwr_dim_003.get("accepted_response_rows", 0) or 0)
    pwr_dim_003_accepted = (
        pwr_dim_003.get("dim_003_accepted") is True
        and accepted_response_rows == 18
        and pwr_dim_003.get("routing_authorized") is True
        and pwr_dim_003.get("harness_length_release_authorized") is True
    )
    check(
        "pcb_pwr_dim_003_acceptance",
        pwr_dim_003_accepted,
        f"{accepted_response_rows}/18 responses accepted",
        (
            "PCB-PWR DIM-003 mechanical acceptance remains open: "
            f"{accepted_response_rows}/18 attributable responses accepted"
        ),
    )

    pwr_stackup_copper = run_json_audit(
        "audit_pcb_pwr_stackup_copper_request_rev_a.py"
    )
    pwr_stackup_packet_ready = (
        pwr_stackup_copper.get("status") ==
        "PASS_INTERNAL_STACKUP_COPPER_REQUEST_READY_EXTERNAL_RESPONSES_PENDING"
        and pwr_stackup_copper.get("internal_packet_complete") is True
        and pwr_stackup_copper.get("required_fabricator_slots") == ["FAB-A", "FAB-B"]
        and pwr_stackup_copper.get("required_response_rows") == 24
        and pwr_stackup_copper.get("accepted_fabricator_slots") == 0
        and pwr_stackup_copper.get("accepted_response_rows") == 0
        and pwr_stackup_copper.get("numeric_power_geometry_authorized") is False
        and pwr_stackup_copper.get("routing_authorized") is False
        and pwr_stackup_copper.get("manufacturing_release") is False
    )
    check(
        "pcb_pwr_stackup_copper_request_packet",
        pwr_stackup_packet_ready,
        str(pwr_stackup_copper.get("status", "MISSING")),
        "PCB-PWR controlled two-fabricator stackup/copper request packet is not ready",
    )
    accepted_fabricator_slots = int(
        pwr_stackup_copper.get("accepted_fabricator_slots", 0) or 0
    )
    accepted_stackup_rows = int(
        pwr_stackup_copper.get("accepted_response_rows", 0) or 0
    )
    selected_pwr_fabricator = pwr_stackup_copper.get("selected_fabricator_slot")
    pwr_stackup_accepted = (
        pwr_stackup_copper.get("complete") is True
        and accepted_fabricator_slots == 2
        and accepted_stackup_rows == 24
        and selected_pwr_fabricator in {"FAB-A", "FAB-B"}
        and pwr_stackup_copper.get("stackup_accepted") is True
        and pwr_stackup_copper.get("copper_weights_and_plating_accepted") is True
        and pwr_stackup_copper.get("numeric_power_geometry_authorized") is True
    )
    check(
        "pcb_pwr_stackup_copper_acceptance",
        pwr_stackup_accepted,
        (
            f"accepted_rows={accepted_stackup_rows}/24 "
            f"fabricators={accepted_fabricator_slots}/2 "
            f"selected={selected_pwr_fabricator or 'NONE'}"
        ),
        (
            "PCB-PWR stackup/copper acceptance remains open: "
            f"{accepted_stackup_rows}/24 responses and "
            f"{accepted_fabricator_slots}/2 fabricator sets accepted; "
            f"selected construction={selected_pwr_fabricator or 'NONE'}"
        ),
    )

    harness = run_json_audit("audit_harness_manufacturing_rev_a.py")
    harness_packet_ok = (
        harness.get("status") == "PASS_CONTROLLED_PRELIMINARY_LENGTHS_OPEN"
        and harness.get("packet_complete") is True
        and harness.get("controlled_conductors") == 38
    )
    check(
        "harness_controlled_preliminary_packet",
        harness_packet_ok,
        str(harness.get("status", "MISSING")),
        "internal harness drawing and point-to-point manufacturing schedule are incomplete",
    )
    harness_released = harness.get("manufacturing_release") is True
    harness_blockers = [str(item) for item in harness.get("open_blockers", [])]
    check(
        "harness_manufacturing_release",
        harness_released,
        (
            "physical harness release PASS"
            if harness_released
            else f"controlled preliminary; {len(harness_blockers)} release blockers"
        ),
        "harness manufacturing release remains open: " + " | ".join(harness_blockers),
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
    main_evidence = main_review_b.get("evidence", {}) if isinstance(main_review_b, dict) else {}
    main_stackup = (
        main_evidence.get("stackup_impedance_handoff", {})
        if isinstance(main_evidence, dict) else {}
    )
    main_stackup_files = [
        main_stackup.get("packet"),
        main_stackup.get("machine_contract"),
        main_stackup.get("response_register"),
    ] if isinstance(main_stackup, dict) else []
    main_stackup_packet_ready = (
        isinstance(main_stackup, dict)
        and main_stackup.get("internal_packet_complete") is True
        and main_stackup.get("required_fabricator_slots") == ["FAB-A", "FAB-B"]
        and all(isinstance(path, str) and (ROOT / path).is_file()
                for path in main_stackup_files)
    )
    check(
        "pcb_main_stackup_impedance_request_packet",
        main_stackup_packet_ready,
        str(main_stackup.get("status", "MISSING")) if isinstance(main_stackup, dict) else "MISSING",
        "PCB-MAIN controlled two-fabricator stackup/impedance request packet is not ready",
    )
    accepted_fabricator_count = (
        main_stackup.get("accepted_fabricator_response_count", 0)
        if isinstance(main_stackup, dict) else 0
    )
    selected_fabricator = (
        main_stackup.get("selected_fabricator_slot")
        if isinstance(main_stackup, dict) else None
    )
    main_stackup_accepted = (
        isinstance(main_stackup, dict)
        and main_stackup.get("complete") is True
        and accepted_fabricator_count == 2
        and selected_fabricator in {"FAB-A", "FAB-B"}
        and main_stackup.get("stackup_accepted") is True
        and main_stackup.get("rf_50ohm_numeric_geometry_accepted") is True
        and main_stackup.get("usb_90ohm_numeric_geometry_accepted") is True
    )
    check(
        "pcb_main_stackup_impedance_acceptance",
        main_stackup_accepted,
        f"accepted={accepted_fabricator_count}/2 selected={selected_fabricator or 'NONE'}",
        (
            "PCB-MAIN stackup/impedance acceptance remains open: "
            f"{accepted_fabricator_count}/2 fabricator responses accepted and "
            f"selected construction={selected_fabricator or 'NONE'}"
        ),
    )
    main_assembler = (
        main_evidence.get("assembler_dfm_stencil_handoff", {})
        if isinstance(main_evidence, dict) else {}
    )
    main_assembler_files = [
        main_assembler.get("packet"),
        main_assembler.get("machine_contract"),
        main_assembler.get("response_register"),
    ] if isinstance(main_assembler, dict) else []
    main_assembler_response_path = (
        ROOT / main_assembler_files[2]
        if len(main_assembler_files) == 3
        and isinstance(main_assembler_files[2], str)
        else None
    )
    main_assembler_rows = (
        read_csv(main_assembler_files[2])
        if main_assembler_response_path is not None
        and main_assembler_response_path.is_file()
        else []
    )
    main_assembler_packet_ready = (
        isinstance(main_assembler, dict)
        and main_assembler.get("internal_packet_complete") is True
        and main_assembler.get("required_scope_references") ==
        ["U2", "U25", "U26", "U9"]
        and main_assembler.get("required_response_rows") == 14
        and all(isinstance(path, str) and (ROOT / path).is_file()
                for path in main_assembler_files)
        and len(main_assembler_rows) == 14
        and all(row.get("Gate_ID", "").startswith("ASM-MAIN-")
                and row.get("Blocking") == "YES"
                for row in main_assembler_rows)
    )
    check(
        "pcb_main_assembler_dfm_stencil_request_packet",
        main_assembler_packet_ready,
        str(main_assembler.get("status", "MISSING"))
        if isinstance(main_assembler, dict) else "MISSING",
        "PCB-MAIN bounded assembler DFM/stencil request packet is not ready",
    )
    accepted_response_rows = (
        main_assembler.get("accepted_response_rows", 0)
        if isinstance(main_assembler, dict) else 0
    )
    selected_assembler = (
        main_assembler.get("selected_assembler_legal_entity")
        if isinstance(main_assembler, dict) else None
    )
    selected_site = (
        main_assembler.get("selected_manufacturing_site")
        if isinstance(main_assembler, dict) else None
    )
    main_assembler_accepted = (
        isinstance(main_assembler, dict)
        and main_assembler.get("complete") is True
        and accepted_response_rows == 14
        and isinstance(selected_assembler, str) and bool(selected_assembler.strip())
        and isinstance(selected_site, str) and bool(selected_site.strip())
        and all(main_assembler.get(key) is True for key in (
            "u2_land_mask_stencil_accepted",
            "u25_u26_land_mask_stencil_accepted",
            "u9_stencil_reflow_inspection_accepted",
            "pnp_polarity_accepted",
            "first_article_plan_accepted",
            "blocker_critical_dfm_closed",
        ))
    )
    check(
        "pcb_main_assembler_dfm_stencil_acceptance",
        main_assembler_accepted,
        (
            f"accepted={accepted_response_rows}/14 "
            f"assembler={selected_assembler or 'NONE'} "
            f"site={selected_site or 'NONE'}"
        ),
        (
            "PCB-MAIN assembler DFM/stencil acceptance remains open: "
            f"{accepted_response_rows}/14 responses accepted and selected "
            f"assembler={selected_assembler or 'NONE'} site={selected_site or 'NONE'}"
        ),
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
        "pcb_layer_count_authority": layer_authority,
        "pcb_pwr_hierarchy": pwr_hierarchy,
        "pcb_pwr_dim_003": pwr_dim_003,
        "pcb_pwr_stackup_copper": pwr_stackup_copper,
        "harness": harness,
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
