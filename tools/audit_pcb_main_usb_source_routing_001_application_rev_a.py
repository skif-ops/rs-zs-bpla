#!/usr/bin/env python3
"""Audit exact application of accepted PCB-MAIN USB source routing 001."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from kiutils.board import Board


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-SOURCE-ROUTING-001/"
    "PCB-MAIN_USB_SOURCE_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-SOURCE-ROUTING-001/"
    "PCB-MAIN_USB_SOURCE_CANDIDATE_REV_A.kicad_pcb"
)
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_USB_SOURCE_ROUTING_001_APPROVAL_REV_A.json"
MAPPING = ROOT / "hardware/reviews/PCB_MAIN_USB_SOURCE_ROUTING_001_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_SOURCE_ROUTING_001_APPLICATION_REV_A.json"
GENERATOR = ROOT / "tools/generate_pcb_main_usb_source_routing_001_application_rev_a.py"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"

BASE_SHA256 = "d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e"
CANDIDATE_SHA256 = "76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5"
APPROVAL_SHA256 = "3e12b820b1fd488cd44d57131fd9fc0c6c8c75e7321c1c8855eef9c0ba86a284"
MAPPING_SHA256 = "d98c0f0f5c74c3a6777f34d6f68b823cadbd57d89f4114926181f5b3c45b8eca"
GENERATOR_SHA256 = "91e16d5fb317721485a24a324f49d835ac900f95e43bab1268ded10fd25ec02a"
APPROVAL_COMMIT = "98b53498eda8cc5d6070d2d702c14119fa20781d"
APPLICATION_COMMIT = "6c27d3ae148a613fa07243dd09c26d8c2accad8e"
APPLICATION_TREE = "9c44688dcd1db6c51609ffd4efcf17502b5e9458"
CI_RUN_ID = 35533128214
PCB_NATIVE_RUN_ID = 35533128125
ARTIFACT_ID = 10611393138
ARTIFACT_DIGEST = (
    "sha256:7fba5414f2fc3e1df3938f12b98e0468c44cd50cf29b64e65342eed0612768ff"
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drc_inventory(path: Path) -> tuple[Counter[str], int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = Counter(
        item.get("type", "UNKNOWN")
        for item in payload.get("violations", [])
        if item.get("severity") == "error"
    )
    return errors, len(payload.get("violations", [])), len(payload.get("unconnected_items", []))


def audit_drc(base_path: Path, active_path: Path) -> dict[str, object]:
    base_errors, base_violations, base_unconnected = drc_inventory(base_path)
    active_errors, active_violations, active_unconnected = drc_inventory(active_path)
    added = {
        kind: active_errors[kind] - base_errors[kind]
        for kind in active_errors
        if active_errors[kind] > base_errors[kind]
    }
    require(not added, f"applied USB source routing adds KiCad 9 errors: {added}")
    require(active_unconnected == base_unconnected - 2,
            "applied USB source routing must close exactly two pad connections")
    return {
        "status": "PASS_NO_NEW_ERRORS_EXACT_TWO_CONNECTION_REDUCTION",
        "base_violations": base_violations,
        "active_violations": active_violations,
        "base_unconnected": base_unconnected,
        "active_unconnected": active_unconnected,
        "new_errors": 0,
        "unconnected_reduction": 2,
    }


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict[str, object]:
    for path in (BASE, CANDIDATE, BOARD, APPROVAL, MAPPING, APPLICATION,
                 GENERATOR, STATUS):
        require(path.is_file() and path.stat().st_size > 0,
                f"missing USB source application input: {path}")
    require(sha256(BASE) == BASE_SHA256, "USB source predecessor SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "USB source candidate SHA-256 drift")
    require(sha256(BOARD) == CANDIDATE_SHA256 and
            BOARD.read_bytes() == CANDIDATE.read_bytes(),
            "authoritative PCB-MAIN is not the exact accepted USB source candidate")
    require(sha256(APPROVAL) == APPROVAL_SHA256,
            "USB source approval SHA-256 drift")
    require(sha256(MAPPING) == MAPPING_SHA256,
            "USB source review mapping SHA-256 drift")
    require(sha256(GENERATOR) == GENERATOR_SHA256,
            "USB source application generator drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    require(
        approval.get("reviewed_github_commit_sha") ==
        "8fdb96c684a935cadeda6ae6ec8c78db32cbd610"
        and approval.get("decision") == "ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and approval.get("authorization", {}).get(
            "apply_exact_hash_bound_usb_mcu_source_routing_delta"
        ) is True
        and approval.get("authorization", {}).get("review_b_complete") is False
        and approval.get("authorization", {}).get(
            "cam_or_manufacturing_release"
        ) is False,
        "USB source approval identity or boundary drift",
    )
    require(
        mapping.get("reviewed_github_commit_sha") ==
        "8fdb96c684a935cadeda6ae6ec8c78db32cbd610"
        and mapping.get("candidate_board_sha256") == CANDIDATE_SHA256
        and mapping.get("equivalence") == "EXACT_REVIEWED_TREE_AND_BLOBS"
        and mapping.get("review_b_complete") is False
        and mapping.get("cam_or_manufacturing_release") is False,
        "USB source review mapping drift",
    )
    applied = application.get("applied", {})
    gate = application.get("machine_gate", {})
    require(
        application.get("approval_commit_sha") == APPROVAL_COMMIT
        and application.get("approval_sha256") == APPROVAL_SHA256
        and application.get("review_mapping_sha256") == MAPPING_SHA256
        and application.get("decision") == "ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE"
        and application.get("scope") ==
        "EXACT_U1_TO_R91_R92_PAIR_AND_REVIEWED_LOCAL_GND_DIGITAL_FANOUT_DELTA_ONLY"
        and application.get("predecessor", {}).get("board_sha256") == BASE_SHA256
        and application.get("application_generator", {}).get("sha256") ==
        GENERATOR_SHA256
        and applied.get("board_sha256") == CANDIDATE_SHA256
        and applied.get("exact_candidate_byte_identity") is True
        and applied.get("routed_nets") == ["USB_DM_U1", "USB_DP_U1"]
        and applied.get("added_segments") == 13
        and applied.get("added_signal_vias") == 0
        and applied.get("trace_items") == 988
        and applied.get("track_segments") == 705
        and applied.get("vias") == 283
        and applied.get("copper_zones") == 8
        and application.get("remaining_usb_routing") == [
            "USB_MAIN_CONNECTOR_SEGMENT",
            "USB_CELL_MODEM_SEGMENT",
            "USB_CELL_FIXTURE_SEGMENT",
        ]
        and application.get("review_b_complete") is False
        and application.get("cam_or_manufacturing_release") is False
        and application.get("manufacturing_release") is False,
        "USB source application identity, geometry, or release boundary drift",
    )
    require(
        application.get("application_commit_sha") == APPLICATION_COMMIT
        and gate.get("status") == "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE"
        and gate.get("source_commit_sha") == APPLICATION_COMMIT
        and gate.get("source_tree_sha") == APPLICATION_TREE
        and gate.get("ci_run_id") == CI_RUN_ID
        and gate.get("ci_run_number") == 562
        and gate.get("ci_conclusion") == "success"
        and gate.get("pcb_native_run_id") == PCB_NATIVE_RUN_ID
        and gate.get("pcb_native_run_number") == 289
        and gate.get("pcb_native_conclusion") == "success"
        and gate.get("application_audit") ==
        "PASS_EXACT_ACCEPTED_USB_MCU_SOURCE_ROUTING_APPLICATION"
        and gate.get("comparative_drc") ==
        "PASS_NO_NEW_ERRORS_EXACT_TWO_CONNECTION_REDUCTION"
        and gate.get("base_violations") == 232
        and gate.get("active_violations") == 232
        and gate.get("base_unconnected") == 429
        and gate.get("active_unconnected") == 427
        and gate.get("new_errors") == 0
        and gate.get("artifact_id") == ARTIFACT_ID
        and gate.get("artifact_digest") == ARTIFACT_DIGEST,
        "USB source application commit-bound evidence drift",
    )

    board = Board.from_file(str(BOARD), encoding="utf-8")
    segments = [item for item in board.traceItems if type(item).__name__ == "Segment"]
    vias = [item for item in board.traceItems if type(item).__name__ == "Via"]
    require(len(board.traceItems) == 988 and len(segments) == 705 and
            len(vias) == 283 and len(board.zones) == 8,
            "USB source authoritative copper inventory drift")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    evidence = status.get("review_b", {}).get("evidence", {})
    control = evidence.get("usb_source_routing_001_control", {})
    route_control = evidence.get("routing_constraint_control", {})
    require(
        evidence.get("usb_source_routing_001_status") ==
        "APPROVED_APPLIED_EXACT_MCU_SOURCE_PAIR_COMMIT_BOUND_KICAD9_GATE_PASS"
        and control.get("active_board_sha256") == CANDIDATE_SHA256
        and control.get("exact_candidate_byte_identity") is True
        and control.get("trace_items") == 988
        and control.get("review_b_complete") is False
        and control.get("manufacturing_release") is False
        and route_control.get("board_sha256") == CANDIDATE_SHA256
        and route_control.get("trace_items") == 988
        and route_control.get("usb_mcu_source_routing_subgate") ==
        "APPLIED_EXACT_ACCEPTED_CANDIDATE_COMMIT_BOUND_GATE_PASS"
        and status.get("review_b", {}).get("complete") is False
        and status.get("manufacturing_release") is False,
        "capture-status USB source application traceability drift",
    )

    report: dict[str, object] = {
        "schema_version": "dioneya.pcb-main-usb-source-routing-001-application-audit.v1",
        "status": "PASS_EXACT_ACCEPTED_USB_MCU_SOURCE_ROUTING_APPLICATION",
        "predecessor_sha256": BASE_SHA256,
        "active_board_sha256": CANDIDATE_SHA256,
        "routed_nets": ["USB_DM_U1", "USB_DP_U1"],
        "added_segments": 13,
        "added_signal_vias": 0,
        "trace_items": 988,
        "machine_gate": gate.get("status"),
        "application_commit_sha": APPLICATION_COMMIT,
        "ci_run_id": CI_RUN_ID,
        "pcb_native_run_id": PCB_NATIVE_RUN_ID,
        "artifact_id": ARTIFACT_ID,
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
    print("PCB-MAIN USB source routing 001 application audit:", report["status"])
    print("active_board_sha256=" + CANDIDATE_SHA256 + " trace_items=988")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
