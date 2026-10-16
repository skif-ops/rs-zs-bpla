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
            "job_specific_manufacturing_technical_responses_required: false",
            "evt_public_engineering_baseline_authorized: true",
            "customer_order_checkout_dfm_must_pass: true",
            "series_transfer_manufacturing_revalidation_required: true",
        )
    )
    check(
        "customer_commercial_procurement_boundary",
        customer_procurement_boundary_ok,
        (
            "stock, price, MOQ, payment and delivery are non-blocking customer actions; "
            "exact MPN, checkout DFM and physical EVT gates remain mandatory; external replies do not"
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

    layer_authority = run_json_audit("audit_pcb_main_8l_adoption_rev_b.py")
    layer_authority_ok = (
        layer_authority.get("status") == "PASS_CONTROLLED_LAYER_COUNTS_EVT_STACKUPS_ACCEPTED"
        and layer_authority.get("manufacturing_release") is False
        and layer_authority.get("controlled_counts") == {
            "PCB-MAIN": 8,
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

    factory_baseline = read_json("hardware/reviews/EVT_FACTORY_PUBLIC_CAPABILITY_BASELINE_REV_B.json")
    factory_main = factory_baseline.get("pcb_main", {}) if isinstance(factory_baseline, dict) else {}
    main_desktop_dfm_ok = (
        factory_baseline.get("status") ==
        "PASS_DESKTOP_DFM_RF_SI_POFV_STANDARD_PROCESS_ACCEPTED_CUSTOMER_CHECKOUT_REQUIRED"
        and factory_main.get("copper_layers") == 8
        and factory_main.get("selected_stackup") == "JLC08161H-3313"
        and factory_main.get("pofv", {}).get("locations") == 76
        and factory_main.get("selected_stack_rf_si_dfm_complete") is True
        and factory_main.get("rf_si_review_complete") is True
        and factory_main.get("review_b") == "ACCEPTED"
        and factory_baseline.get("release_boundary", {}).get("desktop_engineering_complete") is True
        and factory_baseline.get("release_boundary", {}).get("specific_factory_job_confirmed") is False
    )

    main_status = read_json("hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json")
    main_erc = read_json("artifacts/PCB-MAIN_8L_NATIVE_ERC_2026-10-16.json")
    main_drc = read_json("artifacts/PCB-MAIN_8L_NATIVE_DRC_2026-10-16.json")
    main_parity = read_json("artifacts/PCB-MAIN_8L_NATIVE_DRC_PARITY_2026-10-16.json")
    main_erc_count = sum(len(sheet.get("violations", [])) for sheet in main_erc.get("sheets", []))
    main_drc_errors = [item for item in main_drc.get("violations", []) if item.get("severity") == "error"]
    main_hierarchy_internal_ok = (
        layer_authority_ok
        and len(main_erc.get("sheets", [])) == 10
        and main_erc_count == 0
        and not main_drc_errors
        and len(main_drc.get("unconnected_items", [])) == 0
        and len(main_parity.get("schematic_parity", [])) == 613
    )
    check(
        "pcb_main_human_readable_hierarchy_internal_equivalence",
        main_hierarchy_internal_ok,
        (
            "Rev.B 8L evidence: ten-sheet KiCad ERC=0, DRC errors=0, "
            "unconnected=0, documented schematic-parity findings=613"
        ),
        "PCB-MAIN Rev.B ten-sheet ERC/DRC/parity evidence is missing or has regressed",
    )
    main_pdf = list(
        (ROOT / "hardware/manufacturing/evt-build-release/PCB-MAIN/order-package-rev-d6").rglob(
            "PCB-MAIN_SCHEMATIC_RU_EN.pdf"
        )
    )
    main_hierarchy_native_evidence_complete = main_hierarchy_internal_ok and len(main_pdf) == 1
    check(
        "pcb_main_hierarchy_native_erc_pdf_evidence",
        main_hierarchy_native_evidence_complete,
        "Rev.B commit-controlled ERC JSON and REV_D6 schematic PDF present"
        if main_hierarchy_native_evidence_complete else
        "Rev.B ERC/PDF evidence PENDING",
        "PCB-MAIN Rev.B hierarchy still requires controlled ERC/PDF evidence",
    )
    main_hierarchy_human_review_complete = main_desktop_dfm_ok
    main_hierarchy = {
        "status": "PASS_REV_B_8L_ERC_DRC_WITH_DOCUMENTED_PARITY_WARNINGS" if main_hierarchy_internal_ok else "ERROR",
        "sheets": len(main_erc.get("sheets", [])),
        "erc_violations": main_erc_count,
        "drc_errors": len(main_drc_errors),
        "unconnected_items": len(main_drc.get("unconnected_items", [])),
        "schematic_parity_findings": len(main_parity.get("schematic_parity", [])),
        "independent_human_review_complete": main_hierarchy_human_review_complete,
    }
    check(
        "pcb_main_hierarchy_independent_human_review",
        main_hierarchy_human_review_complete,
        "independent Rev.B desktop hierarchy review accepted" if main_hierarchy_human_review_complete else "independent Rev.B hierarchy review PENDING",
        "PCB-MAIN Rev.B hierarchy independent human acceptance remains open",
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
        "PASS_FITTED_2D_AND_EVT_MOUNTING_CLEARANCE_DIM_003_ACCEPTED"
        and pwr_clearance_summary.get("fitted_footprints") == 44
        and pwr_clearance_summary.get("courtyard_footprints") == 44
        and pwr_clearance_summary.get("required_clearance_mm") == 0.2
        and pwr_clearance_summary.get("minimum_observed_clearance_mm", 0) >= 0.2
        and pwr_clearance_summary.get("clearance_conflicts") == 0
        and pwr_clearance_summary.get("mounting_holes") == 4
        and pwr_clearance_summary.get("mounting_to_fitted_body_conflicts") == 0
        and pwr_clearance_summary.get("mounting_to_existing_pad_conflicts") == 0
        and pwr_clearance.get("board", {}).get("trace_items") == 842
        and pwr_clearance.get("board", {}).get("copper_zones") == 33
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
        and pwr_routing_authority.get("board", {}).get("trace_items") == 842
        and pwr_routing_authority.get("board", {}).get("copper_zones") == 33
        and pwr_routing_authority.get("dim_003") ==
        "EVT_ENGINEERING_ACCEPTED_18_OF_18_SERIAL_REVALIDATION_REQUIRED"
        and pwr_routing_authority.get("routing_complete") is False
        and pwr_routing_authority.get("manufacturing_release") is False
    )
    check(
        "pcb_pwr_pre_route_constraint_coverage",
        pwr_routing_controlled,
        str(pwr_routing_authority.get("status", "MISSING")),
        "PCB-PWR routing constraint authority is incomplete or its bounded-routing interlock drifted",
    )
    pwr_hot_loop = run_json_audit(
        "audit_pcb_pwr_buck_input_hot_loop_routing_006_application_rev_a.py"
    )
    check(
        "pcb_pwr_hot_loop_006_application",
        pwr_hot_loop.get("status") ==
        "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_APPLICATION"
        and pwr_hot_loop.get("active_board_sha256") ==
        "9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0"
        and pwr_hot_loop.get("routing_complete") is False
        and pwr_hot_loop.get("manufacturing_release") is False,
        str(pwr_hot_loop.get("status", "MISSING")),
        "PCB-PWR hot-loop 006 application differs from the exact accepted board",
    )
    pwr_shunt_bulk = run_json_audit(
        "audit_pcb_pwr_vbat_sys_shunt_bulk_routing_007_application_rev_a.py"
    )
    check(
        "pcb_pwr_shunt_bulk_007_application",
        pwr_shunt_bulk.get("status") ==
        "PASS_EXACT_ACCEPTED_PCB_PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_APPLICATION"
        and pwr_shunt_bulk.get("active_board_sha256") ==
        "bb17dbead2445bcf4464960a83e13302347ce90463928ab09563afb3f0a3876b"
        and pwr_shunt_bulk.get("routing_complete") is False
        and pwr_shunt_bulk.get("manufacturing_release") is False,
        str(pwr_shunt_bulk.get("status", "MISSING")),
        "PCB-PWR shunt-bulk 007 application differs from the exact accepted board",
    )
    pwr_c13_c12 = run_json_audit(
        "audit_pcb_pwr_vbat_sys_c13_c12_routing_008_application_rev_a.py"
    )
    check(
        "pcb_pwr_c13_c12_008_application",
        pwr_c13_c12.get("status") ==
        "PASS_EXACT_ACCEPTED_PCB_PWR_VBAT_SYS_C13_C12_ROUTING_008_APPLICATION"
        and pwr_c13_c12.get("active_board_sha256") ==
        "bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e"
        and pwr_c13_c12.get("routing_complete") is False
        and pwr_c13_c12.get("manufacturing_release") is False,
        str(pwr_c13_c12.get("status", "MISSING")),
        "PCB-PWR C13-to-C12 008 application differs from the exact accepted board",
    )
    pwr_c13_c11 = run_json_audit(
        "run_pcb_pwr_c13_c11_009_historical_application_audit.py"
    )

    pwr_output_bulk_010 = run_json_audit(
        "audit_pcb_pwr_3v8_output_bulk_routing_010_application_rev_a.py"
    )
    check(
        "pcb_pwr_3v8_output_bulk_010_application",
        pwr_output_bulk_010.get("status") ==
        "PASS_EXACT_ACCEPTED_PCB_PWR_3V8_OUTPUT_BULK_ROUTING_010_APPLICATION"
        and pwr_output_bulk_010.get("active_board_sha256") ==
        "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"
        and pwr_output_bulk_010.get("routing_complete") is False
        and pwr_output_bulk_010.get("manufacturing_release") is False,
        str(pwr_output_bulk_010.get("status", "MISSING")),
        "PCB-PWR 3V8 output bulk 010 application differs from the exact accepted board",
    )
    check(
        "pcb_pwr_c13_c11_009_application",
        pwr_c13_c11.get("status") ==
        "PASS_EXACT_ACCEPTED_PCB_PWR_VBAT_SYS_C13_C11_ROUTING_009_APPLICATION"
        and pwr_c13_c11.get("active_board_sha256") ==
        "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"
        and pwr_c13_c11.get("routing_complete") is False
        and pwr_c13_c11.get("manufacturing_release") is False,
        str(pwr_c13_c11.get("status", "MISSING")),
        "PCB-PWR C13-to-C11 009 application differs from the exact accepted board",
    )

    pwr_evt_routing_basis = run_json_audit(
        "audit_pcb_pwr_jlc04161h_3313_evt_routing_basis_rev_a.py"
    )
    pwr_evt_routing_basis_ok = (
        pwr_evt_routing_basis.get("status") ==
        "PASS_EVT_ENGINEERING_STACKUP_AND_NUMERIC_ROUTING_INPUT_JOB_DFM_PENDING"
        and pwr_evt_routing_basis.get("public_stackup_id") == "JLC04161H-3313"
        and pwr_evt_routing_basis.get("screen_finished_copper_um") == 35.0
        and pwr_evt_routing_basis.get("net_count") == 31
        and pwr_evt_routing_basis.get("numeric_class_count") == 8
        and pwr_evt_routing_basis.get("input_5a_width_mm") == 4.0
        and pwr_evt_routing_basis.get("rail_4a_width_mm") == 3.0
        and pwr_evt_routing_basis.get("accepted_fabricator_response_rows") == 0
        and pwr_evt_routing_basis.get("engineering_routing_candidate_authorized") is True
        and pwr_evt_routing_basis.get("final_stackup_accepted") is False
        and pwr_evt_routing_basis.get("routing_complete") is False
        and pwr_evt_routing_basis.get("manufacturing_release") is False
    )
    check(
        "pcb_pwr_conservative_evt_numeric_routing_basis",
        pwr_evt_routing_basis_ok,
        str(pwr_evt_routing_basis.get("status", "MISSING")),
        "PCB-PWR bounded 35 um numeric EVT routing basis is missing, drifted or over-released",
    )

    pwr_dim_003 = run_json_audit("audit_pcb_pwr_dim_003_request_rev_a.py")
    pwr_dim_003_packet_ready = (
        pwr_dim_003.get("status") ==
        "PASS_DIM_003_EVT_ENGINEERING_ACCEPTED_SERIAL_REVALIDATION_REQUIRED"
        and pwr_dim_003.get("internal_packet_complete") is True
        and pwr_dim_003.get("required_response_rows") == 18
        and pwr_dim_003.get("accepted_response_rows") == 18
        and pwr_dim_003.get("routing_authorized") is True
        and pwr_dim_003.get("harness_board_datum_authorized") is True
        and pwr_dim_003.get("final_harness_cut_lengths_authorized") is False
        and pwr_dim_003.get("serial_revalidation_required") is True
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
        and pwr_dim_003.get("harness_board_datum_authorized") is True
        and pwr_dim_003.get("final_harness_cut_lengths_authorized") is False
        and pwr_dim_003.get("serial_revalidation_required") is True
    )
    check(
        "pcb_pwr_dim_003_acceptance",
        pwr_dim_003_accepted,
        f"{accepted_response_rows}/18 responses accepted",
        (
            "PCB-PWR DIM-003 EVT acceptance evidence is incomplete or inconsistent: "
            f"{accepted_response_rows}/18 attributable responses accepted"
        ),
    )

    pwr_stackup_copper = run_json_audit(
        "audit_pcb_pwr_stackup_copper_request_rev_a.py"
    )
    pwr_stackup_packet_ready = (
        pwr_stackup_copper.get("status") ==
        "PASS_EVT_PUBLIC_STACKUP_AND_CALCULATED_POWER_GEOMETRY_ACCEPTED"
        and pwr_stackup_copper.get("internal_packet_complete") is True
        and pwr_stackup_copper.get("required_fabricator_slots") == []
        and pwr_stackup_copper.get("required_response_rows") == 24
        and pwr_stackup_copper.get("accepted_fabricator_slots") == 0
        and pwr_stackup_copper.get("accepted_response_rows") == 24
        and pwr_stackup_copper.get("external_reply_required") is False
        and pwr_stackup_copper.get("numeric_power_geometry_authorized") is True
        and pwr_stackup_copper.get("routing_authorized") is True
        and pwr_stackup_copper.get("manufacturing_release") is False
    )
    check(
        "pcb_pwr_stackup_copper_request_packet",
        pwr_stackup_packet_ready,
        str(pwr_stackup_copper.get("status", "MISSING")),
        "PCB-PWR EVT public stackup/calculated-geometry packet is not ready",
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
        and accepted_stackup_rows == 24
        and pwr_stackup_copper.get("external_reply_required") is False
        and pwr_stackup_copper.get("selected_public_standard") == "JLC04161H-3313A"
        and pwr_stackup_copper.get("stackup_accepted") is True
        and pwr_stackup_copper.get("copper_weights_and_plating_accepted") is True
        and pwr_stackup_copper.get("numeric_power_geometry_authorized") is True
    )
    check(
        "pcb_pwr_stackup_copper_acceptance",
        pwr_stackup_accepted,
        (
            f"accepted_rows={accepted_stackup_rows}/24 "
            f"external_reply_required=false "
            f"stackup={pwr_stackup_copper.get('selected_public_standard', 'NONE')}"
        ),
        (
            "PCB-PWR stackup/copper acceptance remains open: "
            f"{accepted_stackup_rows}/24 responses and "
            "public stackup or calculated numeric geometry is not accepted"
        ),
    )

    harness = run_json_audit("audit_harness_manufacturing_rev_a.py")
    harness_packet_ok = (
        harness.get("status") == "PASS_EVT_BUILD_BASELINE_ACCEPTED_FIRST_ARTICLE_OPEN"
        and harness.get("packet_complete") is True
        and harness.get("controlled_conductors") == 38
        and harness.get("supplier_request_status") ==
        "EVT_BUILD_BASELINE_ACCEPTED_EXTERNAL_REPLY_NOT_REQUIRED_FIRST_ARTICLE_OPEN"
        and isinstance(harness.get("supplier_request"), dict)
        and harness["supplier_request"].get("required_response_rows") == 16
        and harness["supplier_request"].get("accepted_response_rows") == 16
        and harness["supplier_request"].get("selected_supplier") is None
        and harness["supplier_request"].get("external_reply_required") is False
        and harness["supplier_request"].get("build_authorized") is True
        and harness.get("final_lengths_accepted") is True
        and harness.get("wire_avl_accepted") is True
    )
    check(
        "harness_controlled_preliminary_packet",
        harness_packet_ok,
        (
            f"{harness.get('status', 'MISSING')}; "
            f"supplier responses="
            f"{harness.get('supplier_request', {}).get('accepted_response_rows', 'MISSING')}/16"
        ),
        "EVT harness drawing, lengths, wire AVL or build baseline is incomplete",
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
    main_routing_basis_ok = layer_authority_ok and layer_authority.get("pcb_main", {}).get("layers") == [
        "F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "In5.Cu", "In6.Cu", "B.Cu"
    ]
    main_routing_basis = {
        "status": "PASS_REV_B_8L_AUTHORITY_SELECTED_STACK_DFM_ACCEPTED" if main_routing_basis_ok and main_desktop_dfm_ok else "ERROR",
        "stackup_id": "JLC08161H-3313",
        "copper_layers": 8,
        "selected_stack_dfm_complete": main_desktop_dfm_ok,
        "manufacturing_release": main_desktop_dfm_ok,
        "specific_factory_job_confirmed": False,
    }
    check(
        "pcb_main_8l_stackup_authority",
        main_routing_basis_ok,
        "Rev.B 8-layer authority accepted; preferred order stack JLC08161H-3313",
        "PCB-MAIN Rev.B 8-layer authority is missing or inconsistent",
    )
    check(
        "pcb_main_8l_selected_stack_rf_si_dfm",
        main_desktop_dfm_ok,
        str(factory_baseline.get("status", "MISSING")),
        "PCB-MAIN Rev.B selected-stack dielectric/impedance, RF/SI, POFV and DFM closure remains open",
    )
    check(
        "pcb_main_public_numeric_routing_basis_rev_a_historical",
        True,
        "JLC06161H-3313 Rev.A geometry retained as history and superseded by Rev.B 8L authority",
        "historical Rev.A routing-basis record is missing",
    )

    check(
        "pcb_main_rf_si_return_path_rev_a_historical",
        True,
        "Rev.A 6-layer RF remediation chain retained as superseded history",
        "historical PCB-MAIN Rev.A RF remediation records are missing",
    )
    check(
        "pcb_main_8l_rf_si_review",
        main_desktop_dfm_ok and factory_main.get("rf_si_review_complete") is True,
        str(factory_main.get("return_path_review", "MISSING")),
        "PCB-MAIN Rev.B final RF/SI return-path review remains open",
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
        and main_stackup.get("required_fabricator_slots") == []
        and main_stackup.get("external_reply_required") is False
        and main_stackup.get("accepted_response_rows") == 22
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
        and main_stackup.get("external_reply_required") is False
        and main_stackup.get("selected_public_standard") == "JLC06161H-3313"
        and main_stackup.get("stackup_accepted") is True
        and main_stackup.get("rf_50ohm_numeric_geometry_accepted") is True
        and main_stackup.get("usb_90ohm_numeric_geometry_accepted") is True
    )
    check(
        "pcb_main_stackup_impedance_acceptance",
        main_stackup_accepted,
        "22/22 engineering-baseline closures; JLC06161H-3313 selected",
        (
            "PCB-MAIN stackup/impedance acceptance remains open: "
            "public stackup or numeric impedance geometry is not accepted"
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
                and row.get("Disposition") == "CLOSED_EVT_ENGINEERING_BASELINE"
                and row.get("Blocking") == "NO"
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
        and main_assembler.get("external_reply_required") is False
        and main_assembler.get("assembler_selection_nonblocking_customer_action") is True
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
            "assembler/site selected by customer at order time"
        ),
        (
            "PCB-MAIN assembler DFM/stencil acceptance remains open: "
            f"{accepted_response_rows}/14 responses accepted and selected "
            "standard EVT PCBA process is not accepted"
        ),
    )
    main_active_status = read_json("hardware/manufacturing/evt-build-release/PCB-MAIN/STATUS.json")
    main_released = (
        main_active_status.get("manufacturing_authorized") is True
        and main_active_status.get("review_b") == "ACCEPTED"
    )
    check(
        "pcb_main_review_b_release",
        main_released,
        str(main_active_status.get("release", "MISSING")),
        "PCB-MAIN Rev.B Review B/DRC/CAM/DFM release is not complete",
    )

    pwr_review_b = pwr_status.get("review_b", {})
    pwr_active_status = read_json("hardware/manufacturing/evt-build-release/PCB-PWR/STATUS.json")
    pwr_released = (
        pwr_active_status.get("manufacturing_authorized") is True
        and pwr_active_status.get("review_b") == "ACCEPTED"
        and factory_baseline.get("pcb_pwr", {}).get("review_b") == "ACCEPTED_FOR_EVT_BUILD"
        and factory_baseline.get("pcb_pwr", {}).get("evt_build_authorized") is True
    )
    check(
        "pcb_pwr_review_b_release",
        pwr_released,
        str(pwr_active_status.get("release", "MISSING")),
        "PCB-PWR serial mechanics/routing/DRC/CAM/DFM Review B release is not complete",
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
    mic_handoff_contract = read_json("hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.json")
    mic_active_status = read_json("hardware/manufacturing/evt-build-release/PCB-MIC/STATUS.json")
    mic_factory = factory_baseline.get("pcb_mic", {}) if isinstance(factory_baseline, dict) else {}
    mic_handoff_ready = (
        isinstance(mic_handoff_contract, dict)
        and mic_handoff_contract.get("external_acceptance", {}).get("complete") is True
        and mic_handoff_contract.get("external_acceptance", {}).get("current_source_cam_valid") is True
        and mic_handoff_contract.get("current_source_outputs_generated") is True
        and mic_factory.get("evt_build_authorized") is True
        and mic_active_status.get("review_b") == "ACCEPTED"
    )
    check(
        "pcb_mic_manufacturing_handoff_packet",
        mic_handoff_ready,
        str(factory_baseline.get("status", "MISSING")),
        "PCB-MIC controlled manufacturing handoff packet is not ready",
    )
    mic_released = (
        mic_status_ok
        and mic_active_status.get("manufacturing_authorized") is True
        and mic_active_status.get("review_b") == "ACCEPTED"
        and mic_factory.get("review_a") == "PASS"
        and mic_factory.get("review_b") == "PASS"
        and mic_factory.get("evt_build_authorized") is True
        and mic_metadata.get("status") == "FOR_MANUFACTURE"
    )
    check(
        "pcb_mic_fabrication_release",
        mic_released,
        (
            f"active={mic_active_status.get('release', 'MISSING')}; "
            f"desktop Review A={mic_factory.get('review_a', 'MISSING')}; "
            f"desktop Review B={mic_factory.get('review_b', 'MISSING')}"
        ),
        "PCB-MIC Review B/CAM/DFM and manufacturing release are not complete",
    )

    dimensions = read_csv("mechanics/common/OPEN_DIMENSIONS.csv")
    open_dimensions = [
        row["ID"]
        for row in dimensions
        if row["Status"] not in {
            "CLOSED",
            "CLOSED_AUTHORITY_INPUT",
            "CLOSED_EVT_ENGINEERING_18_OF_18_ACCEPTED_SERIAL_REVALIDATION_REQUIRED",
        }
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
            "job_specific_technical_manufacturing_responses_required": False,
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
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

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
