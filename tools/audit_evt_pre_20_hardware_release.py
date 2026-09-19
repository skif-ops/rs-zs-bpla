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

    customer_procurement_boundary_ok = all(
        token in baseline
        for token in (
            "commercial_procurement_owner: CUSTOMER",
            "supplier_stock_price_moq_and_delivery_gate: NON_BLOCKING_CUSTOMER_ACTION",
            "engineering_procurement_handoff_requires_quote_fields: false",
            "exact_mpn_and_no_substitution_required: true",
            "job_specific_manufacturing_technical_responses_required: true",
        )
    )
    check(
        "customer_commercial_procurement_boundary",
        customer_procurement_boundary_ok,
        (
            "stock, price, MOQ, payment and delivery are non-blocking customer actions; "
            "exact MPN and job-specific technical manufacturing gates remain mandatory"
        ),
        "customer procurement boundary is missing or weakens exact-MPN/technical manufacturing controls",
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

    system_ots_identity = run_json_audit(
        "audit_evt_system_ots_procurement_identity_rev_a.py"
    )
    system_ots_identity_ok = (
        system_ots_identity.get("status")
        == "PASS_DOCUMENTARY_PURCHASE_IDENTITY_PHYSICAL_VALIDATION_DURING_ASSEMBLY_EOL_EVT"
        and system_ots_identity.get("documentary_purchase_identity_complete") is True
        and system_ots_identity.get("controlled_item_count") == 8
        and system_ots_identity.get("standalone_preorder_qualification_unit_required") is False
        and system_ots_identity.get("receiving_hold_required") is False
        and system_ots_identity.get("physical_qualification_complete") is False
        and system_ots_identity.get("manufacturing_release") is False
    )
    check(
        "system_ots_documentary_procurement_identity",
        system_ots_identity_ok,
        str(system_ots_identity.get("status", "MISSING")),
        "exact system OTS documentary purchase identity is incomplete or inconsistent",
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

    main_status = read_json("hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json")
    main_hierarchy = run_json_audit("audit_pcb_main_hierarchy_rev_a.py")
    main_hierarchy_internal_ok = (
        main_hierarchy.get("status") ==
        "PASS_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE"
        and main_hierarchy.get("pages") == 10
        and main_hierarchy.get("root_sheets") == 9
        and main_hierarchy.get("symbols") == 248
        and main_hierarchy.get("physical_symbols") == 247
        and main_hierarchy.get("logical_pad_numbers") == 1066
        and main_hierarchy.get("physical_pad_occurrences") == 1077
        and main_hierarchy.get("repeated_logical_pad_numbers") == 7
        and main_hierarchy.get("duplicate_pad_occurrences") == 11
        and main_hierarchy.get("wire_segments") == 1073
        and main_hierarchy.get("connected_pin_wires") == 905
        and main_hierarchy.get("explicit_nc") == 169
        and main_hierarchy.get("cross_sheet_nets") == 75
        and main_hierarchy.get("hierarchical_labels") == 168
        and main_hierarchy.get("pin_net_semantic_sha256") ==
        "d320bdd98712a65f9736bd520a8f9197d4f53fedb4be3b798086810e7a8f4bf6"
        and main_hierarchy.get("routing_authorized") is False
        and main_hierarchy.get("manufacturing_release") is False
    )
    check(
        "pcb_main_human_readable_hierarchy_internal_equivalence",
        main_hierarchy_internal_ok,
        str(main_hierarchy.get("status", "MISSING")),
        "PCB-MAIN ten-page hierarchy or exact 247-position/1077-physical-pad net equivalence has regressed",
    )
    main_hierarchy_record = main_status.get("human_readable_hierarchy", {})
    main_hierarchy_control = (
        main_hierarchy_record.get("control", {})
        if isinstance(main_hierarchy_record, dict)
        else {}
    )
    main_hierarchy_native_evidence_complete = (
        main_hierarchy_internal_ok
        and isinstance(main_hierarchy_control, dict)
        and main_hierarchy_control.get("native_kicad_9_erc_pass") is True
        and main_hierarchy_control.get("committed_erc_evidence") is True
        and main_hierarchy_control.get("committed_pdf_evidence") is True
    )
    check(
        "pcb_main_hierarchy_native_erc_pdf_evidence",
        main_hierarchy_native_evidence_complete,
        "commit-bound KiCad 9 ERC/PDF evidence PASS"
        if main_hierarchy_native_evidence_complete else
        "commit-bound KiCad 9 ERC/PDF evidence PENDING",
        "PCB-MAIN hierarchy still requires commit-bound KiCad 9 ERC/PDF evidence",
    )
    main_hierarchy_human_review_complete = (
        main_hierarchy_native_evidence_complete
        and main_hierarchy_control.get("independent_human_review_complete") is True
    )
    check(
        "pcb_main_hierarchy_independent_human_review",
        main_hierarchy_human_review_complete,
        "independent human hierarchy review PASS"
        if main_hierarchy_human_review_complete else
        "independent human hierarchy review PENDING",
        "PCB-MAIN hierarchy independent human acceptance remains open",
    )

    pwr_status = read_json("hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json")
    pwr_design = run_json_audit("audit_pcb_pwr_design_rev_a.py")
    pwr_ti_primary_check = next(
        (
            item
            for item in pwr_design.get("checks", [])
            if item.get("check") == "ti_primary_source_binding"
        ),
        {},
    )
    pwr_ti_status = pwr_status.get("ti_primary_source_evidence", {})
    pwr_ti_control = (
        pwr_ti_status.get("control", {})
        if isinstance(pwr_ti_status, dict)
        else {}
    )
    pwr_ti_primary_ok = (
        pwr_ti_primary_check.get("status") == "PASS"
        and pwr_ti_primary_check.get("exact_orderable") == "LMR604403SRAKR"
        and pwr_ti_primary_check.get("orderable_status") == "Active Production"
        and pwr_ti_primary_check.get("modes") == {
            "U3": "ADJUSTABLE_3V801",
            "U4": "FIXED_3V3",
        }
        and pwr_ti_primary_check.get("vcap_f") == 1e-7
        and pwr_ti_primary_check.get("schematic_changed") is False
        and pwr_ti_primary_check.get("manufacturing_release") is False
        and pwr_ti_control.get("state")
        == "PASS_TI_PRIMARY_SOURCE_BINDING_SCHEMATIC_UNCHANGED"
        and pwr_ti_control.get("electrical_schematic_changed") is False
        and pwr_ti_control.get("independent_human_hierarchy_acceptance_complete") is True
        and pwr_ti_control.get("routing_authorized") is False
        and pwr_ti_control.get("manufacturing_release") is False
    )
    check(
        "pcb_pwr_ti_primary_source_binding",
        pwr_ti_primary_ok,
        "LMR604403SRAKR U3 adjustable/U4 fixed and LM74700 VCAP primary evidence PASS",
        "PCB-PWR TI primary-source orderable/mode/VCAP binding is missing or inconsistent",
    )
    pwr_hierarchy = run_json_audit("audit_pcb_pwr_hierarchy_rev_a.py")
    pwr_hierarchy_internal_ok = (
        pwr_hierarchy.get("status") ==
        "PASS_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE"
        and pwr_hierarchy.get("pages") == 5
        and pwr_hierarchy.get("root_sheets") == 4
        and pwr_hierarchy.get("symbols") == 65
        and pwr_hierarchy.get("physical_symbols") == 62
        and pwr_hierarchy.get("wire_segments") == 189
        and pwr_hierarchy.get("cross_sheet_nets") == 9
        and pwr_hierarchy.get("hierarchical_labels") == 26
        and pwr_hierarchy.get("pin_net_semantic_sha256") ==
        "84a35aa607bac3ee65b5d8f60684e958277b2fa5a7ed01f810af32f0b52b73f7"
        and pwr_hierarchy.get("pin_net_review_a") ==
        "RETAINED_BY_EXACT_ELECTRICAL_EQUIVALENCE"
        and pwr_hierarchy.get("manufacturing_release") is False
    )
    check(
        "pcb_pwr_human_readable_hierarchy_internal_equivalence",
        pwr_hierarchy_internal_ok,
        str(pwr_hierarchy.get("status", "MISSING")),
        "PCB-PWR five-page hierarchy or exact 62-position pad/net equivalence has regressed",
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

    pwr_input_protection = run_json_audit(
        "audit_pcb_pwr_input_protection_rev_a.py"
    )
    pwr_input_protection_packet_ready = (
        pwr_input_protection.get("status") ==
        "PASS_CONTROLLED_QUALIFICATION_PLAN_PHYSICAL_EVIDENCE_PENDING"
        and pwr_input_protection.get("fuse", {}).get("signed_native_mpn") ==
        "0451005.MRL"
        and pwr_input_protection.get("fuse", {}).get("target_evt_mpn") ==
        "0451008.MRL"
        and pwr_input_protection.get("required_rows") == 20
        and pwr_input_protection.get("accepted_rows") == 4
        and pwr_input_protection.get("physical_qualification_complete") is False
        and pwr_input_protection.get("pcba_procurement_authorized") is False
        and pwr_input_protection.get("manufacturing_release") is False
    )
    check(
        "pcb_pwr_input_protection_qualification_packet",
        pwr_input_protection_packet_ready,
        str(pwr_input_protection.get("status", "MISSING")),
        "PCB-PWR fuse/TVS input-protection qualification packet is incomplete or inconsistent",
    )
    accepted_input_protection_rows = int(
        pwr_input_protection.get("accepted_rows", 0) or 0
    )
    required_input_protection_rows = int(
        pwr_input_protection.get("required_rows", 20) or 20
    )
    pwr_input_protection_qualified = (
        pwr_input_protection.get("status") == "PASS_QUALIFIED_FOR_RELEASE"
        and pwr_input_protection.get("native_value_eco_applied") is True
        and accepted_input_protection_rows == required_input_protection_rows
        and pwr_input_protection.get("physical_qualification_complete") is True
    )
    check(
        "pcb_pwr_input_protection_release",
        pwr_input_protection_qualified,
        (
            f"native ECO={pwr_input_protection.get('native_value_eco_applied', False)}; "
            f"qualification={accepted_input_protection_rows}/"
            f"{required_input_protection_rows} PASS"
        ),
        (
            "PCB-PWR input-protection release remains open: "
            f"native value ECO={pwr_input_protection.get('native_value_eco_applied', False)}; "
            f"qualification evidence={accepted_input_protection_rows}/"
            f"{required_input_protection_rows} PASS"
        ),
    )

    pwr_clearance = run_json_audit("audit_pcb_pwr_placement_clearance_rev_a.py")
    pwr_clearance_summary = pwr_clearance.get("summary", {})
    pwr_clearance_controlled = (
        isinstance(pwr_clearance_summary, dict)
        and pwr_clearance_summary.get("state") ==
        "PASS_FITTED_2D_PLACEMENT_CLEARANCE_DIM_003_OPEN"
        and pwr_clearance_summary.get("fitted_footprints") == 44
        and pwr_clearance_summary.get("courtyard_footprints") == 44
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
        and harness.get("supplier_request_status") ==
        "PACKET_READY_16_ATTRIBUTABLE_RESPONSES_REQUIRED_FINAL_LENGTHS_OPEN_NOT_FOR_BUILD"
        and isinstance(harness.get("supplier_request"), dict)
        and harness["supplier_request"].get("required_response_rows") == 16
        and harness["supplier_request"].get("accepted_response_rows") == 0
        and harness["supplier_request"].get("selected_supplier") is None
        and harness["supplier_request"].get("build_authorized") is False
    )
    check(
        "harness_controlled_preliminary_packet",
        harness_packet_ok,
        (
            f"{harness.get('status', 'MISSING')}; "
            f"supplier responses="
            f"{harness.get('supplier_request', {}).get('accepted_response_rows', 'MISSING')}/16"
        ),
        "internal harness drawing schedule or supplier capability request packet is incomplete",
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
    main_routing_basis_evidence = (
        main_evidence.get("routing_design_basis", {})
        if isinstance(main_evidence, dict) else {}
    )
    main_routing_basis = run_json_audit(
        "audit_pcb_main_jlc06161h_3313_routing_basis_rev_a.py"
    )
    main_routing_basis_ok = (
        isinstance(main_routing_basis_evidence, dict)
        and main_routing_basis_evidence.get("status") ==
        "PASS_PUBLIC_STANDARD_NUMERIC_ROUTING_INPUT_FINAL_FABRICATOR_ACCEPTANCE_PENDING"
        and main_routing_basis_evidence.get("public_stackup_id") == "JLC06161H-3313"
        and main_routing_basis_evidence.get("rf_50ohm_trace_width_mm") == 0.1509
        and main_routing_basis_evidence.get("usb_90ohm_trace_width_mm") == 0.1537
        and main_routing_basis_evidence.get("usb_90ohm_pair_gap_mm") == 0.2032
        and main_routing_basis_evidence.get("engineering_candidate_numeric_input_authorized") is True
        and main_routing_basis_evidence.get("pair_aware_routing_and_audit_required") is True
        and main_routing_basis_evidence.get("final_job_stackup_accepted") is False
        and main_routing_basis_evidence.get("manufacturing_release") is False
        and main_routing_basis.get("status") ==
        "PASS_PUBLIC_STANDARD_NUMERIC_ROUTING_INPUT_FINAL_FABRICATOR_ACCEPTANCE_PENDING"
        and main_routing_basis.get("stackup_id") == "JLC06161H-3313"
        and main_routing_basis.get("rf_50ohm_trace_width_mm") == 0.1509
        and main_routing_basis.get("usb_90ohm_trace_width_mm") == 0.1537
        and main_routing_basis.get("usb_90ohm_pair_gap_mm") == 0.2032
        and main_routing_basis.get("pending_fabricator_response_rows") == 22
        and main_routing_basis.get("manufacturing_release") is False
    )
    check(
        "pcb_main_public_numeric_routing_basis",
        main_routing_basis_ok,
        (
            "JLC06161H-3313 candidate RF=0.1509 mm USB=0.1537/0.2032 mm; "
            "22 final fabricator response rows remain pending"
        ),
        "PCB-MAIN public numeric routing basis is missing, drifted or improperly promoted",
    )
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
        "customer_commercial_rfq_fields",
        True,
        (
            "customer-owned quote/stock fields populated for all sourcing rows"
            if not incomplete_rfq
            else f"non-blocking customer fields remain blank in {len(incomplete_rfq)} sourcing rows"
        ),
        "commercial RFQ fields are advisory and must never become an engineering blocker",
        design=False,
        purchase=False,
    )

    design_ready = not design_blockers
    purchase_ready = design_ready and not purchase_blockers
    return {
        "schema": "dioneya-hardware-production-release-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "scope": {
            "included": ["BOM", "PCB-MAIN", "PCB-MIC", "PCB-PWR", "mechanics", "harness", "supplier_DFM", "purchase_lot"],
            "excluded": [
                "application_firmware",
                "server",
                "Android",
                "customer_supplier_selection",
                "supplier_stock",
                "commercial_price",
                "MOQ",
                "payment_terms",
                "freight",
                "destination_delivery",
            ],
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
            "meaning": "engineering handoff for customer-owned procurement; not an executed purchase order",
            "owner": "CUSTOMER",
            "commercial_quote_or_availability_required": False,
            "job_specific_technical_manufacturing_responses_required": True,
            "selected_station_quantity": selected_quantity,
            "blockers": purchase_blockers,
        },
        "boards": board_results,
        "bom_qg2": bom_qg2,
        "system_ots_procurement_identity": system_ots_identity,
        "pcb_layer_count_authority": layer_authority,
        "pcb_main_hierarchy": main_hierarchy,
        "pcb_main_public_numeric_routing_basis": main_routing_basis,
        "pcb_pwr_hierarchy": pwr_hierarchy,
        "pcb_pwr_input_protection": pwr_input_protection,
        "pcb_pwr_dim_003": pwr_dim_003,
        "pcb_pwr_stackup_copper": pwr_stackup_copper,
        "harness": harness,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero until the hardware design and customer procurement handoff are ready",
    )
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
    print(f"- customer procurement handoff: {purchase['status']}")
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
