#!/usr/bin/env python3
"""Audit exact application of accepted PCB-MAIN cellular USB modem routing."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from kiutils.board import Board


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-MODEM-ROUTING-001/PCB-MAIN_USB_CELL_MODEM_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-MODEM-ROUTING-001/PCB-MAIN_USB_CELL_MODEM_CANDIDATE_REV_A.kicad_pcb"
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_MODEM_ROUTING_001_APPROVAL_REV_A.json"
MAPPING = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_MODEM_ROUTING_001_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_MODEM_ROUTING_001_APPLICATION_REV_A.json"
FIXTURE_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_FIXTURE_ROUTING_001_APPLICATION_REV_A.json"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"

BASE_SHA256 = "76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5"
CANDIDATE_SHA256 = "4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5"
FIXTURE_SUCCESSOR_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
APPROVAL_SHA256 = "771c1f8d4b0fad0a78785ac280b3c02c5d9764a706384a902fddb153e94e8301"
MAPPING_SHA256 = "b117715ef83872d5443d6067112b38ce8037993d02d7a52197d7f6af3e0b00fe"
APPROVAL_COMMIT = "4c9a2a8561fd5cf25ba4d2cb334a158b8a33cb88"
APPLICATION_COMMIT = "4c9a2a8561fd5cf25ba4d2cb334a158b8a33cb88"
APPLICATION_TREE = "0cf141aea24c77fe19f89aa28fd00b7547a66ca4"
CI_RUN_ID = 35538085583
PCB_NATIVE_RUN_ID = 35538085389
ARTIFACT_ID = 10612868581
ARTIFACT_DIGEST = (
    "sha256:6f37e792d7f0f7e09c22e5746743976e3953f6b12a5ccfa8f86e1ccd16f5b615"
)
AUTHORIZED_NETS = {"CELL_USB_DP_U8", "CELL_USB_DM_U8"}


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
        for kind in active_errors if active_errors[kind] > base_errors[kind]
    }
    require(not added, f"cellular USB modem application introduces errors: {added}")
    require(active_unconnected == base_unconnected - 2,
            "cellular USB modem application must close exactly two connections")
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
    require(sha256(BASE) == BASE_SHA256, "cellular USB modem base drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "cellular USB modem candidate drift")
    active_sha256 = sha256(BOARD)
    require(active_sha256 in {CANDIDATE_SHA256, FIXTURE_SUCCESSOR_SHA256},
            "authoritative PCB-MAIN is outside accepted cellular USB modem lineage")
    if active_sha256 == CANDIDATE_SHA256:
        require(BOARD.read_bytes() == CANDIDATE.read_bytes(),
                "authoritative PCB-MAIN is not exact accepted cellular USB modem candidate")
    else:
        fixture_application = json.loads(
            FIXTURE_APPLICATION.read_text(encoding="utf-8")
        )
        require(
            fixture_application.get("decision") ==
            "ACCEPT_USB_CELL_FIXTURE_ROUTING_SUBGATE"
            and fixture_application.get("predecessor", {}).get("board_sha256") ==
            CANDIDATE_SHA256
            and fixture_application.get("applied", {}).get("board_sha256") ==
            FIXTURE_SUCCESSOR_SHA256
            and fixture_application.get("applied", {}).get(
                "exact_candidate_byte_identity"
            ) is True
            and fixture_application.get("review_b_complete") is False
            and fixture_application.get("manufacturing_release") is False,
            "cellular USB fixture successor boundary drift",
        )
    require(sha256(APPROVAL) == APPROVAL_SHA256, "cellular USB modem approval drift")
    require(sha256(MAPPING) == MAPPING_SHA256, "cellular USB modem mapping drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    gate = application.get("machine_gate", {})
    require(
        approval.get("decision") == "ACCEPT_USB_CELL_MODEM_ROUTING_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and application.get("decision") == "ACCEPT_USB_CELL_MODEM_ROUTING_SUBGATE"
        and application.get("approval_commit_sha") == APPROVAL_COMMIT
        and application.get("application_commit_sha") == APPLICATION_COMMIT
        and application.get("approval_sha256") == APPROVAL_SHA256
        and application.get("review_mapping_sha256") == MAPPING_SHA256
        and application.get("applied", {}).get("board_sha256") == CANDIDATE_SHA256
        and application.get("applied", {}).get("exact_candidate_byte_identity") is True
        and application.get("status") ==
        "APPLIED_EXACT_ACCEPTED_USB_CELL_MODEM_ROUTING_COMMIT_BOUND_KICAD9_GATE_PASS"
        and application.get("review_b_complete") is False
        and application.get("manufacturing_release") is False,
        "cellular USB modem application identity or release boundary drift",
    )
    require(
        gate.get("status") == "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE"
        and gate.get("source_commit_sha") == APPLICATION_COMMIT
        and gate.get("source_tree_sha") == APPLICATION_TREE
        and gate.get("ci_run_id") == CI_RUN_ID
        and gate.get("ci_run_number") == 566
        and gate.get("ci_conclusion") == "success"
        and gate.get("pcb_native_run_id") == PCB_NATIVE_RUN_ID
        and gate.get("pcb_native_run_number") == 293
        and gate.get("pcb_native_conclusion") == "success"
        and gate.get("application_audit") ==
        "PASS_EXACT_APPLICATION_KICAD9_COMPARATIVE"
        and gate.get("comparative_drc") ==
        "PASS_NO_NEW_ERRORS_EXACT_TWO_CONNECTION_REDUCTION"
        and gate.get("base_violations") == 232
        and gate.get("active_violations") == 232
        and gate.get("base_unconnected") == 427
        and gate.get("active_unconnected") == 425
        and gate.get("new_errors") == 0
        and gate.get("artifact_id") == ARTIFACT_ID
        and gate.get("artifact_digest") == ARTIFACT_DIGEST,
        "cellular USB modem application commit-bound evidence drift",
    )

    base = Board.from_file(str(BASE), encoding="utf-8")
    accepted = Board.from_file(str(CANDIDATE), encoding="utf-8")
    active = Board.from_file(str(BOARD), encoding="utf-8")
    base_items = {item.tstamp: item for item in base.traceItems}
    accepted_items = {item.tstamp: item for item in accepted.traceItems}
    require(set(base_items) <= set(accepted_items)
            and all(base_items[key] == accepted_items[key] for key in base_items),
            "cellular USB modem application changes accepted predecessor copper")
    net_names = {item.number: item.name for item in accepted.nets}
    additions = [item for key, item in accepted_items.items() if key not in base_items]
    require(len(additions) == 6
            and all(type(item).__name__ == "Segment" for item in additions)
            and {net_names[item.net] for item in additions} == AUTHORIZED_NETS,
            "cellular USB modem application added-copper inventory drift")
    segments = [item for item in active.traceItems if type(item).__name__ == "Segment"]
    vias = [item for item in active.traceItems if type(item).__name__ == "Via"]
    require(len(active.traceItems) == (
                1023 if active_sha256 == FIXTURE_SUCCESSOR_SHA256 else 994
            ) and len(segments) == (
                738 if active_sha256 == FIXTURE_SUCCESSOR_SHA256 else 711
            ) and len(vias) == (
                285 if active_sha256 == FIXTURE_SUCCESSOR_SHA256 else 283
            ) and len(active.zones) == 8,
            "cellular USB modem authoritative copper inventory drift")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    evidence = status.get("review_b", {}).get("evidence", {})
    control = evidence.get("usb_cell_modem_routing_001_control", {})
    route_control = evidence.get("routing_constraint_control", {})
    require(
        evidence.get("usb_cell_modem_routing_001_status") ==
        "APPROVED_APPLIED_EXACT_CELL_MODEM_PAIR_COMMIT_BOUND_GATE_PASS"
        and control.get("active_board_sha256") == CANDIDATE_SHA256
        and control.get("exact_candidate_byte_identity") is True
        and control.get("trace_items") == 994
        and route_control.get("board_sha256") == active_sha256
        and route_control.get("trace_items") == (
            1023 if active_sha256 == FIXTURE_SUCCESSOR_SHA256 else 994
        )
        and route_control.get("usb_cell_modem_routing_subgate") ==
        "APPLIED_EXACT_ACCEPTED_CANDIDATE_COMMIT_BOUND_GATE_PASS"
        and status.get("review_b", {}).get("complete") is False
        and status.get("manufacturing_release") is False,
        "capture-status cellular USB modem application traceability drift",
    )

    report: dict[str, object] = {
        "schema": "dioneya.pcb-main-usb-cell-modem-routing-001-application-audit.v1",
        "status": "PASS_EXACT_ACCEPTED_USB_CELL_MODEM_ROUTING_APPLICATION",
        "predecessor_sha256": BASE_SHA256,
        "active_board_sha256": active_sha256,
        "routed_nets": sorted(AUTHORIZED_NETS),
        "added_segments": 6,
        "added_signal_vias": 0,
        "trace_items": len(active.traceItems),
        "machine_gate": gate.get("status"),
        "application_commit_sha": APPLICATION_COMMIT,
        "ci_run_id": CI_RUN_ID,
        "pcb_native_run_id": PCB_NATIVE_RUN_ID,
        "artifact_id": ARTIFACT_ID,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_active is None),
            "both application DRC paths are required together")
    if drc_base is not None and drc_active is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_active)
        report["status"] = "PASS_EXACT_APPLICATION_KICAD9_COMPARATIVE"
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
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN cellular USB modem application audit:", report["status"])
    print("active_board_sha256=" + report["active_board_sha256"]
          + f" trace_items={report['trace_items']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
