#!/usr/bin/env python3
"""Apply/check the exact accepted PCB-MAIN cellular USB modem candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-MODEM-ROUTING-001/"
    "PCB-MAIN_USB_CELL_MODEM_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-MODEM-ROUTING-001/"
    "PCB-MAIN_USB_CELL_MODEM_CANDIDATE_REV_A.kicad_pcb"
)
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
APPROVAL = (
    ROOT / "hardware/reviews/"
    "PCB_MAIN_USB_CELL_MODEM_ROUTING_001_APPROVAL_REV_A.json"
)
MAPPING = (
    ROOT / "hardware/reviews/"
    "PCB_MAIN_USB_CELL_MODEM_ROUTING_001_REVIEW_COMMIT_MAPPING.json"
)
FIXTURE_APPLICATION = (
    ROOT / "hardware/reviews/"
    "PCB_MAIN_USB_CELL_FIXTURE_ROUTING_001_APPLICATION_REV_A.json"
)

BASE_SHA256 = "76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5"
CANDIDATE_SHA256 = "4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5"
FIXTURE_SUCCESSOR_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
APPROVAL_SHA256 = "771c1f8d4b0fad0a78785ac280b3c02c5d9764a706384a902fddb153e94e8301"
MAPPING_SHA256 = "b117715ef83872d5443d6067112b38ce8037993d02d7a52197d7f6af3e0b00fe"
REVIEWED_EVIDENCE_COMMIT = "88292432cee87cec4e209ed2d0e4d142071af2cb"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    require(sha256(BASE) == BASE_SHA256, "cellular USB modem predecessor drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "accepted cellular USB modem candidate drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256,
            "cellular USB modem approval SHA-256 drift")
    require(sha256(MAPPING) == MAPPING_SHA256,
            "cellular USB modem review mapping SHA-256 drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    authorization = approval.get("authorization", {})
    require(
        approval.get("decision") == "ACCEPT_USB_CELL_MODEM_ROUTING_SUBGATE"
        and approval.get("reviewed_github_commit_sha") == REVIEWED_EVIDENCE_COMMIT
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and mapping.get("reviewed_github_commit_sha") == REVIEWED_EVIDENCE_COMMIT
        and mapping.get("candidate_board_sha256") == CANDIDATE_SHA256
        and authorization.get(
            "apply_exact_hash_bound_usb_cell_modem_routing_delta"
        ) is True
        and authorization.get("main_connector_usb_segment_complete") is False
        and authorization.get("cellular_fixture_usb_segment_complete") is False
        and authorization.get("review_b_complete") is False
        and authorization.get("cam_or_manufacturing_release") is False,
        "cellular USB modem approval identity or boundary drift",
    )
    return CANDIDATE.read_bytes()


def apply(output: Path, check: bool) -> dict[str, object]:
    payload = accepted_payload()
    if check:
        require(output.is_file(), "cellular USB modem application output is missing")
        output_sha256 = sha256(output)
        require(output_sha256 in {CANDIDATE_SHA256, FIXTURE_SUCCESSOR_SHA256},
                "authoritative PCB-MAIN is outside accepted cellular USB modem lineage")
        if output_sha256 == CANDIDATE_SHA256:
            require(output.read_bytes() == payload,
                    "authoritative PCB-MAIN is not the exact accepted cellular USB modem candidate")
        else:
            fixture_application = json.loads(
                FIXTURE_APPLICATION.read_text(encoding="utf-8")
            )
            require(
                fixture_application.get("decision") ==
                "ACCEPT_USB_CELL_FIXTURE_ROUTING_SUBGATE"
                and fixture_application.get("predecessor", {}).get(
                    "board_sha256"
                ) == CANDIDATE_SHA256
                and fixture_application.get("applied", {}).get(
                    "board_sha256"
                ) == FIXTURE_SUCCESSOR_SHA256
                and fixture_application.get("applied", {}).get(
                    "exact_candidate_byte_identity"
                ) is True
                and fixture_application.get("review_b_complete") is False
                and fixture_application.get("manufacturing_release") is False,
                "cellular USB fixture successor boundary drift",
            )
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    return {
        "status": "PASS_EXACT_ACCEPTED_USB_CELL_MODEM_ROUTING_APPLICATION",
        "reviewed_evidence_commit": REVIEWED_EVIDENCE_COMMIT,
        "approval_sha256": APPROVAL_SHA256,
        "review_mapping_sha256": MAPPING_SHA256,
        "predecessor_sha256": BASE_SHA256,
        "applied_sha256": CANDIDATE_SHA256,
        "routed_nets": ["CELL_USB_DM_U8", "CELL_USB_DP_U8"],
        "added_segments": 6,
        "added_signal_vias": 0,
        "main_connector_usb_segment_complete": False,
        "cellular_fixture_usb_segment_complete": False,
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
