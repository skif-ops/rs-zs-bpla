#!/usr/bin/env python3
"""Apply/check the exact accepted PCB-MAIN USB MCU source-routing candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


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
APPROVAL = (
    ROOT / "hardware/reviews/"
    "PCB_MAIN_USB_SOURCE_ROUTING_001_APPROVAL_REV_A.json"
)

BASE_SHA256 = "d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e"
CANDIDATE_SHA256 = "76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5"
APPROVAL_SHA256 = "3e12b820b1fd488cd44d57131fd9fc0c6c8c75e7321c1c8855eef9c0ba86a284"
APPROVAL_COMMIT = "98b53498eda8cc5d6070d2d702c14119fa20781d"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    require(sha256(BASE) == BASE_SHA256, "USB source predecessor SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "accepted USB source-routing candidate SHA-256 drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256,
            "USB source-routing approval SHA-256 drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval.get("authorization", {})
    require(
        approval.get("decision") == "ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and authorization.get(
            "apply_exact_hash_bound_usb_mcu_source_routing_delta"
        ) is True
        and authorization.get("main_connector_usb_segment_complete") is False
        and authorization.get("cellular_usb_segments_complete") is False
        and authorization.get("review_b_complete") is False
        and authorization.get("cam_or_manufacturing_release") is False,
        "USB source-routing approval identity or boundary drift",
    )
    return CANDIDATE.read_bytes()


def apply(output: Path, check: bool) -> dict[str, object]:
    payload = accepted_payload()
    if check:
        require(output.is_file() and output.read_bytes() == payload,
                "authoritative PCB-MAIN is not the exact accepted USB source candidate")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    return {
        "status": "PASS_EXACT_ACCEPTED_USB_MCU_SOURCE_ROUTING_APPLICATION",
        "approval_commit": APPROVAL_COMMIT,
        "approval_sha256": APPROVAL_SHA256,
        "predecessor_sha256": BASE_SHA256,
        "applied_sha256": CANDIDATE_SHA256,
        "routed_nets": ["USB_DM_U1", "USB_DP_U1"],
        "added_segments": 13,
        "added_signal_vias": 0,
        "main_connector_usb_segment_complete": False,
        "cellular_usb_segments_complete": False,
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
