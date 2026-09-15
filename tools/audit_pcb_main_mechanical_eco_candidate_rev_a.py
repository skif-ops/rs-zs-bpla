#!/usr/bin/env python3
"""Audit the approved PCB-MAIN limited mechanical ECO and its application.

The immutable candidate remains the exact proposal reviewed by the customer.
Its sidecar approval authorizes only the bounded MAIN-AUTH-011 delta.  This
audit reconstructs the reviewed baseline from Git, repeats the independent
overlay calculation, and accepts either the signed pre-application state or an
exact application of that delta.  It never releases manufacturing.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from typing import Any

from kiutils.board import Board

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_pcb_main_placement_clearance_rev_a import (  # noqa: E402
    COURTYARD_SOURCE,
    FIXTURE_PACKAGE_PREFIX,
    component_collision,
    envelope_of,
    load_authority,
    load_tool_clearances,
    mounting_conflict,
    ref_of,
    tool_clearance_conflict,
)

DEFAULT_CANDIDATE = ROOT / "hardware/reviews/PCB_MAIN_MECHANICAL_ECO_CANDIDATE_REV_A.json"
DEFAULT_APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_MECHANICAL_ECO_APPROVAL_REV_A.json"
DEFAULT_REVIEW_COMMIT_MAPPING = (
    ROOT / "hardware/reviews/PCB_MAIN_MECHANICAL_ECO_REVIEW_COMMIT_MAPPING_REV_A.json"
)
DEFAULT_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_MECHANICAL_ECO_APPLICATION_REV_A.json"
NUMERIC_TOLERANCE = 1e-6
REVIEWED_COMMIT = "61cbe796de2f87560342a44b063ff6283a8ce1e8"
REVIEWED_CANDIDATE_SHA256 = "5ef7d0390da97796febbef6a69f0206a06efe00782e238bf7c8f32bf29d08fc1"
EXPECTED_CHANGES = {
    "MECH-007": {"Y_mm": (13.0, 15.0)},
    "MECH-008": {"Y_mm": (30.0, 42.5)},
    "MECH-014": {"Y_mm": (68.0, 71.5)},
    "MECH-016": {"Y_mm": (68.0, 71.5)},
    "MECH-019": {"Y_mm": (13.0, 15.0)},
    "MECH-020": {"Y_mm": (53.0, 52.0)},
    "MECH-024": {"Y_mm": (42.0, 34.0), "Extent_Y_mm": (30.0, 40.0)},
    "MECH-026": {"Extent_Y_mm": (26.0, 28.0)},
    "MECH-032": {"Y_mm": (25.0, 37.5), "Extent_X_mm": (12.0, 10.0)},
}
NUMERIC_FIELDS = {
    "X_mm", "Y_mm", "Rotation_deg", "Extent_X_mm", "Extent_Y_mm",
    "Z_Min_mm", "Z_Max_mm",
}
BOARD_POSITION_LINES = {
    "J_PWR": ("    (at 0 13 90)", "    (at 0 15 90)"),
    "J_MIC1": ("    (at 0 30 90)", "    (at 0 42.5 90)"),
    "J8": ("    (at 16 68)", "    (at 16 71.5)"),
    "J10": ("    (at 74 68)", "    (at 74 71.5)"),
    "J13": ("    (at 110 13 -90)", "    (at 110 15 -90)"),
    "U8": ("    (at 24 53)", "    (at 24 52)"),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git_blob(commit: str, relative_path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    require(
        completed.returncode == 0,
        f"cannot read reviewed Git object {commit}:{relative_path}: "
        f"{completed.stderr.decode('utf-8', errors='replace').strip()}",
    )
    return completed.stdout


def git_object_exists(commit: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def git_tree_sha(commit: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", f"{commit}^{{tree}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0,
            f"cannot resolve reviewed tree for {commit}")
    return completed.stdout.strip()


def git_blob_sha(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def validate_review_commit_mapping(
    mapping_path: Path,
    approval: dict[str, Any],
) -> tuple[dict[str, Any], bytes]:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    require(set(mapping) == {
                "schema_version", "configuration", "proposal_id",
                "reviewed_local_commit_sha", "github_equivalent_commit_sha",
                "reviewed_tree_sha", "candidate_path", "candidate_blob_sha",
                "candidate_sha256", "equivalence", "transport", "reason",
                "manufacturing_release",
            }, "mechanical ECO review-commit mapping schema drift")
    require(mapping["schema_version"] ==
            "dioneya.pcb-main-mechanical-eco-review-commit-mapping.v1" and
            mapping["configuration"] == "EVT-PRE-20 Rev.A" and
            mapping["proposal_id"] == "PCB-MAIN-MECH-ECO-001",
            "mechanical ECO review-commit mapping identity drift")
    require(mapping["reviewed_local_commit_sha"] == approval["reviewed_commit_sha"] and
            mapping["reviewed_local_commit_sha"] == REVIEWED_COMMIT and
            mapping["github_equivalent_commit_sha"] ==
            "e265d1f1a0a74f94b9c887e12794a9b59fc2bfa0",
            "mechanical ECO review-commit mapping SHA drift")
    require(mapping["reviewed_tree_sha"] ==
            "f1fd423bbcfedefa830677ce2d8b3c54b2294caa" and
            mapping["candidate_path"] == approval["reviewed_candidate"] and
            mapping["candidate_blob_sha"] ==
            "b3dede3b466676bbab4e3bd737160cacfc57ad28" and
            mapping["candidate_sha256"] == approval["reviewed_candidate_sha256"],
            "mechanical ECO review tree or candidate mapping drift")
    require(mapping["equivalence"] == "EXACT_TREE_AND_CANDIDATE_BLOB" and
            mapping["transport"] == "GITHUB_APP_GIT_DATABASE_API" and
            mapping["reason"] == "LOCAL_HTTPS_CREDENTIAL_UNAVAILABLE" and
            mapping["manufacturing_release"] is False,
            "mechanical ECO transport or release interlock drift")

    present = [
        commit for commit in (
            mapping["reviewed_local_commit_sha"],
            mapping["github_equivalent_commit_sha"],
        )
        if git_object_exists(commit)
    ]
    require(present, "neither reviewed local nor exact-tree GitHub commit is available")
    reviewed_candidate = b""
    for commit in present:
        require(git_tree_sha(commit) == mapping["reviewed_tree_sha"],
                f"reviewed commit tree drift: {commit}")
        payload = git_blob(commit, mapping["candidate_path"])
        require(git_blob_sha(payload) == mapping["candidate_blob_sha"] and
                sha256_bytes(payload) == mapping["candidate_sha256"],
                f"reviewed candidate blob drift: {commit}")
        if reviewed_candidate:
            require(payload == reviewed_candidate,
                    "local and GitHub reviewed candidate blobs differ")
        reviewed_candidate = payload
    return mapping, reviewed_candidate


def validate_approval(approval_path: Path, candidate_path: Path) -> dict[str, Any]:
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    require(set(approval) == {
                "schema_version", "configuration", "proposal_id", "reviewer",
                "date", "reviewed_commit_sha", "reviewed_candidate",
                "reviewed_candidate_sha256", "decision", "scope",
                "approved_change_records", "implementation_authorized",
                "retained_blockers", "manufacturing_release",
            }, "mechanical ECO approval schema drift")
    require(approval["schema_version"] ==
            "dioneya.pcb-main-mechanical-eco-approval.v1",
            "mechanical ECO approval schema version drift")
    require(approval["configuration"] == "EVT-PRE-20 Rev.A" and
            approval["proposal_id"] == "PCB-MAIN-MECH-ECO-001",
            "mechanical ECO approval identity drift")
    require(approval["reviewer"] == "Скиф" and approval["date"] == "2026-09-15",
            "mechanical ECO reviewer or date drift")
    require(approval["reviewed_commit_sha"] == REVIEWED_COMMIT,
            "mechanical ECO reviewed commit drift")
    require(approval["reviewed_candidate"] ==
            str(candidate_path.resolve().relative_to(ROOT)),
            "mechanical ECO reviewed-candidate path drift")
    require(approval["reviewed_candidate_sha256"] == REVIEWED_CANDIDATE_SHA256,
            "mechanical ECO reviewed-candidate SHA-256 drift")
    require(approval["decision"] == "ACCEPT_LIMITED_MECHANICAL_ECO" and
            approval["scope"] == "LIMITED_MAIN_AUTH_011_MECHANICAL_ECO_ONLY" and
            approval["implementation_authorized"] is True,
            "mechanical ECO approval decision or scope drift")
    require(approval["approved_change_records"] == list(EXPECTED_CHANGES),
            "mechanical ECO approved record sequence drift")
    require(isinstance(approval["retained_blockers"], list) and
            len(approval["retained_blockers"]) == 7 and
            all(isinstance(item, str) and item for item in approval["retained_blockers"]),
            "mechanical ECO retained-blocker record drift")
    require(approval["manufacturing_release"] is False,
            "mechanical ECO approval cannot release manufacturing")
    return approval


def footprint_block(source: str, ref: str) -> tuple[int, int, str]:
    for match in re.finditer(r"(?m)^  \(footprint ", source):
        start = match.start() + 2
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(source)):
            char = source[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    block = source[start:end]
                    if re.search(
                        rf'(?m)^    \(fp_text reference "{re.escape(ref)}"(?: |\))',
                        block,
                    ):
                        return start, end, block
                    break
    raise AssertionError(f"baseline board footprint not found: {ref}")


def expected_applied_board(baseline: bytes) -> bytes:
    source = baseline.decode("utf-8")
    for ref, (old_line, new_line) in BOARD_POSITION_LINES.items():
        start, end, block = footprint_block(source, ref)
        require(block.count(old_line) == 1,
                f"{ref}: reviewed baseline position line drift")
        require(new_line not in block, f"{ref}: reviewed baseline is already moved")
        block = block.replace(old_line, new_line, 1)
        source = source[:start] + block + source[end:]
    return source.encode("utf-8")


def authority_matches_applied(
    live_path: Path,
    expected_by_id: dict[str, dict[str, Any]],
) -> bool:
    live_rows, live_by_id = load_rows(live_path)
    require(len(live_rows) == len(expected_by_id) and
            set(live_by_id) == set(expected_by_id),
            "applied MAIN-AUTH-011 record set drift")
    for record_id, expected in expected_by_id.items():
        actual = live_by_id[record_id]
        require(set(actual) == set(expected),
                f"{record_id}: applied MAIN-AUTH-011 field set drift")
        for field, expected_value in expected.items():
            if field in NUMERIC_FIELDS:
                require(close(float(actual[field]), float(expected_value)),
                        f"{record_id}.{field}: applied value drift")
            else:
                require(actual[field] == expected_value,
                        f"{record_id}.{field}: applied value drift")
    return True


def validate_application(
    application_path: Path,
    candidate: dict[str, Any],
    approval: dict[str, Any],
    live_board_sha: str,
    live_authority_sha: str,
) -> dict[str, Any]:
    application = json.loads(application_path.read_text(encoding="utf-8"))
    require(set(application) == {
                "schema_version", "configuration", "proposal_id", "approval",
                "application_date", "reviewed_commit_sha",
                "reviewed_candidate_sha256", "decision", "baseline", "applied",
                "post_application_clearance", "status", "review_b_complete",
                "manufacturing_release",
            }, "mechanical ECO application schema drift")
    require(application["schema_version"] ==
            "dioneya.pcb-main-mechanical-eco-application.v1" and
            application["configuration"] == candidate["configuration"] and
            application["proposal_id"] == candidate["proposal_id"],
            "mechanical ECO application identity drift")
    require(application["approval"] ==
            "hardware/reviews/PCB_MAIN_MECHANICAL_ECO_APPROVAL_REV_A.json" and
            application["application_date"] == "2026-09-15",
            "mechanical ECO application provenance drift")
    require(application["reviewed_commit_sha"] == approval["reviewed_commit_sha"] and
            application["reviewed_candidate_sha256"] ==
            approval["reviewed_candidate_sha256"] and
            application["decision"] == approval["decision"],
            "mechanical ECO application approval binding drift")
    require(application["baseline"] == {
                "commit_sha": candidate["baseline"]["inspected_commit"],
                "board_sha256": candidate["baseline"]["board_sha256"],
                "authority_sha256": candidate["baseline"]["authority_sha256"],
            }, "mechanical ECO application baseline drift")
    applied = application["applied"]
    require(applied == {
                "board": candidate["baseline"]["board"],
                "board_sha256": live_board_sha,
                "authority": candidate["baseline"]["authority"],
                "authority_sha256": live_authority_sha,
                "changed_records": list(EXPECTED_CHANGES),
                "moved_board_anchors": list(BOARD_POSITION_LINES),
            }, "mechanical ECO applied-file record drift")
    require(application["post_application_clearance"] ==
            candidate["expected_audit"]["candidate_unresolved_placement"] | {
                "locked_authority_component_conflicts": [],
                "locked_authority_mounting_conflicts": [],
                "locked_authority_tool_conflicts": [],
            }, "mechanical ECO post-application clearance record drift")
    require(application["status"] == "APPLIED_FULL_REPACK_REQUIRED" and
            application["review_b_complete"] is False and
            application["manufacturing_release"] is False,
            "mechanical ECO application release interlock drift")
    return application


def close(first: float, second: float) -> bool:
    return abs(float(first) - float(second)) <= NUMERIC_TOLERANCE


def rounded(value: float) -> float:
    return round(value, 6)


def bounds(row: dict[str, Any]) -> tuple[float, float, float, float]:
    x = float(row["X_mm"])
    y = float(row["Y_mm"])
    return x, y, x + float(row["Extent_X_mm"]), y + float(row["Extent_Y_mm"])


def overlap_area(first: tuple[float, float, float, float],
                 second: tuple[float, float, float, float]) -> float:
    overlap_x = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    overlap_y = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    return overlap_x * overlap_y


def rect_gap(first: Any, second: Any) -> float:
    gap_x = max(0.0, first.xmin - second.xmax, second.xmin - first.xmax)
    gap_y = max(0.0, first.ymin - second.ymax, second.ymin - first.ymax)
    return math.hypot(gap_x, gap_y)


def rect_tuple_gap(first: tuple[float, float, float, float], second: Any) -> float:
    gap_x = max(0.0, first[0] - second.xmax, second.xmin - first[2])
    gap_y = max(0.0, first[1] - second.ymax, second.ymin - first[3])
    return math.hypot(gap_x, gap_y)


def nearest_distance(hole: dict[str, Any], envelope: Any) -> float:
    nearest_x = max(envelope.xmin, min(float(hole["x_mm"]), envelope.xmax))
    nearest_y = max(envelope.ymin, min(float(hole["y_mm"]), envelope.ymax))
    return math.hypot(nearest_x - float(hole["x_mm"]),
                      nearest_y - float(hole["y_mm"]))


def load_rows(path: Path) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    by_id = {row["Record_ID"]: row for row in rows}
    require(len(by_id) == len(rows), "duplicate MAIN-AUTH-011 record ID")
    return rows, by_id


def apply_candidate(candidate: dict[str, Any], baseline_by_id: dict[str, dict[str, str]]) -> dict[str, dict[str, Any]]:
    changes = candidate.get("changes")
    require(isinstance(changes, list), "candidate changes must be a list")
    require({change.get("record_id") for change in changes} == set(EXPECTED_CHANGES),
            "limited ECO record set drift")
    result = {record_id: dict(row) for record_id, row in baseline_by_id.items()}
    for change in changes:
        record_id = change["record_id"]
        expected_fields = EXPECTED_CHANGES[record_id]
        require(change.get("refdes") == baseline_by_id[record_id]["RefDes"],
                f"{record_id}: RefDes mismatch")
        fields = change.get("fields")
        require(isinstance(fields, dict) and set(fields) == set(expected_fields),
                f"{record_id}: changed field set drift")
        for field, (expected_from, expected_to) in expected_fields.items():
            transition = fields[field]
            require(set(transition) == {"from", "to"},
                    f"{record_id}.{field}: transition schema drift")
            require(close(float(baseline_by_id[record_id][field]), expected_from),
                    f"{record_id}.{field}: authority baseline drift")
            require(close(float(transition["from"]), expected_from) and
                    close(float(transition["to"]), expected_to),
                    f"{record_id}.{field}: candidate transition drift")
            result[record_id][field] = str(expected_to)
    return result


def collision_sets(envelopes: list[Any], mounting_holes: list[dict[str, Any]],
                   tool_clearances: list[dict[str, Any]]) -> tuple[list[list[str]], list[list[str]], list[list[str]]]:
    component_pairs = []
    for first, second in combinations(envelopes, 2):
        finding = component_collision(first, second)
        if finding is not None:
            component_pairs.append(finding["pair"])
    mounting_pairs = []
    for hole in mounting_holes:
        for envelope in envelopes:
            finding = mounting_conflict(hole, envelope)
            if finding is not None:
                mounting_pairs.append(finding["pair"])
    tool_pairs = []
    for clearance in tool_clearances:
        for envelope in envelopes:
            finding = tool_clearance_conflict(clearance, envelope)
            if finding is not None:
                tool_pairs.append(finding["pair"])
    return sorted(component_pairs), sorted(mounting_pairs), sorted(tool_pairs)


def candidate_tool_clearances(baseline: list[dict[str, Any]],
                              candidate_by_id: dict[str, dict[str, Any]],
                              baseline_by_id: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    record_by_ref = {
        row["RefDes"]: row["Record_ID"] for row in baseline_by_id.values()
        if row["Feature_Type"] == "CONNECTOR_PLACEMENT"
    }
    result = []
    for clearance in baseline:
        row = candidate_by_id[record_by_ref[clearance["ref"]]]
        result.append({
            **clearance,
            "x_mm": float(row["X_mm"]),
            "y_mm": float(row["Y_mm"]),
        })
    return result


def circle_to_envelope_gap(clearance: dict[str, Any], envelope: Any) -> float:
    nearest_x = max(envelope.xmin, min(clearance["x_mm"], envelope.xmax))
    nearest_y = max(envelope.ymin, min(clearance["y_mm"], envelope.ymax))
    return math.hypot(nearest_x - clearance["x_mm"],
                      nearest_y - clearance["y_mm"]) - clearance["diameter_mm"] / 2.0


def circle_to_hole_exclusion_gap(clearance: dict[str, Any], hole: dict[str, Any]) -> float:
    center_distance = math.hypot(clearance["x_mm"] - hole["x_mm"],
                                 clearance["y_mm"] - hole["y_mm"])
    return (center_distance - clearance["diameter_mm"] / 2.0 -
            hole["component_exclusion_diameter_mm"] / 2.0)


def audit(
    candidate_path: Path,
    approval_path: Path,
    mapping_path: Path,
    application_path: Path,
) -> dict[str, Any]:
    approval = validate_approval(approval_path, candidate_path)
    mapping, reviewed_candidate = validate_review_commit_mapping(mapping_path, approval)
    live_candidate = candidate_path.read_bytes()
    require(sha256_bytes(live_candidate) == REVIEWED_CANDIDATE_SHA256,
            "live mechanical ECO candidate SHA-256 does not match approval")
    require(sha256_bytes(reviewed_candidate) == approval["reviewed_candidate_sha256"],
            "reviewed Git candidate SHA-256 does not match approval")
    require(live_candidate == reviewed_candidate,
            "live mechanical ECO candidate differs from reviewed Git candidate")
    candidate = json.loads(reviewed_candidate.decode("utf-8"))
    require(candidate.get("schema_version") == "dioneya.pcb-main-mechanical-eco-candidate.v1",
            "candidate schema version drift")
    require(candidate.get("configuration") == "EVT-PRE-20 Rev.A",
            "candidate configuration drift")
    require(candidate.get("proposal_id") == "PCB-MAIN-MECH-ECO-001",
            "candidate proposal ID drift")
    require(candidate.get("status") == "PROPOSED_NOT_APPROVED",
            "candidate must remain explicitly unapproved")
    require(candidate.get("scope") == "LIMITED_MAIN_AUTH_011_MECHANICAL_ECO",
            "candidate scope drift")
    require(candidate.get("manufacturing_release") is False,
            "candidate cannot release manufacturing")
    require(candidate.get("approval") == {
                "reviewer": None, "date": None, "decision": None, "commit_sha": None,
            }, "unapproved candidate contains approval data")

    baseline = candidate["baseline"]
    require(baseline.get("inspected_commit") ==
            "989ce217d44795ba2986453d1f37152af5a8e1fc",
            "candidate inspected commit drift")
    baseline_board = git_blob(baseline["inspected_commit"], baseline["board"])
    baseline_authority = git_blob(baseline["inspected_commit"], baseline["authority"])
    require(sha256_bytes(baseline_board) == baseline["board_sha256"],
            "candidate baseline board SHA-256 drift")
    require(sha256_bytes(baseline_authority) == baseline["authority_sha256"],
            "candidate baseline authority SHA-256 drift")

    history = tempfile.TemporaryDirectory(prefix="pcb-main-mechanical-eco-")
    board_path = Path(history.name) / "PCB-MAIN-baseline.kicad_pcb"
    authority_path = Path(history.name) / "PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_BASELINE.csv"
    board_path.write_bytes(baseline_board)
    authority_path.write_bytes(baseline_authority)

    rows, baseline_by_id = load_rows(authority_path)
    require(len(rows) == 70, "MAIN-AUTH-011 record count drift")
    candidate_by_id = apply_candidate(candidate, baseline_by_id)

    immutable = candidate["immutable_constraints"]
    outline = candidate_by_id["MECH-001"]
    require([float(outline["Extent_X_mm"]), float(outline["Extent_Y_mm"])] ==
            immutable["board_outline_mm"], "board outline candidate drift")
    require(outline["Geometry"] == "ROUNDED_RECT_R3" and
            close(immutable["board_corner_radius_mm"], 3.0),
            "board corner radius candidate drift")
    require(immutable["mounting_holes_unchanged"] is True and
            immutable["connector_and_module_rotations_unchanged"] is True and
            immutable["electrical_connectivity_unchanged"] is True,
            "immutable constraint declaration drift")

    locked_refs, mounting_holes = load_authority(authority_path)
    baseline_tool_clearances = load_tool_clearances(authority_path)
    proposed_tool_clearances = candidate_tool_clearances(
        baseline_tool_clearances, candidate_by_id, baseline_by_id
    )
    require(all(close(hole["component_exclusion_diameter_mm"],
                      immutable["component_exclusion_diameter_mm"])
                for hole in mounting_holes), "mounting exclusion candidate drift")
    board = Board.from_file(str(board_path), encoding="utf-8")
    footprints = {ref_of(footprint): footprint for footprint in board.footprints}
    require(len(footprints) == len(board.footprints), "duplicate footprint reference")

    baseline_locked = []
    candidate_locked = []
    candidate_envelopes: dict[str, Any] = {}
    for ref in sorted(locked_refs):
        baseline_row = next(row for row in rows if row["RefDes"] == ref and
                            row["Feature_Type"] in {"CONNECTOR_PLACEMENT", "MODULE_PLACEMENT"})
        candidate_row = candidate_by_id[baseline_row["Record_ID"]]
        footprint = footprints[ref]
        require(close(footprint.position.X, float(baseline_row["X_mm"])) and
                close(footprint.position.Y, float(baseline_row["Y_mm"])),
                f"{ref}: native board does not match candidate baseline authority")
        actual_angle = float(footprint.position.angle or 0.0) % 360.0
        require(close(actual_angle, float(baseline_row["Rotation_deg"]) % 360.0),
                f"{ref}: native board orientation does not match baseline authority")
        require(close(float(candidate_row["Rotation_deg"]), float(baseline_row["Rotation_deg"])),
                f"{ref}: candidate changes a locked orientation")
        envelope = envelope_of(footprint, locked_refs)
        require(envelope.source == COURTYARD_SOURCE,
                f"{ref}: locked candidate evaluation requires a controlled courtyard")
        baseline_locked.append(envelope)
        dx = float(candidate_row["X_mm"]) - float(baseline_row["X_mm"])
        dy = float(candidate_row["Y_mm"]) - float(baseline_row["Y_mm"])
        shifted = replace(envelope, xmin=envelope.xmin + dx, xmax=envelope.xmax + dx,
                          ymin=envelope.ymin + dy, ymax=envelope.ymax + dy)
        candidate_locked.append(shifted)
        candidate_envelopes[ref] = shifted

    baseline_components, baseline_mounting, baseline_tools = collision_sets(
        baseline_locked, mounting_holes, baseline_tool_clearances
    )
    candidate_components, candidate_mounting, candidate_tools = collision_sets(
        candidate_locked, mounting_holes, proposed_tool_clearances
    )
    expected = candidate["expected_audit"]
    require(baseline_components == expected["baseline_locked_component_conflicts"],
            "baseline locked component-conflict set drift")
    require(baseline_mounting == expected["baseline_locked_mounting_conflicts"],
            "baseline locked mounting-conflict set drift")
    require(baseline_tools == expected["baseline_locked_tool_conflicts"],
            "baseline locked tool-conflict set drift")
    require(candidate_components == expected["candidate_locked_component_conflicts"],
            "candidate creates a locked component conflict")
    require(candidate_mounting == expected["candidate_locked_mounting_conflicts"],
            "candidate creates a locked mounting conflict")
    require(candidate_tools == expected["candidate_locked_tool_conflicts"],
            "candidate creates a locked tool-clearance conflict")

    # Calculate residual findings on the unchanged, unrouted placement after
    # applying only the six proposed anchor translations.  These counts must
    # stay non-zero: this proposal is not a packed board.
    assembly = []
    for footprint in board.footprints:
        if footprint.properties.get("DIONEA_POPULATION") != "FITTED":
            continue
        if footprint.properties.get("DIONEA_PACKAGE", "").startswith(FIXTURE_PACKAGE_PREFIX):
            continue
        envelope = envelope_of(footprint, locked_refs)
        if envelope.ref in candidate_envelopes:
            envelope = candidate_envelopes[envelope.ref]
        assembly.append(envelope)
    component_findings = [finding for first, second in combinations(assembly, 2)
                          if (finding := component_collision(first, second)) is not None]
    mounting_findings = [finding for hole in mounting_holes for envelope in assembly
                         if (finding := mounting_conflict(hole, envelope)) is not None]
    tool_findings = [finding for clearance in proposed_tool_clearances for envelope in assembly
                     if (finding := tool_clearance_conflict(clearance, envelope)) is not None]
    component_counts = Counter(finding["classification"] for finding in component_findings)
    mounting_counts = Counter(finding["classification"] for finding in mounting_findings)
    tool_counts = Counter(finding["classification"] for finding in tool_findings)
    unresolved = {
        "confirmed_component_collisions": component_counts["CONFIRMED_COURTYARD_COLLISION"],
        "screening_component_collisions": component_counts["SCREENING_PAD_ENVELOPE_COLLISION"],
        "confirmed_mounting_clearance_conflicts":
            mounting_counts["CONFIRMED_COURTYARD_TO_MOUNTING_EXCLUSION_CONFLICT"],
        "screening_mounting_clearance_conflicts":
            mounting_counts["SCREENING_PAD_ENVELOPE_TO_MOUNTING_EXCLUSION_CONFLICT"],
        "confirmed_tool_clearance_conflicts":
            tool_counts["CONFIRMED_TOOL_CLEARANCE_TO_COURTYARD_CONFLICT"],
        "screening_tool_clearance_conflicts":
            tool_counts["SCREENING_TOOL_CLEARANCE_TO_PAD_ENVELOPE_CONFLICT"],
    }
    require(unresolved == expected["candidate_unresolved_placement"],
            "candidate residual placement inventory drift")
    require(sum(unresolved.values()) > 0, "candidate incorrectly appears placement-complete")

    hole_by_ref = {hole["ref"]: hole for hole in mounting_holes}
    cell_zone = bounds(candidate_by_id["MECH-024"])
    lora_zone = bounds(candidate_by_id["MECH-026"])
    audio_zone = bounds(candidate_by_id["MECH-031"])
    mic1_corridor = bounds(candidate_by_id["MECH-032"])
    j8 = candidate_envelopes["J8"]
    j9 = candidate_envelopes["J9"]
    j10 = candidate_envelopes["J10"]
    u8 = candidate_envelopes["U8"]
    u9 = candidate_envelopes["U9"]
    u10 = candidate_envelopes["U10"]
    j_pwr = candidate_envelopes["J_PWR"]
    j_mic1 = candidate_envelopes["J_MIC1"]
    j13 = candidate_envelopes["J13"]
    require(cell_zone[0] <= j8.xmin and cell_zone[1] <= j8.ymin and
            cell_zone[2] >= j8.xmax and cell_zone[3] >= j8.ymax,
            "moved J8 courtyard is outside proposed ZONE_CELL")
    require(lora_zone[0] <= j10.xmin and lora_zone[1] <= j10.ymin and
            lora_zone[2] >= j10.xmax and lora_zone[3] >= j10.ymax,
            "moved J10 courtyard is outside proposed ZONE_LORA")
    require(close(overlap_area(cell_zone, audio_zone), 0.0),
            "proposed ZONE_CELL overlaps ZONE_AUDIO_DIGITAL")
    require(close(overlap_area(cell_zone, mic1_corridor), 0.0),
            "proposed MIC1 corridor enters ZONE_CELL")
    require(close(mic1_corridor[2] - mic1_corridor[0], 10.0),
            "proposed MIC1 inboard corridor is not 10 mm")

    tool_by_ref = {clearance["ref"]: clearance for clearance in proposed_tool_clearances}
    edge_clearance = float(immutable["board_component_edge_clearance_mm"])
    board_width = float(outline["Extent_X_mm"])
    board_height = float(outline["Extent_Y_mm"])
    for ref in ("J8", "J10"):
        envelope = candidate_envelopes[ref]
        require(min(envelope.xmin, envelope.ymin,
                    board_width - envelope.xmax, board_height - envelope.ymax) >=
                edge_clearance - NUMERIC_TOLERANCE,
                f"{ref}: proposed courtyard violates board component-edge clearance")

    metrics = {
        "j_pwr_to_j_mic1_edge_gap": rounded(rect_gap(j_pwr, j_mic1)),
        "j8_to_u8_edge_gap": rounded(rect_gap(j8, u8)),
        "j10_to_u10_edge_gap": rounded(rect_gap(j10, u10)),
        "h1_to_j_pwr_component_exclusion": rounded(
            nearest_distance(hole_by_ref["H1"], j_pwr) -
            hole_by_ref["H1"]["component_exclusion_diameter_mm"] / 2.0),
        "h2_to_j13_component_exclusion": rounded(
            nearest_distance(hole_by_ref["H2"], j13) -
            hole_by_ref["H2"]["component_exclusion_diameter_mm"] / 2.0),
        "mic1_corridor_to_u8_edge_gap": rounded(rect_tuple_gap(mic1_corridor, u8)),
        "cell_zone_to_audio_zone_gap": rounded(max(0.0, audio_zone[0] - cell_zone[2])),
        "cell_zone_to_north_board_edge": rounded(float(outline["Extent_Y_mm"]) - cell_zone[3]),
        "lora_zone_to_north_board_edge": rounded(board_height - lora_zone[3]),
        "cell_zone_south_strip_below_u8_courtyard": rounded(u8.ymin - cell_zone[1]),
        "j8_courtyard_to_north_board_edge": rounded(board_height - j8.ymax),
        "j10_courtyard_to_north_board_edge": rounded(board_height - j10.ymax),
        "j8_tool_to_u8_courtyard": rounded(circle_to_envelope_gap(tool_by_ref["J8"], u8)),
        "j9_tool_to_u9_courtyard": rounded(circle_to_envelope_gap(tool_by_ref["J9"], u9)),
        "j10_tool_to_u10_courtyard": rounded(circle_to_envelope_gap(tool_by_ref["J10"], u10)),
        "j8_tool_to_h4_component_exclusion": rounded(
            circle_to_hole_exclusion_gap(tool_by_ref["J8"], hole_by_ref["H4"])
        ),
    }
    require(metrics == expected["margins_mm"],
            f"candidate clearance metrics drift: {metrics!r}")
    require(min(metrics.values()) >= 0.0, "candidate contains a negative controlled margin")
    service_geometry = {
        "ufl_tool_diameter": rounded(tool_by_ref["J8"]["diameter_mm"]),
        "ufl_tool_height": rounded(tool_by_ref["J8"]["height_mm"]),
        "j8_tool_north_overhang": rounded(
            max(0.0, tool_by_ref["J8"]["y_mm"] +
                tool_by_ref["J8"]["diameter_mm"] / 2.0 - board_height)),
        "j10_tool_north_overhang": rounded(
            max(0.0, tool_by_ref["J10"]["y_mm"] +
                tool_by_ref["J10"]["diameter_mm"] / 2.0 - board_height)),
    }
    require(service_geometry == expected["service_geometry_mm"],
            f"candidate service geometry drift: {service_geometry!r}")

    open_validation = candidate.get("open_validation")
    require(isinstance(open_validation, list) and len(open_validation) == 4 and
            all(isinstance(item, str) and item for item in open_validation),
            "candidate open-validation list drift")
    live_board_path = ROOT / baseline["board"]
    live_authority_path = ROOT / baseline["authority"]
    require(live_board_path.is_file(), "live PCB-MAIN board is missing")
    require(live_authority_path.is_file(), "live MAIN-AUTH-011 authority is missing")
    live_board_sha = sha256(live_board_path)
    live_authority_sha = sha256(live_authority_path)
    baseline_is_live = (
        live_board_sha == baseline["board_sha256"] and
        live_authority_sha == baseline["authority_sha256"]
    )
    if baseline_is_live:
        application_status = "APPROVED_PENDING_APPLICATION"
    else:
        require(live_board_sha != baseline["board_sha256"] and
                live_authority_sha != baseline["authority_sha256"],
                "mechanical ECO is only partially applied")
        authority_matches_applied(live_authority_path, candidate_by_id)
        require(live_board_path.read_bytes() == expected_applied_board(baseline_board),
                "native PCB-MAIN differs from the exact approved six-anchor move")
        require(application_path.is_file(), "mechanical ECO application record is missing")
        validate_application(
            application_path, candidate, approval, live_board_sha, live_authority_sha
        )
        application_status = (
            "PASS_APPROVED_ECO_APPLIED_GEOMETRY_ONLY_PLACEMENT_REPACK_REQUIRED"
        )

    return {
        "schema_version": "dioneya.pcb-main-mechanical-eco-audit.v1",
        "proposal_id": candidate["proposal_id"],
        "status": application_status,
        "candidate_file": str(candidate_path.resolve().relative_to(ROOT)),
        "candidate_sha256": sha256(candidate_path),
        "baseline_board_sha256": sha256_bytes(baseline_board),
        "baseline_authority_sha256": sha256_bytes(baseline_authority),
        "live_board_sha256": live_board_sha,
        "live_authority_sha256": live_authority_sha,
        "changed_records": sorted(EXPECTED_CHANGES),
        "baseline_locked_component_conflicts": baseline_components,
        "baseline_locked_mounting_conflicts": baseline_mounting,
        "baseline_locked_tool_conflicts": baseline_tools,
        "candidate_locked_component_conflicts": candidate_components,
        "candidate_locked_mounting_conflicts": candidate_mounting,
        "candidate_locked_tool_conflicts": candidate_tools,
        "candidate_unresolved_placement": unresolved,
        "margins_mm": metrics,
        "service_geometry_mm": service_geometry,
        "approval": {
            "reviewer": approval["reviewer"],
            "date": approval["date"],
            "reviewed_commit_sha": approval["reviewed_commit_sha"],
            "reviewed_candidate_sha256": approval["reviewed_candidate_sha256"],
            "decision": approval["decision"],
            "scope": approval["scope"],
        },
        "review_commit_mapping": {
            "reviewed_local_commit_sha": mapping["reviewed_local_commit_sha"],
            "github_equivalent_commit_sha": mapping["github_equivalent_commit_sha"],
            "reviewed_tree_sha": mapping["reviewed_tree_sha"],
            "candidate_blob_sha": mapping["candidate_blob_sha"],
            "equivalence": mapping["equivalence"],
        },
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--approval", type=Path, default=DEFAULT_APPROVAL)
    parser.add_argument(
        "--review-commit-mapping", type=Path, default=DEFAULT_REVIEW_COMMIT_MAPPING
    )
    parser.add_argument("--application", type=Path, default=DEFAULT_APPLICATION)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    candidate_path = args.candidate.resolve()
    approval_path = args.approval.resolve()
    mapping_path = args.review_commit_mapping.resolve()
    application_path = args.application.resolve()
    require(candidate_path.is_file(), f"candidate not found: {candidate_path}")
    require(approval_path.is_file(), f"approval not found: {approval_path}")
    require(mapping_path.is_file(), f"review commit mapping not found: {mapping_path}")
    report = audit(candidate_path, approval_path, mapping_path, application_path)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    print(f"PCB-MAIN mechanical ECO candidate: {report['status']}")
    print(f"changed_records={report['changed_records']}")
    print(
        "locked_conflicts="
        f"components:{report['candidate_locked_component_conflicts']} "
        f"mounting:{report['candidate_locked_mounting_conflicts']} "
        f"tool:{report['candidate_locked_tool_conflicts']}"
    )
    print(f"residual_unlocked_placement={report['candidate_unresolved_placement']}")
    print(f"margins_mm={report['margins_mm']}")
    print(
        "approval=ACCEPT_LIMITED_MECHANICAL_ECO "
        f"application={report['status']} manufacturing_release=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
