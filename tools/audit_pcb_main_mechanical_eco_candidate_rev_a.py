#!/usr/bin/env python3
"""Audit the unapproved PCB-MAIN limited mechanical ECO candidate.

The candidate is an overlay calculation only.  It deliberately does not edit
MAIN-AUTH-011 or the native board and cannot be used as manufacturing release.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
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
NUMERIC_TOLERANCE = 1e-6
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


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def audit(candidate_path: Path) -> dict[str, Any]:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
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
    board_path = ROOT / baseline["board"]
    authority_path = ROOT / baseline["authority"]
    require(board_path.is_file(), "candidate baseline board is missing")
    require(authority_path.is_file(), "candidate baseline authority is missing")
    require(sha256(board_path) == baseline["board_sha256"],
            "candidate baseline board SHA-256 drift")
    require(sha256(authority_path) == baseline["authority_sha256"],
            "candidate baseline authority SHA-256 drift")

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
    return {
        "schema_version": "dioneya.pcb-main-mechanical-eco-audit.v1",
        "proposal_id": candidate["proposal_id"],
        "status": "PASS_PROPOSAL_GEOMETRY_ONLY_NOT_APPROVED",
        "candidate_file": str(candidate_path.resolve().relative_to(ROOT)),
        "candidate_sha256": sha256(candidate_path),
        "baseline_board_sha256": sha256(board_path),
        "baseline_authority_sha256": sha256(authority_path),
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
        "approval": candidate["approval"],
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    candidate_path = args.candidate.resolve()
    require(candidate_path.is_file(), f"candidate not found: {candidate_path}")
    report = audit(candidate_path)
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
    print("authority_mutated=false approval=false manufacturing_release=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
