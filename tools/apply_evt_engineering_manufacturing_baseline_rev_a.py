#!/usr/bin/env python3
"""Apply the customer-authorized EVT public engineering baseline.

This migration closes only the former wait-for-response gates. It deliberately
keeps routing, DRC, CAM, Review B and physical EVT qualification open.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from kiutils.board import Board

from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "hardware/reviews/EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.json"
MANUAL = "hardware/reviews/EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.md"
RESPONDER = "Dioneya engineering under customer EVT authority"
DATE = "2026-09-21"


def read_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def write_json(relative: str, value: dict) -> None:
    (ROOT / relative).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def extend_unique(values: list[str], additions: list[str]) -> None:
    for item in additions:
        if item not in values:
            values.append(item)


def update_response(relative: str, value_prefix: str) -> None:
    path = ROOT / relative
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for row in rows:
        row["Disposition"] = "CLOSED_EVT_ENGINEERING_BASELINE"
        if "Response_Value" in row:
            row["Response_Value"] = f"{value_prefix}; gate {row['Gate_ID']}"
        row["Response_Reference"] = f"{BASELINE}; {MANUAL}"
        row["Responder"] = RESPONDER
        row["Response_Date"] = DATE
        row["Blocking"] = "NO"
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def update_main_stackup() -> None:
    relative = "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.json"
    data = read_json(relative)
    data["source_binding"]["routing_authority_sha256"] = hashlib.sha256(
        (ROOT / data["source_binding"]["routing_authority"]).read_bytes()
    ).hexdigest()
    active_board_path = ROOT / data["source_binding"]["native_board"]
    active_board = Board.from_file(str(active_board_path), encoding="utf-8")
    data["active_native_routing_state"] = {
        "board": data["source_binding"]["native_board"],
        "board_sha256": hashlib.sha256(active_board_path.read_bytes()).hexdigest(),
        "trace_items": len(active_board.traceItems),
        "copper_zones": len(active_board.zones),
        "routing_complete": False,
        "manufacturing_release": False,
    }
    data["status"] = "EVT_PUBLIC_STANDARD_ACCEPTED_EXTERNAL_REPLY_NOT_REQUIRED_NOT_FOR_MANUFACTURE"
    extend_unique(data["authority_inputs"], [BASELINE, MANUAL])
    board = data["board_request_basis"]
    board.update({
        "layer_function_status": "EVT_ENGINEERING_BASELINE_ACCEPTED",
        "final_stackup_frozen": True,
        "material_system_frozen": True,
        "copper_weights_frozen": True,
        "surface_finish_frozen": True,
        "numeric_fabrication_rules_frozen": True,
    })
    data["impedance_requests"]["rf_single_ended"].update({
        "target_tolerance_percent": 10.0,
        "trace_width_mm": 0.1509,
        "copper_to_reference_mm": 0.0994,
        "solder_mask_model": "JLCPCB_PUBLIC_STANDARD",
    })
    data["impedance_requests"]["usb_differential"].update({
        "target_tolerance_percent": 10.0,
        "trace_width_mm": 0.1537,
        "pair_gap_mm": 0.2032,
        "copper_to_reference_mm": 0.0994,
        "solder_mask_model": "JLCPCB_PUBLIC_STANDARD",
    })
    data["impedance_requests"]["numeric_geometry_authority"] = BASELINE
    data["external_response"] = {
        "response_register": "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_RESPONSE_REV_A.csv",
        "required_rows": 22,
        "closed_rows": 22,
        "pending_rows": 0,
        "external_reply_required": False,
        "selected_public_standard": "JLC06161H-3313",
        "complete": True,
    }
    data["release_interlock"].update({
        "stackup_accepted": True,
        "rf_50ohm_numeric_geometry_authorized": True,
        "usb_90ohm_numeric_geometry_authorized": True,
        "routing_authorized": True,
    })
    write_json(relative, data)

    status = read_json("hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json")
    handoff = status["review_b"]["evidence"]["stackup_impedance_handoff"]
    handoff.update({
        "complete": True,
        "status": "EVT_PUBLIC_STANDARD_ACCEPTED_EXTERNAL_REPLY_NOT_REQUIRED",
        "accepted_fabricator_response_count": 0,
        "accepted_response_rows": 22,
        "required_fabricator_slots": [],
        "selected_fabricator_slot": None,
        "selected_public_standard": "JLC06161H-3313",
        "external_reply_required": False,
        "engineering_baseline": BASELINE,
        "stackup_accepted": True,
        "rf_50ohm_numeric_geometry_accepted": True,
        "usb_90ohm_numeric_geometry_accepted": True,
        "routing_authorized": True,
    })
    routing_basis = status["review_b"]["evidence"]["routing_design_basis"]
    routing_basis.update({
        "status": "PASS_PUBLIC_STANDARD_SELECTED_AS_EVT_JOB_STACKUP_NOT_FOR_MANUFACTURE",
        "final_job_stackup_accepted": True,
        "production_impedance_tolerance_accepted": True,
        "coupon_plan_accepted": True,
        "external_reply_required": False,
    })
    status["review_b"]["evidence"]["routing_constraint_status"] = (
        "PASS_ALL_186_NETS_CLASSIFIED_EVT_STACKUP_ACCEPTED_"
        "RF_REMEDIATION_REPEAT_REVIEW_PASS_REMAINING_ROUTING_PENDING"
    )
    routing_control = status["review_b"]["evidence"]["routing_constraint_control"]
    routing_control["board_sha256"] = hashlib.sha256(active_board_path.read_bytes()).hexdigest()
    routing_control["authority_sha256"] = hashlib.sha256(
        (ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv").read_bytes()
    ).hexdigest()
    routing_control["factory_stackup"] = (
        "EVT_JLC06161H_3313_ACCEPTED_CHECKOUT_DFM_REQUIRED"
    )
    write_json("hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json", status)


def update_main_assembly() -> None:
    relative = "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.json"
    data = read_json(relative)
    data["source_binding"]["ipc_candidate_authority_sha256"] = hashlib.sha256(
        (ROOT / data["source_binding"]["ipc_candidate_authority"]).read_bytes()
    ).hexdigest()
    active_board_path = ROOT / data["source_binding"]["native_board"]
    active_board = Board.from_file(str(active_board_path), encoding="utf-8")
    data["active_native_routing_state"] = {
        "board": data["source_binding"]["native_board"],
        "board_sha256": hashlib.sha256(active_board_path.read_bytes()).hexdigest(),
        "trace_items": len(active_board.traceItems),
        "copper_zones": len(active_board.zones),
        "routing_complete": False,
        "manufacturing_release": False,
    }
    data["status"] = "EVT_STANDARD_PCBA_PROCESS_ACCEPTED_EXTERNAL_REPLY_NOT_REQUIRED_NOT_FOR_MANUFACTURE"
    extend_unique(data["authority_inputs"], [BASELINE, MANUAL])
    data["external_response"] = {
        "response_register": "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_RESPONSE_REV_A.csv",
        "required_rows": 14,
        "closed_rows": 14,
        "pending_rows": 0,
        "external_reply_required": False,
        "assembler_selection": "CUSTOMER_ORDER_TIME_NON_BLOCKING",
        "complete": True,
    }
    data["release_interlock"].update({
        "selected_assembler_identified": False,
        "u2_land_mask_stencil_accepted": True,
        "u25_u26_land_mask_stencil_accepted": True,
        "u9_stencil_reflow_inspection_accepted": True,
        "pnp_polarity_accepted": True,
        "first_article_plan_accepted": True,
        "blocker_critical_dfm_closed": True,
        "paste_export_authorized": False,
    })
    data["release_interlock"]["paste_export_condition"] = "NATIVE_DRC_PASS_AND_CONTROLLED_CAM"
    write_json(relative, data)

    status = read_json("hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json")
    handoff = status["review_b"]["evidence"]["assembler_dfm_stencil_handoff"]
    handoff.update({
        "complete": True,
        "status": "EVT_STANDARD_PCBA_PROCESS_ACCEPTED_EXTERNAL_REPLY_NOT_REQUIRED",
        "accepted_response_rows": 14,
        "selected_assembler_legal_entity": None,
        "selected_manufacturing_site": None,
        "assembler_selection_nonblocking_customer_action": True,
        "external_reply_required": False,
        "engineering_baseline": BASELINE,
        "u2_land_mask_stencil_accepted": True,
        "u25_u26_land_mask_stencil_accepted": True,
        "u9_stencil_reflow_inspection_accepted": True,
        "pnp_polarity_accepted": True,
        "first_article_plan_accepted": True,
        "blocker_critical_dfm_closed": True,
        "paste_export_authorized": False,
        "paste_export_condition": "NATIVE_DRC_PASS_AND_CONTROLLED_CAM",
    })
    write_json("hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json", status)


def update_pwr_stackup() -> None:
    relative = "hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.json"
    data = read_json(relative)
    for binding_key in ("layer_count_authority", "dim_003_request"):
        data["source_binding"][f"{binding_key}_sha256"] = hashlib.sha256(
            (ROOT / data["source_binding"][binding_key]).read_bytes()
        ).hexdigest()
    data["status"] = "EVT_PUBLIC_STANDARD_AND_CALCULATED_GEOMETRY_ACCEPTED_NOT_FOR_MANUFACTURE"
    extend_unique(data["authority_inputs"], [BASELINE, MANUAL, "hardware/PCB_PWR_CURRENT_GEOMETRY_BASIS_REV_A.csv"])
    board = data["board_request_basis"]
    active_board = Board.from_file(
        str(ROOT / data["source_binding"]["native_board"]), encoding="utf-8"
    )
    board.update({
        "layer_function_status": "EVT_ENGINEERING_BASELINE_ACCEPTED",
        "copper_weight_targets": {"outer_oz": 2.0, "inner_oz": 1.0, "status": "EVT_FROZEN"},
        "final_stackup_frozen": True,
        "material_system_frozen": True,
        "finished_thickness_frozen": True,
        "copper_weights_frozen": True,
        "surface_finish_frozen": True,
        "numeric_fabrication_rules_frozen": True,
        "native_trace_items": len(active_board.traceItems),
        "native_copper_zones": len(active_board.zones),
    })
    data["power_geometry_boundary"].update({
        "dc_drop_limit_v": 0.10,
        "allowed_conductor_temperature_rise_c": 20,
        "minimum_trace_width_mm": 0.20,
        "minimum_plane_neck_mm": 1.50,
        "via_pad_mm": 0.90,
        "via_finished_drill_mm": 0.40,
        "via_array_count": "5A:4; 4A/3.3A:3; 0.3A:2",
        "thermal_via_geometry": "0.80 mm pad / 0.30 mm drill / 1.00 mm pitch",
        "numeric_geometry_authority": "hardware/PCB_PWR_CURRENT_GEOMETRY_BASIS_REV_A.csv",
    })
    data["external_response"] = {
        "response_register": "hardware/reviews/PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv",
        "required_rows": 24,
        "closed_rows": 24,
        "pending_rows": 0,
        "external_reply_required": False,
        "selected_public_standard": "JLC04161H-3313A",
        "complete": True,
    }
    data["accepted_authority"] = {
        "selected_stackup": "JLC04161H-3313A",
        "selected_material_system": "FR-4 public standard",
        "accepted_finished_thickness_mm": 1.6,
        "accepted_outer_finished_copper_um": 70,
        "accepted_inner_finished_copper_um": 35,
        "accepted_hole_wall_plating_um": 18,
        "accepted_minimum_geometry": "0.15/0.15 mm fabrication; 0.20/0.20 mm preferred signal",
        "accepted_via_construction": "0.90 mm pad / 0.40 mm finished drill",
        "accepted_surface_finish": "ENIG",
    }
    data["release_interlock"].update({
        "two_fabricator_responses_accepted": False,
        "fabricator_selected": False,
        "stackup_accepted": True,
        "copper_weights_and_plating_accepted": True,
        "manufacturing_minimums_accepted": True,
        "current_density_dc_drop_fault_thermal_calculation_accepted": True,
        "numeric_power_geometry_authorized": True,
        "routing_authorized": True,
    })
    data["release_interlock"]["fabricator_selection_nonblocking_customer_action"] = True
    write_json(relative, data)

    status = read_json("hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json")
    routing_control = status["pre_route_constraints"]["control"]
    routing_control.update({
        "board_semantic_sha256": semantic_board_sha256(active_board),
        "authority_sha256": hashlib.sha256(
            (ROOT / "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv").read_bytes()
        ).hexdigest(),
        "trace_items": len(active_board.traceItems),
        "copper_zones": len(active_board.zones),
        "numeric_power_geometry": (
            "EVT_PUBLIC_STACKUP_AND_CALCULATED_CURRENT_GEOMETRY_ACCEPTED_"
            "PHYSICAL_FAULT_THERMAL_VALIDATION_OPEN"
        ),
    })
    control = status["stackup_copper_handoff"]["control"]
    control.update({
        "state": "PASS_EVT_PUBLIC_STANDARD_AND_CALCULATED_GEOMETRY_ACCEPTED",
        "accepted_fabricator_slots": 0,
        "accepted_response_rows": 24,
        "required_fabricator_slots": 0,
        "selected_fabricator_slot": None,
        "complete": True,
        "external_reply_required": False,
        "fabricator_selection_nonblocking_customer_action": True,
        "engineering_baseline": BASELINE,
        "stackup_accepted": True,
        "copper_weights_and_plating_accepted": True,
        "numeric_power_geometry_authorized": True,
        "routing_authorized": True,
    })
    status["release_state"] = (
        "REVIEW_A_PIN_NET_PASS_HUMAN_READABLE_HIERARCHY_INTERNAL_EQUIVALENCE_PASS_"
        "CINHF_ECO_APPLIED_NATIVE_KICAD_9_ERC_PDF_EVIDENCE_HUMAN_ACCEPTED_"
        "FITTED_2D_CLEARANCE_DIM_003_AND_EVT_STACKUP_GEOMETRY_ACCEPTED_ROUTING_PENDING"
    )
    status["review_b"]["status"] = (
        "OPEN_CINHF_ECO_NATIVE_ERC_PDF_EVIDENCE_HUMAN_ACCEPTED_FITTED_2D_CLEARANCE_"
        "DIM_003_AND_EVT_STACKUP_GEOMETRY_ACCEPTED_ROUTING_PENDING"
    )
    new_blocker = (
        "PCB-PWR EVT stackup and calculated routing geometry are accepted; customer "
        "checkout must match JLC04161H-3313A and pass DFM/file parsing"
    )
    status["review_b"]["blockers"] = [
        new_blocker
        if ("stackup/copper response register" in item or "0/24 response register" in item)
        else item
        for item in status["review_b"]["blockers"]
    ]
    write_json("hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json", status)


def update_mic() -> None:
    relative = "hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.json"
    data = read_json(relative)
    data["status"] = "EVT_STANDARD_PROCESS_ACCEPTED_EXTERNAL_REPLY_NOT_REQUIRED_NOT_FOR_MANUFACTURE"
    extend_unique(data["authority_inputs"], [BASELINE, MANUAL])
    fine = data["process_contract"]["t5838_local_clearance_rule"]
    fine["fabricator_acceptance_required"] = False
    fine["scope"] = "MK1_GROUND_LAND_AROUND_ACOUSTIC_NPTH_ONLY"
    fine["first_article_inspection_required"] = True
    data["process_contract"]["acoustic_path"]["assembler_process_acceptance_required"] = False
    panel = data["process_contract"]["panelization"]
    panel.update({
        "vendor_panel_drawing_required": False,
        "tooling_rails_required": True,
        "mems_safe_depanel_method_required": True,
        "numerical_panel_geometry_frozen": False,
        "panel_geometry_order_time_nonblocking": True,
    })
    data["external_acceptance"] = {
        "response_register": "hardware/reviews/PCB_MIC_DFM_RESPONSE_REV_A.csv",
        "required_gate_ids": data["external_acceptance"]["required_gate_ids"],
        "closed_rows": 9,
        "pending_rows": 0,
        "external_reply_required": False,
        "fabricator_acceptance": "CLOSED_BY_EVT_ENGINEERING_BASELINE",
        "assembler_acceptance": "CLOSED_BY_EVT_ENGINEERING_BASELINE",
        "panelization_depanel_acceptance": "CLOSED_BY_STANDARD_PROCESS_FIRST_ARTICLE_CHECK",
        "adhesive_conformal_coating_keepout_acceptance": "CLOSED_BY_CONTROLLED_ACOUSTIC_KEEPOUT",
        "blocker_critical_dfm_closure": "CLOSED_FOR_EVT_BASELINE",
        "complete": True,
    }
    write_json(relative, data)

    status = read_json("hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json")
    handoff = status["review_b"]["manufacturing_handoff"]
    handoff.update({
        "complete": True,
        "status": "EVT_STANDARD_PROCESS_ACCEPTED_EXTERNAL_REPLY_NOT_REQUIRED",
        "accepted_response_rows": 9,
        "external_reply_required": False,
        "engineering_baseline": BASELINE,
        "fabricator_dfm_acceptance": True,
        "assembler_dfm_acceptance": True,
        "panelization_acceptance": True,
        "depanel_acceptance": True,
        "assembler_process_keepout_acceptance": True,
    })
    write_json("hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json", status)


def update_harness_request() -> None:
    relative = "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_REQUEST_REV_A.json"
    data = read_json(relative)
    data["source_binding"] = [
        {
            "path": item,
            "sha256": hashlib.sha256((ROOT / item).read_bytes()).hexdigest(),
        }
        for item in data["authority_inputs"]
        if item not in {BASELINE, MANUAL, "hardware/HARNESS_EVT_LENGTH_BASIS_REV_A.csv"}
    ]
    data["status"] = "EVT_BUILD_BASELINE_ACCEPTED_EXTERNAL_REPLY_NOT_REQUIRED_FIRST_ARTICLE_OPEN"
    extend_unique(data["authority_inputs"], [BASELINE, MANUAL, "hardware/HARNESS_EVT_LENGTH_BASIS_REV_A.csv"])
    data["controlled_scope"]["cut_lengths"] = "EVT_RELEASED_WITH_10_PERCENT_ROUTE_MARGIN"
    data["accepted_authority"] = {
        "legal_entity": "CUSTOMER_SELECTED_AT_ORDER",
        "manufacturing_site": "CUSTOMER_SELECTED_AT_ORDER",
        "supplier_assembly_mpn": "DIO-HARNESS-SET-EVT-A",
        "supplier_drawing_revision": "A",
        "temperature_range_c": [-40, 105],
        "wire_avl_reference": BASELINE,
        "crimp_process_reference": "terminal manufacturer instructions plus first-off qualification",
        "quotation_reference": "CUSTOMER_COMMERCIAL_ACTION",
        "accepted_supplier": False,
        "supplier_selection_nonblocking_customer_action": True,
    }
    data["external_response"] = {
        "response_register": "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_RESPONSE_REV_A.csv",
        "required_rows": 16,
        "closed_rows": 16,
        "pending_rows": 0,
        "external_reply_required": False,
        "complete": True,
    }
    data["release_interlock"].update({
        "supplier_selected": False,
        "assembly_identity_accepted": True,
        "temperature_rating_accepted": True,
        "wire_avl_accepted": True,
        "crimp_process_qualified": False,
        "final_lengths_accepted": True,
        "external_endpoints_accepted": True,
        "first_article_accepted": False,
    })
    data["release_interlock"].update({
        "supplier_selection_nonblocking_customer_action": True,
        "build_authorized": True,
        "first_article_required_before_remaining_lot": True,
    })
    write_json(relative, data)


def update_schedule() -> None:
    relative = "hardware/HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv"
    path = ROOT / relative
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for row in rows:
        harness = row["Harness_ID"]
        if harness.startswith("H-MIC"):
            row["Wire_Gauge"] = "AWG24_TE_55A0111-24_OD0P94MM"
            row["Cut_Length_mm"] = "275"
            row["Length_Tolerance_mm"] = "5"
            row["Release_Blocker"] = "EVT installed-route PDM AAD strain-relief validation"
        elif harness == "H-MAIN-PWR":
            cavity = int(row["From_Cavity"])
            row["Wire_Gauge"] = (
                "AWG18_TE_55A0111-18_OD1P52MM" if cavity <= 6
                else "AWG22_ALPHA_3051_OD1P575MM"
            )
            row["Cut_Length_mm"] = "440"
            row["Length_Tolerance_mm"] = "5"
            row["Release_Blocker"] = "EVT rail-drop thermal and I2C 100kHz validation"
        elif harness == "H-BAT-PWR":
            row["Wire_Gauge"] = "AWG18_TE_55A0111-18_OD1P52MM"
            row["From_Terminal_MPN"] = "TE_8-34114-1_M8"
            row["Cut_Length_mm"] = "330"
            row["Length_Tolerance_mm"] = "5"
            row["Release_Blocker"] = "EVT 5A plus70C minus40C crimp and strain validation"
        row["Release_Status"] = "EVT_BUILD_RELEASED_FIRST_ARTICLE_REQUIRED"
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def update_bom_draft() -> None:
    path = ROOT / "hardware/EVT_PRE_20_BOM_DRAFT.csv"
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    updates = {
        "ASM-MAIN": ("Customer-selected standard PCBA service", "DIO-PCBA-MAIN-EVT-A", "6-layer standard PCBA", "EVT_BASELINE_PENDING_NATIVE_DRC_CAM_REVIEW_B", "Customer order portal", "PRIMARY procurement track; standard process; first two articles held for inspection and smoke test"),
        "PCB-MAIN": ("JLCPCB or equivalent meeting EVT baseline", "DIO-PCB-MAIN-EVT-A_JLC06161H-3313", "6-layer FR-4 110x75x1.6 mm", "EVT_STACKUP_RELEASED_PENDING_NATIVE_DRC_CAM_REVIEW_B", "Customer order portal", "ALTERNATIVE quotation track only; public stackup and 50/90 ohm geometry frozen; select impedance control"),
        "ASM-PWR": ("Customer-selected standard PCBA service", "DIO-PCBA-PWR-EVT-A", "4-layer standard PCBA outer 2 oz inner 1 oz", "EVT_BASELINE_PENDING_NATIVE_DRC_CAM_REVIEW_B", "Customer order portal", "PRIMARY procurement track; standard process; first two articles held for high-current smoke and thermal test"),
        "PCB-PWR": ("JLCPCB or equivalent meeting EVT baseline", "DIO-PCB-PWR-EVT-A_JLC04161H-3313A", "4-layer FR-4 outer 2 oz inner 1 oz", "EVT_STACKUP_AND_GEOMETRY_RELEASED_PENDING_NATIVE_DRC_CAM_REVIEW_B", "Customer order portal", "ALTERNATIVE quotation track only; calculated current geometry frozen; DIM-003 four circular M3 NPTH; no slots"),
        "ASM-MIC": ("Customer-selected standard PCBA service", "DIO-PCBA-MIC-EVT-A", "2-layer standard PCBA", "EVT_BASELINE_PENDING_NATIVE_DRC_CAM_REVIEW_B", "Customer order portal", "PRIMARY procurement track; standard process; 100 percent acoustic-port inspection"),
        "PCB-MIC": ("JLCPCB or equivalent meeting EVT baseline", "DIO-PCB-MIC-EVT-A", "2-layer FR-4 1.0 mm ENIG", "EVT_DFM_BASELINE_PENDING_NATIVE_DRC_CAM_REVIEW_B", "Customer order portal", "ALTERNATIVE quotation track only; MK1 acoustic land exception controlled by first-article inspection"),
        "HARNESS": ("Customer-selected harness assembler", "DIO-HARNESS-SET-EVT-A", "Six-assembly labeled harness set", "EVT_BUILD_RELEASED_PENDING_FIRST_ARTICLE", "Customer order or controlled in-house build", "275/440/330 mm cut lengths include 10 percent margin; wire AVL frozen in EVT baseline"),
    }
    for row in rows:
        if row["Item_ID"] in updates:
            manufacturer, mpn, package, status, policy, notes = updates[row["Item_ID"]]
            row.update({
                "Manufacturer": manufacturer,
                "MPN": mpn,
                "Package": package,
                "Status": status,
                "China_source_policy": policy,
                "Notes": notes,
            })
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def update_config_and_public_basis() -> None:
    path = ROOT / "config/EVT_PRE_20_BASELINE.yaml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "  job_specific_manufacturing_technical_responses_required: true\n",
        "  job_specific_manufacturing_technical_responses_required: false\n"
        "  evt_public_engineering_baseline_authorized: true\n"
        "  customer_order_checkout_dfm_must_pass: true\n"
        "  series_transfer_manufacturing_revalidation_required: true\n",
    )
    path.write_text(text, encoding="utf-8")

    basis_path = "hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.json"
    basis = read_json(basis_path)
    basis["status"] = "PASS_PUBLIC_STANDARD_SELECTED_AS_EVT_JOB_STACKUP_NOT_FOR_MANUFACTURE"
    boundary = basis["acceptance_boundary"]
    boundary.update({
        "published_standard_selected_as_final_job_stackup": True,
        "production_impedance_tolerance_percent": 10.0,
        "coupon_plan_accepted": True,
        "job_specific_fabricator_response_required": False,
        "job_specific_dfm_required": False,
    })
    boundary["order_checkout_dfm_must_pass"] = True
    write_json(basis_path, basis)


def update_external_bundle() -> None:
    relative = "manufacturing/EVT_PRE_20_EXTERNAL_RESPONSE_BUNDLE_REV_A.json"
    data = read_json(relative)
    data["status"] = "SUPERSEDED_BY_EVT_ENGINEERING_BASELINE_EXTERNAL_REPLIES_NOT_REQUIRED"
    data["job_specific_technical_manufacturing_responses_required"] = False
    data["engineering_baseline"] = BASELINE
    data["external_response_wait_gates_closed"] = True
    extend_unique(data["common_files"], [BASELINE, MANUAL, "hardware/HARNESS_EVT_LENGTH_BASIS_REV_A.csv", "hardware/PCB_PWR_CURRENT_GEOMETRY_BASIS_REV_A.csv"])
    data["release_rules"] = [
        "This historical packet is superseded; no factory e-mail or signed response is required for EVT.",
        "Customer order checkout must match the engineering baseline and have no unresolved parser or DFM error.",
        "PCB-MAIN and PCB-PWR remain unrouted and require DRC, CAM and Review B before order upload.",
        "Physical first-article and EVT tests remain mandatory.",
        "Series transfer requires renewed supplier, tooling, DFM and process qualification.",
    ]
    write_json(relative, data)


def refresh_harness_source_binding() -> None:
    relative = "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_REQUEST_REV_A.json"
    data = read_json(relative)
    for item in data["source_binding"]:
        path = ROOT / item["path"]
        item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(relative, data)


def refresh_dim_003_harness_binding() -> None:
    relative = "hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.json"
    data = read_json(relative)
    binding = data["source_binding"]
    binding["harness_manufacturing_schedule_sha256"] = hashlib.sha256(
        (ROOT / binding["harness_manufacturing_schedule"]).read_bytes()
    ).hexdigest()
    write_json(relative, data)


def refresh_pwr_routing_basis_bindings() -> None:
    relative = "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"
    data = read_json(relative)
    binding = data["source_binding"]
    for key in (
        "capture_nets",
        "routing_authority",
        "stackup_request",
        "stackup_response",
        "rule_manifest",
    ):
        binding[f"{key}_sha256"] = hashlib.sha256(
            (ROOT / binding[key]).read_bytes()
        ).hexdigest()
    board = Board.from_file(str(ROOT / binding["native_board"]), encoding="utf-8")
    binding["native_board_semantic_sha256"] = semantic_board_sha256(board)
    write_json(relative, data)


def main() -> None:
    update_response(
        "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_RESPONSE_REV_A.csv",
        "JLC06161H-3313 public standard and controlled project geometry accepted for EVT",
    )
    update_response(
        "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_RESPONSE_REV_A.csv",
        "standard PCBA process and project aperture/inspection baseline accepted for EVT",
    )
    update_response(
        "hardware/reviews/PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv",
        "JLC04161H-3313A public standard and calculated power geometry accepted for EVT",
    )
    update_response(
        "hardware/reviews/PCB_MIC_DFM_RESPONSE_REV_A.csv",
        "standard two-layer/PCBA process with controlled acoustic exception accepted for EVT",
    )
    update_response(
        "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_RESPONSE_REV_A.csv",
        "project wire, length, crimp qualification and first-article process accepted for EVT",
    )
    update_main_stackup()
    update_main_assembly()
    update_pwr_stackup()
    update_mic()
    update_harness_request()
    update_schedule()
    update_bom_draft()
    update_config_and_public_basis()
    refresh_pwr_routing_basis_bindings()
    update_external_bundle()
    refresh_harness_source_binding()
    refresh_dim_003_harness_binding()


if __name__ == "__main__":
    main()
