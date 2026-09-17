#!/usr/bin/env python3
"""Audit the bounded PCB-PWR stackup and copper-process request.

This audit proves only that a source-bound two-fabricator request and blank
response register are ready. It must never promote target copper weights,
provisional dimensions or vendor capability into numeric power geometry,
routing authority or manufacturing release.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from kiutils.board import Board

from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
RULES = ROOT / "hardware/kicad/PCB_RULES.md"
LAYER_AUTHORITY = ROOT / "hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv"
POWER_BASELINE = ROOT / "hardware/POWER_DESIGN_BASELINE_REV_A.json"
POWER_CALC = ROOT / "hardware/POWER_DESIGN_CALC_REV_A.md"
PLACEMENT = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv"
ROUTING = ROOT / "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv"
ROUTING_RECORD = ROOT / "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.md"
DIM_003_CONTRACT = ROOT / "hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.json"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
REVIEW_B = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_CHECKLIST_REV_A.md"
RFQ = ROOT / "hardware/CHINA_PROCUREMENT_RFQ.csv"
PROCUREMENT = ROOT / "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv"
RELEASE_CHECKLIST = ROOT / "hardware/PCB_RELEASE_CHECKLIST.csv"
CONTRACT = ROOT / "hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.json"
PACKET = ROOT / "hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.md"
RESPONSE = ROOT / "hardware/reviews/PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv"
RELEASE_GATE = ROOT / "hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md"
DECISIONS = ROOT / "docs/DECISION_LOG.csv"
DELIVERABLES = ROOT / "docs/DELIVERABLE_REGISTER_EVT_PRE_20.csv"
RISKS = ROOT / "docs/RISK_REGISTER.csv"
README = ROOT / "README.md"
BRANCH_SCOPE = ROOT / "BRANCH_SCOPE.md"
KICAD_README = ROOT / "hardware/kicad/README.md"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
NATIVE_WORKFLOW = ROOT / ".github/workflows/pcb-native.yml"
PWR_WORKFLOW = ROOT / ".github/workflows/pcb-pwr-schematic.yml"
HARDWARE_RELEASE_AUDIT = ROOT / "tools/audit_evt_pre_20_hardware_release.py"
RELEASE_AUDIT = ROOT / "tools/audit_evt_pre_20_release.py"
BASELINE_VALIDATOR = ROOT / "tools/validate_evt_pre_20.py"
KICAD_NATIVE_GATE = ROOT / "tools/kicad_native_gate.py"

STATE = "PASS_INTERNAL_STACKUP_COPPER_REQUEST_READY_EXTERNAL_RESPONSES_PENDING"
CONTRACT_STATUS = (
    "PACKET_READY_TWO_FABRICATOR_RESPONSES_REQUIRED_"
    "NOT_FOR_ROUTING_OR_MANUFACTURE"
)
REVIEW_B_STATUS = (
    "OPEN_CINHF_ECO_NATIVE_ERC_PDF_EVIDENCE_HUMAN_ACCEPTED_FITTED_2D_"
    "CLEARANCE_PRE_ROUTE_DIM_003_AND_"
    "STACKUP_REQUESTS_READY_ROUTING_PENDING"
)

AUTHORITY_INPUTS = [
    "hardware/kicad/PCB_RULES.md",
    "hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv",
    "hardware/POWER_DESIGN_BASELINE_REV_A.json",
    "hardware/POWER_DESIGN_CALC_REV_A.md",
    "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv",
    "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv",
    "hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.json",
    "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json",
    "hardware/reviews/PCB_PWR_REVIEW_B_CHECKLIST_REV_A.md",
    "hardware/CHINA_PROCUREMENT_RFQ.csv",
    "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv",
    "hardware/PCB_RELEASE_CHECKLIST.csv",
]

FABRICATOR_SLOTS = ["FAB-A", "FAB-B"]
QUESTION_IDS = [
    "STACKUP-CROSS-SECTION",
    "MATERIAL-THERMAL-SYSTEM",
    "FINISHED-THICKNESS",
    "COPPER-WEIGHT-PLATING",
    "HEAVY-COPPER-ETCH",
    "VIA-DRILL-PLATING",
    "THERMAL-VIA-FILL",
    "MIN-GEOMETRY-REGISTRATION",
    "MASK-FINISH",
    "COPPER-BALANCE-PANEL-WARPAGE",
    "NETTEST-TRACEABILITY-MICROSECTION",
    "DFM-CLOSURE",
]

QUESTION_TOKENS = {
    "STACKUP-CROSS-SECTION": ("four-layer", "f.cu", "core", "prepreg", "tolerances"),
    "MATERIAL-THERMAL-SYSTEM": ("tg", "td", "z-axis cte", "thermal conductivity", "lot-control"),
    "FINISHED-THICKNESS": ("1.60 mm", "tolerance", "dim-003"),
    "COPPER-WEIGHT-PLATING": ("outer copper", "inner copper", "hole-wall plating", "outer 2 oz", "inner 1 oz"),
    "HEAVY-COPPER-ETCH": ("etch compensation", "undercut", "final width", "spacing", "current capacity"),
    "VIA-DRILL-PLATING": ("finished drill", "annular ring", "aspect ratio", "hole-wall plating", "via arrays"),
    "THERMAL-VIA-FILL": ("thermal-via", "tenting", "plugging", "resin-fill", "inspection"),
    "MIN-GEOMETRY-REGISTRATION": ("minimum copper width", "spacing", "copper-to-edge", "registration", "hole-position"),
    "MASK-FINISH": ("solder-mask", "cured thickness", "surface finish", "assembly compatibility"),
    "COPPER-BALANCE-PANEL-WARPAGE": ("copper-balance", "panelization", "depanelization", "warpage"),
    "NETTEST-TRACEABILITY-MICROSECTION": ("100 percent net test", "ipc-356", "traceability", "microsection"),
    "DFM-CLOSURE": ("unique id", "severity", "owner", "disposition", "silent source changes", "blocker"),
}

RESPONSE_FIELDS = [
    "Gate_ID",
    "Fabricator_Slot",
    "Required_Party",
    "Requirement",
    "Required_Evidence",
    "Disposition",
    "Response_Value",
    "Response_Reference",
    "Responder",
    "Response_Date",
    "Blocking",
]

CONTROLLED_SOURCES = [
    BOARD,
    RULES,
    LAYER_AUTHORITY,
    POWER_BASELINE,
    POWER_CALC,
    PLACEMENT,
    ROUTING,
    ROUTING_RECORD,
    DIM_003_CONTRACT,
    STATUS,
    REVIEW_B,
    RFQ,
    PROCUREMENT,
    RELEASE_CHECKLIST,
    CONTRACT,
    PACKET,
    RESPONSE,
    RELEASE_GATE,
    DECISIONS,
    DELIVERABLES,
    RISKS,
    README,
    BRANCH_SCOPE,
    KICAD_README,
    CI_WORKFLOW,
    NATIVE_WORKFLOW,
    PWR_WORKFLOW,
    HARDWARE_RELEASE_AUDIT,
    RELEASE_AUDIT,
    BASELINE_VALIDATOR,
    KICAD_NATIVE_GATE,
    Path(__file__).resolve(),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None, f"CSV header missing: {relative(path)}")
        return list(reader.fieldnames), list(reader)


def validate_git_binding(commit_sha: str, require_clean_source: bool) -> None:
    require(re.fullmatch(r"[0-9a-f]{40}", commit_sha) is not None,
            f"invalid evidence commit SHA: {commit_sha!r}")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(head == commit_sha, f"evidence commit {commit_sha} != checked-out HEAD {head}")
    if require_clean_source:
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--", *[relative(path) for path in CONTROLLED_SOURCES]],
            cwd=ROOT,
            text=True,
        ).strip()
        require(not dirty, f"controlled PCB-PWR stackup-request source set is dirty: {dirty}")


def validate_board_and_bindings(contract: dict[str, Any]) -> dict[str, Any]:
    for path in CONTROLLED_SOURCES:
        require(path.is_file(), f"controlled source missing: {relative(path)}")
    require(contract.get("authority_inputs") == AUTHORITY_INPUTS,
            "PCB-PWR stackup request authority-input set differs")
    for item in AUTHORITY_INPUTS:
        require((ROOT / item).is_file(), f"authority input missing: {item}")

    board = Board.from_file(str(BOARD), encoding="utf-8")
    copper_layers = [str(layer.name) for layer in board.layers if str(layer.name).endswith(".Cu")]
    board_nets = {
        str(net.name) for net in board.nets
        if int(net.number) != 0 and str(net.name)
    }
    require(copper_layers == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
            f"PCB-PWR copper layers differ: {copper_layers}")
    require(float(board.general.thickness) == 1.6,
            f"provisional PCB-PWR thickness differs: {board.general.thickness}")
    require(len(board.footprints) == 62,
            f"PCB-PWR footprint count is {len(board.footprints)}, expected 62")
    require(len(board_nets) == 31,
            f"PCB-PWR net count is {len(board_nets)}, expected 31")
    require(len(board.traceItems) == 0 and len(board.zones) == 0,
            "stackup request must be revised after routed copper or zones appear")

    expected_binding = {
        "native_board": relative(BOARD),
        "native_board_semantic_sha256": semantic_board_sha256(board),
        "placement_authority": relative(PLACEMENT),
        "placement_authority_sha256": sha256(PLACEMENT),
        "routing_authority": relative(ROUTING),
        "routing_authority_sha256": sha256(ROUTING),
        "layer_count_authority": relative(LAYER_AUTHORITY),
        "layer_count_authority_sha256": sha256(LAYER_AUTHORITY),
        "power_design_baseline": relative(POWER_BASELINE),
        "power_design_baseline_sha256": sha256(POWER_BASELINE),
        "power_design_calculation": relative(POWER_CALC),
        "power_design_calculation_sha256": sha256(POWER_CALC),
        "dim_003_request": relative(DIM_003_CONTRACT),
        "dim_003_request_sha256": sha256(DIM_003_CONTRACT),
    }
    require(contract.get("source_binding") == expected_binding,
            "PCB-PWR stackup request source-hash binding differs")
    return {
        "path": relative(BOARD),
        "semantic_sha256": semantic_board_sha256(board),
        "copper_layers": len(copper_layers),
        "footprints": len(board.footprints),
        "nets": len(board_nets),
        "trace_items": len(board.traceItems),
        "copper_zones": len(board.zones),
    }


def validate_request_basis(contract: dict[str, Any]) -> dict[str, Any]:
    _, layer_rows = read_csv(LAYER_AUTHORITY)
    rows = [row for row in layer_rows if row.get("Board") == "PCB-PWR"]
    require(len(rows) == 1, "PCB-PWR layer-count authority missing or duplicated")
    layer = rows[0]
    require(
        layer.get("Copper_Layers") == "4"
        and layer.get("Native_Layer_Order") == "F.Cu;In1.Cu;In2.Cu;B.Cu"
        and layer.get("Layer_Count_Status") == "FROZEN_REV_A"
        and layer.get("Board_Thickness_mm") == "1.6"
        and layer.get("Thickness_Status") == "PROVISIONAL_DIM_003_OPEN"
        and layer.get("Copper_Weight_Target") == "outer 2 oz target; inner 1 oz target"
        and layer.get("Copper_Weight_Status") == "TARGET_ONLY_NOT_FROZEN"
        and layer.get("Layer_Function_Intent") == "POWER_SIGNAL;REFERENCE;POWER_RETURN;POWER_SIGNAL",
        "PCB-PWR layer-count/request basis differs",
    )

    expected_basis = {
        "provisional_outline_mm": [90.0, 60.0],
        "outline_status": "PROVISIONAL_DIM_003_OPEN_NOT_A_FABRICATION_DIMENSION",
        "finished_thickness_target_mm": 1.6,
        "finished_thickness_status": "PROVISIONAL_DIM_003_OPEN",
        "copper_layers": 4,
        "native_layer_order": ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
        "layer_function_intent": ["POWER_SIGNAL", "REFERENCE", "POWER_RETURN", "POWER_SIGNAL"],
        "layer_function_status": "REQUEST_BASIS_ONLY_VENDOR_ALTERNATIVE_REQUIRES_CONTROLLED_REVIEW",
        "base_material_family": "FR-4",
        "copper_weight_targets": {
            "outer_oz": 2.0,
            "inner_oz": 1.0,
            "status": "REQUEST_TARGETS_ONLY_NOT_FROZEN",
        },
        "final_stackup_frozen": False,
        "material_system_frozen": False,
        "finished_thickness_frozen": False,
        "copper_weights_frozen": False,
        "surface_finish_frozen": False,
        "numeric_fabrication_rules_frozen": False,
        "native_trace_items": 0,
        "native_copper_zones": 0,
    }
    require(contract.get("board_request_basis") == expected_basis,
            "PCB-PWR provisional stackup request basis differs")
    return expected_basis


def validate_power_geometry_boundary(contract: dict[str, Any]) -> dict[str, Any]:
    fields, rows = read_csv(ROUTING)
    require(fields[:3] == ["Net_Name", "Route_Class", "Reference_Domain"] and len(rows) == 31,
            "PCB-PWR routing-authority structure or row count differs")
    by_net = {row["Net_Name"]: row for row in rows}
    require(len(by_net) == len(rows), "PCB-PWR routing authority has duplicate nets")
    for net in ("VBAT_RAW", "VBAT_FUSED", "VBAT_PROTECTED", "VBAT_SYS"):
        require(by_net[net]["Route_Class"] == "POWER_INPUT_HIGH_CURRENT"
                and "5A" in by_net[net]["Current_Basis"],
                f"{net}: 5 A high-current basis differs")
    require("3P3A" in by_net["3V8_MODEM"]["Current_Basis"],
            "3V8_MODEM 3.3 A peak basis differs")
    require("4A" in by_net["3V3_DIGITAL"]["Current_Basis"],
            "3V3_DIGITAL 4 A rating basis differs")
    require("0P3A" in by_net["1V8_MIC"]["Current_Basis"],
            "1V8_MIC 0.3 A rating basis differs")

    expected = {
        "system_expected_max_input_current_a": 5.0,
        "system_fault_and_transient_envelope_status": "OPEN",
        "buck_channel_rating_a": 4.0,
        "modem_3v8_peak_basis_a": 3.3,
        "microphone_1v8_regulator_rating_a": 0.3,
        "ambient_requirement_c": [-40, 70],
        "dc_drop_limit_v": None,
        "allowed_conductor_temperature_rise_c": None,
        "minimum_trace_width_mm": None,
        "minimum_plane_neck_mm": None,
        "via_pad_mm": None,
        "via_finished_drill_mm": None,
        "via_array_count": None,
        "thermal_via_geometry": None,
        "numeric_geometry_authority": (
            "SELECTED_FABRICATION_INPUTS_PLUS_PROJECT_CURRENT_DENSITY_DC_DROP_"
            "FAULT_ENERGY_AND_PLUS70C_THERMAL_REVIEW_REQUIRED"
        ),
    }
    require(contract.get("power_geometry_boundary") == expected,
            "PCB-PWR power-geometry no-guess boundary differs")
    return expected


def validate_response_register(contract: dict[str, Any]) -> list[dict[str, str]]:
    fields, rows = read_csv(RESPONSE)
    require(fields == RESPONSE_FIELDS, f"PCB-PWR stackup response fields differ: {fields}")
    require(len(rows) == 24, f"PCB-PWR stackup response count is {len(rows)}, expected 24")
    expected_ids = [f"{slot}-{question}" for slot in FABRICATOR_SLOTS for question in QUESTION_IDS]
    require([row["Gate_ID"] for row in rows] == expected_ids,
            "PCB-PWR stackup gate order or membership differs")
    blank_fields = ("Response_Value", "Response_Reference", "Responder", "Response_Date")
    for row in rows:
        slot = row["Fabricator_Slot"]
        require(slot in FABRICATOR_SLOTS, f"unexpected fabricator slot: {slot}")
        question = row["Gate_ID"].removeprefix(f"{slot}-")
        require(question in QUESTION_TOKENS, f"unexpected stackup question: {question}")
        require(row["Required_Party"] == "FABRICATOR",
                f"{row['Gate_ID']}: required party differs")
        requirement = row["Requirement"].lower()
        for token in QUESTION_TOKENS[question]:
            require(token in requirement,
                    f"{row['Gate_ID']}: requirement missing token {token!r}")
        require(bool(row["Required_Evidence"].strip()),
                f"{row['Gate_ID']}: evidence requirement is blank")
        require(row["Disposition"] == "PENDING_EXTERNAL_RESPONSE",
                f"{row['Gate_ID']}: unaccepted packet has disposition {row['Disposition']!r}")
        require(all(not row[field].strip() for field in blank_fields),
                f"{row['Gate_ID']}: response attribution populated without acceptance")
        require(row["Blocking"] == "YES", f"{row['Gate_ID']}: gate is not blocking")

    by_slot_question = {
        (row["Fabricator_Slot"], row["Gate_ID"].removeprefix(f"{row['Fabricator_Slot']}-")): row
        for row in rows
    }
    for question in QUESTION_IDS:
        first = by_slot_question[("FAB-A", question)]
        second = by_slot_question[("FAB-B", question)]
        for field in ("Required_Party", "Requirement", "Required_Evidence", "Blocking"):
            require(first[field] == second[field],
                    f"{question}: FAB-A/FAB-B request field {field} differs")

    require(contract.get("required_fabricator_slots") == FABRICATOR_SLOTS,
            "required fabricator slots differ")
    require(contract.get("required_question_ids") == QUESTION_IDS,
            "required question membership differs")
    require(contract.get("external_response") == {
        "response_register": relative(RESPONSE),
        "required_rows": 24,
        "pending_rows": 24,
        "accepted_fabricator_slots": 0,
        "selected_fabricator_slot": None,
        "complete": False,
    }, "PCB-PWR stackup external-response interlock differs")
    return rows


def validate_release_interlocks(contract: dict[str, Any]) -> None:
    require(contract.get("accepted_authority") == {
        "selected_stackup": None,
        "selected_material_system": None,
        "accepted_finished_thickness_mm": None,
        "accepted_outer_finished_copper_um": None,
        "accepted_inner_finished_copper_um": None,
        "accepted_hole_wall_plating_um": None,
        "accepted_minimum_geometry": None,
        "accepted_via_construction": None,
        "accepted_surface_finish": None,
    }, "PCB-PWR accepted stackup authority contains premature values")
    require(contract.get("release_interlock") == {
        "two_fabricator_responses_accepted": False,
        "fabricator_selected": False,
        "stackup_accepted": False,
        "copper_weights_and_plating_accepted": False,
        "manufacturing_minimums_accepted": False,
        "dim_003_accepted": False,
        "current_density_dc_drop_fault_thermal_calculation_accepted": False,
        "numeric_power_geometry_authorized": False,
        "routing_authorized": False,
        "review_b_complete": False,
        "manufacturing_release": False,
        "fabrication_authorized": False,
    }, "PCB-PWR stackup release interlock differs")


def validate_integrations() -> None:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    handoff = status.get("stackup_copper_handoff", {})
    control = handoff.get("control", {}) if isinstance(handoff, dict) else {}
    require(
        handoff.get("request_packet") == relative(PACKET)
        and handoff.get("machine_contract") == relative(CONTRACT)
        and handoff.get("response_register") == relative(RESPONSE)
        and handoff.get("independent_audit") == relative(Path(__file__).resolve()),
        "PCB-PWR status does not bind stackup/copper handoff",
    )
    require(control == {
        "state": STATE,
        "required_fabricator_slots": 2,
        "required_response_rows": 24,
        "accepted_fabricator_slots": 0,
        "accepted_response_rows": 0,
        "selected_fabricator_slot": None,
        "complete": False,
        "stackup_accepted": False,
        "copper_weights_and_plating_accepted": False,
        "numeric_power_geometry_authorized": False,
        "routing_authorized": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }, "PCB-PWR status stackup/copper control differs")
    require(status.get("review_b", {}).get("status") == REVIEW_B_STATUS,
            "PCB-PWR Review-B status does not expose stackup request readiness")

    integrations = {
        REVIEW_B: ("0/24", "0/2", "PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv"),
        RELEASE_GATE: ("PCB-PWR stackup/copper", "0/24", "0/2"),
        RISKS: ("R-027", "0/2", "stackup/copper"),
        DELIVERABLES: ("HW-P-005", "24-row", "two-fabricator"),
        DECISIONS: ("DEC-055", "24-row", "two independent fabricators"),
        README: ("PCB-PWR", "0/24", "stackup/copper"),
        BRANCH_SCOPE: ("PCB-PWR", "stackup/copper", "0/24"),
        KICAD_README: ("PCB_PWR_STACKUP_COPPER_REQUEST_REV_A", "0/24"),
        ROUTING_RECORD: ("0/24", "PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv"),
        CI_WORKFLOW: ("audit_pcb_pwr_stackup_copper_request_rev_a.py", "pcb_pwr_stackup_copper_request_rev_a.json"),
        NATIVE_WORKFLOW: ("audit_pcb_pwr_stackup_copper_request_rev_a.py", "stackup_copper_request_audit.json"),
        PWR_WORKFLOW: ("audit_pcb_pwr_stackup_copper_request_rev_a.py", "stackup_copper_request_audit.json"),
        HARDWARE_RELEASE_AUDIT: ("pcb_pwr_stackup_copper_request_packet", "accepted_fabricator_slots", "numeric_power_geometry_authorized"),
        RELEASE_AUDIT: ("PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.json", "audit_pcb_pwr_stackup_copper_request_rev_a.py"),
        BASELINE_VALIDATOR: ("DEC-055", "IMPLEMENTED_TWO_FABRICATOR_RESPONSES_PENDING", "0/24"),
        KICAD_NATIVE_GATE: ("PCB_PWR_STACKUP_COPPER_AUDIT", "stackup_copper_request_state"),
    }
    for path, tokens in integrations.items():
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            require(token in text,
                    f"{relative(path)} missing PCB-PWR stackup integration token {token!r}")

    packet_text = " ".join(PACKET.read_text(encoding="utf-8").split())
    for token in (
        "0 OF 24 ROWS ACCEPTED",
        "not a released outline",
        "contains no accepted trace width",
        "does not by itself authorize numeric geometry or routing",
    ):
        require(token in packet_text,
                f"PCB-PWR stackup packet missing boundary statement {token!r}")


def audit() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    require(contract.get("schema") == "dioneya-pcb-pwr-stackup-copper-request-v1",
            "PCB-PWR stackup contract schema differs")
    require(
        contract.get("configuration") == "EVT-PRE-20 Rev.A"
        and contract.get("assembly") == "PCB-PWR"
        and contract.get("revision") == "A",
        "PCB-PWR stackup contract identity differs",
    )
    require(contract.get("status") == CONTRACT_STATUS,
            "PCB-PWR stackup contract status differs")
    board = validate_board_and_bindings(contract)
    basis = validate_request_basis(contract)
    power_boundary = validate_power_geometry_boundary(contract)
    rows = validate_response_register(contract)
    validate_release_interlocks(contract)
    validate_integrations()
    return {
        "schema": "dioneya-pcb-pwr-stackup-copper-request-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-PWR",
        "status": STATE,
        "internal_packet_complete": True,
        "packet": relative(PACKET),
        "machine_contract": relative(CONTRACT),
        "response_register": relative(RESPONSE),
        "required_fabricator_slots": FABRICATOR_SLOTS,
        "required_response_rows": len(rows),
        "accepted_fabricator_slots": 0,
        "accepted_response_rows": 0,
        "selected_fabricator_slot": None,
        "complete": False,
        "board": board,
        "request_basis": basis,
        "power_geometry_boundary": power_boundary,
        "stackup_accepted": False,
        "copper_weights_and_plating_accepted": False,
        "numeric_power_geometry_authorized": False,
        "routing_authorized": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--commit-sha", default="")
    parser.add_argument("--require-clean-source", action="store_true")
    args = parser.parse_args()
    if args.commit_sha:
        validate_git_binding(args.commit_sha, args.require_clean_source)
    elif args.require_clean_source:
        raise RuntimeError("--require-clean-source requires --commit-sha")

    result = audit()
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("PCB-PWR stackup/copper request audit PASS")
    print("24/24 blocking questions present; 0 accepted; numeric power geometry, routing and manufacture remain prohibited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
