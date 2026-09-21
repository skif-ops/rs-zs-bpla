#!/usr/bin/env python3
"""Audit the accepted and exactly applied PCB-PWR warning remediation 001."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from kiutils.board import Board

import audit_pcb_pwr_buck_warning_remediation_001_candidate_rev_a as candidate_audit
import audit_pcb_pwr_placement_clearance_rev_a as clearance_audit
from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
BASE = candidate_audit.BASE
CANDIDATE = candidate_audit.CANDIDATE
APPROVAL = (
    ROOT
    / "hardware/reviews/PCB_PWR_BUCK_WARNING_REMEDIATION_001_APPROVAL_REV_A.json"
)
MAPPING = (
    ROOT
    / "hardware/reviews/PCB_PWR_BUCK_WARNING_REMEDIATION_001_REVIEW_COMMIT_MAPPING.json"
)
APPLICATION = (
    ROOT
    / "hardware/reviews/PCB_PWR_BUCK_WARNING_REMEDIATION_001_APPLICATION_REV_A.json"
)
GENERATOR = (
    ROOT
    / "tools/generate_pcb_pwr_buck_warning_remediation_001_application_rev_a.py"
)
PLACEMENT = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"

BASE_SHA256 = "9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37"
CANDIDATE_SHA256 = "b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957"
BOARD_SEMANTIC_SHA256 = "b94eb0e53a714a2259e7362df7b96d1333c885f48399102b7ac279fb368d3276"
BOOTSTRAP_CANDIDATE_SHA256 = "a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236"
BOOTSTRAP_SEMANTIC_SHA256 = "d90ef0332ed5da798029a5cb580a0f3a5f68387068811eeb9e4c06d0681500ae"
VCAP_CANDIDATE_SHA256 = "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5"
VCAP_SEMANTIC_SHA256 = "07ce41bb361e68dd3a5310a6879030f097e4498e9397f2506ea5b78f49c47234"
APPROVAL_SHA256 = "386ece8201dae24da18db811845cf3501512192593c6e1bf31767fd3c71d5837"
MAPPING_SHA256 = "9f4411ecb9dcfe53974f80af0c1901389c93e544eb979d6734de2b52d8c4541e"
GENERATOR_SHA256 = "406b6d7ae50d5cc7603f11749a12a7d16870ab7ef116504661fbe71764cb50cd"
REVIEWED_COMMIT = "63d87153e441d956117323ed8d9887568c5033ac"
REVIEWED_TREE = "87b2c7ab4d8fbc1b5d0d3c88c703994abef773bf"
EVIDENCE_COMMIT = "036787a5674242de94d6dd455acf8ec6bf741952"
EVIDENCE_TREE = "f672828fac47e373f7b34a081f95e11bd8c345b6"
APPROVAL_COMMIT = "54083a35e0c6c33a34dd9ddc1cf2d4255409b7d7"
APPLICATION_SOURCE_COMMIT = "d22eb808f16058f1d90547b87a64aeb5de0c7cbc"
APPLICATION_SOURCE_TREE = "b6bae322dcbefa806fb3bb20ccfc1906ad689a6d"
APPLICATION_EVIDENCE_COMMIT = "f027aea4c546ff5d475b792d70526767eefbf844"
APPLICATION_EVIDENCE_TREE = "9cfacbf2e855a524489af2a5669fb3277816afc9"
APPLICATION_ARTIFACT_DIGEST = \
    "sha256:eae868305524381942f3b06e8de156b1954f17c194efc42fae5f56aff2907b02"
SCHEMATIC_ARTIFACT_DIGEST = \
    "sha256:20d40319e45a2b5bfed173383253f25b263910a9518c20abcde22bab33cfbf1c"
KICAD_CONTAINER_DIGEST = \
    "sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
EVIDENCE_SHA256 = {
    "application_audit.json":
    "ae8a0bebcd5ae8993b91f13acdb741293d2a14330ffa14a04182dc4e1786a302",
    "baseline_drc.json":
    "265967678bda12e8a139c53117fa551bb7d12eca3055b5a50aa873ecc98bc5b9",
    "candidate_drc.json":
    "6e49dcb937375e9b5526fd1f7fffe019469edeb6f09687bfb315505851e54c5f",
    "comparative_audit.json":
    "51506afefbd8e7c26b3beeee104c983299d64d98c02357cfd28c4a78cbe983ff",
    "placement_clearance.json":
    "66a97f8c0406612b86b65aa23aac05fbfd6dcbd07caff3f22660d78fba8ca2bc",
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(
    drc_base: Path | None = None,
    drc_active: Path | None = None,
) -> dict[str, object]:
    for path in (
        BOARD, BASE, CANDIDATE, APPROVAL, MAPPING, APPLICATION,
        GENERATOR, PLACEMENT, STATUS,
    ):
        require(path.is_file() and path.stat().st_size > 0,
                f"missing PCB-PWR warning-remediation application input: {path}")
    require(sha256(BASE) == BASE_SHA256,
            "PCB-PWR warning-remediation predecessor SHA-256 drift")
    require(
        sha256(CANDIDATE) == CANDIDATE_SHA256
        and sha256(BOARD) in {CANDIDATE_SHA256, BOOTSTRAP_CANDIDATE_SHA256,
                             VCAP_CANDIDATE_SHA256},
        "authoritative PCB-PWR is not the exact accepted warning-remediation candidate",
    )
    board = Board.from_file(str(BOARD), encoding="utf-8")
    require(semantic_board_sha256(board) in {BOARD_SEMANTIC_SHA256,
            BOOTSTRAP_SEMANTIC_SHA256, VCAP_SEMANTIC_SHA256},
            "applied PCB-PWR warning-remediation semantic identity drift")
    require(len(board.traceItems) in {0, 2, 3} and len(board.zones) == 0,
            "warning-remediation successor exceeds accepted bootstrap copper")
    require(sha256(APPROVAL) == APPROVAL_SHA256,
            "PCB-PWR warning-remediation approval SHA-256 drift")
    require(sha256(MAPPING) == MAPPING_SHA256,
            "PCB-PWR warning-remediation review mapping SHA-256 drift")
    require(sha256(GENERATOR) == GENERATOR_SHA256,
            "PCB-PWR warning-remediation application generator drift")

    historical = candidate_audit.audit()
    require(historical.get("status") == "PASS_STATIC_ACCEPTED_AND_APPLIED",
            "accepted warning-remediation candidate historical audit drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    authorization = approval.get("authorization", {})
    require(
        approval.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and approval.get("reviewed_tree_sha") == REVIEWED_TREE
        and approval.get("gate_evidence_commit_sha") == EVIDENCE_COMMIT
        and approval.get("gate_evidence_tree_sha") == EVIDENCE_TREE
        and approval.get("decision") ==
        "ACCEPT_PCB_PWR_BUCK_WARNING_REMEDIATION_001_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") ==
        CANDIDATE_SHA256
        and authorization.get(
            "apply_exact_hash_bound_warning_remediation_candidate"
        ) is True
        and authorization.get("expected_authoritative_predecessor_sha256") ==
        BASE_SHA256
        and authorization.get("authorized_applied_board_sha256") ==
        CANDIDATE_SHA256
        and authorization.get(
            "preserve_all_component_poses_pad_copper_nets_outline_and_layers"
        ) is True
        and authorization.get("close_only_the_four_bound_warning_findings")
        is True
        and authorization.get("routing_complete") is False
        and authorization.get("review_b_complete") is False
        and authorization.get("cam_or_manufacturing_release") is False,
        "PCB-PWR warning-remediation approval identity or boundary drift",
    )
    gate = mapping.get("machine_gate", {})
    require(
        mapping.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and mapping.get("reviewed_tree_sha") == REVIEWED_TREE
        and mapping.get("candidate_board_sha256") == CANDIDATE_SHA256
        and mapping.get("equivalence") == "EXACT_REVIEWED_TREE_AND_BLOBS"
        and gate.get("status") ==
        "PASS_EXACT_FOUR_WARNING_CLOSURE_NO_OTHER_DRC_DELTA"
        and gate.get("base_violations") == 90
        and gate.get("candidate_violations") == 86
        and gate.get("base_unconnected") == 126
        and gate.get("candidate_unconnected") == 126
        and gate.get("new_errors") == 0
        and gate.get("new_warnings") == 0
        and gate.get("all_other_drc_fingerprints_match") is True
        and mapping.get("cam_or_manufacturing_release") is False,
        "PCB-PWR warning-remediation review mapping drift",
    )

    applied = application.get("applied", {})
    application_gate = application.get("machine_gate", {})
    require(
        application.get("reviewed_proposal_commit_sha") == REVIEWED_COMMIT
        and application.get("gate_evidence_commit_sha") == EVIDENCE_COMMIT
        and application.get("approval_commit_sha") == APPROVAL_COMMIT
        and application.get("application_source_commit_sha") ==
        APPLICATION_SOURCE_COMMIT
        and application.get("application_source_tree_sha") ==
        APPLICATION_SOURCE_TREE
        and application.get("gate_evidence_application_commit_sha") ==
        APPLICATION_EVIDENCE_COMMIT
        and application.get("gate_evidence_application_tree_sha") ==
        APPLICATION_EVIDENCE_TREE
        and application.get("approval_sha256") == APPROVAL_SHA256
        and application.get("decision") ==
        "ACCEPT_PCB_PWR_BUCK_WARNING_REMEDIATION_001_SUBGATE"
        and application.get("scope") ==
        "EXACT_C4_C6_REPRESENTATION_NORMALIZATION_AND_R10_REFERENCE_MOVE_ONLY"
        and application.get("predecessor", {}).get("board_sha256") ==
        BASE_SHA256
        and application.get("application_generator", {}).get("sha256") ==
        GENERATOR_SHA256
        and applied.get("board_sha256") == CANDIDATE_SHA256
        and applied.get("board_semantic_sha256") == BOARD_SEMANTIC_SHA256
        and applied.get("exact_candidate_byte_identity") is True
        and applied.get("normalized_instances") == ["C4", "C6"]
        and applied.get("moved_reference_fields") == ["R10"]
        and applied.get("component_poses_changed") is False
        and applied.get("pad_centres_sizes_layers_nets_changed") is False
        and applied.get("copper_geometry_changed") is False
        and applied.get("trace_items") == 0
        and applied.get("copper_zones") == 0
        and application.get("authorized_warning_closure") == {
            "lib_footprint_mismatch_C4_C6": 2,
            "silk_overlap_L2_R10": 1,
            "silk_over_copper_R10": 1,
        }
        and application_gate.get("status") ==
        "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE"
        and application.get("routing_complete") is False
        and application.get("review_b_complete") is False
        and application.get("cam_or_manufacturing_release") is False,
        "PCB-PWR warning-remediation application boundary drift",
    )
    toolchain = application_gate.get("toolchain", {})
    ci = application_gate.get("ci", {})
    native = application_gate.get("pcb_native", {})
    schematic = application_gate.get("pcb_pwr_schematic", {})
    comparative = application_gate.get("comparative_drc", {})
    require(
        application_gate.get("required_application_audit") ==
        "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_WARNING_REMEDIATION_APPLICATION"
        and application_gate.get("required_comparative_drc") ==
        "PASS_EXACT_FOUR_WARNING_CLOSURE_NO_OTHER_DRC_DELTA"
        and application_gate.get("expected_base_violations") == 90
        and application_gate.get("expected_active_violations") == 86
        and application_gate.get("expected_base_unconnected") == 126
        and application_gate.get("expected_active_unconnected") == 126
        and application_gate.get("expected_new_errors") == 0
        and application_gate.get("expected_new_warnings") == 0
        and application_gate.get("all_other_drc_fingerprints_must_match")
        is True
        and application_gate.get("minimum_observed_clearance_mm") == 0.22
        and toolchain.get("kicad_version") == "9.0.9"
        and toolchain.get("container") == "ghcr.io/kicad/kicad:9.0.9"
        and toolchain.get("container_digest") == KICAD_CONTAINER_DIGEST
        and ci == {
            "run_number": 592,
            "run_id": 35603311617,
            "url": "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35603311617",
            "conclusion": "success",
        }
        and native.get("run_number") == 319
        and native.get("run_id") == 35603311534
        and native.get("job_id") == 106344331014
        and native.get("conclusion") == "success"
        and native.get("artifact_id") == 10640361017
        and native.get("artifact_digest") == APPLICATION_ARTIFACT_DIGEST
        and schematic.get("run_number") == 70
        and schematic.get("run_id") == 35603311708
        and schematic.get("conclusion") == "success"
        and schematic.get("artifact_id") == 10639907320
        and schematic.get("artifact_digest") == SCHEMATIC_ARTIFACT_DIGEST
        and application_gate.get("evidence_sha256") == EVIDENCE_SHA256
        and comparative == {
            "status": "PASS_EXACT_FOUR_WARNING_CLOSURE_NO_OTHER_DRC_DELTA",
            "base_violations": 90,
            "active_violations": 86,
            "base_unconnected": 126,
            "active_unconnected": 126,
            "new_errors": 0,
            "new_warnings": 0,
            "all_other_drc_fingerprints_match": True,
            "removed_warnings": {
                "lib_footprint_mismatch_C4_C6": 2,
                "silk_overlap_L2_R10": 1,
                "silk_over_copper_R10": 1,
            },
        },
        "passed application-gate evidence contract drift",
    )

    clearance = clearance_audit.audit(BOARD, PLACEMENT)
    summary = clearance.get("summary", {})
    require(
        summary.get("state") ==
        "PASS_FITTED_2D_AND_EVT_MOUNTING_CLEARANCE_DIM_003_ACCEPTED"
        and summary.get("minimum_observed_clearance_mm") == 0.22
        and summary.get("clearance_conflicts") == 0
        and summary.get("mounting_to_fitted_body_conflicts") == 0
        and summary.get("mounting_to_existing_pad_conflicts") == 0,
        "applied warning-remediation strict-clearance drift",
    )

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    layout = status.get("native_layout", {})
    placement_eco = layout.get("buck_placement_eco_001", {})
    remediation = placement_eco.get("warning_remediation_001", {})
    require(
        placement_eco.get("active_board_sha256") == VCAP_CANDIDATE_SHA256
        and placement_eco.get("board_semantic_sha256") ==
        VCAP_SEMANTIC_SHA256
        and placement_eco.get("active_controlled_successor") ==
        "PCB-PWR-LM74700-VCAP-ROUTING-002"
        and placement_eco.get("routing_added") is True
        and remediation.get("status") in {
            "APPROVED_APPLIED_EXACT_WARNING_REMEDIATION_PENDING_COMMIT_BOUND_KICAD9_GATE",
            "APPROVED_APPLIED_EXACT_WARNING_REMEDIATION_COMMIT_BOUND_KICAD9_GATE_PASS",
        }
        and remediation.get("active_board_sha256") == VCAP_CANDIDATE_SHA256
        and remediation.get("board_semantic_sha256") ==
        VCAP_SEMANTIC_SHA256
        and remediation.get("exact_candidate_byte_identity") is True
        and remediation.get("authoritative_board_modified") is True
        and remediation.get("human_acceptance_complete") is True
        and remediation.get("application_machine_gate") ==
        "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE"
        and placement_eco.get("warning_only_items_closed") is True
        and remediation.get("routing_added") is True
        and layout.get("routing_present") is True
        and layout.get("copper_zones_present") is False
        and layout.get("cam_export_authorized") is False
        and status.get("review_b", {}).get("complete") is False
        and status.get("manufacturing_release") is False,
        "PCB-PWR capture-status warning-remediation or release boundary drift",
    )

    report: dict[str, object] = {
        "schema_version":
        "dioneya.pcb-pwr-buck-warning-remediation-001-application-audit.v1",
        "status":
        "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_WARNING_REMEDIATION_APPLICATION",
        "predecessor_sha256": BASE_SHA256,
        "active_board_sha256": CANDIDATE_SHA256,
        "board_semantic_sha256": BOARD_SEMANTIC_SHA256,
        "normalized_instances": ["C4", "C6"],
        "moved_reference_fields": ["R10"],
        "component_poses_changed": False,
        "pad_copper_changed": False,
        "strict_placement_clearance": "PASS_MINIMUM_0P22_MM",
        "machine_gate": application_gate.get("status"),
        "warning_only_items_closed": True,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_active is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_active is not None:
        comparative: dict[str, Any] = candidate_audit.audit_drc(
            drc_base, drc_active
        )
        report["comparative_drc"] = comparative
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-active", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.drc_base, args.drc_active)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print("PCB-PWR buck warning-remediation 001 application audit:",
          report["status"])
    print(
        f"active_board_sha256={CANDIDATE_SHA256} "
        "poses_changed=False copper_changed=False minimum_clearance_mm=0.22"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
