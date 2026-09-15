#!/usr/bin/env python3
"""Audit the bounded PCB-MAIN stackup/impedance request packet.

The packet may prove only that a controlled request and blank two-fabricator
response register are ready.  It must never promote provisional construction
or guessed impedance geometry into routing or manufacturing authority.
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


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
RULES = ROOT / "hardware/kicad/PCB_RULES.md"
MECHANICAL = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
PLACEMENT = ROOT / "hardware/PCB_MAIN_PLACEMENT_REPACK_REV_A.csv"
ROUTING = ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv"
ROUTING_RECORD = ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.md"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
RFQ = ROOT / "hardware/CHINA_PROCUREMENT_RFQ.csv"
PROCUREMENT = ROOT / "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv"
DOUBLE_REVIEW = ROOT / "hardware/PCB_DOUBLE_REVIEW_GATE.md"
RELEASE_CHECKLIST = ROOT / "hardware/PCB_RELEASE_CHECKLIST.csv"
REVIEW_B_CHECKLIST = ROOT / "hardware/reviews/PCB_MAIN_REVIEW_B_CHECKLIST_REV_A.md"
RELEASE_GATE = ROOT / "hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md"
CONTRACT = ROOT / "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.json"
PACKET = ROOT / "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.md"
RESPONSE = ROOT / "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_RESPONSE_REV_A.csv"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
NATIVE_WORKFLOW = ROOT / ".github/workflows/pcb-native.yml"
HARDWARE_RELEASE_AUDIT = ROOT / "tools/audit_evt_pre_20_hardware_release.py"

FABRICATOR_SLOTS = ["FAB-A", "FAB-B"]
QUESTION_IDS = [
    "STACKUP-CROSS-SECTION",
    "MATERIAL-DK-DF",
    "COPPER-PLATING",
    "RF50-GEOMETRY",
    "USB90-GEOMETRY",
    "IMPEDANCE-TOLERANCE",
    "IMPEDANCE-COUPON",
    "MIN-GEOMETRY-REGISTRATION",
    "VIA-DRILL",
    "MASK-FINISH",
    "PANEL-NETTEST-DFM",
]

RF_NETS = [
    "CELL_RF",
    "CELL_RF_ANT",
    "GNSS_RF_ANT_BIASED",
    "GNSS_RF_DC_BLOCK",
    "GNSS_RF_FILTERED",
    "LORA_RF_ANT",
    "LORA_RF_MODULE",
]
USB_PAIR_GROUPS = {
    "USB_MAIN_MCU_SEGMENT": ["USB_DM_U1", "USB_DP_U1"],
    "USB_MAIN_CONNECTOR_SEGMENT": ["USB_DM_CONN", "USB_DP_CONN"],
    "USB_CELL_MODEM_SEGMENT": ["CELL_USB_DM_U8", "CELL_USB_DP_U8"],
    "USB_CELL_FIXTURE_SEGMENT": ["CELL_USB_DM_TP", "CELL_USB_DP_TP"],
}

AUTHORITY_INPUTS = [
    "hardware/kicad/PCB_RULES.md",
    "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_PLACEMENT_REPACK_REV_A.csv",
    "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv",
    "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json",
    "hardware/CHINA_PROCUREMENT_RFQ.csv",
    "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv",
    "hardware/PCB_DOUBLE_REVIEW_GATE.md",
    "hardware/PCB_RELEASE_CHECKLIST.csv",
]

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

QUESTION_TOKENS = {
    "STACKUP-CROSS-SECTION": ["six-layer", "1.60 mm", "core", "prepreg", "tolerance"],
    "MATERIAL-DK-DF": ["tg", "dk", "df", "test method", "frequency", "lot-control"],
    "COPPER-PLATING": ["outer copper", "inner copper", "hole-wall plating", "tolerances"],
    "RF50-GEOMETRY": ["50 ohm", "single-ended", "width", "mask model", "solver frequency"],
    "USB90-GEOMETRY": ["90 ohm", "differential", "trace width", "pair gap", "solver frequency"],
    "IMPEDANCE-TOLERANCE": ["guaranteed production tolerance", "50 ohm", "90 ohm"],
    "IMPEDANCE-COUPON": ["50 ohm", "90 ohm", "coupon", "measurement method", "lot report"],
    "MIN-GEOMETRY-REGISTRATION": ["minimum copper width", "spacing", "registration", "copper-to-edge"],
    "VIA-DRILL": ["finished drill", "annular ring", "aspect ratio", "plating"],
    "MASK-FINISH": ["solder-mask", "cured thickness", "dielectric model", "surface finish"],
    "PANEL-NETTEST-DFM": ["100 percent net-test", "ipc-356", "traceability", "dfm"],
}

CONTROLLED_SOURCES = [
    BOARD,
    RULES,
    MECHANICAL,
    PLACEMENT,
    ROUTING,
    ROUTING_RECORD,
    STATUS,
    RFQ,
    PROCUREMENT,
    DOUBLE_REVIEW,
    RELEASE_CHECKLIST,
    REVIEW_B_CHECKLIST,
    RELEASE_GATE,
    CONTRACT,
    PACKET,
    RESPONSE,
    CI_WORKFLOW,
    NATIVE_WORKFLOW,
    HARDWARE_RELEASE_AUDIT,
    Path(__file__).resolve(),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None, f"CSV header missing: {relative(path)}")
        return list(reader.fieldnames), list(reader)


def validate_git_binding(commit_sha: str, require_clean_source: bool) -> None:
    require(re.fullmatch(r"[0-9a-f]{40}", commit_sha) is not None,
            f"invalid evidence commit SHA: {commit_sha!r}")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    require(head == commit_sha, f"evidence commit {commit_sha} != checked-out HEAD {head}")
    if require_clean_source:
        dirty = subprocess.check_output(
            [
                "git", "status", "--porcelain", "--",
                *[relative(path) for path in CONTROLLED_SOURCES],
            ],
            cwd=ROOT,
            text=True,
        ).strip()
        require(not dirty, f"controlled stackup-request source set is dirty: {dirty}")


def validate_board_and_bindings(contract: dict[str, Any]) -> dict[str, Any]:
    for path in CONTROLLED_SOURCES:
        require(path.is_file(), f"controlled source is missing: {relative(path)}")
    require(contract.get("authority_inputs") == AUTHORITY_INPUTS,
            "stackup request authority-input set mismatch")
    for item in AUTHORITY_INPUTS:
        require((ROOT / item).is_file(), f"authority input is missing: {item}")

    expected_binding = {
        "native_board": relative(BOARD),
        "native_board_sha256": sha256(BOARD),
        "mechanical_authority": relative(MECHANICAL),
        "mechanical_authority_sha256": sha256(MECHANICAL),
        "placement_manifest": relative(PLACEMENT),
        "placement_manifest_sha256": sha256(PLACEMENT),
        "routing_authority": relative(ROUTING),
        "routing_authority_sha256": sha256(ROUTING),
    }
    require(contract.get("source_binding") == expected_binding,
            "stackup request source-hash binding mismatch")

    board = Board.from_file(str(BOARD), encoding="utf-8")
    copper_layers = [layer.name for layer in board.layers if layer.name.endswith(".Cu")]
    require(copper_layers == ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"],
            f"native board copper-layer set differs: {copper_layers}")
    require(float(board.general.thickness) == 1.6,
            f"native board thickness differs: {board.general.thickness}")
    require(len(board.traceItems) == 0 and len(board.zones) == 0,
            "stackup request must be revised after routed copper or zones appear")
    board_nets = {
        str(net.name) for net in board.nets
        if int(net.number) != 0 and str(net.name)
    }
    require(len(board_nets) == 186, f"native board net count is {len(board_nets)}, expected 186")

    _, mechanical_rows = read_csv(MECHANICAL)
    outline = [row for row in mechanical_rows if row.get("Record_ID") == "MECH-001"]
    require(len(outline) == 1, "MECH-001 board-outline authority missing or duplicated")
    row = outline[0]
    require(row.get("Feature_Type") == "BOARD_OUTLINE"
            and row.get("Geometry") == "ROUNDED_RECT_R3"
            and row.get("Extent_X_mm") == "110.00"
            and row.get("Extent_Y_mm") == "75.00"
            and row.get("Z_Max_mm") == "1.60"
            and row.get("Disposition") == "LOCKED_CAPTURE_INPUT",
            "MECH-001 board-outline request basis differs")

    basis = contract.get("board_request_basis", {})
    require(basis == {
        "outline_mm": [110.0, 75.0],
        "finished_thickness_mm": 1.6,
        "copper_layers": 6,
        "base_material_family": "FR-4",
        "layer_function_intent": [
            "SIGNAL_RF", "REFERENCE", "POWER_DOMAINS",
            "SIGNAL", "REFERENCE", "SIGNAL",
        ],
        "layer_function_status":
            "REQUEST_BASIS_ONLY_VENDOR_ALTERNATIVE_REQUIRES_CONTROLLED_REVIEW",
        "final_stackup_frozen": False,
        "material_system_frozen": False,
        "copper_weights_frozen": False,
        "surface_finish_frozen": False,
        "numeric_fabrication_rules_frozen": False,
        "native_trace_items": 0,
        "native_copper_zones": 0,
    }, "board request basis or provisional/frozen interlock differs")
    return {
        "path": relative(BOARD),
        "sha256": sha256(BOARD),
        "outline_mm": [110.0, 75.0],
        "finished_thickness_mm": 1.6,
        "copper_layers": len(copper_layers),
        "net_count": len(board_nets),
        "trace_items": len(board.traceItems),
        "copper_zones": len(board.zones),
    }


def validate_impedance_scope(contract: dict[str, Any]) -> dict[str, Any]:
    routing_fields, rows = read_csv(ROUTING)
    require(routing_fields[:3] == ["Net_Name", "Route_Class", "Reference_Domain"]
            and len(rows) == 186,
            "routing-authority structure or row count differs")
    by_net = {row["Net_Name"]: row for row in rows}
    require(len(by_net) == len(rows), "routing authority has duplicate net names")

    actual_rf = sorted(
        name for name, row in by_net.items() if row.get("Route_Class") == "RF_50OHM"
    )
    require(actual_rf == sorted(RF_NETS), f"50-ohm routing scope differs: {actual_rf}")
    for name in RF_NETS:
        row = by_net[name]
        require(row.get("Impedance_Target") == "50_OHM_SINGLE_ENDED_FACTORY_STACKUP_PENDING"
                and row.get("Geometry_Rule") == "NO_NUMERIC_WIDTH_UNTIL_FACTORY_STACKUP",
                f"{name}: 50-ohm stackup interlock differs")

    actual_usb: dict[str, list[str]] = {}
    for name, row in by_net.items():
        if row.get("Route_Class") == "USB_90OHM_DIFF":
            actual_usb.setdefault(row.get("Pair_Group", ""), []).append(name)
            require(row.get("Impedance_Target") ==
                    "90_OHM_DIFFERENTIAL_FACTORY_STACKUP_PENDING"
                    and row.get("Geometry_Rule") ==
                    "NO_NUMERIC_WIDTH_OR_GAP_UNTIL_FACTORY_STACKUP",
                    f"{name}: 90-ohm stackup interlock differs")
    actual_usb = {key: sorted(value) for key, value in actual_usb.items()}
    expected_usb = {key: sorted(value) for key, value in USB_PAIR_GROUPS.items()}
    require(actual_usb == expected_usb, f"90-ohm USB pair scope differs: {actual_usb}")

    requests = contract.get("impedance_requests", {})
    rf = requests.get("rf_single_ended", {})
    require(rf.get("target_ohm") == 50.0
            and rf.get("nets") == RF_NETS
            and rf.get("preferred_route_reference") ==
            "OUTER_SIGNAL_LAYER_TO_ADJACENT_UNINTERRUPTED_LOCAL_REFERENCE",
            "50-ohm request scope differs")
    for field in (
        "target_tolerance_percent", "solver_frequency_hz", "trace_width_mm",
        "copper_to_reference_mm", "solder_mask_model",
    ):
        require(rf.get(field) is None, f"50-ohm {field} was guessed or prematurely frozen")

    usb = requests.get("usb_differential", {})
    require(usb.get("target_ohm") == 90.0
            and usb.get("pair_groups") == USB_PAIR_GROUPS
            and usb.get("preferred_route_reference") ==
            "ONE_SIGNAL_LAYER_TO_ADJACENT_UNINTERRUPTED_LOCAL_REFERENCE",
            "90-ohm request scope differs")
    for field in (
        "target_tolerance_percent", "solver_frequency_hz", "trace_width_mm",
        "pair_gap_mm", "copper_to_reference_mm", "solder_mask_model",
    ):
        require(usb.get(field) is None, f"90-ohm {field} was guessed or prematurely frozen")
    require(requests.get("numeric_geometry_authority") ==
            "SELECTED_FABRICATOR_RESPONSE_PLUS_PROJECT_RF_SI_REVIEW_REQUIRED",
            "numeric geometry authority interlock differs")
    return {
        "routing_authority_path": relative(ROUTING),
        "routing_authority_sha256": sha256(ROUTING),
        "routing_rows": len(rows),
        "rf_50ohm_nets": RF_NETS,
        "usb_90ohm_pair_groups": USB_PAIR_GROUPS,
        "numeric_geometry_frozen": False,
    }


def validate_response_register(contract: dict[str, Any]) -> dict[str, Any]:
    fields, rows = read_csv(RESPONSE)
    require(fields == RESPONSE_FIELDS, f"response-register fields differ: {fields}")
    expected_gate_ids = [
        f"{slot}-{question}" for slot in FABRICATOR_SLOTS for question in QUESTION_IDS
    ]
    by_gate = {row.get("Gate_ID", ""): row for row in rows}
    require(len(rows) == len(by_gate) == 22
            and [row.get("Gate_ID") for row in rows] == expected_gate_ids,
            "response register is not the ordered 2 x 11 gate cross-product")

    canonical_text: dict[str, tuple[str, str]] = {}
    for slot in FABRICATOR_SLOTS:
        for question in QUESTION_IDS:
            gate_id = f"{slot}-{question}"
            row = by_gate[gate_id]
            require(row.get("Fabricator_Slot") == slot
                    and row.get("Required_Party") == "FABRICATOR",
                    f"{gate_id}: fabricator identity differs")
            requirement = row.get("Requirement", "")
            evidence = row.get("Required_Evidence", "")
            require(requirement and evidence, f"{gate_id}: requirement/evidence missing")
            lower = requirement.lower()
            require(all(token in lower for token in QUESTION_TOKENS[question]),
                    f"{gate_id}: question semantics incomplete")
            if question in canonical_text:
                require(canonical_text[question] == (requirement, evidence),
                        f"{gate_id}: fabricator slots ask different questions")
            else:
                canonical_text[question] = (requirement, evidence)
            require(row.get("Disposition") == "PENDING_EXTERNAL_RESPONSE"
                    and row.get("Blocking") == "YES",
                    f"{gate_id}: response is not pending/blocking")
            require(all(not row.get(field) for field in (
                "Response_Value", "Response_Reference", "Responder", "Response_Date",
            )), f"{gate_id}: unsigned response fields are not blank")

    require(contract.get("required_fabricator_slots") == FABRICATOR_SLOTS
            and contract.get("required_question_ids") == QUESTION_IDS,
            "machine contract response matrix differs")
    external = contract.get("external_response", {})
    require(external == {
        "response_register": relative(RESPONSE),
        "required_rows": 22,
        "pending_rows": 22,
        "accepted_fabricator_slots": 0,
        "selected_fabricator_slot": None,
        "complete": False,
    }, "machine contract external-response state differs")
    return {
        "path": relative(RESPONSE),
        "sha256": sha256(RESPONSE),
        "questions_per_fabricator": len(QUESTION_IDS),
        "rows": len(rows),
        "pending_rows": len(rows),
        "accepted_fabricator_slots": 0,
        "selected_fabricator_slot": None,
    }


def validate_release_interlocks(contract: dict[str, Any]) -> None:
    _, rfq_rows = read_csv(RFQ)
    rfq = {row["RFQ_ID"]: row for row in rfq_rows}
    main_fab = rfq.get("RFQ-023", {})
    require(main_fab.get("BOM_Item_IDs") == "PCB-MAIN"
            and main_fab.get("Preferred_channel") ==
            "Two independent qualified PCB fabricators"
            and "controlled six-layer stackup" in main_fab.get("Blocking_check", "")
            and "impedance coupon" in main_fab.get("Blocking_check", "")
            and "no fabrication while routing Review B DRC CAM or DFM is open"
            in main_fab.get("Blocking_check", ""),
            "RFQ-023 does not preserve two-fabricator stackup/release interlocks")

    _, procurement_rows = read_csv(PROCUREMENT)
    procurement = {row["Procurement_ID"]: row for row in procurement_rows}
    bare_pcb = procurement.get("PR-013", {})
    require(bare_pcb.get("Assemblies") == "PCB-MAIN"
            and bare_pcb.get("MPN") == "TBD"
            and bare_pcb.get("Status") == "RFQ_REQUIRED"
            and bare_pcb.get("China_source_policy") == "Two independent fab quotations"
            and all(token in bare_pcb.get("Incoming_control", "")
                    for token in ("Coupon", "stackup", "impedance", "netlist test")),
            "PR-013 does not preserve two-fabricator stackup evidence requirements")

    double_review = DOUBLE_REVIEW.read_text(encoding="utf-8")
    require("Fabrication stackup, copper weights, minimum geometry and finish are accepted"
            in double_review
            and "Factory DFM review is archived" in double_review
            and "DFM response/closure" in double_review,
            "double-review gate does not preserve stackup/DFM acceptance")

    _, checklist_rows = read_csv(RELEASE_CHECKLIST)
    checklist = {row["Check_ID"]: row for row in checklist_rows}
    require(checklist.get("PCB-MAIN-008", {}).get("Status") == "OPEN"
            and checklist.get("PCB-MAIN-008", {}).get("Required_Evidence") ==
            "Stackup field solve and layout review",
            "PCB-MAIN-008 RF release gate was advanced or weakened")
    require(checklist.get("PCB-GEN-009", {}).get("Status") == "OPEN"
            and checklist.get("PCB-GEN-009", {}).get("Required_Evidence") ==
            "DFM report and dispositions",
            "PCB-GEN-009 DFM release gate was advanced or weakened")

    interlock = contract.get("release_interlock", {})
    require(interlock == {
        "stackup_accepted": False,
        "rf_50ohm_numeric_geometry_authorized": False,
        "usb_90ohm_numeric_geometry_authorized": False,
        "routing_authorized": False,
        "review_b_complete": False,
        "manufacturing_release": False,
        "fabrication_authorized": False,
    }, "machine contract release interlock differs")


def validate_status_packet_and_ci(contract: dict[str, Any]) -> None:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    handoff = status.get("review_b", {}).get("evidence", {}).get(
        "stackup_impedance_handoff", {}
    )
    require(handoff == {
        "complete": False,
        "status": "PACKET_READY_TWO_FABRICATOR_RESPONSES_REQUIRED",
        "internal_packet_complete": True,
        "packet": relative(PACKET),
        "machine_contract": relative(CONTRACT),
        "response_register": relative(RESPONSE),
        "audit": "artifacts/pcb_main_stackup_impedance_request_rev_a.json",
        "required_fabricator_slots": FABRICATOR_SLOTS,
        "accepted_fabricator_response_count": 0,
        "selected_fabricator_slot": None,
        "stackup_accepted": False,
        "rf_50ohm_numeric_geometry_accepted": False,
        "usb_90ohm_numeric_geometry_accepted": False,
        "routing_authorized": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }, "PCB-MAIN capture status stackup/impedance handoff differs")
    require(status.get("review_b", {}).get("complete") is False
            and status.get("manufacturing_release") is False,
            "internal request packet advanced Review B or manufacturing release")

    packet = PACKET.read_text(encoding="utf-8")
    packet_flat = " ".join(packet.split())
    packet_tokens = [
        "NOT FOR MANUFACTURE",
        contract["source_binding"]["native_board_sha256"],
        contract["source_binding"]["mechanical_authority_sha256"],
        contract["source_binding"]["placement_manifest_sha256"],
        contract["source_binding"]["routing_authority_sha256"],
        "zero tracks, zero vias and zero copper zones",
        "All 22 rows",
        "FAB-A",
        "FAB-B",
        "50-ohm",
        "90-ohm",
        "explicitly `null`",
        "`GND_MODEM`, `GND_DIGITAL` and `GND_MIC` remain separate",
        "does not automatically authorize routing",
        relative(RESPONSE),
    ]
    require(all(" ".join(token.split()) in packet_flat for token in packet_tokens),
            "human-readable stackup/impedance request packet is incomplete")

    routing_record = ROUTING_RECORD.read_text(encoding="utf-8")
    review_b = REVIEW_B_CHECKLIST.read_text(encoding="utf-8")
    release_gate = RELEASE_GATE.read_text(encoding="utf-8")
    require(relative(CONTRACT) in routing_record and relative(RESPONSE) in routing_record,
            "routing authority record does not reference the controlled request/response")
    require("0/2 accepted fabricator responses" in review_b,
            "Review-B checklist does not expose the pending two-fabricator gate")
    require("0/2 fabricator responses accepted" in release_gate,
            "hardware release gate does not expose the pending stackup responses")

    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    native = NATIVE_WORKFLOW.read_text(encoding="utf-8")
    command = "audit_pcb_main_stackup_impedance_request_rev_a.py"
    require(command in ci and command in native,
            "stackup request audit is not enforced by both CI workflows")
    for workflow, name in ((ci, "CI"), (native, "PCB Native Gate")):
        require("--commit-sha \"$GITHUB_SHA\"" in workflow
                and "--require-clean-source" in workflow,
                f"{name} lacks commit/clean-source audit binding")
    for source in (relative(CONTRACT), relative(PACKET), relative(RESPONSE)):
        require(source in ci and source in native,
                f"workflow artifact/source coverage missing for {source}")
    hardware_release = HARDWARE_RELEASE_AUDIT.read_text(encoding="utf-8")
    require("pcb_main_stackup_impedance_request_packet" in hardware_release
            and "pcb_main_stackup_impedance_acceptance" in hardware_release
            and "accepted_fabricator_response_count" in hardware_release,
            "hardware production-release audit does not enforce stackup acceptance")


def audit(commit_sha: str, require_clean_source: bool) -> dict[str, Any]:
    validate_git_binding(commit_sha, require_clean_source)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    require(contract.get("schema") == "dioneya-pcb-main-stackup-impedance-request-v1"
            and contract.get("configuration") == "EVT-PRE-20 Rev.A"
            and contract.get("assembly") == "PCB-MAIN"
            and contract.get("revision") == "A",
            "stackup/impedance request identity mismatch")
    require(contract.get("status") ==
            "PACKET_READY_TWO_FABRICATOR_RESPONSES_REQUIRED_NOT_FOR_ROUTING_OR_MANUFACTURE",
            "stackup/impedance request status is not bounded")

    board = validate_board_and_bindings(contract)
    impedance = validate_impedance_scope(contract)
    response = validate_response_register(contract)
    validate_release_interlocks(contract)
    validate_status_packet_and_ci(contract)

    return {
        "schema": "dioneya-pcb-main-stackup-impedance-request-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MAIN",
        "status": "PASS_PACKET_READY_TWO_FABRICATOR_RESPONSES_REQUIRED",
        "evidence_commit_sha": commit_sha,
        "board": board,
        "impedance_scope": impedance,
        "external_response_register": response,
        "source_hashes": {
            relative(path): sha256(path) for path in CONTROLLED_SOURCES
        },
        "stackup_accepted": False,
        "routing_authorized": False,
        "review_b_complete": False,
        "manufacturing_release": False,
        "fabrication_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--commit-sha")
    parser.add_argument("--require-clean-source", action="store_true")
    args = parser.parse_args()
    commit_sha = args.commit_sha or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    try:
        report = audit(commit_sha, args.require_clean_source)
    except Exception as exc:
        report = {
            "schema": "dioneya-pcb-main-stackup-impedance-request-audit-v1",
            "configuration": "EVT-PRE-20 Rev.A",
            "assembly": "PCB-MAIN",
            "status": "FAIL_STACKUP_IMPEDANCE_REQUEST_AUDIT",
            "evidence_commit_sha": commit_sha,
            "error": f"{type(exc).__name__}: {exc}",
            "stackup_accepted": False,
            "routing_authorized": False,
            "review_b_complete": False,
            "manufacturing_release": False,
            "fabrication_authorized": False,
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"PCB-MAIN stackup/impedance request audit FAIL: {exc}")
        return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN stackup/impedance request audit: PASS")
    print(
        "fabricators=2 questions_per_fabricator=11 response_rows=22 "
        "accepted=0 stackup_accepted=false routing_authorized=false "
        "manufacturing_release=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
