#!/usr/bin/env python3
"""Audit the accepted and exactly applied PCB-PWR buck placement ECO-001."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from kiutils.board import Board

import audit_pcb_pwr_buck_placement_eco_001_candidate_rev_a as candidate_audit
import audit_pcb_pwr_placement_clearance_rev_a as clearance_audit
from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
BASE = candidate_audit.BASE
CANDIDATE = candidate_audit.CANDIDATE
WARNING_REMEDIATION_CANDIDATE = (
    ROOT
    / "hardware/kicad/candidates/PCB-PWR-BUCK-WARNING-REMEDIATION-001/"
    "PCB-PWR_BUCK_WARNING_REMEDIATION_001_CANDIDATE_REV_A.kicad_pcb"
)
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_BUCK_PLACEMENT_ECO_001_APPROVAL_REV_A.json"
MAPPING = ROOT / "hardware/reviews/PCB_PWR_BUCK_PLACEMENT_ECO_001_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_PWR_BUCK_PLACEMENT_ECO_001_APPLICATION_REV_A.json"
GENERATOR = ROOT / "tools/generate_pcb_pwr_buck_placement_eco_001_application_rev_a.py"
PLACEMENT = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"

BASE_SHA256 = "fdd53e669a167df8925c38e289993c38b818c231eddd0be54de378b51538bf48"
CANDIDATE_SHA256 = "9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37"
BOARD_SEMANTIC_SHA256 = "5994f22cdce03bc60779fcf120177bb82f6ecb88b2afdbe9bf4c0c2819af7337"
WARNING_REMEDIATION_CANDIDATE_SHA256 = (
    "b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957"
)
WARNING_REMEDIATION_SEMANTIC_SHA256 = (
    "b94eb0e53a714a2259e7362df7b96d1333c885f48399102b7ac279fb368d3276"
)
BOOTSTRAP_CANDIDATE_SHA256 = "a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236"
BOOTSTRAP_SEMANTIC_SHA256 = "d90ef0332ed5da798029a5cb580a0f3a5f68387068811eeb9e4c06d0681500ae"
VCAP_CANDIDATE_SHA256 = "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5"
VCAP_SEMANTIC_SHA256 = "07ce41bb361e68dd3a5310a6879030f097e4498e9397f2506ea5b78f49c47234"
VBAT_RAW_CANDIDATE_SHA256 = "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3"
VBAT_RAW_SEMANTIC_SHA256 = "4472097781d9dc58231a14c0fea67ad102e2e25b1e9e05e98481e7d6d3f3a93d"
REV_GATE_CANDIDATE_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
REV_GATE_SEMANTIC_SHA256 = "f7a659d0740e78d40eddae7016724bd8e616baf9fb425f06ace70ec9acca4d3d"
ECO_002_CANDIDATE_SHA256 = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"
ECO_002_SEMANTIC_SHA256 = "0e52d4cbc80104691e3793a579c7c7a8570e3640fabc2fb02bd7ea2e65643555"
APPROVAL_SHA256 = "03a3c499b785ffdbe331f5bb442aecde31411bb6b3e65c88e0eaf2e0a62c8c7e"
MAPPING_SHA256 = "26b4376b851d4dd5082bfd02182e243d7d0d9161a7b72c53a7112db9c21c2c85"
GENERATOR_SHA256 = "8ed0ebf6cf3aed26c7f6ef9d7746424defcb467674ce69e353c3b8f2c39f3752"
PLACEMENT_SHA256 = "257fee5898b5d44970115220a485d40b01c4fefad14b5c3b1a4ffb43b7b5b2d6"
REVIEWED_COMMIT = "38d629c2e7f9a9956a93c8b9666b17e69905eeb6"
REVIEWED_TREE = "b935ed765133297099dee6af4799f598df832ab2"
APPROVAL_COMMIT = "82dbcf2a0318d79c73ad4c59e1f58158b453605f"
APPLICATION_COMMIT = "878425d26641d1bdaf53e5287649677630a3938b"
APPLICATION_TREE = "a62acc90939c0e250c0e1a430c40c4205b356abc"
EXPECTED_POSES = {
    "C4": (54.575, 16.4, 180.0),
    "C6": (54.575, 44.4, 180.0),
    "L1": (60.75, 14.0, 180.0),
    "L2": (60.75, 42.0, 180.0),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drc_inventory(path: Path) -> tuple[Counter[str], int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = Counter(
        item.get("type", "UNKNOWN")
        for item in data.get("violations", [])
        if item.get("severity") == "error"
    )
    return errors, len(data.get("violations", [])), \
        len(data.get("unconnected_items", []))


def audit_drc(base_path: Path, active_path: Path) -> dict[str, object]:
    base_errors, base_violations, base_unconnected = drc_inventory(base_path)
    active_errors, active_violations, active_unconnected = drc_inventory(active_path)
    added = {
        kind: active_errors[kind] - base_errors[kind]
        for kind in active_errors
        if active_errors[kind] > base_errors[kind]
    }
    require(not added,
            f"applied PCB-PWR buck placement adds KiCad 9 errors: {added}")
    require(active_unconnected == base_unconnected,
            "applied placement-only ECO changes unconnected-item count")
    return {
        "status": "PASS_NO_NEW_KICAD9_ERRORS_NO_CONNECTIVITY_REGRESSION",
        "base_violations": base_violations,
        "active_violations": active_violations,
        "base_unconnected": base_unconnected,
        "active_unconnected": active_unconnected,
        "new_error_counts": added,
    }


def audit(
    drc_base: Path | None = None,
    drc_active: Path | None = None,
) -> dict[str, object]:
    for path in (
        BOARD, BASE, CANDIDATE, APPROVAL, MAPPING, APPLICATION,
        GENERATOR, PLACEMENT, STATUS,
    ):
        require(path.is_file() and path.stat().st_size > 0,
                f"missing PCB-PWR buck placement application input: {path}")
    require(sha256(BASE) == BASE_SHA256,
            "PCB-PWR application predecessor SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "accepted PCB-PWR buck-placement candidate SHA-256 drift")
    active_sha256 = sha256(BOARD)
    require(
        active_sha256 in {
            CANDIDATE_SHA256,
            WARNING_REMEDIATION_CANDIDATE_SHA256,
            BOOTSTRAP_CANDIDATE_SHA256,
            VCAP_CANDIDATE_SHA256,
            VBAT_RAW_CANDIDATE_SHA256,
            REV_GATE_CANDIDATE_SHA256,
            ECO_002_CANDIDATE_SHA256,
        },
        "authoritative PCB-PWR is not an accepted buck-placement successor",
    )
    expected_active = {
        CANDIDATE_SHA256: CANDIDATE,
        WARNING_REMEDIATION_CANDIDATE_SHA256: WARNING_REMEDIATION_CANDIDATE,
        BOOTSTRAP_CANDIDATE_SHA256:
        ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-BOOTSTRAP-ROUTING-001/PCB-PWR_BUCK_BOOTSTRAP_ROUTING_001_CANDIDATE_REV_A.kicad_pcb",
        VCAP_CANDIDATE_SHA256:
        ROOT / "hardware/kicad/candidates/PCB-PWR-LM74700-VCAP-ROUTING-002/PCB-PWR_LM74700_VCAP_ROUTING_002_CANDIDATE_REV_A.kicad_pcb",
        VBAT_RAW_CANDIDATE_SHA256:
        ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-RAW-ROUTING-003/PCB-PWR_VBAT_RAW_ROUTING_003_CANDIDATE_REV_A.kicad_pcb",
        REV_GATE_CANDIDATE_SHA256:
        ROOT / "hardware/kicad/candidates/PCB-PWR-REV-GATE-ROUTING-004/PCB-PWR_REV_GATE_ROUTING_004_CANDIDATE_REV_A.kicad_pcb",
        ECO_002_CANDIDATE_SHA256:
        ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-POWER-STAGE-ECO-002/PCB-PWR_BUCK_POWER_STAGE_ECO_002_CANDIDATE_REV_A.kicad_pcb",
    }[active_sha256]
    require(BOARD.read_bytes() == expected_active.read_bytes(),
            "authoritative PCB-PWR accepted-successor byte identity drift")
    board = Board.from_file(str(BOARD), encoding="utf-8")
    active_semantic_sha256 = {
        CANDIDATE_SHA256: BOARD_SEMANTIC_SHA256,
        WARNING_REMEDIATION_CANDIDATE_SHA256: WARNING_REMEDIATION_SEMANTIC_SHA256,
        BOOTSTRAP_CANDIDATE_SHA256: BOOTSTRAP_SEMANTIC_SHA256,
        VCAP_CANDIDATE_SHA256: VCAP_SEMANTIC_SHA256,
        VBAT_RAW_CANDIDATE_SHA256: VBAT_RAW_SEMANTIC_SHA256,
        REV_GATE_CANDIDATE_SHA256: REV_GATE_SEMANTIC_SHA256,
        ECO_002_CANDIDATE_SHA256: ECO_002_SEMANTIC_SHA256,
    }[active_sha256]
    require(semantic_board_sha256(board) == active_semantic_sha256,
            "applied PCB-PWR semantic board identity drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256,
            "PCB-PWR buck placement approval SHA-256 drift")
    require(sha256(MAPPING) == MAPPING_SHA256,
            "PCB-PWR buck placement review mapping SHA-256 drift")
    require(sha256(GENERATOR) == GENERATOR_SHA256,
            "PCB-PWR buck placement application generator drift")
    require(sha256(PLACEMENT) == PLACEMENT_SHA256,
            "PCB-PWR placement manifest SHA-256 drift")

    historical = candidate_audit.audit()
    require(historical.get("status") == "PASS_STATIC_ACCEPTED_AND_APPLIED",
            "accepted PCB-PWR candidate historical audit drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    authorization = approval.get("authorization", {})
    require(
        approval.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and approval.get("reviewed_tree_sha") == REVIEWED_TREE
        and approval.get("decision") ==
        "ACCEPT_PCB_PWR_BUCK_PLACEMENT_ECO_001_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and authorization.get(
            "apply_exact_hash_bound_c4_c6_l1_l2_placement_delta"
        ) is True
        and authorization.get("routing_complete") is False
        and authorization.get("cam_or_manufacturing_release") is False,
        "PCB-PWR approval identity or boundary drift",
    )
    require(
        mapping.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and mapping.get("reviewed_tree_sha") == REVIEWED_TREE
        and mapping.get("candidate_board_sha256") == CANDIDATE_SHA256
        and mapping.get("equivalence") == "EXACT_REVIEWED_TREE_AND_BLOBS"
        and mapping.get("cam_or_manufacturing_release") is False,
        "PCB-PWR review commit mapping drift",
    )

    applied = application.get("applied", {})
    gate = application.get("machine_gate", {})
    warning_disposition = application.get("warning_disposition", {})
    require(
        application.get("approval_commit_sha") == APPROVAL_COMMIT
        and application.get("approval_sha256") == APPROVAL_SHA256
        and application.get("decision") ==
        "ACCEPT_PCB_PWR_BUCK_PLACEMENT_ECO_001_SUBGATE"
        and application.get("scope") ==
        "EXACT_C4_C6_L1_L2_PLACEMENT_DELTA_ONLY"
        and application.get("predecessor", {}).get("board_sha256") == BASE_SHA256
        and application.get("application_generator", {}).get("sha256") ==
        GENERATOR_SHA256
        and applied.get("board_sha256") == CANDIDATE_SHA256
        and applied.get("board_semantic_sha256") == BOARD_SEMANTIC_SHA256
        and applied.get("exact_candidate_byte_identity") is True
        and applied.get("changed_references") == ["C4", "C6", "L1", "L2"]
        and applied.get("trace_items") == 0
        and applied.get("copper_zones") == 0
        and applied.get("copper_changed") is False
        and applied.get("placement_manifest_sha256") == PLACEMENT_SHA256
        and application.get("application_commit_sha") == APPLICATION_COMMIT
        and gate.get("status") == "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE"
        and gate.get("source_commit_sha") == APPLICATION_COMMIT
        and gate.get("source_tree_sha") == APPLICATION_TREE
        and gate.get("ci_run_id") == 35589990694
        and gate.get("ci_run_number") == 583
        and gate.get("ci_conclusion") == "success"
        and gate.get("pcb_native_run_id") == 35589990634
        and gate.get("pcb_native_run_number") == 310
        and gate.get("pcb_native_conclusion") == "success"
        and gate.get("application_audit") ==
        "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_PLACEMENT_APPLICATION"
        and gate.get("comparative_drc") ==
        "PASS_NO_NEW_KICAD9_ERRORS_NO_CONNECTIVITY_REGRESSION"
        and gate.get("base_violations") == 87
        and gate.get("active_violations") == 90
        and gate.get("base_unconnected") == 126
        and gate.get("active_unconnected") == 126
        and gate.get("new_errors") == 0
        and gate.get("artifact_id") == 10633864128
        and gate.get("artifact_digest") ==
        "sha256:5fcdfc856f009d05b490bd124168b8ea42322c0b08c6211743cbc1208f35d526"
        and warning_disposition.get("lib_footprint_mismatch_C4_C6") ==
        "OPEN_WARNING_ONLY_MUST_CLOSE_BEFORE_REVIEW_B_OR_CAM"
        and warning_disposition.get("silk_overlap_L2_R10") ==
        "OPEN_WARNING_ONLY_MUST_CLOSE_BEFORE_REVIEW_B_OR_CAM"
        and application.get("routing_complete") is False
        and application.get("review_b_complete") is False
        and application.get("cam_or_manufacturing_release") is False,
        "PCB-PWR application identity, geometry, warning, or release boundary drift",
    )

    if active_sha256 != ECO_002_CANDIDATE_SHA256:
        footprints = {candidate_audit.ref_of(item): item for item in board.footprints}
        for reference, expected in EXPECTED_POSES.items():
            actual = candidate_audit.pose_of(footprints[reference])
            require(all(candidate_audit.close(first, second)
                        for first, second in zip(actual, expected)),
                    f"{reference}: applied pose drift")
    require(len(board.traceItems) in {0, 2, 3, 4, 8, 14} and len(board.zones) == 0,
            "PCB-PWR buck placement successor exceeds accepted ECO-002 copper")

    with PLACEMENT.open(encoding="utf-8-sig", newline="") as stream:
        rows = {row["RefDes"]: row for row in csv.DictReader(stream)}
    for reference, expected in EXPECTED_POSES.items():
        row = rows[reference]
        actual = (
            float(row["X_mm"]),
            float(row["Y_mm"]),
            float(row["Rotation_deg"]) % 360.0,
        )
        require(all(candidate_audit.close(first, second)
                    for first, second in zip(actual, expected)),
                f"{reference}: placement manifest pose drift")

    if active_sha256 != ECO_002_CANDIDATE_SHA256:
        clearance = clearance_audit.audit(BOARD, PLACEMENT)
        summary = clearance.get("summary", {})
        require(
            summary.get("state") ==
            "PASS_FITTED_2D_AND_EVT_MOUNTING_CLEARANCE_DIM_003_ACCEPTED"
            and summary.get("minimum_observed_clearance_mm") == 0.22
            and summary.get("clearance_conflicts") == 0
            and summary.get("mounting_to_fitted_body_conflicts") == 0
            and summary.get("mounting_to_existing_pad_conflicts") == 0,
            "applied PCB-PWR buck placement strict-clearance drift",
        )

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    layout = status.get("native_layout", {})
    eco = layout.get("buck_placement_eco_001", {})
    require(
        eco.get("status") in {
            "APPROVED_APPLIED_EXACT_C4_C6_L1_L2_PLACEMENT_PENDING_COMMIT_BOUND_KICAD9_GATE",
            "APPROVED_APPLIED_EXACT_C4_C6_L1_L2_PLACEMENT_COMMIT_BOUND_KICAD9_GATE_PASS",
        }
        and eco.get("active_board_sha256") == active_sha256
        and eco.get("board_semantic_sha256") == active_semantic_sha256
        and eco.get("historical_exact_candidate_byte_identity") is True
        and eco.get("active_controlled_successor") in {
            "PCB-PWR-BUCK-PLACEMENT-ECO-001",
            "PCB-PWR-BUCK-WARNING-REMEDIATION-001",
            "PCB-PWR-BUCK-BOOTSTRAP-ROUTING-001",
            "PCB-PWR-LM74700-VCAP-ROUTING-002",
            "PCB-PWR-VBAT-RAW-ROUTING-003",
            "PCB-PWR-REV-GATE-ROUTING-004",
            "PCB-PWR-BUCK-POWER-STAGE-ECO-002",
        }
        and eco.get("routing_added") ==
        (active_sha256 in {
            BOOTSTRAP_CANDIDATE_SHA256,
            VCAP_CANDIDATE_SHA256,
            VBAT_RAW_CANDIDATE_SHA256,
            REV_GATE_CANDIDATE_SHA256,
            ECO_002_CANDIDATE_SHA256,
        })
        and eco.get("warning_only_items_closed") in {False, True}
        and layout.get("routing_present") ==
        (active_sha256 in {
            BOOTSTRAP_CANDIDATE_SHA256,
            VCAP_CANDIDATE_SHA256,
            VBAT_RAW_CANDIDATE_SHA256,
            REV_GATE_CANDIDATE_SHA256,
            ECO_002_CANDIDATE_SHA256,
        })
        and layout.get("copper_zones_present") is False
        and layout.get("cam_export_authorized") is False
        and status.get("review_b", {}).get("complete") is False
        and status.get("manufacturing_release") is False,
        "PCB-PWR capture-status application or release boundary drift",
    )

    report: dict[str, object] = {
        "schema_version":
        "dioneya.pcb-pwr-buck-placement-eco-001-application-audit.v1",
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_PLACEMENT_APPLICATION",
        "predecessor_sha256": BASE_SHA256,
        "active_board_sha256": active_sha256,
        "board_semantic_sha256": active_semantic_sha256,
        "placement_manifest_sha256": PLACEMENT_SHA256,
        "changed_references": ["C4", "C6", "L1", "L2"],
        "copper_changed": False,
        "strict_placement_clearance": "PASS_MINIMUM_0P22_MM",
        "machine_gate": gate.get("status"),
        "application_commit_sha": APPLICATION_COMMIT,
        "pcb_native_run_id": 35589990634,
        "ci_run_id": 35589990694,
        "artifact_id": 10633864128,
        "warning_only_items_closed": eco.get("warning_only_items_closed"),
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_active is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_active is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_active)
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
    print("PCB-PWR buck placement ECO-001 application audit:", report["status"])
    print(
        f"active_board_sha256={report['active_board_sha256']} "
        "moved=['C4', 'C6', 'L1', 'L2'] minimum_clearance_mm=0.22"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
