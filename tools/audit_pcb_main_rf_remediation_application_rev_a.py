#!/usr/bin/env python3
"""Audit the composed application of both accepted PCB-MAIN RF remediations."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from kiutils.board import Board

import audit_pcb_main_gnss_rf_eco_001_candidate_rev_a as gnss_audit
import audit_pcb_main_placement_clearance_rev_a as placement_audit
import audit_pcb_main_rf_return_001_candidate_rev_a as cellular_audit
import generate_pcb_main_rf_remediation_application_rev_a as generator


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-GNSS-RF-ECO-001/"
    "PCB-MAIN_GNSS_RF_ECO_001_BASE_REV_A.kicad_pcb"
)
GNSS_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-GNSS-RF-ECO-001/"
    "PCB-MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.kicad_pcb"
)
CELLULAR_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-RETURN-001/"
    "PCB-MAIN_RF_RETURN_CANDIDATE_REV_A.kicad_pcb"
)
COMPOSED = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-REMEDIATION-APPLICATION-001/"
    "PCB-MAIN_RF_REMEDIATION_COMPOSED_REV_A.kicad_pcb"
)
CELLULAR_APPROVAL = (
    ROOT / "hardware/reviews/PCB_MAIN_RF_RETURN_001_APPROVAL_REV_A.json"
)
CELLULAR_MAPPING = (
    ROOT / "hardware/reviews/PCB_MAIN_RF_RETURN_001_REVIEW_COMMIT_MAPPING.json"
)
CELLULAR_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_RF_RETURN_001_APPLICATION_REV_A.json"
)
GNSS_APPROVAL = (
    ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_APPROVAL_REV_A.json"
)
GNSS_MAPPING = (
    ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_REVIEW_COMMIT_MAPPING.json"
)
GNSS_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_APPLICATION_REV_A.json"
)
REPEAT_REVIEW = (
    ROOT / "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_002_REV_A.json"
)
GENERATOR = ROOT / "tools/generate_pcb_main_rf_remediation_application_rev_a.py"
PLACEMENT_AUTHORITY = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
CAPTURE_STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"

BASE_SHA256 = "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
CELLULAR_SHA256 = "22ddd8c56ceabf397ed033a44235b439625d3104fa2cf798bb57b782d24b1352"
GNSS_SHA256 = "d4c0eaa95bb62c7b9ae15b110fb3a76e6a056f462f0a36a734b3fa63730d2aee"
COMPOSED_SHA256 = "f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9"
GENERATOR_SHA256 = "9014e03d6dbd3fe6f153d1a5a557ac2832904e264f165b03ba0cdca38a7fe3fa"
CELLULAR_APPROVAL_SHA256 = "000e323f116d9b4aa371142c9efe37d85241563ea8db41c2f9b23bfca6bee079"
GNSS_APPROVAL_SHA256 = "3668c63ab845186cbfc669f63765b98ffe70b281a59e58f00a4f26841ff69127"
CELLULAR_APPROVAL_COMMIT = "404f18316bcf3659f3afe787420ed1711aa9c019"
GNSS_APPROVAL_COMMIT = "8840ef36653e1d62d80c128f21934e4f4c1a5e91"
CELLULAR_APPLICATION_COMMIT = "3a309159db6479144ac2eb0a72c1a12742036ab9"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref_of(footprint: Any) -> str:
    property_ref = str(footprint.properties.get("Reference", ""))
    if property_ref:
        return property_ref
    return next(
        str(item.text)
        for item in footprint.graphicItems
        if getattr(item, "type", None) == "reference"
    )


def drc_inventory(path: Path) -> tuple[Counter[str], int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = Counter(
        item.get("type", "UNKNOWN")
        for item in data.get("violations", [])
        if item.get("severity") == "error"
    )
    return errors, len(data.get("violations", [])), len(data.get("unconnected_items", []))


def audit_drc(base_path: Path, candidate_path: Path) -> dict[str, object]:
    base_errors, base_violations, base_unconnected = drc_inventory(base_path)
    candidate_errors, candidate_violations, candidate_unconnected = drc_inventory(candidate_path)
    added_errors = {
        key: candidate_errors[key] - base_errors[key]
        for key in candidate_errors
        if candidate_errors[key] > base_errors[key]
    }
    require(not added_errors, f"composed RF remediation adds DRC errors: {added_errors}")
    require(
        candidate_unconnected <= base_unconnected,
        "composed RF remediation increases unconnected items",
    )
    return {
        "status": "PASS_NO_NEW_KICAD9_DRC_ERRORS_OR_UNCONNECTED_REGRESSION",
        "base_violations": base_violations,
        "candidate_violations": candidate_violations,
        "base_errors": dict(base_errors),
        "candidate_errors": dict(candidate_errors),
        "base_unconnected_items": base_unconnected,
        "candidate_unconnected_items": candidate_unconnected,
        "new_error_counts": added_errors,
    }


def static_audit() -> dict[str, object]:
    for path in (
        BOARD, BASE, GNSS_CANDIDATE, CELLULAR_CANDIDATE, COMPOSED,
        CELLULAR_APPROVAL, CELLULAR_MAPPING, CELLULAR_APPLICATION,
        GNSS_APPROVAL, GNSS_MAPPING, GNSS_APPLICATION, REPEAT_REVIEW, GENERATOR,
        PLACEMENT_AUTHORITY, CAPTURE_STATUS,
    ):
        require(path.is_file() and path.stat().st_size > 0,
                f"missing RF-remediation application input: {path}")

    require(sha256(BASE) == BASE_SHA256, "reviewed RF base SHA-256 drift")
    require(sha256(CELLULAR_CANDIDATE) == CELLULAR_SHA256,
            "reviewed cellular candidate SHA-256 drift")
    require(sha256(GNSS_CANDIDATE) == GNSS_SHA256,
            "reviewed GNSS candidate SHA-256 drift")
    require(sha256(COMPOSED) == COMPOSED_SHA256 and
            sha256(BOARD) == COMPOSED_SHA256 and
            BOARD.read_bytes() == COMPOSED.read_bytes() == generator.composed_bytes(),
            "authoritative board is not the exact deterministic composition")
    require(sha256(GENERATOR) == GENERATOR_SHA256,
            "RF-remediation composition generator SHA-256 drift")
    require(sha256(CELLULAR_APPROVAL) == CELLULAR_APPROVAL_SHA256,
            "cellular approval SHA-256 drift")
    require(sha256(GNSS_APPROVAL) == GNSS_APPROVAL_SHA256,
            "GNSS approval SHA-256 drift")

    cellular_approval = json.loads(CELLULAR_APPROVAL.read_text(encoding="utf-8"))
    gnss_approval = json.loads(GNSS_APPROVAL.read_text(encoding="utf-8"))
    require(
        cellular_approval.get("decision") ==
        "ACCEPT_CELLULAR_L2_RETURN_PLANE_SUBGATE"
        and cellular_approval.get("reviewed_candidate_board_sha256") == CELLULAR_SHA256
        and cellular_approval.get("authorization", {}).get(
            "cam_or_manufacturing_release"
        ) is False,
        "cellular approval identity or boundary drift",
    )
    require(
        gnss_approval.get("decision") ==
        "ACCEPT_GNSS_RF_PLACEMENT_ROUTEABILITY_SUBGATE"
        and gnss_approval.get("reviewed_candidate_board_sha256") == GNSS_SHA256
        and gnss_approval.get("authorization", {}).get(
            "cam_or_manufacturing_release"
        ) is False,
        "GNSS approval identity or boundary drift",
    )

    cellular_mapping = json.loads(CELLULAR_MAPPING.read_text(encoding="utf-8"))
    gnss_mapping = json.loads(GNSS_MAPPING.read_text(encoding="utf-8"))
    require(
        cellular_mapping.get("reviewed_github_commit_sha") ==
        "239016fdd295426766cc88209822be39610297db"
        and cellular_mapping.get("reviewed_tree_sha") ==
        "7a6e0c226318bd85e6456d17bae119b489d2aff1"
        and cellular_mapping.get("candidate_board_sha256") == CELLULAR_SHA256
        and cellular_mapping.get("equivalence") == "EXACT_REVIEWED_TREE_AND_BLOBS",
        "cellular reviewed-commit mapping drift",
    )
    require(
        gnss_mapping.get("reviewed_github_commit_sha") ==
        "67538ba5dfea4cde08c06738cc6b537847a25398"
        and gnss_mapping.get("reviewed_tree_sha") ==
        "f45c0923461b299eb3ccfaa97eb9ca2cf069a285"
        and gnss_mapping.get("candidate_board_sha256") == GNSS_SHA256
        and gnss_mapping.get("equivalence") == "EXACT_REVIEWED_TREE_AND_BLOBS",
        "GNSS reviewed-commit mapping drift",
    )

    cellular_application = json.loads(
        CELLULAR_APPLICATION.read_text(encoding="utf-8")
    )
    gnss_application = json.loads(GNSS_APPLICATION.read_text(encoding="utf-8"))
    require(
        cellular_application.get("approval_commit_sha") == CELLULAR_APPROVAL_COMMIT
        and cellular_application.get("approval_sha256") == CELLULAR_APPROVAL_SHA256
        and cellular_application.get("reviewed_candidate_board_sha256") ==
        CELLULAR_SHA256
        and cellular_application.get("applied_intermediate", {}).get(
            "board_sha256"
        ) == CELLULAR_SHA256
        and cellular_application.get("applied_intermediate", {}).get(
            "exact_candidate_byte_identity"
        ) is True
        and cellular_application.get("successor_composition", {}).get(
            "combined_machine_gate_status"
        ) == "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE"
        and cellular_application.get("routing_complete") is False
        and cellular_application.get("review_b_complete") is False
        and cellular_application.get("cam_or_manufacturing_release") is False,
        "cellular application identity, geometry, or boundary drift",
    )
    applied = gnss_application.get("applied", {})
    composition = gnss_application.get("composition", {})
    require(
        gnss_application.get("approval_commit_sha") == GNSS_APPROVAL_COMMIT
        and gnss_application.get("approval_sha256") == GNSS_APPROVAL_SHA256
        and gnss_application.get("reviewed_candidate_board_sha256") == GNSS_SHA256
        and gnss_application.get("predecessor_application", {}).get("commit_sha") ==
        CELLULAR_APPLICATION_COMMIT
        and composition.get("generator_sha256") == GENERATOR_SHA256
        and composition.get("composed_board_sha256") == COMPOSED_SHA256
        and composition.get("remove_exact_cellular_zone_yields_reviewed_gnss_candidate")
        is True
        and composition.get("reviewed_gnss_delta_regenerates_exactly") is True
        and composition.get("cellular_l2_zone_preserved_exactly") is True
        and applied.get("board_sha256") == COMPOSED_SHA256
        and applied.get("exact_composed_board_byte_identity") is True
        and applied.get("exact_reviewed_gnss_delta_identity") is True
        and applied.get("combined_machine_gate_status") ==
        "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE"
        and gnss_application.get("combined_machine_gate_review") ==
        str(REPEAT_REVIEW.relative_to(ROOT))
        and gnss_application.get("routing_complete") is False
        and gnss_application.get("rf_si_review_complete") is False
        and gnss_application.get("review_b_complete") is False
        and gnss_application.get("cam_or_manufacturing_release") is False,
        "GNSS application identity, composition, or boundary drift",
    )
    repeat_review = json.loads(REPEAT_REVIEW.read_text(encoding="utf-8"))
    repeat_boundary = repeat_review.get("decision_boundary", {})
    machine_gate = repeat_review.get("commit_bound_machine_gate", {})
    require(
        repeat_review.get("status") ==
        "PASS_BOUNDED_RETURN_PATH_REMEDIATIONS_FINAL_SI_AND_REVIEW_B_OPEN"
        and repeat_review.get("reviewed_board_sha256") == COMPOSED_SHA256
        and repeat_review.get("decision") ==
        "PASS_BOUNDED_RETURN_PATH_REMEDIATIONS_FINAL_SI_AND_REVIEW_B_OPEN"
        and machine_gate.get("source_commit_sha") ==
        "7ee9cfc9b4059dc7e487ca5513704b78c22da4e0"
        and machine_gate.get("source_tree_sha") ==
        "fbffec8ca34f283b5c689818780a6ab10495f843"
        and machine_gate.get("pcb_native_gate", {}).get("run_id") == 35516448594
        and machine_gate.get("ci_run", {}).get("run_id") == 35516448578
        and machine_gate.get("artifact", {}).get("id") == 10606594205
        and machine_gate.get("comparative_drc", {}).get("new_error_count") == 0
        and machine_gate.get("comparative_drc", {}).get(
            "candidate_unconnected_items"
        ) == 429
        and machine_gate.get("cellular_filled_reference", {}).get(
            "uncovered_samples"
        ) == 0
        and machine_gate.get("gnss_filled_reference", {}).get(
            "uncovered_samples"
        ) == 0
        and repeat_boundary.get("return_path_remediation_review_complete") is True
        and repeat_boundary.get("final_si_review_complete") is False
        and repeat_boundary.get("remaining_routing_complete") is False
        and repeat_boundary.get("review_b_complete") is False
        and repeat_boundary.get("cam_or_manufacturing_release") is False,
        "commit-bound combined RF-remediation gate or release boundary drift",
    )

    reviewed_gnss = Board.from_file(str(GNSS_CANDIDATE), encoding="utf-8")
    active = Board.from_file(str(BOARD), encoding="utf-8")
    for field in (
        "general", "layers", "setup", "properties", "graphicItems",
        "dimensions", "groups", "targets", "nets", "footprints", "traceItems",
    ):
        require(getattr(reviewed_gnss, field) == getattr(active, field),
                f"composed application changes GNSS-reviewed field: {field}")
    reviewed_zones = {str(item.tstamp): item for item in reviewed_gnss.zones}
    active_zones = {str(item.tstamp): item for item in active.zones}
    require(
        set(active_zones) - set(reviewed_zones) == {cellular_audit.ZONE_TSTAMP}
        and all(reviewed_zones[key] == active_zones[key] for key in reviewed_zones),
        "composed application does not add exactly the accepted cellular L2 zone",
    )
    zone = active_zones[cellular_audit.ZONE_TSTAMP]
    require(
        zone.name == cellular_audit.ZONE_NAME
        and zone.netName == "GND_MODEM"
        and zone.layers == ["In1.Cu"],
        "applied cellular L2 zone identity drift",
    )

    footprints = {ref_of(item): item for item in active.footprints}
    require(
        (float(footprints["FL1"].position.X),
         float(footprints["FL1"].position.Y),
         float(footprints["FL1"].position.angle or 0.0)) == (56.8, 51.6, 270.0)
        and (float(footprints["C64"].position.X),
             float(footprints["C64"].position.Y),
             float(footprints["C64"].position.angle or 0.0)) == (58.3, 51.6, 180.0)
        and (float(footprints["U9"].position.X),
             float(footprints["U9"].position.Y)) == (53.5, 58.0)
        and (float(footprints["J9"].position.X),
             float(footprints["J9"].position.Y)) == (53.5, 68.0),
        "applied GNSS placement or fixed anchors drift",
    )
    segments = [item for item in active.traceItems if type(item).__name__ == "Segment"]
    vias = [item for item in active.traceItems if type(item).__name__ == "Via"]
    length = sum(
        math.hypot(
            float(item.end.X) - float(item.start.X),
            float(item.end.Y) - float(item.start.Y),
        )
        for item in segments
    )
    require(
        len(active.traceItems) == 975
        and len(segments) == 692
        and len(vias) == 283
        and len(active.zones) == 8
        and math.isclose(length, 887.091202891827, abs_tol=1e-9),
        "composed authoritative board inventory drift",
    )

    placement = placement_audit.audit(BOARD, PLACEMENT_AUTHORITY)
    require(
        placement.get("summary", {}).get("state") == "PASS"
        and placement.get("summary", {}).get("confirmed_component_collisions") == 0
        and placement.get("summary", {}).get("confirmed_mounting_clearance_conflicts") == 0
        and placement.get("summary", {}).get("confirmed_tool_clearance_conflicts") == 0,
        "composed authoritative board strict placement clearance drift",
    )

    status = json.loads(CAPTURE_STATUS.read_text(encoding="utf-8"))
    evidence = status.get("review_b", {}).get("evidence", {})
    require(
        evidence.get("rf_si_return_path_status") ==
        "PASS_BOUNDED_REMEDIATIONS_COMBINED_KICAD9_GATE_FINAL_SI_AND_REVIEW_B_OPEN"
        and evidence.get("rf_return_001_status") ==
        "APPROVED_APPLIED_EXACT_CELLULAR_L2_RETURN_ZONE_COMPOSED_WITH_GNSS_ECO"
        and evidence.get("gnss_rf_eco_001_status") ==
        "APPROVED_APPLIED_EXACT_REVIEWED_DELTA_WITH_CELLULAR_L2_ZONE_COMBINED_GATE_PASS"
        and status.get("review_b", {}).get("complete") is False
        and status.get("manufacturing_release") is False,
        "capture-status RF-remediation traceability or release boundary drift",
    )

    return {
        "schema_version": "dioneya.pcb-main-rf-remediation-application-audit.v1",
        "status": "PASS_BOTH_ACCEPTED_RF_REMEDIATIONS_COMPOSED_COMBINED_KICAD9_GATE_BOUND",
        "base_sha256": BASE_SHA256,
        "cellular_candidate_sha256": CELLULAR_SHA256,
        "gnss_candidate_sha256": GNSS_SHA256,
        "composed_board_sha256": COMPOSED_SHA256,
        "trace_items": len(active.traceItems),
        "track_segments": len(segments),
        "vias": len(vias),
        "zones": len(active.zones),
        "strict_placement_clearance": "PASS",
        "combined_machine_gate": "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE",
        "return_path_remediation_review_complete": True,
        "final_si_review_complete": False,
        "routing_complete": False,
        "rf_si_review_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-candidate", type=Path)
    parser.add_argument("--filled-candidate", type=Path)
    args = parser.parse_args()
    report = static_audit()
    if args.drc_base or args.drc_candidate:
        require(bool(args.drc_base and args.drc_candidate),
                "both comparative DRC reports are required")
        report["comparative_drc"] = audit_drc(
            args.drc_base.resolve(), args.drc_candidate.resolve()
        )
    if args.filled_candidate:
        require(bool(args.drc_base and args.drc_candidate),
                "filled-reference audit requires comparative DRC inputs")
        filled = args.filled_candidate.resolve()
        report["cellular_filled_reference"] = cellular_audit.audit_filled_reference(filled)
        report["gnss_filled_reference"] = gnss_audit.audit_filled_reference(filled)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    print("PCB-MAIN composed RF-remediation application audit: PASS")
    print(f"board_sha256={COMPOSED_SHA256} trace_items=975 zones=8")
    print("release_boundary=FINAL_SI_REMAINING_ROUTING_REVIEW_B_AND_MANUFACTURING_OPEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
