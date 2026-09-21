#!/usr/bin/env python3
"""Audit the accepted PCB-PWR DIM-003 EVT mechanical authority.

This proves that all 18 mechanical responses are attributable, the native board
implements the accepted H1-H4 pattern, the frozen STEP is hash-bound, and the
remaining stackup/Review-B/manufacturing interlocks are still explicit.
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

from audit_pcb_pwr_placement_clearance_rev_a import audit as clearance_audit
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
EVT_AUTHORITY = ROOT / "hardware/reviews/PCB_PWR_DIM_003_EVT_AUTHORITY_REV_A.json"
EVT_AUTHORITY_RECORD = ROOT / "hardware/reviews/PCB_PWR_DIM_003_EVT_AUTHORITY_REV_A.md"
FROZEN_STEP = ROOT / "mechanics/pcb_pwr/PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_A.step"
MOUNTING_FOOTPRINT = ROOT / "hardware/kicad/native/PCB-PWR/libs/DioneyaPWR.pretty/MountingHole_M3_3.4_EVT.kicad_mod"
STEP_GENERATOR = ROOT / "tools/generate_pcb_pwr_evt_mechanical_step_rev_a.py"
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

STATE = "PASS_DIM_003_EVT_ENGINEERING_ACCEPTED_SERIAL_REVALIDATION_REQUIRED"
CONTRACT_STATUS = (
    "EVT_ENGINEERING_ACCEPTED_18_OF_18_SERIAL_REVALIDATION_REQUIRED_"
    "NOT_FOR_MANUFACTURE"
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
    "hardware/reviews/PCB_PWR_DIM_003_EVT_AUTHORITY_REV_A.json",
    "hardware/reviews/PCB_PWR_DIM_003_EVT_AUTHORITY_REV_A.md",
    "mechanics/pcb_pwr/PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_A.step",
]

RESPONSE_FIELDS = [
    "Gate_ID", "Required_Party", "Requirement", "Required_Evidence",
    "Disposition", "Response_Value", "Response_Reference", "Responder",
    "Response_Date", "Blocking",
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

EXPECTED_HOLES = {
    "H1": (5.0, 5.0),
    "H2": (82.0, 5.0),
    "H3": (68.0, 55.0),
    "H4": (5.0, 55.0),
}

CONTROLLED_SOURCES = [
    BOARD, PLACEMENT, PLACEMENT_RECORD, PLACEMENT_CLEARANCE_RECORD,
    PLACEMENT_CLEARANCE_AUDIT, ROUTING, FOOTPRINTS, HARNESS_PINOUT,
    HARNESS_SCHEDULE, OPEN_DIMENSIONS, STATUS, REVIEW_B, CONTRACT, PACKET,
    RESPONSE, EVT_AUTHORITY, EVT_AUTHORITY_RECORD, FROZEN_STEP,
    MOUNTING_FOOTPRINT, STEP_GENERATOR, RELEASE_GATE, DECISIONS, DELIVERABLES,
    RISKS, README, CI_WORKFLOW, NATIVE_WORKFLOW, PWR_WORKFLOW,
    HARDWARE_RELEASE_AUDIT, RELEASE_AUDIT, BASELINE_VALIDATOR,
    KICAD_NATIVE_GATE, Path(__file__).resolve(),
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


def ref_of(footprint: Any) -> str:
    if footprint.properties.get("Reference"):
        return str(footprint.properties["Reference"])
    return next((str(item.text) for item in footprint.graphicItems
                 if getattr(item, "type", None) == "reference"), "")


def validate_git_binding(commit_sha: str, require_clean_source: bool) -> None:
    require(re.fullmatch(r"[0-9a-f]{40}", commit_sha) is not None,
            f"invalid evidence commit SHA: {commit_sha!r}")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(head == commit_sha, f"evidence commit {commit_sha} != checked-out HEAD {head}")
    if require_clean_source:
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--", *[relative(path) for path in CONTROLLED_SOURCES]],
            cwd=ROOT, text=True,
        ).strip()
        require(not dirty, f"controlled DIM-003 accepted source set is dirty: {dirty}")


def expected_source_binding(board: Board) -> dict[str, str]:
    return {
        "native_board": relative(BOARD),
        "native_board_semantic_sha256": semantic_board_sha256(board),
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
        "accepted_evt_authority": relative(EVT_AUTHORITY),
        "accepted_evt_authority_sha256": sha256(EVT_AUTHORITY),
        "accepted_evt_authority_record": relative(EVT_AUTHORITY_RECORD),
        "accepted_evt_authority_record_sha256": sha256(EVT_AUTHORITY_RECORD),
        "frozen_evt_step": relative(FROZEN_STEP),
        "frozen_evt_step_sha256": sha256(FROZEN_STEP),
    }


def validate_board_and_sources(contract: dict[str, Any]) -> dict[str, Any]:
    for path in CONTROLLED_SOURCES:
        require(path.is_file(), f"controlled source missing: {relative(path)}")
    require(contract.get("authority_inputs") == AUTHORITY_INPUTS,
            "DIM-003 authority-input set differs")

    board = Board.from_file(str(BOARD), encoding="utf-8")
    copper_layers = [str(layer.name) for layer in board.layers if str(layer.name).endswith(".Cu")]
    board_nets = {str(net.name) for net in board.nets
                  if int(net.number) != 0 and str(net.name)}
    require(copper_layers == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
            f"PCB-PWR copper layers differ: {copper_layers}")
    require(abs(float(board.general.thickness) - 1.6) <= 1e-9,
            f"PCB-PWR thickness differs: {board.general.thickness}")
    require(len(board.footprints) == 66, f"PCB-PWR footprint count is {len(board.footprints)}, expected 66")
    require(len(board_nets) == 31, f"PCB-PWR net count is {len(board_nets)}, expected 31")
    require(len(board.traceItems) in {0, 2} and len(board.zones) == 0,
            "DIM-003 evidence does not cover copper beyond bootstrap routing 001")

    footprints = {ref_of(footprint): footprint for footprint in board.footprints}
    require(len(footprints) == 66 and set(EXPECTED_HOLES).issubset(footprints),
            "PCB-PWR unique reference or mounting-hole set differs")
    for reference, (x, y) in EXPECTED_HOLES.items():
        footprint = footprints[reference]
        require(str(footprint.libId) == "DioneyaPWR:MountingHole_M3_3.4_EVT",
                f"{reference}: mounting footprint differs")
        require(abs(float(footprint.position.X) - x) <= 0.002 and
                abs(float(footprint.position.Y) - y) <= 0.002,
                f"{reference}: mounting coordinate differs")
        require(footprint.attributes.boardOnly and
                footprint.attributes.excludeFromBom and
                footprint.attributes.excludeFromPosFiles,
                f"{reference}: mounting release attributes differ")
        require(len(footprint.pads) == 1, f"{reference}: expected one NPTH")
        pad = footprint.pads[0]
        require(str(pad.type) == "np_thru_hole" and str(pad.shape) == "circle" and
                abs(float(pad.size.X) - 3.4) <= 0.001 and
                pad.drill is not None and abs(float(pad.drill.diameter) - 3.4) <= 0.001 and
                abs(float(pad.clearance) - 2.3) <= 0.001,
                f"{reference}: NPTH or D8 copper exclusion differs")

    require(contract.get("source_binding") == expected_source_binding(board),
            "DIM-003 accepted source binding differs")
    clearance = clearance_audit(BOARD, PLACEMENT)
    summary = clearance["summary"]
    require(summary["state"] == "PASS_FITTED_2D_AND_EVT_MOUNTING_CLEARANCE_DIM_003_ACCEPTED" and
            summary["mounting_holes"] == 4 and
            summary["mounting_to_fitted_body_conflicts"] == 0 and
            summary["mounting_to_existing_pad_conflicts"] == 0,
            "DIM-003 mounting/placement clearance evidence differs")
    return {
        "path": relative(BOARD),
        "semantic_sha256": semantic_board_sha256(board),
        "copper_layers": len(copper_layers),
        "electrical_footprints": 62,
        "mounting_holes": 4,
        "nets": len(board_nets),
        "trace_items": len(board.traceItems),
        "copper_zones": len(board.zones),
        "minimum_mounting_to_fitted_body_margin_mm":
            summary["minimum_mounting_to_fitted_body_margin_mm"],
    }


def validate_evt_authority(contract: dict[str, Any]) -> dict[str, Any]:
    authority = json.loads(EVT_AUTHORITY.read_text(encoding="utf-8"))
    require(authority.get("schema") == "dioneya-pcb-pwr-dim-003-evt-authority-v1" and
            authority.get("configuration") == "EVT-PRE-20 Rev.A" and
            authority.get("assembly") == "PCB-PWR",
            "DIM-003 EVT authority identity differs")
    require(authority.get("status") ==
            "ACCEPTED_FOR_EVT_MECHANICAL_ROUTING_INPUT_SERIAL_REVALIDATION_REQUIRED",
            "DIM-003 EVT authority status differs")
    require(authority["outline"] == {
        "geometry": "RECTANGLE_FOUR_STRAIGHT_EDGE_CUTS_NO_CUTOUTS",
        "size_mm": [90.0, 60.0],
        "edge_profile_tolerance_mm": 0.15,
        "finished_thickness_mm": 1.6,
        "finished_thickness_tolerance_mm": 0.16,
        "scope": "EVT_LOT_ONLY",
    }, "DIM-003 EVT outline/thickness authority differs")
    mounting = authority["mounting"]
    require(mounting["hole_type"] == "ROUND_NPTH" and
            mounting["nominal_drill_mm"] == 3.4 and
            mounting["all_copper_exclusion_diameter_mm"] == 8.0 and
            mounting["fitted_component_exclusion_diameter_mm"] == 10.0 and
            {item["reference"]: tuple(item["xy_mm"]) for item in mounting["holes"]} ==
            EXPECTED_HOLES and mounting["slot_policy"].startswith("NO_PCB_SLOTS"),
            "DIM-003 EVT mounting authority differs")
    require(authority["assembled_z_envelope_mm"]["minimum"] == -3.0 and
            authority["assembled_z_envelope_mm"]["maximum"] == 18.0,
            "DIM-003 assembled Z envelope differs")
    require(authority["connector_service_volumes"]["J1"]["mating_direction"] == "+Z" and
            authority["connector_service_volumes"]["J2"]["mating_direction"] == "+X_EAST",
            "DIM-003 connector service direction differs")
    require(authority["dft_fixture"]["primary_datum"] == "H1_CENTER" and
            "DIAMOND_PIN" in authority["dft_fixture"]["secondary_datum"],
            "DIM-003 DFT datum differs")
    step = authority["frozen_step"]
    require(step["path"] == relative(FROZEN_STEP) and step["sha256"] == sha256(FROZEN_STEP) and
            step["interference_review"] == "PASS_NO_FITTED_BODY_TO_MOUNTING_EXCLUSION_CONFLICT",
            "DIM-003 frozen STEP binding differs")
    header = FROZEN_STEP.read_text(encoding="utf-8", errors="strict")[:512]
    require(header.startswith("ISO-10303-21;") and "Open CASCADE" in header,
            "DIM-003 frozen STEP header differs")
    require(authority["release_boundary"] == {
        "dim_003_accepted_for_evt": True,
        "mechanical_input_to_routing_authorized": True,
        "harness_board_datum_authorized": True,
        "final_harness_cut_lengths_authorized": False,
        "review_b_complete": False,
        "manufacturing_release": False,
        "serial_release": False,
    }, "DIM-003 EVT authority release boundary differs")

    expected_basis = {
        "outline_mm": [90.0, 60.0],
        "outline_tolerance_mm": 0.15,
        "finished_thickness_mm": 1.6,
        "finished_thickness_tolerance_mm": 0.16,
        "mounting_holes": 4,
        "mounting_hole_diameter_mm": 3.4,
        "mounting_hole_coordinates_mm": {key: list(value) for key, value in EXPECTED_HOLES.items()},
        "mounting_copper_exclusion_diameter_mm": 8.0,
        "mounting_fitted_component_exclusion_diameter_mm": 10.0,
        "copper_layers": 4,
        "native_trace_items": 0,
        "native_copper_zones": 0,
        "j1_reference_position_mm": [6.0, 28.0],
        "j1_reference_rotation_deg": 0.0,
        "j1_service_status": "EVT_TOP_ENTRY_AND_CABLE_VOLUME_ACCEPTED",
        "j2_reference_position_mm": [90.0, 56.0],
        "j2_reference_rotation_deg": 270.0,
        "j2_service_status": "EVT_EAST_EXIT_AND_CABLE_VOLUME_ACCEPTED",
        "dft_reference_row": {
            "references": [f"TP{index}" for index in range(1, 11)],
            "first_xy_mm": [25.0, 56.0], "last_xy_mm": [47.86, 56.0],
            "pitch_mm": 2.54, "side": "TOP",
            "status": "EVT_FIXTURE_DATUM_AND_PROBE_ACCESS_ACCEPTED",
        },
        "basis_status": "ACCEPTED_FOR_EVT_ROUTING_INPUT_SERIAL_REVALIDATION_REQUIRED",
    }
    require(contract.get("accepted_evt_basis") == expected_basis,
            "DIM-003 accepted EVT basis differs")
    return authority


def validate_response_register(contract: dict[str, Any]) -> list[dict[str, str]]:
    fields, rows = read_csv(RESPONSE)
    require(fields == RESPONSE_FIELDS, f"DIM-003 response fields differ: {fields}")
    require(len(rows) == len(GATES), f"DIM-003 response count is {len(rows)}, expected {len(GATES)}")
    expected_ids = [f"DIM003-{gate}" for gate, _, _ in GATES]
    require([row["Gate_ID"] for row in rows] == expected_ids,
            "DIM-003 gate order or membership differs")
    for row, (gate, party, tokens) in zip(rows, GATES, strict=True):
        require(row["Required_Party"] == party, f"DIM003-{gate}: responsible party differs")
        requirement = row["Requirement"].lower()
        for token in tokens:
            require(token in requirement, f"DIM003-{gate}: requirement missing token {token!r}")
        require(row["Required_Evidence"].strip(), f"DIM003-{gate}: evidence requirement is blank")
        require(row["Disposition"] == "ACCEPTED_EVT_ENGINEERING",
                f"DIM003-{gate}: acceptance disposition differs")
        for field in ("Response_Value", "Response_Reference", "Responder", "Response_Date"):
            require(row[field].strip(), f"DIM003-{gate}: accepted attribution field {field} is blank")
        require(row["Responder"] == "Project engineering / owner-authorized" and
                row["Response_Date"] == "2026-09-21" and row["Blocking"] == "NO",
                f"DIM003-{gate}: attribution/blocking state differs")
        evidence_path = row["Response_Reference"].split("#", 1)[0]
        require((ROOT / evidence_path).is_file(),
                f"DIM003-{gate}: response evidence is missing: {evidence_path}")
    require(contract.get("required_gate_ids") == [gate for gate, _, _ in GATES],
            "DIM-003 required-gate membership differs")
    require(contract.get("external_response") == {
        "response_register": relative(RESPONSE),
        "required_rows": 18, "pending_rows": 0, "accepted_rows": 18, "complete": True,
    }, "DIM-003 response interlock differs")
    return rows


def validate_release_interlocks(contract: dict[str, Any]) -> None:
    require(contract.get("accepted_authority") == {
        "authority": relative(EVT_AUTHORITY),
        "final_outline_mm": [90.0, 60.0],
        "finished_thickness_mm": 1.6,
        "mounting_pattern": "H1_H4_ROUND_NPTH_3P4_D8_COPPER_D10_FITTED_BODY",
        "assembled_z_envelope_mm": [-3.0, 18.0],
        "j1_mating_and_cable_volume": "ACCEPTED_EVT_TOP_ENTRY_PLUS_Z_THEN_WEST",
        "j2_mating_and_cable_volume": "ACCEPTED_EVT_EAST_EXIT_PLUS_X",
        "dft_fixture_and_probe_volume": "ACCEPTED_EVT_H1_H2_DATUM_TOP_POGO",
        "thermal_interface": "EVT_OPEN_AIR_NO_COMPRESSIVE_PAD",
        "enclosure_keep_out": "EVT_OPEN_FRAME_NONCONDUCTIVE_GUARD",
        "harness_length_datums": "J1_J2_MATING_FACE_CENTERLINES",
        "frozen_step_path": relative(FROZEN_STEP),
        "frozen_step_sha256": sha256(FROZEN_STEP),
        "accepted_dim_003": True,
        "serial_revalidation_required": True,
    }, "DIM-003 accepted authority differs")
    require(contract.get("release_interlock") == {
        "dim_003_accepted": True,
        "outline_and_mounting_frozen": True,
        "connector_service_volumes_accepted": True,
        "dft_fixture_access_accepted": True,
        "frozen_step_accepted": True,
        "placement_revalidation_complete": True,
        "harness_board_datum_authorized": True,
        "final_harness_cut_lengths_authorized": False,
        "routing_authorized": True,
        "serial_revalidation_required": True,
        "review_b_complete": False,
        "manufacturing_release": False,
    }, "DIM-003 release interlock differs")


def validate_integrations() -> None:
    _, dimensions = read_csv(OPEN_DIMENSIONS)
    dim_rows = [row for row in dimensions if row.get("ID") == "DIM-003"]
    require(len(dim_rows) == 1, "DIM-003 open-dimensions row missing or duplicated")
    dim = dim_rows[0]
    require(dim.get("Owner") == "EE_ME" and dim.get("Status") ==
            "CLOSED_EVT_ENGINEERING_18_OF_18_ACCEPTED_SERIAL_REVALIDATION_REQUIRED" and
            "serial" in dim.get("Blocks", "").lower(),
            "DIM-003 open-dimensions acceptance state differs")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    mechanical = status.get("mechanical_freeze_input", {})
    require(mechanical.get("dim_id") == "DIM-003" and
            mechanical.get("request_packet") == relative(PACKET) and
            mechanical.get("machine_contract") == relative(CONTRACT) and
            mechanical.get("response_register") == relative(RESPONSE) and
            mechanical.get("accepted_authority") == relative(EVT_AUTHORITY) and
            mechanical.get("frozen_step") == relative(FROZEN_STEP) and
            mechanical.get("independent_audit") == relative(Path(__file__).resolve()),
            "PCB-PWR status does not bind accepted DIM-003 authority")
    require(mechanical.get("control") == {
        "state": STATE,
        "required_response_rows": 18, "accepted_response_rows": 18,
        "pending_response_rows": 0, "complete": True,
        "outline_and_mounting_frozen": True,
        "connector_service_volumes_accepted": True,
        "dft_fixture_access_accepted": True,
        "frozen_step_accepted": True,
        "harness_board_datum_authorized": True,
        "final_harness_cut_lengths_authorized": False,
        "routing_authorized": True,
        "serial_revalidation_required": True,
        "manufacturing_release": False,
    }, "PCB-PWR status DIM-003 control differs")

    integrations = {
        REVIEW_B: ("18/18", "[x] `DIM-003`", "serial"),
        RELEASE_GATE: ("18/18", "DIM-003", "serial"),
        RISKS: ("R-027", "18/18", "DIM-003"),
        DELIVERABLES: ("HW-P-004", "18 accepted", "DIM-003"),
        DECISIONS: ("DEC-097", "DIM-003", "four round"),
        README: ("18/18", "DIM-003", "PCB-PWR"),
        CI_WORKFLOW: ("audit_pcb_pwr_dim_003_request_rev_a.py", "pcb_pwr_dim_003_request_rev_a.json"),
        NATIVE_WORKFLOW: ("PCB_PWR_EVT_MECHANICAL_ENVELOPE_REV_A.step", "dim_003_request_audit.json"),
        PWR_WORKFLOW: ("PCB_PWR_DIM_003_EVT_AUTHORITY_REV_A.json", "dim_003_request_audit.json"),
        HARDWARE_RELEASE_AUDIT: ("pcb_pwr_dim_003_acceptance", "accepted_response_rows", "18"),
        RELEASE_AUDIT: ("PCB_PWR_DIM_003_REQUEST_REV_A.json", "audit_pcb_pwr_dim_003_request_rev_a.py"),
        BASELINE_VALIDATOR: ("DEC-097", "ACCEPTED_EVT_DIM_003_SERIAL_REVALIDATION_REQUIRED", "18/18"),
        KICAD_NATIVE_GATE: ("PCB_PWR_DIM_003_AUDIT", "mechanical_request_state"),
    }
    for path, tokens in integrations.items():
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            require(token in text, f"{relative(path)} missing DIM-003 integration token {token!r}")

    packet_text = " ".join(PACKET.read_text(encoding="utf-8").split())
    for token in ("18 OF 18 RESPONSES ACCEPTED", "serial", "no longer blocks PCB-PWR routing input"):
        require(token in packet_text, f"DIM-003 packet missing accepted boundary statement {token!r}")


def audit() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    require(contract.get("schema") == "dioneya-pcb-pwr-dim-003-request-v2",
            "DIM-003 contract schema differs")
    require(contract.get("configuration") == "EVT-PRE-20 Rev.A" and
            contract.get("assembly") == "PCB-PWR" and
            contract.get("revision") == "A" and contract.get("input_id") == "DIM-003",
            "DIM-003 contract identity differs")
    require(contract.get("status") == CONTRACT_STATUS, "DIM-003 contract status differs")
    board = validate_board_and_sources(contract)
    validate_evt_authority(contract)
    rows = validate_response_register(contract)
    validate_release_interlocks(contract)
    validate_integrations()
    return {
        "schema": "dioneya-pcb-pwr-dim-003-request-audit-v2",
        "configuration": "EVT-PRE-20 Rev.A", "assembly": "PCB-PWR",
        "status": STATE, "internal_packet_complete": True,
        "packet": relative(PACKET), "machine_contract": relative(CONTRACT),
        "response_register": relative(RESPONSE), "accepted_authority": relative(EVT_AUTHORITY),
        "frozen_step": relative(FROZEN_STEP), "frozen_step_sha256": sha256(FROZEN_STEP),
        "required_response_rows": len(GATES), "accepted_response_rows": len(rows),
        "pending_response_rows": 0, "dim_003_accepted": True,
        "serial_revalidation_required": True, "board": board,
        "routing_authorized": True, "harness_board_datum_authorized": True,
        "final_harness_cut_lengths_authorized": False,
        "review_b_complete": False, "manufacturing_release": False,
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
    print("PCB-PWR DIM-003 EVT acceptance audit PASS")
    print("18/18 accepted; H1-H4/STEP bound; serial revalidation required; manufacture remains prohibited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
