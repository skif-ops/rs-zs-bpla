#!/usr/bin/env python3
"""Audit PCB-PWR buck warning-remediation candidate 001."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from kiutils.board import Board

import audit_pcb_pwr_placement_clearance_rev_a as clearance_audit


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIR = (
    ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-WARNING-REMEDIATION-001"
)
BASE = (
    CANDIDATE_DIR
    / "PCB-PWR_BUCK_WARNING_REMEDIATION_001_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    CANDIDATE_DIR
    / "PCB-PWR_BUCK_WARNING_REMEDIATION_001_CANDIDATE_REV_A.kicad_pcb"
)
ACTIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
PLACEMENT = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv"
GENERATOR = (
    ROOT
    / "tools/generate_pcb_pwr_buck_warning_remediation_001_candidate_rev_a.py"
)
REVIEW = (
    ROOT
    / "hardware/reviews/PCB_PWR_BUCK_WARNING_REMEDIATION_001_CANDIDATE_REV_A.json"
)
MAPPING = (
    ROOT
    / "hardware/reviews/PCB_PWR_BUCK_WARNING_REMEDIATION_001_REVIEW_COMMIT_MAPPING.json"
)

BASE_SHA256 = "9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37"
CANDIDATE_SHA256 = "b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957"
BASE_SEMANTIC_SHA256 = "5994f22cdce03bc60779fcf120177bb82f6ecb88b2afdbe9bf4c0c2819af7337"
CANDIDATE_SEMANTIC_SHA256 = "b94eb0e53a714a2259e7362df7b96d1333c885f48399102b7ac279fb368d3276"
BOOTSTRAP_CANDIDATE_SHA256 = "a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236"
BOOTSTRAP_CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-BOOTSTRAP-ROUTING-001/PCB-PWR_BUCK_BOOTSTRAP_ROUTING_001_CANDIDATE_REV_A.kicad_pcb"
GENERATOR_SHA256 = "30041af847360568ed8ab43f34e0cc194d61683da95bacba02eead15946d5eb1"
REVIEWED_GITHUB_COMMIT_SHA = "63d87153e441d956117323ed8d9887568c5033ac"
REVIEWED_TREE_SHA = "87b2c7ab4d8fbc1b5d0d3c88c703994abef773bf"
MACHINE_GATE_ARTIFACT_DIGEST = (
    "sha256:77a1d81b3e03e896c248992ae607c89b2158d7e8692331e45635abcb3f3a84a1"
)
TARGET_REFERENCES = {"C4", "C6", "R10"}
EXPECTED_POSES = {
    "C4": (54.575, 16.4, 180.0),
    "C6": (54.575, 44.4, 180.0),
    "L1": (60.75, 14.0, 180.0),
    "L2": (60.75, 42.0, 180.0),
    "R10": (58.0, 47.0, 0.0),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref_of(footprint: Any) -> str:
    if footprint.properties.get("Reference"):
        return str(footprint.properties["Reference"])
    return next(
        (
            str(item.text)
            for item in footprint.graphicItems
            if getattr(item, "type", None) == "reference"
        ),
        "",
    )


def pose_of(footprint: Any) -> tuple[float, float, float]:
    return (
        float(footprint.position.X),
        float(footprint.position.Y),
        float(footprint.position.angle or 0.0) % 360.0,
    )


def close(first: float, second: float, tolerance: float = 1e-6) -> bool:
    return abs(float(first) - float(second)) <= tolerance


def footprint_block(source: str, reference: str) -> str:
    marker = f'(property "Reference" "{reference}"'
    require(source.count(marker) == 1,
            f"missing or duplicate footprint reference {reference}")
    marker_index = source.index(marker)
    start = source.rfind("\n\t(footprint ", 0, marker_index)
    require(start >= 0, f"cannot locate start of footprint {reference}")
    start += 1
    end = source.find("\n\t(footprint ", marker_index)
    if end < 0:
        for token in ("\n\t(segment ", "\n\t(zone ", "\n\t(gr_"):
            end = source.find(token, marker_index)
            if end >= 0:
                break
    require(end > start, f"cannot locate end of footprint {reference}")
    return source[start:end]


def changed_line_pairs(first: str, second: str) -> Counter[tuple[str, str]]:
    before = first.splitlines()
    after = second.splitlines()
    require(len(before) == len(after), "candidate changes board line count")
    return Counter((old, new) for old, new in zip(before, after) if old != new)


def expected_c4_c6_pairs() -> Counter[tuple[str, str]]:
    return Counter({
        ("\t\t\t(at 0 -1.4 0)", "\t\t\t(at 0 -1.4 180)"): 1,
        ("\t\t\t(at 0 1.16 0)", "\t\t\t(at 0 1.16 180)"): 1,
        ("\t\t\t(at 0 0 0)", "\t\t\t(at 0 0 180)"): 3,
        ("\t\t\t(at -0.48 0)", "\t\t\t(at -0.48 0 180)"): 1,
        ("\t\t\t(at 0.48 0)", "\t\t\t(at 0.48 0 180)"): 1,
    })


def physical_footprint_copy(footprint: Any) -> Any:
    """Normalize representation-only 180-degree child angles for comparison."""
    result = copy.deepcopy(footprint)
    if ref_of(result) in {"C4", "C6"}:
        for item in result.graphicItems:
            position = getattr(item, "position", None)
            if position is not None:
                position.angle = float(position.angle or 0.0) % 180.0
        for pad in result.pads:
            pad.position.angle = float(pad.position.angle or 0.0) % 180.0
    return result


def drc_fingerprint(violation: dict[str, Any]) -> tuple[object, ...]:
    items = []
    for item in violation.get("items", []):
        position = item.get("pos", {})
        items.append((
            item.get("description", ""),
            round(float(position.get("x", 0.0)), 6),
            round(float(position.get("y", 0.0)), 6),
        ))
    return (
        violation.get("severity", ""),
        violation.get("type", ""),
        violation.get("description", ""),
        tuple(sorted(items)),
    )


def is_target_warning(violation: dict[str, Any]) -> bool:
    descriptions = {
        item.get("description", "") for item in violation.get("items", [])
    }
    return (
        violation.get("severity") == "warning"
        and (
            (
                violation.get("type") == "lib_footprint_mismatch"
                and descriptions in ({"Footprint C4"}, {"Footprint C6"})
            )
            or (
                violation.get("type") == "silk_overlap"
                and descriptions == {
                    "Polygon of L2 on F.Silkscreen",
                    "Reference field of R10",
                }
            )
            or (
                violation.get("type") == "silk_over_copper"
                and descriptions == {"Reference field of R10"}
            )
        )
    )


def audit_drc(base_path: Path, candidate_path: Path) -> dict[str, object]:
    base_data = json.loads(base_path.read_text(encoding="utf-8"))
    candidate_data = json.loads(candidate_path.read_text(encoding="utf-8"))
    base_violations = base_data.get("violations", [])
    candidate_violations = candidate_data.get("violations", [])
    base_targets = [item for item in base_violations if is_target_warning(item)]
    candidate_targets = [
        item for item in candidate_violations if is_target_warning(item)
    ]
    require(len(base_targets) == 4,
            f"expected four base warning targets; got {len(base_targets)}")
    require(not candidate_targets,
            "candidate retains a C4/C6 library, L2/R10 overlap, or R10 mask target warning")

    base_remaining = Counter(
        drc_fingerprint(item)
        for item in base_violations
        if not is_target_warning(item)
    )
    candidate_remaining = Counter(
        drc_fingerprint(item) for item in candidate_violations
    )
    require(candidate_remaining == base_remaining,
            "candidate changes DRC findings outside the four warning targets")
    require(len(candidate_violations) == len(base_violations) - 4,
            "candidate does not remove exactly four DRC warnings")
    require(
        len(candidate_data.get("unconnected_items", [])) ==
        len(base_data.get("unconnected_items", [])),
        "warning-only remediation changes unconnected-item count",
    )
    require(
        Counter(
            item.get("type", "UNKNOWN")
            for item in base_violations
            if item.get("severity") == "error"
        ) == Counter(
            item.get("type", "UNKNOWN")
            for item in candidate_violations
            if item.get("severity") == "error"
        ),
        "warning-only remediation changes error inventory",
    )
    return {
        "status": "PASS_EXACT_FOUR_WARNING_CLOSURE_NO_OTHER_DRC_DELTA",
        "base_violations": len(base_violations),
        "candidate_violations": len(candidate_violations),
        "warnings_removed": {
            "lib_footprint_mismatch_C4_C6": 2,
            "silk_overlap_L2_R10": 1,
            "silk_over_copper_R10": 1,
        },
        "base_unconnected": len(base_data.get("unconnected_items", [])),
        "candidate_unconnected": len(candidate_data.get("unconnected_items", [])),
        "new_errors": 0,
        "new_warnings": 0,
    }


def audit(
    drc_base: Path | None = None,
    drc_candidate: Path | None = None,
) -> dict[str, object]:
    for path in (BASE, CANDIDATE, ACTIVE, PLACEMENT, GENERATOR, REVIEW, MAPPING):
        require(path.is_file() and path.stat().st_size > 0,
                f"missing PCB-PWR warning-remediation input: {path}")
    require(sha256(BASE) == BASE_SHA256,
            "PCB-PWR warning-remediation base SHA-256 drift")
    active_sha256 = sha256(ACTIVE)
    require(active_sha256 in {BASE_SHA256, CANDIDATE_SHA256, BOOTSTRAP_CANDIDATE_SHA256,
            "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5",
            "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3"},
            "authoritative PCB-PWR is neither the controlled predecessor nor candidate")
    expected_active = {
        BASE_SHA256: BASE,
        CANDIDATE_SHA256: CANDIDATE,
        BOOTSTRAP_CANDIDATE_SHA256: BOOTSTRAP_CANDIDATE,
        "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5":
        ROOT / "hardware/kicad/candidates/PCB-PWR-LM74700-VCAP-ROUTING-002/PCB-PWR_LM74700_VCAP_ROUTING_002_CANDIDATE_REV_A.kicad_pcb",
        "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3":
        ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-RAW-ROUTING-003/PCB-PWR_VBAT_RAW_ROUTING_003_CANDIDATE_REV_A.kicad_pcb",
    }[active_sha256]
    require(ACTIVE.read_bytes() == expected_active.read_bytes(),
            "authoritative PCB-PWR does not match its controlled byte identity")
    applied = active_sha256 != BASE_SHA256
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "PCB-PWR warning-remediation candidate SHA-256 drift")
    require(sha256(GENERATOR) == GENERATOR_SHA256,
            "PCB-PWR warning-remediation generator SHA-256 drift")

    base_text = BASE.read_text(encoding="utf-8")
    candidate_text = CANDIDATE.read_text(encoding="utf-8")
    expected_board_pairs = Counter({
        pair: count * 2 for pair, count in expected_c4_c6_pairs().items()
    })
    expected_board_pairs.update({
        ("\t\t\t(at 0 -1.4 0)", "\t\t\t(at 0 1.4 0)"): 1,
    })
    require(
        changed_line_pairs(base_text, candidate_text) == expected_board_pairs,
        "candidate raw delta exceeds C4/C6 normalization plus R10 reference move",
    )
    for reference in ("C4", "C6"):
        require(
            changed_line_pairs(
                footprint_block(base_text, reference),
                footprint_block(candidate_text, reference),
            ) == expected_c4_c6_pairs(),
            f"{reference}: rotated-instance normalization delta drift",
        )
    require(
        changed_line_pairs(
            footprint_block(base_text, "R10"),
            footprint_block(candidate_text, "R10"),
        ) == Counter({
            ("\t\t\t(at 0 -1.4 0)", "\t\t\t(at 0 1.4 0)"): 1,
        }),
        "R10 reference-field delta drift",
    )

    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    base_footprints = {ref_of(item): item for item in base.footprints}
    candidate_footprints = {ref_of(item): item for item in candidate.footprints}
    require(base_footprints.keys() == candidate_footprints.keys(),
            "candidate footprint inventory drift")
    require(len(base_footprints) == 66,
            "candidate does not retain 62 electrical plus four mounting footprints")

    for reference in base_footprints:
        first = base_footprints[reference]
        second = candidate_footprints[reference]
        require(
            all(close(a, b) for a, b in zip(pose_of(first), pose_of(second))),
            f"{reference}: footprint pose changed",
        )
        require(
            physical_footprint_copy(first).__dict__ ==
            physical_footprint_copy(second).__dict__,
            f"{reference}: physical footprint data changed",
        )
        if reference not in TARGET_REFERENCES:
            require(
                footprint_block(base_text, reference) ==
                footprint_block(candidate_text, reference),
                f"{reference}: raw footprint block changed outside scope",
            )

    for reference, expected in EXPECTED_POSES.items():
        actual = pose_of(candidate_footprints[reference])
        require(all(close(a, b) for a, b in zip(actual, expected)),
                f"{reference}: controlled pose drift")
    require(len(base.traceItems) == len(candidate.traceItems) == 0 and
            len(base.zones) == len(candidate.zones) == 0,
            "warning-only proposal contains routed copper")
    for field in (
        "version", "generator", "general", "paper", "titleBlock", "layers",
        "setup", "properties", "nets", "traceItems", "zones", "graphicItems",
        "dimensions", "targets", "groups",
    ):
        require(getattr(base, field) == getattr(candidate, field),
                f"candidate changes non-footprint board field {field}")

    clearance = clearance_audit.audit(CANDIDATE, PLACEMENT)
    summary = clearance["summary"]
    require(
        summary.get("state") ==
        "PASS_FITTED_2D_AND_EVT_MOUNTING_CLEARANCE_DIM_003_ACCEPTED"
        and summary.get("minimum_observed_clearance_mm") == 0.22
        and summary.get("clearance_conflicts") == 0
        and summary.get("mounting_to_fitted_body_conflicts") == 0
        and summary.get("mounting_to_existing_pad_conflicts") == 0,
        "warning-remediation candidate strict-clearance drift",
    )

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    require(
        review.get("proposal_id") == "PCB-PWR-BUCK-WARNING-REMEDIATION-001"
        and review.get("status") in {
            "STATIC_PROPOSAL_READY_COMMIT_BOUND_KICAD9_GATE_PENDING",
            "COMMIT_BOUND_KICAD9_GATE_PASS_HUMAN_SUBGATE_PENDING",
        }
        and review.get("base", {}).get("board_sha256") == BASE_SHA256
        and review.get("candidate", {}).get("board_sha256") == CANDIDATE_SHA256
        and review.get("candidate", {}).get("board_semantic_sha256") ==
        CANDIDATE_SEMANTIC_SHA256
        and review.get("candidate", {}).get("generator_sha256") ==
        GENERATOR_SHA256
        and review.get("bounded_delta", {}).get("component_poses_changed") is False
        and review.get("bounded_delta", {}).get("copper_geometry_changed") is False
        and review.get("decision_boundary", {}).get("proposal_only") is True
        and review.get("decision_boundary", {}).get(
            "applied_to_authoritative_board"
        ) is False
        and review.get("decision_boundary", {}).get("manufacturing_release") is False,
        "PCB-PWR warning-remediation proposal boundary drift",
    )
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    gate = mapping.get("machine_gate", {})
    review_gate = review.get("commit_bound_machine_gate", {})
    require(
        mapping.get("proposal_id") ==
        "PCB-PWR-BUCK-WARNING-REMEDIATION-001"
        and mapping.get("reviewed_github_commit_sha") ==
        REVIEWED_GITHUB_COMMIT_SHA
        and mapping.get("reviewed_tree_sha") == REVIEWED_TREE_SHA
        and mapping.get("proposal_blob_sha") ==
        "eae224fc642ee39d650cae26858b0c6d304e3c7e"
        and mapping.get("proposal_sha256") ==
        "195d439e320cc00327f38fa584712e6e4f41b9685a1108a7df046fef9d0739d4"
        and mapping.get("proposal_record_blob_sha") ==
        "d78b9ae2a5e13b73a6380a18ef9fe1d4d05fc1fa"
        and mapping.get("candidate_board_blob_sha") ==
        "1d023412761183a37d596cfa2ad4843945b9dc26"
        and mapping.get("candidate_board_sha256") == CANDIDATE_SHA256
        and mapping.get("generator_blob_sha") ==
        "016b84ffc9a3afbe86838ef2fd6bb8b5b67611c5"
        and mapping.get("generator_sha256") == GENERATOR_SHA256
        and mapping.get("audit_blob_sha") ==
        "9bc71f3a81bfdf08d16e31fd91c22bb4be7a4ca6"
        and mapping.get("audit_sha256") ==
        "473741f73c21cf64039fb700feaf3ad582ab1669e58f65728b67f6f5d40f8059"
        and gate.get("status") ==
        "PASS_EXACT_FOUR_WARNING_CLOSURE_NO_OTHER_DRC_DELTA"
        and gate.get("pcb_native_run_id") == 35595182381
        and gate.get("pcb_native_run_number") == 313
        and gate.get("pcb_native_conclusion") == "success"
        and gate.get("ci_run_id") == 35595182283
        and gate.get("ci_run_number") == 586
        and gate.get("ci_conclusion") == "success"
        and gate.get("artifact_id") == 10636550793
        and gate.get("artifact_digest") == MACHINE_GATE_ARTIFACT_DIGEST
        and gate.get("base_violations") == 90
        and gate.get("candidate_violations") == 86
        and gate.get("base_unconnected") == 126
        and gate.get("candidate_unconnected") == 126
        and gate.get("new_errors") == 0
        and gate.get("new_warnings") == 0
        and gate.get("all_other_drc_fingerprints_match") is True
        and mapping.get("human_subgate_pending") is True
        and mapping.get("applied_to_authoritative_board") is False,
        "PCB-PWR warning-remediation review mapping drift",
    )
    require(
        review_gate.get("status") == gate.get("status")
        and review_gate.get("head_commit_sha") == REVIEWED_GITHUB_COMMIT_SHA
        and review_gate.get("head_tree_sha") == REVIEWED_TREE_SHA
        and review_gate.get("pcb_native_run_id") == gate.get("pcb_native_run_id")
        and review_gate.get("ci_run_id") == gate.get("ci_run_id")
        and review_gate.get("artifact_id") == gate.get("artifact_id")
        and review_gate.get("artifact_digest") == MACHINE_GATE_ARTIFACT_DIGEST
        and review_gate.get("base_violations") == gate.get("base_violations")
        and review_gate.get("candidate_violations") ==
        gate.get("candidate_violations")
        and review_gate.get("base_unconnected") == gate.get("base_unconnected")
        and review_gate.get("candidate_unconnected") ==
        gate.get("candidate_unconnected")
        and review_gate.get("new_errors") == 0
        and review_gate.get("new_warnings") == 0
        and review_gate.get("all_other_drc_fingerprints_match") is True,
        "PCB-PWR warning-remediation machine-gate evidence drift",
    )

    report: dict[str, object] = {
        "schema_version":
        "dioneya.pcb-pwr-buck-warning-remediation-001-candidate-audit.v1",
        "status": (
            "PASS_STATIC_ACCEPTED_AND_APPLIED"
            if applied else
            "PASS_COMMIT_BOUND_KICAD9_WARNING_REMEDIATION_HUMAN_REVIEW_PENDING"
        ),
        "base_sha256": BASE_SHA256,
        "base_semantic_sha256": BASE_SEMANTIC_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "candidate_semantic_sha256": CANDIDATE_SEMANTIC_SHA256,
        "normalized_instances": ["C4", "C6"],
        "moved_reference_fields": ["R10"],
        "component_poses_changed": False,
        "pad_centres_sizes_layers_nets_changed": False,
        "copper_geometry_changed": False,
        "trace_items": 0,
        "copper_zones": 0,
        "strict_placement_clearance": "PASS_MINIMUM_0P22_MM",
        "authoritative_board_modified": applied,
        "human_subgate_pending": not applied,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_candidate is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_candidate is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_candidate)
        report["status"] = (
            "PASS_KICAD9_COMPARATIVE_ACCEPTED_AND_APPLIED"
            if applied else
            "PASS_KICAD9_COMPARATIVE_WARNING_REMEDIATION_HUMAN_REVIEW_PENDING"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.drc_base, args.drc_candidate)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print("PCB-PWR buck warning-remediation candidate audit:", report["status"])
    print(
        f"candidate_sha256={CANDIDATE_SHA256} "
        "poses_changed=False copper_changed=False minimum_clearance_mm=0.22"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
