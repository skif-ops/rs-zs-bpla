#!/usr/bin/env python3
"""Audit the bounded PCB-PWR DIM-003 mechanical-freeze request.

This audit proves only that the current provisional board is bound to a complete
and blank 18-row mechanical input request. It must never turn provisional board,
connector, fixture or harness geometry into routing or manufacturing authority.
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
PLACEMENT = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv"
PLACEMENT_RECORD = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.md"
PLACEMENT_CLEARANCE_RECORD = ROOT / "hardware/reviews/PCB_PWR_PLACEMENT_CLEARANCE_REV_A.md"
PLACEMENT_CLEARANCE_AUDIT = ROOT / "tools/audit_pcb_pwr_placement_clearance_rev_a.py"
ROUTING = ROOT / "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv"
FOOTPRINTS = ROOT / "hardware/PCB_PWR_FOOTPRINT_AUTHORITY_REV_A.md"
HARNESS_PINOUT = ROOT / "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv"
HARNESS_SCHEDULE = ROOT / "hardware/HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv"
OPEN_DIMENSIONS = ROOT / "mechanics/common/OPEN_DIMENSIONS.csv"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
REVIEW_B = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_CHECKLIST_REV_A.md"
CONTRACT = ROOT / "hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.json"
PACKET = ROOT / "hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.md"
RESPONSE = ROOT / "hardware/reviews/PCB_PWR_DIM_003_RESPONSE_REV_A.csv"
RELEASE_GATE = ROOT / "hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md"
DECISIONS = ROOT / "docs/DECISION_LOG.csv"
DELIVERABLES = ROOT / "docs/DELIVERABLE_REGISTER_EVT_PRE_20.csv"
RISKS = ROOT / "docs/RISK_REGISTER.csv"
README = ROOT / "README.md"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
NATIVE_WORKFLOW = ROOT / ".github/workflows/pcb-native.yml"
PWR_WORKFLOW = ROOT / ".github/workflows/pcb-pwr-schematic.yml"
HARDWARE_RELEASE_AUDIT = ROOT / "tools/audit_evt_pre_20_hardware_release.py"
RELEASE_AUDIT = ROOT / "tools/audit_evt_pre_20_release.py"
BASELINE_VALIDATOR = ROOT / "tools/validate_evt_pre_20.py"
KICAD_NATIVE_GATE = ROOT / "tools/kicad_native_gate.py"

STATE = "PASS_INTERNAL_DIM_003_REQUEST_READY_EXTERNAL_RESPONSE_PENDING"
CONTRACT_STATUS = (
    "PACKET_READY_18_ATTRIBUTABLE_RESPONSES_REQUIRED_"
    "NOT_FOR_ROUTING_OR_MANUFACTURE"
)

AUTHORITY_INPUTS = [
    "mechanics/common/OPEN_DIMENSIONS.csv",
    "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv",
    "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.md",
    "hardware/reviews/PCB_PWR_PLACEMENT_CLEARANCE_REV_A.md",
    "hardware/PCB_PWR_FOOTPRINT_AUTHORITY_REV_A.md",
    "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv",
    "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv",
    "hardware/HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv",
    "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json",
    "hardware/reviews/PCB_PWR_REVIEW_B_CHECKLIST_REV_A.md",
    "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb",
]

RESPONSE_FIELDS = [
    "Gate_ID",
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

GATES: list[tuple[str, str, tuple[str, ...]]] = [
    ("COORDINATE-DATUM", "EE_ME", ("coordinate system", "origin", "axes", "datum")),
    ("OUTLINE-DISPOSITION", "EE_ME", ("90.00 x 60.00", "accept", "eco", "routing")),
    ("OUTLINE-GEOMETRY", "MECHANICAL", ("edge.cuts", "corner radii", "cut-outs", "tolerances")),
    ("THICKNESS-TOLERANCE", "EE_ME_FABRICATION", ("finished pcb thickness", "tolerance", "stackup")),
    ("MOUNTING-PATTERN", "MECHANICAL", ("mounting-hole", "coordinates", "tolerances", "keep-outs")),
    ("MOUNTING-HARDWARE", "MECHANICAL_MANUFACTURING", ("standoffs", "screws", "torque", "support")),
    ("ASSEMBLED-Z-ENVELOPE", "EE_ME", ("top and bottom heights", "tolerances", "clearance")),
    ("J1-MATING-VOLUME", "EE_HARNESS_ME", ("j1", "insertion", "tool access", "volume")),
    ("J1-CABLE-VOLUME", "HARNESS_MECHANICAL", ("battery cable", "bend radius", "strain relief", "service")),
    ("J2-MATING-VOLUME", "EE_HARNESS_ME", ("j2", "insertion", "tool access", "volume")),
    ("J2-CABLE-VOLUME", "HARNESS_MECHANICAL", ("main harness", "bend radius", "strain relief", "service")),
    ("DFT-FIXTURE-DATUM", "TEST_MECHANICAL", ("fixture", "datums", "tp1 through tp10", "retention")),
    ("DFT-PROBE-VOLUME", "TEST_MANUFACTURING", ("probe", "tip diameter", "travel", "wear")),
    ("THERMAL-INTERFACE", "POWER_MECHANICAL", ("cooling", "thermal-interface", "tolerance", "pressure")),
    ("ENCLOSURE-KEEP-OUT", "MECHANICAL", ("wall", "boss", "fastener", "clearance")),
    ("ASSEMBLY-SERVICE-SEQUENCE", "MECHANICAL_MANUFACTURING", ("insertion", "fastening", "removal", "tool")),
    ("HARNESS-LENGTH-DATUMS", "HARNESS_MECHANICAL", ("length measurement datums", "tbd cut lengths", "enclosure")),
    ("FROZEN-STEP", "EE_ME_CONFIGURATION", ("frozen pcb assembly step", "revision", "sha-256", "interference")),
]

CONTROLLED_SOURCES = [
    BOARD,
    PLACEMENT,
    PLACEMENT_RECORD,
    PLACEMENT_CLEARANCE_RECORD,
    PLACEMENT_CLEARANCE_AUDIT,
    ROUTING,
    FOOTPRINTS,
    HARNESS_PINOUT,
    HARNESS_SCHEDULE,
    OPEN_DIMENSIONS,
    STATUS,
    REVIEW_B,
    CONTRACT,
    PACKET,
    RESPONSE,
    RELEASE_GATE,
    DECISIONS,
    DELIVERABLES,
    RISKS,
    README,
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
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    require(head == commit_sha, f"evidence commit {commit_sha} != checked-out HEAD {head}")
    if require_clean_source:
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--", *[relative(path) for path in CONTROLLED_SOURCES]],
            cwd=ROOT,
            text=True,
        ).strip()
        require(not dirty, f"controlled DIM-003 request source set is dirty: {dirty}")


def validate_board_and_sources(contract: dict[str, Any]) -> dict[str, Any]:
    for path in CONTROLLED_SOURCES:
        require(path.is_file(), f"controlled source missing: {relative(path)}")
    require(contract.get("authority_inputs") == AUTHORITY_INPUTS,
            "DIM-003 authority-input set differs")
    for item in AUTHORITY_INPUTS:
        require((ROOT / item).is_file(), f"authority input missing: {item}")

    board = Board.from_file(str(BOARD), encoding="utf-8")
    semantic_digest = semantic_board_sha256(board)
    copper_layers = [layer.name for layer in board.layers if str(layer.name).endswith(".Cu")]
    board_nets = {
        str(net.name) for net in board.nets
        if int(net.number) != 0 and str(net.name)
    }
    require(copper_layers == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
            f"PCB-PWR copper layers differ: {copper_layers}")
    require(float(board.general.thickness) == 1.6,
            f"provisional board thickness differs: {board.general.thickness}")
    require(len(board.footprints) == 62, f"PCB-PWR footprint count is {len(board.footprints)}, expected 62")
    require(len(board_nets) == 31, f"PCB-PWR net count is {len(board_nets)}, expected 31")
    require(len(board.traceItems) == 0 and len(board.zones) == 0,
            "DIM-003 request must be revised after copper routing or zones appear")

    expected_binding = {
        "native_board": relative(BOARD),
        "native_board_semantic_sha256": semantic_digest,
        "placement_authority": relative(PLACEMENT),
        "placement_authority_sha256": sha256(PLACEMENT),
        "placement_clearance_record": relative(PLACEMENT_CLEARANCE_RECORD),
        "placement_clearance_record_sha256": sha256(PLACEMENT_CLEARANCE_RECORD),
        "routing_authority": relative(ROUTING),
        "routing_authority_sha256": sha256(ROUTING),
        "footprint_authority": relative(FOOTPRINTS),
        "footprint_authority_sha256": sha256(FOOTPRINTS),
        "harness_logical_pinout": relative(HARNESS_PINOUT),
        "harness_logical_pinout_sha256": sha256(HARNESS_PINOUT),
        "harness_manufacturing_schedule": relative(HARNESS_SCHEDULE),
        "harness_manufacturing_schedule_sha256": sha256(HARNESS_SCHEDULE),
        "open_dimensions": relative(OPEN_DIMENSIONS),
        "open_dimensions_sha256": sha256(OPEN_DIMENSIONS),
    }
    require(contract.get("source_binding") == expected_binding,
            "DIM-003 request source binding differs")

    return {
        "path": relative(BOARD),
        "semantic_sha256": semantic_digest,
        "copper_layers": len(copper_layers),
        "footprints": len(board.footprints),
        "nets": len(board_nets),
        "trace_items": len(board.traceItems),
        "copper_zones": len(board.zones),
    }


def validate_provisional_basis(contract: dict[str, Any]) -> dict[str, Any]:
    fields, rows = read_csv(PLACEMENT)
    require(fields[:5] == ["RefDes", "X_mm", "Y_mm", "Rotation_deg", "Side"],
            "placement authority columns differ")
    require(len(rows) == 62, f"placement authority has {len(rows)} rows, expected 62")
    by_ref = {row["RefDes"]: row for row in rows}
    require(len(by_ref) == len(rows), "placement authority has duplicate references")

    for ref, values in {
        "J1": ("6.00", "28.00", "0", "TOP"),
        "J2": ("90.00", "56.00", "270", "TOP"),
    }.items():
        row = by_ref.get(ref, {})
        actual = tuple(row.get(key) for key in ("X_mm", "Y_mm", "Rotation_deg", "Side"))
        require(actual == values, f"{ref} provisional placement differs: {actual}")
        require("PROVISIONAL_SERVICE_CLEARANCE_PENDING" in row.get("Placement_Status", ""),
                f"{ref} service-clearance interlock differs")

    tp_refs = [f"TP{i}" for i in range(1, 11)]
    for index, ref in enumerate(tp_refs):
        row = by_ref.get(ref, {})
        expected_x = f"{25.0 + index * 2.54:.2f}"
        require(row.get("X_mm") == expected_x and row.get("Y_mm") == "56.00"
                and row.get("Side") == "TOP",
                f"{ref} provisional DFT row geometry differs")
        require(row.get("Placement_Status") == "PROVISIONAL_DFT_ACCESS_REVIEW_PENDING",
                f"{ref} DFT access status differs")

    basis = contract.get("provisional_request_basis")
    expected_basis = {
        "outline_mm": [90.0, 60.0],
        "finished_thickness_mm": 1.6,
        "mounting_holes": 0,
        "copper_layers": 4,
        "native_trace_items": 0,
        "native_copper_zones": 0,
        "j1_reference_position_mm": [6.0, 28.0],
        "j1_reference_rotation_deg": 0.0,
        "j1_intended_service": "TOP_ENTRY_BATTERY_INPUT_PROVISIONAL",
        "j2_reference_position_mm": [90.0, 56.0],
        "j2_reference_rotation_deg": 270.0,
        "j2_intended_service": "EAST_EXIT_MAIN_HARNESS_PROVISIONAL",
        "dft_reference_row": {
            "references": tp_refs,
            "first_xy_mm": [25.0, 56.0],
            "last_xy_mm": [47.86, 56.0],
            "pitch_mm": 2.54,
            "side": "TOP",
            "status": "PROVISIONAL_FIXTURE_DATUM_AND_ACCESS_OPEN",
        },
        "basis_status": "REFERENCE_ONLY_EVERY_NUMERIC_MECHANICAL_VALUE_REQUIRES_DIM_003_ACCEPTANCE",
    }
    require(basis == expected_basis, "provisional DIM-003 request basis differs")
    return expected_basis


def validate_response_register(contract: dict[str, Any]) -> list[dict[str, str]]:
    fields, rows = read_csv(RESPONSE)
    require(fields == RESPONSE_FIELDS, f"DIM-003 response fields differ: {fields}")
    require(len(rows) == len(GATES), f"DIM-003 response count is {len(rows)}, expected {len(GATES)}")
    expected_ids = [f"DIM003-{gate}" for gate, _, _ in GATES]
    require([row["Gate_ID"] for row in rows] == expected_ids,
            "DIM-003 gate order or membership differs")

    blank_fields = ("Response_Value", "Response_Reference", "Responder", "Response_Date")
    for row, (gate, party, tokens) in zip(rows, GATES, strict=True):
        require(row["Required_Party"] == party, f"DIM003-{gate}: responsible party differs")
        requirement = row["Requirement"].lower()
        for token in tokens:
            require(token in requirement, f"DIM003-{gate}: requirement missing token {token!r}")
        require(bool(row["Required_Evidence"].strip()), f"DIM003-{gate}: evidence requirement is blank")
        require(row["Disposition"] == "PENDING_EXTERNAL_RESPONSE",
                f"DIM003-{gate}: unaccepted packet contains disposition {row['Disposition']!r}")
        require(all(not row[field].strip() for field in blank_fields),
                f"DIM003-{gate}: response attribution was populated without controlled acceptance")
        require(row["Blocking"] == "YES", f"DIM003-{gate}: gate is not blocking")

    require(contract.get("required_gate_ids") == [gate for gate, _, _ in GATES],
            "contract required-gate membership differs")
    require(contract.get("external_response") == {
        "response_register": relative(RESPONSE),
        "required_rows": 18,
        "pending_rows": 18,
        "accepted_rows": 0,
        "complete": False,
    }, "DIM-003 external-response interlock differs")
    return rows


def validate_release_interlocks(contract: dict[str, Any]) -> None:
    require(contract.get("accepted_authority") == {
        "final_outline_mm": None,
        "finished_thickness_mm": None,
        "mounting_pattern": None,
        "assembled_z_envelope_mm": None,
        "j1_mating_and_cable_volume": None,
        "j2_mating_and_cable_volume": None,
        "dft_fixture_and_probe_volume": None,
        "thermal_interface": None,
        "enclosure_keep_out": None,
        "harness_length_datums": None,
        "frozen_step_path": None,
        "frozen_step_sha256": None,
        "accepted_dim_003": False,
    }, "DIM-003 accepted authority contains premature mechanical values")
    require(contract.get("release_interlock") == {
        "dim_003_accepted": False,
        "outline_and_mounting_frozen": False,
        "connector_service_volumes_accepted": False,
        "dft_fixture_access_accepted": False,
        "frozen_step_accepted": False,
        "placement_revalidation_complete": False,
        "harness_length_release_authorized": False,
        "routing_authorized": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }, "DIM-003 release interlock differs")


def validate_integrations() -> None:
    _, dimensions = read_csv(OPEN_DIMENSIONS)
    dim_rows = [row for row in dimensions if row.get("ID") == "DIM-003"]
    require(len(dim_rows) == 1, "DIM-003 open-dimensions row missing or duplicated")
    dim = dim_rows[0]
    require(dim.get("Owner") == "EE_ME"
            and dim.get("Status") == "CONTROLLED_REQUEST_READY_0_OF_18_ACCEPTED"
            and "PCB_PWR_DIM_003_RESPONSE_REV_A.csv" in dim.get("Required_input", "")
            and "routing" in dim.get("Blocks", "").lower()
            and "harness cut lengths" in dim.get("Blocks", "").lower(),
            "DIM-003 open-dimensions request state differs")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    mechanical = status.get("mechanical_freeze_input", {})
    control = mechanical.get("control", {}) if isinstance(mechanical, dict) else {}
    require(mechanical.get("dim_id") == "DIM-003"
            and mechanical.get("request_packet") == relative(PACKET)
            and mechanical.get("machine_contract") == relative(CONTRACT)
            and mechanical.get("response_register") == relative(RESPONSE)
            and mechanical.get("independent_audit") == relative(Path(__file__).resolve()),
            "PCB-PWR status does not bind the DIM-003 packet")
    require(control == {
        "state": STATE,
        "required_response_rows": 18,
        "accepted_response_rows": 0,
        "complete": False,
        "outline_and_mounting_frozen": False,
        "connector_service_volumes_accepted": False,
        "dft_fixture_access_accepted": False,
        "frozen_step_accepted": False,
        "harness_length_release_authorized": False,
        "routing_authorized": False,
        "manufacturing_release": False,
    }, "PCB-PWR status DIM-003 control differs")

    integrations = {
        REVIEW_B: ("0/18", "PCB_PWR_DIM_003_RESPONSE_REV_A.csv", "[ ] `DIM-003`"),
        RELEASE_GATE: ("0/18", "PCB_PWR_DIM_003_RESPONSE_REV_A.csv", "DIM-003"),
        RISKS: ("R-027", "0/18", "DIM-003"),
        DELIVERABLES: ("HW-P-004", "0 accepted", "DIM-003"),
        DECISIONS: ("DEC-054", "18-row", "DIM-003"),
        README: ("0/18", "DIM-003", "PCB-PWR"),
        CI_WORKFLOW: ("audit_pcb_pwr_dim_003_request_rev_a.py", "pcb_pwr_dim_003_request_rev_a.json"),
        NATIVE_WORKFLOW: ("audit_pcb_pwr_dim_003_request_rev_a.py", "dim_003_request_audit.json"),
        PWR_WORKFLOW: ("audit_pcb_pwr_dim_003_request_rev_a.py", "dim_003_request_audit.json"),
        HARDWARE_RELEASE_AUDIT: ("pcb_pwr_dim_003_request_packet", "accepted_response_rows", "DIM-003"),
        RELEASE_AUDIT: ("PCB_PWR_DIM_003_REQUEST_REV_A.json", "audit_pcb_pwr_dim_003_request_rev_a.py"),
        BASELINE_VALIDATOR: ("DEC-054", "IMPLEMENTED_DIM_003_EXTERNAL_ACCEPTANCE_PENDING", "0/18"),
        KICAD_NATIVE_GATE: ("PCB_PWR_DIM_003_AUDIT", "mechanical_request_state"),
    }
    for path, tokens in integrations.items():
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            require(token in text, f"{relative(path)} missing DIM-003 integration token {token!r}")

    packet_text = " ".join(PACKET.read_text(encoding="utf-8").split())
    for token in (
        "0 OF 18 RESPONSES ACCEPTED",
        "not acceptance of the provisional outline",
        "Any accepted",
        "does not by itself authorize routing",
    ):
        require(token in packet_text, f"DIM-003 packet missing boundary statement {token!r}")


def audit() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    require(contract.get("schema") == "dioneya-pcb-pwr-dim-003-request-v1",
            "DIM-003 contract schema differs")
    require(contract.get("configuration") == "EVT-PRE-20 Rev.A"
            and contract.get("assembly") == "PCB-PWR"
            and contract.get("revision") == "A"
            and contract.get("input_id") == "DIM-003",
            "DIM-003 contract identity differs")
    require(contract.get("status") == CONTRACT_STATUS, "DIM-003 contract status differs")

    board = validate_board_and_sources(contract)
    basis = validate_provisional_basis(contract)
    rows = validate_response_register(contract)
    validate_release_interlocks(contract)
    validate_integrations()
    return {
        "schema": "dioneya-pcb-pwr-dim-003-request-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-PWR",
        "status": STATE,
        "internal_packet_complete": True,
        "packet": relative(PACKET),
        "machine_contract": relative(CONTRACT),
        "response_register": relative(RESPONSE),
        "required_response_rows": len(GATES),
        "accepted_response_rows": 0,
        "pending_response_rows": len(rows),
        "dim_003_accepted": False,
        "provisional_basis": basis,
        "board": board,
        "routing_authorized": False,
        "harness_length_release_authorized": False,
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
    print("PCB-PWR DIM-003 request audit PASS")
    print("18/18 blocking questions present; 0 accepted; routing and manufacture remain prohibited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
