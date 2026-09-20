#!/usr/bin/env python3
"""Apply/check the exact accepted PCB-MAIN USB placement ECO-001 candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-PLACEMENT-ECO-001/"
    "PCB-MAIN_USB_PLACEMENT_ECO_001_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-PLACEMENT-ECO-001/"
    "PCB-MAIN_USB_PLACEMENT_ECO_001_CANDIDATE_REV_A.kicad_pcb"
)
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_USB_PLACEMENT_ECO_001_APPROVAL_REV_A.json"

BASE_SHA256 = "f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9"
CANDIDATE_SHA256 = "d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e"
APPROVAL_SHA256 = "d071f6e0993d225ddab094b8e9d3cc4a24e52045286ca3f43d9929cb7597bf35"
APPROVAL_COMMIT = "20632248d9c70b6456d8fe5e3a30d99b25dd39f8"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    require(sha256(BASE) == BASE_SHA256, "USB application predecessor SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "accepted USB placement candidate SHA-256 drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "USB placement approval SHA-256 drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    require(
        approval.get("decision") ==
        "ACCEPT_USB_SOURCE_TERMINATION_PLACEMENT_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and approval.get("authorization", {}).get(
            "apply_exact_hash_bound_r91_r92_placement_delta"
        ) is True
        and approval.get("authorization", {}).get("usb_pair_routing_complete") is False
        and approval.get("authorization", {}).get(
            "cam_or_manufacturing_release"
        ) is False,
        "USB placement approval identity or boundary drift",
    )
    return CANDIDATE.read_bytes()


def apply(output: Path, check: bool) -> dict[str, object]:
    payload = accepted_payload()
    if check:
        require(output.read_bytes() == payload,
                "authoritative PCB-MAIN is not the exact accepted USB placement candidate")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    return {
        "status": "PASS_EXACT_ACCEPTED_USB_PLACEMENT_APPLICATION",
        "approval_commit": APPROVAL_COMMIT,
        "approval_sha256": APPROVAL_SHA256,
        "predecessor_sha256": BASE_SHA256,
        "applied_sha256": CANDIDATE_SHA256,
        "moved_footprints": ["R91", "R92"],
        "copper_changed": False,
        "usb_pair_routing_complete": False,
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
