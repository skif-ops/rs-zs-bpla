#!/usr/bin/env python3
"""Audit exact application of accepted PCB-MAIN cellular USB fixture routing."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from kiutils.board import Board


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-FIXTURE-ROUTING-001/PCB-MAIN_USB_CELL_FIXTURE_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-FIXTURE-ROUTING-001/PCB-MAIN_USB_CELL_FIXTURE_CANDIDATE_REV_A.kicad_pcb"
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_FIXTURE_ROUTING_001_APPROVAL_REV_A.json"
MAPPING = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_FIXTURE_ROUTING_001_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_FIXTURE_ROUTING_001_APPLICATION_REV_A.json"
STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"

BASE_SHA256 = "4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5"
CANDIDATE_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
APPROVAL_SHA256 = "ceec87a1ef444f417cc0817df4ba089808284aa42d10cb47771d0c31b8f76307"
MAPPING_SHA256 = "00f9793cb95feb781812c00da181262d5252741e80601671b0e97ddff3de6698"
AUTHORIZED_NETS = {"CELL_USB_DP_TP", "CELL_USB_DM_TP"}


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
    require(not added, f"cellular USB fixture application introduces errors: {added}")
    require(active_unconnected == base_unconnected - 4,
            "cellular USB fixture application must close exactly four connections")
    return {
        "status": "PASS_NO_NEW_ERRORS_EXACT_FOUR_CONNECTION_REDUCTION",
        "base_violations": base_violations,
        "active_violations": active_violations,
        "base_unconnected": base_unconnected,
        "active_unconnected": active_unconnected,
        "new_errors": 0,
        "unconnected_reduction": 4,
    }


def audit(drc_base: Path | None = None, drc_active: Path | None = None) -> dict[str, object]:
    require(sha256(BASE) == BASE_SHA256, "cellular USB fixture base drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "cellular USB fixture candidate drift")
    require(sha256(BOARD) == CANDIDATE_SHA256 and BOARD.read_bytes() == CANDIDATE.read_bytes(),
            "authoritative PCB-MAIN is not exact accepted cellular USB fixture candidate")
    require(sha256(APPROVAL) == APPROVAL_SHA256,
            "cellular USB fixture approval drift")
    require(sha256(MAPPING) == MAPPING_SHA256,
            "cellular USB fixture mapping drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    gate = application.get("machine_gate", {})
    require(
        approval.get("decision") == "ACCEPT_USB_CELL_FIXTURE_ROUTING_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and application.get("decision") == "ACCEPT_USB_CELL_FIXTURE_ROUTING_SUBGATE"
        and application.get("approval_sha256") == APPROVAL_SHA256
        and application.get("review_mapping_sha256") == MAPPING_SHA256
        and application.get("applied", {}).get("board_sha256") == CANDIDATE_SHA256
        and application.get("applied", {}).get("exact_candidate_byte_identity") is True
        and gate.get("status") in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE",
        }
        and application.get("review_b_complete") is False
        and application.get("manufacturing_release") is False,
        "cellular USB fixture application identity or release boundary drift",
    )

    base = Board.from_file(str(BASE), encoding="utf-8")
    active = Board.from_file(str(BOARD), encoding="utf-8")
    base_items = {item.tstamp: item for item in base.traceItems}
    active_items = {item.tstamp: item for item in active.traceItems}
    require(set(base_items) <= set(active_items)
            and all(base_items[key] == active_items[key] for key in base_items),
            "cellular USB fixture application changes accepted predecessor copper")
    net_names = {item.number: item.name for item in active.nets}
    additions = [item for key, item in active_items.items() if key not in base_items]
    added_segments = [item for item in additions if type(item).__name__ == "Segment"]
    added_vias = [item for item in additions if type(item).__name__ == "Via"]
    require(len(additions) == 29 and len(added_segments) == 27 and len(added_vias) == 2
            and {net_names[item.net] for item in additions} == AUTHORIZED_NETS,
            "cellular USB fixture application added-copper inventory drift")
    segments = [item for item in active.traceItems if type(item).__name__ == "Segment"]
    vias = [item for item in active.traceItems if type(item).__name__ == "Via"]
    require(len(active.traceItems) == 1023 and len(segments) == 738
            and len(vias) == 285 and len(active.zones) == 8,
            "cellular USB fixture authoritative copper inventory drift")

    status = json.loads(STATUS.read_text(encoding="utf-8"))
    evidence = status.get("review_b", {}).get("evidence", {})
    control = evidence.get("usb_cell_fixture_routing_001_control", {})
    route_control = evidence.get("routing_constraint_control", {})
    require(
        evidence.get("usb_cell_fixture_routing_001_status") ==
        "APPROVED_APPLIED_EXACT_CELL_FIXTURE_PAIR_COMMIT_BOUND_GATE_PENDING"
        and control.get("active_board_sha256") == CANDIDATE_SHA256
        and control.get("exact_candidate_byte_identity") is True
        and control.get("trace_items") == 1023
        and route_control.get("board_sha256") == CANDIDATE_SHA256
        and route_control.get("trace_items") == 1023
        and route_control.get("usb_cell_fixture_routing_subgate") ==
        "APPLIED_EXACT_ACCEPTED_CANDIDATE_COMMIT_BOUND_GATE_PENDING"
        and status.get("review_b", {}).get("complete") is False
        and status.get("manufacturing_release") is False,
        "capture-status cellular USB fixture application traceability drift",
    )

    report: dict[str, object] = {
        "schema": "dioneya.pcb-main-usb-cell-fixture-routing-001-application-audit.v1",
        "status": "PASS_EXACT_ACCEPTED_USB_CELL_FIXTURE_ROUTING_APPLICATION",
        "predecessor_sha256": BASE_SHA256,
        "active_board_sha256": CANDIDATE_SHA256,
        "routed_nets": sorted(AUTHORIZED_NETS),
        "added_segments": 27,
        "added_signal_vias": 2,
        "trace_items": 1023,
        "machine_gate": gate.get("status"),
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
    print("PCB-MAIN cellular USB fixture application audit:", report["status"])
    print("active_board_sha256=" + CANDIDATE_SHA256 + " trace_items=1023")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
