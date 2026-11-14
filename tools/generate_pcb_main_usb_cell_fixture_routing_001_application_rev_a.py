#!/usr/bin/env python3
"""Apply/check the exact accepted PCB-MAIN cellular USB fixture candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")) if str(ROOT / "tools") not in sys.path else None
import pcb_main_lineage_rev_a as _lineage  # noqa: E402  (PCB-MAIN 003: earlier sub-gates read the predecessor)
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-FIXTURE-ROUTING-001/"
    "PCB-MAIN_USB_CELL_FIXTURE_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-FIXTURE-ROUTING-001/"
    "PCB-MAIN_USB_CELL_FIXTURE_CANDIDATE_REV_A.kicad_pcb"
)
BOARD = _lineage.historical_board()
APPROVAL = (
    ROOT / "hardware/reviews/"
    "PCB_MAIN_USB_CELL_FIXTURE_ROUTING_001_APPROVAL_REV_A.json"
)
MAPPING = (
    ROOT / "hardware/reviews/"
    "PCB_MAIN_USB_CELL_FIXTURE_ROUTING_001_REVIEW_COMMIT_MAPPING.json"
)

BASE_SHA256 = "4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5"
CANDIDATE_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
APPROVAL_SHA256 = "ceec87a1ef444f417cc0817df4ba089808284aa42d10cb47771d0c31b8f76307"
MAPPING_SHA256 = "00f9793cb95feb781812c00da181262d5252741e80601671b0e97ddff3de6698"
REVIEWED_EVIDENCE_COMMIT = "11af5c9df9ac8e4fd68ba78dbbd5c067bd3fe23f"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    require(sha256(BASE) == BASE_SHA256,
            "cellular USB fixture predecessor drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "accepted cellular USB fixture candidate drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256,
            "cellular USB fixture approval SHA-256 drift")
    require(sha256(MAPPING) == MAPPING_SHA256,
            "cellular USB fixture review mapping SHA-256 drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    authorization = approval.get("authorization", {})
    require(
        approval.get("decision") == "ACCEPT_USB_CELL_FIXTURE_ROUTING_SUBGATE"
        and approval.get("reviewed_github_commit_sha") == REVIEWED_EVIDENCE_COMMIT
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and mapping.get("reviewed_github_commit_sha") == REVIEWED_EVIDENCE_COMMIT
        and mapping.get("candidate_board_sha256") == CANDIDATE_SHA256
        and authorization.get(
            "apply_exact_hash_bound_usb_cell_fixture_routing_delta"
        ) is True
        and authorization.get("main_connector_usb_segment_complete") is False
        and authorization.get("review_b_complete") is False
        and authorization.get("cam_or_manufacturing_release") is False,
        "cellular USB fixture approval identity or boundary drift",
    )
    return CANDIDATE.read_bytes()


def apply(output: Path, check: bool) -> dict[str, object]:
    payload = accepted_payload()
    if check:
        require(output.is_file() and output.read_bytes() == payload,
                "authoritative PCB-MAIN is not the exact accepted cellular USB fixture candidate")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    return {
        "status": "PASS_EXACT_ACCEPTED_USB_CELL_FIXTURE_ROUTING_APPLICATION",
        "reviewed_evidence_commit": REVIEWED_EVIDENCE_COMMIT,
        "approval_sha256": APPROVAL_SHA256,
        "review_mapping_sha256": MAPPING_SHA256,
        "predecessor_sha256": BASE_SHA256,
        "applied_sha256": CANDIDATE_SHA256,
        "routed_nets": ["CELL_USB_DM_TP", "CELL_USB_DP_TP"],
        "added_segments": 27,
        "added_signal_vias": 2,
        "main_connector_usb_segment_complete": False,
        "review_b_complete": False,
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
