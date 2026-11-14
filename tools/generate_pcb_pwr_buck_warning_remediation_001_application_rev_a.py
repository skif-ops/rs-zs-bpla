#!/usr/bin/env python3
"""Apply/check the exact accepted PCB-PWR buck warning remediation 001."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


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
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = (
    ROOT
    / "hardware/reviews/PCB_PWR_BUCK_WARNING_REMEDIATION_001_APPROVAL_REV_A.json"
)

BASE_SHA256 = "9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37"
CANDIDATE_SHA256 = "b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957"
APPROVAL_SHA256 = "386ece8201dae24da18db811845cf3501512192593c6e1bf31767fd3c71d5837"
APPROVAL_COMMIT = "54083a35e0c6c33a34dd9ddc1cf2d4255409b7d7"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    require(sha256(BASE) == BASE_SHA256,
            "PCB-PWR warning-remediation predecessor SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "accepted PCB-PWR warning-remediation candidate SHA-256 drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256,
            "PCB-PWR warning-remediation approval SHA-256 drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval.get("authorization", {})
    require(
        approval.get("decision") ==
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
    return CANDIDATE.read_bytes()


def apply(output: Path, check: bool) -> dict[str, object]:
    payload = accepted_payload()
    if check:
        require(output.read_bytes() == payload,
                "authoritative PCB-PWR is not the exact accepted warning-remediation candidate")
    else:
        require(output.is_file(),
                "authoritative PCB-PWR predecessor is missing")
        require(sha256(output) == BASE_SHA256 and
                output.read_bytes() == BASE.read_bytes(),
                "authoritative PCB-PWR is not the approved predecessor")
        output.write_bytes(payload)
    return {
        "status":
        "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_WARNING_REMEDIATION_APPLICATION",
        "approval_commit": APPROVAL_COMMIT,
        "approval_sha256": APPROVAL_SHA256,
        "predecessor_sha256": BASE_SHA256,
        "applied_sha256": CANDIDATE_SHA256,
        "normalized_instances": ["C4", "C6"],
        "moved_reference_fields": ["R10"],
        "component_poses_changed": False,
        "pad_copper_changed": False,
        "routing_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=BOARD)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(apply(args.output.resolve(), args.check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
