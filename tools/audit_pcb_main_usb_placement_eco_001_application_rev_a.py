#!/usr/bin/env python3
"""Audit the accepted and exactly applied PCB-MAIN USB placement ECO-001."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
import sys
from pathlib import Path
from typing import Any

from kiutils.board import Board

import audit_pcb_main_placement_clearance_rev_a as clearance_audit
import audit_pcb_main_usb_placement_eco_001_candidate_rev_a as candidate_audit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")) if str(ROOT / "tools") not in sys.path else None
import pcb_main_lineage_rev_a as _lineage  # noqa: E402  (PCB-MAIN 003: earlier sub-gates read the predecessor)
BOARD = _lineage.historical_board()
BASE = candidate_audit.BASE
CANDIDATE = candidate_audit.CANDIDATE
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_USB_PLACEMENT_ECO_001_APPROVAL_REV_A.json"
MAPPING = ROOT / "hardware/reviews/PCB_MAIN_USB_PLACEMENT_ECO_001_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_PLACEMENT_ECO_001_APPLICATION_REV_A.json"
GENERATOR = ROOT / "tools/generate_pcb_main_usb_placement_eco_001_application_rev_a.py"
PLACEMENT = _lineage.historical_placement()
AUTHORITY = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
STATUS = _lineage.historical_status()
SOURCE_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_SOURCE_ROUTING_001_APPLICATION_REV_A.json"
CELL_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_MODEM_ROUTING_001_APPLICATION_REV_A.json"
FIXTURE_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_FIXTURE_ROUTING_001_APPLICATION_REV_A.json"
RF_COMPOSED = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-REMEDIATION-APPLICATION-001/"
    "PCB-MAIN_RF_REMEDIATION_COMPOSED_REV_A.kicad_pcb"
)

BASE_SHA256 = "f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9"
CANDIDATE_SHA256 = "d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e"
SOURCE_SUCCESSOR_SHA256 = "76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5"
CELL_SUCCESSOR_SHA256 = "4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5"
FIXTURE_SUCCESSOR_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
APPROVAL_SHA256 = "d071f6e0993d225ddab094b8e9d3cc4a24e52045286ca3f43d9929cb7597bf35"
MAPPING_SHA256 = "f7a5345facf484d1eb7ae3cb650f70a8a872f7c6148149bbc818b74666fa15ba"
GENERATOR_SHA256 = "e3914cc8aad95e4b249aaed1788903043122d88a66b3006e6541daf7e321743a"
PLACEMENT_SHA256 = "df7cdbfc2ac023d43ac040b14eb99440fc392d402793d5a3b03f2fd560af6a6f"
REVIEWED_COMMIT = "a3d774c8e7b0bd0634a60cf44b1cdf3f828a3e8d"
REVIEWED_TREE = "fa9bfd800e79eadc56d379ee4a1591c06a5f9b48"
APPROVAL_COMMIT = "20632248d9c70b6456d8fe5e3a30d99b25dd39f8"
APPLICATION_COMMIT = "1f8c0bad8a7825adb8324dc36976141eab78a645"
APPLICATION_TREE = "1f3d9147cf8d133ae81397af56e4bd83ea7cc243"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref_of(footprint: Any) -> str:
    value = footprint.properties.get("Reference")
    if value:
        return str(value)
    return next(str(item.text) for item in footprint.graphicItems
                if getattr(item, "type", None) == "reference")


def drc_inventory(path: Path) -> tuple[Counter[str], int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = Counter(item.get("type", "UNKNOWN") for item in data.get("violations", [])
                     if item.get("severity") == "error")
    return errors, len(data.get("violations", [])), len(data.get("unconnected_items", []))


def audit_drc(base_path: Path, candidate_path: Path) -> dict[str, object]:
    base_errors, base_violations, base_unconnected = drc_inventory(base_path)
    active_errors, active_violations, active_unconnected = drc_inventory(candidate_path)
    added = {kind: active_errors[kind] - base_errors[kind]
             for kind in active_errors if active_errors[kind] > base_errors[kind]}
    require(not added, f"applied USB placement adds KiCad 9 errors: {added}")
    require(active_unconnected <= base_unconnected,
            "applied USB placement increases unconnected items")
    return {
        "status": "PASS_NO_NEW_KICAD9_DRC_ERRORS_OR_UNCONNECTED_REGRESSION",
        "base_violations": base_violations,
        "active_violations": active_violations,
        "base_unconnected": base_unconnected,
        "active_unconnected": active_unconnected,
        "new_error_counts": added,
    }


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict[str, object]:
    for path in (BOARD, BASE, CANDIDATE, APPROVAL, MAPPING, APPLICATION,
                 GENERATOR, PLACEMENT, AUTHORITY, STATUS, RF_COMPOSED):
        require(path.is_file() and path.stat().st_size > 0,
                f"missing USB placement application input: {path}")
    require(sha256(BASE) == BASE_SHA256 and sha256(RF_COMPOSED) == BASE_SHA256 and
            BASE.read_bytes() == RF_COMPOSED.read_bytes(),
            "accepted RF-remediation predecessor identity drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "accepted USB placement candidate SHA-256 drift")
    active_sha256 = sha256(BOARD)
    require(active_sha256 in {
        CANDIDATE_SHA256, SOURCE_SUCCESSOR_SHA256, CELL_SUCCESSOR_SHA256,
        FIXTURE_SUCCESSOR_SHA256,
    },
            "authoritative PCB-MAIN USB placement lineage drift")
    if active_sha256 == CANDIDATE_SHA256:
        require(BOARD.read_bytes() == CANDIDATE.read_bytes(),
                "authoritative PCB-MAIN USB placement byte identity drift")
    else:
        source_application = json.loads(SOURCE_APPLICATION.read_text(encoding="utf-8"))
        require(
            source_application.get("decision") == "ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE"
            and source_application.get("predecessor", {}).get("board_sha256") ==
            CANDIDATE_SHA256
            and source_application.get("applied", {}).get("board_sha256") ==
            SOURCE_SUCCESSOR_SHA256
            and source_application.get("applied", {}).get(
                "exact_candidate_byte_identity"
            ) is True
            and source_application.get("review_b_complete") is False
            and source_application.get("manufacturing_release") is False,
            "accepted USB source-routing successor boundary drift",
        )
        if active_sha256 in {CELL_SUCCESSOR_SHA256, FIXTURE_SUCCESSOR_SHA256}:
            cell_application = json.loads(
                CELL_APPLICATION.read_text(encoding="utf-8")
            )
            require(
                cell_application.get("decision") ==
                "ACCEPT_USB_CELL_MODEM_ROUTING_SUBGATE"
                and cell_application.get("predecessor", {}).get(
                    "board_sha256"
                ) == SOURCE_SUCCESSOR_SHA256
                and cell_application.get("applied", {}).get("board_sha256") ==
                CELL_SUCCESSOR_SHA256
                and cell_application.get("review_b_complete") is False
                and cell_application.get("manufacturing_release") is False,
                "accepted cellular USB modem successor boundary drift",
            )
        if active_sha256 == FIXTURE_SUCCESSOR_SHA256:
            fixture_application = json.loads(
                FIXTURE_APPLICATION.read_text(encoding="utf-8")
            )
            require(
                fixture_application.get("decision") ==
                "ACCEPT_USB_CELL_FIXTURE_ROUTING_SUBGATE"
                and fixture_application.get("predecessor", {}).get(
                    "board_sha256"
                ) == CELL_SUCCESSOR_SHA256
                and fixture_application.get("applied", {}).get("board_sha256") ==
                FIXTURE_SUCCESSOR_SHA256
                and fixture_application.get("review_b_complete") is False
                and fixture_application.get("manufacturing_release") is False,
                "accepted cellular USB fixture successor boundary drift",
            )
    require(sha256(APPROVAL) == APPROVAL_SHA256, "USB approval SHA-256 drift")
    require(sha256(MAPPING) == MAPPING_SHA256, "USB review mapping SHA-256 drift")
    require(sha256(GENERATOR) == GENERATOR_SHA256, "USB application generator drift")
    require(sha256(PLACEMENT) == PLACEMENT_SHA256, "USB placement manifest drift")

    historical = candidate_audit.audit()
    require(historical.get("placement_clearance_state") == "PASS",
            "accepted USB candidate static audit drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    require(
        approval.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and approval.get("reviewed_tree_sha") == REVIEWED_TREE
        and approval.get("decision") ==
        "ACCEPT_USB_SOURCE_TERMINATION_PLACEMENT_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and approval.get("authorization", {}).get(
            "cam_or_manufacturing_release"
        ) is False,
        "USB approval identity or boundary drift",
    )
    require(
        mapping.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and mapping.get("reviewed_tree_sha") == REVIEWED_TREE
        and mapping.get("candidate_board_sha256") == CANDIDATE_SHA256
        and mapping.get("equivalence") == "EXACT_REVIEWED_TREE_AND_BLOBS"
        and mapping.get("cam_or_manufacturing_release") is False,
        "USB review commit mapping drift",
    )
    applied = application.get("applied", {})
    gate = application.get("machine_gate", {})
    require(
        application.get("approval_commit_sha") == APPROVAL_COMMIT
        and application.get("approval_sha256") == APPROVAL_SHA256
        and application.get("decision") ==
        "ACCEPT_USB_SOURCE_TERMINATION_PLACEMENT_SUBGATE"
        and application.get("scope") == "EXACT_R91_R92_PLACEMENT_DELTA_ONLY"
        and application.get("predecessor", {}).get("board_sha256") == BASE_SHA256
        and application.get("application_generator", {}).get("sha256") ==
        GENERATOR_SHA256
        and applied.get("board_sha256") == CANDIDATE_SHA256
        and applied.get("exact_candidate_byte_identity") is True
        and applied.get("changed_references") == ["R91", "R92"]
        and applied.get("copper_changed") is False
        and applied.get("placement_manifest_sha256") == PLACEMENT_SHA256
        and application.get("application_commit_sha") == APPLICATION_COMMIT
        and gate.get("status") == "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE"
        and gate.get("source_commit_sha") == APPLICATION_COMMIT
        and gate.get("source_tree_sha") == APPLICATION_TREE
        and gate.get("ci_run_id") == 35526956245
        and gate.get("ci_run_number") == 557
        and gate.get("ci_conclusion") == "success"
        and gate.get("pcb_native_run_id") == 35526956229
        and gate.get("pcb_native_run_number") == 284
        and gate.get("pcb_native_conclusion") == "success"
        and gate.get("application_audit") ==
        "PASS_EXACT_ACCEPTED_USB_PLACEMENT_APPLICATION"
        and gate.get("base_violations") == 227
        and gate.get("active_violations") == 232
        and gate.get("base_unconnected") == 429
        and gate.get("active_unconnected") == 429
        and gate.get("new_errors") == 0
        and gate.get("artifact_id") == 10609668700
        and gate.get("artifact_digest") ==
        "sha256:3757976a26955c4e25a3905f7054fbc9f88331823e0d1a99aefe9e7555096387"
        and application.get("usb_pair_routing_complete") is False
        and application.get("review_b_complete") is False
        and application.get("cam_or_manufacturing_release") is False,
        "USB application identity, geometry, or release boundary drift",
    )

    board = Board.from_file(str(BOARD), encoding="utf-8")
    footprints = {ref_of(item): item for item in board.footprints}
    require(
        (float(footprints["R91"].position.X), float(footprints["R91"].position.Y),
         float(footprints["R91"].position.angle or 0.0)) == (64.0, 25.25, 0.0)
        and (float(footprints["R92"].position.X), float(footprints["R92"].position.Y),
             float(footprints["R92"].position.angle or 0.0)) == (64.0, 26.25, 0.0),
        "applied R91/R92 poses drift",
    )
    segments = [item for item in board.traceItems if type(item).__name__ == "Segment"]
    vias = [item for item in board.traceItems if type(item).__name__ == "Via"]
    require(len(board.traceItems) == (
                1023 if active_sha256 == FIXTURE_SUCCESSOR_SHA256
                else 994 if active_sha256 == CELL_SUCCESSOR_SHA256
                else 988 if active_sha256 == SOURCE_SUCCESSOR_SHA256 else 975
            )
            and len(segments) == (
                738 if active_sha256 == FIXTURE_SUCCESSOR_SHA256
                else 711 if active_sha256 == CELL_SUCCESSOR_SHA256
                else 705 if active_sha256 == SOURCE_SUCCESSOR_SHA256 else 692
            )
            and len(vias) == (
                285 if active_sha256 == FIXTURE_SUCCESSOR_SHA256 else 283
            )
            and len(board.zones) == 8,
            "USB application unexpectedly changes copper inventory")

    with PLACEMENT.open(encoding="utf-8", newline="") as stream:
        rows = {row["RefDes"]: row for row in csv.DictReader(stream)}
    for reference, expected in {"R91": (64.0, 25.25, 0.0),
                                "R92": (64.0, 26.25, 0.0)}.items():
        row = rows[reference]
        actual = (float(row["X_mm"]), float(row["Y_mm"]),
                  float(row["Rotation_deg"]) % 360.0)
        require(actual == expected, f"{reference}: placement manifest pose drift")

    clearance = clearance_audit.audit(BOARD, AUTHORITY)
    summary = clearance.get("summary", {})
    require(summary.get("state") == "PASS" and
            summary.get("confirmed_component_collisions") == 0 and
            summary.get("confirmed_mounting_clearance_conflicts") == 0 and
            summary.get("confirmed_tool_clearance_conflicts") == 0,
            "applied USB placement strict-clearance drift")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    evidence = status.get("review_b", {}).get("evidence", {})
    require(
        evidence.get("usb_placement_eco_001_status") in {
            "APPROVED_APPLIED_EXACT_R91_R92_PLACEMENT_PENDING_COMMIT_BOUND_KICAD9_GATE",
            "APPROVED_APPLIED_EXACT_R91_R92_PLACEMENT_COMMIT_BOUND_KICAD9_GATE_PASS",
        }
        and evidence.get("placement_clearance_control", {}).get("board_sha256") ==
        active_sha256
        and evidence.get("routing_constraint_control", {}).get("board_sha256") ==
        active_sha256
        and status.get("review_b", {}).get("complete") is False
        and status.get("manufacturing_release") is False,
        "capture-status USB application traceability or release boundary drift",
    )

    report: dict[str, object] = {
        "schema_version": "dioneya.pcb-main-usb-placement-eco-001-application-audit.v1",
        "status": "PASS_EXACT_ACCEPTED_USB_PLACEMENT_APPLICATION",
        "predecessor_sha256": BASE_SHA256,
        "active_board_sha256": active_sha256,
        "placement_manifest_sha256": PLACEMENT_SHA256,
        "changed_references": ["R91", "R92"],
        "copper_changed": False,
        "strict_placement_clearance": "PASS",
        "machine_gate": gate.get("status"),
        "application_commit_sha": APPLICATION_COMMIT,
        "pcb_native_run_id": 35526956229,
        "ci_run_id": 35526956245,
        "artifact_id": 10609668700,
        "usb_pair_routing_complete": False,
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
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    print("PCB-MAIN USB placement ECO-001 application audit:", report["status"])
    print(f"active_board_sha256={CANDIDATE_SHA256} moved=['R91', 'R92']")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
