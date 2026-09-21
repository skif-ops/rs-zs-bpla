#!/usr/bin/env python3
"""Apply/check the exact accepted PCB-PWR buck placement ECO-001 candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-PLACEMENT-ECO-001/"
    "PCB-PWR_BUCK_PLACEMENT_ECO_001_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-PLACEMENT-ECO-001/"
    "PCB-PWR_BUCK_PLACEMENT_ECO_001_CANDIDATE_REV_A.kicad_pcb"
)
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_BUCK_PLACEMENT_ECO_001_APPROVAL_REV_A.json"

BASE_SHA256 = "fdd53e669a167df8925c38e289993c38b818c231eddd0be54de378b51538bf48"
CANDIDATE_SHA256 = "9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37"
APPROVAL_SHA256 = "03a3c499b785ffdbe331f5bb442aecde31411bb6b3e65c88e0eaf2e0a62c8c7e"
APPROVAL_COMMIT = "82dbcf2a0318d79c73ad4c59e1f58158b453605f"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    require(sha256(BASE) == BASE_SHA256,
            "PCB-PWR application predecessor SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "accepted PCB-PWR buck placement candidate SHA-256 drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256,
            "PCB-PWR buck placement approval SHA-256 drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval.get("authorization", {})
    require(
        approval.get("decision") ==
        "ACCEPT_PCB_PWR_BUCK_PLACEMENT_ECO_001_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and authorization.get(
            "apply_exact_hash_bound_c4_c6_l1_l2_placement_delta"
        ) is True
        and authorization.get(
            "preserve_all_unlisted_footprints_nets_outline_and_copper"
        ) is True
        and authorization.get("routing_complete") is False
        and authorization.get("cam_or_manufacturing_release") is False,
        "PCB-PWR buck placement approval identity or boundary drift",
    )
    return CANDIDATE.read_bytes()


def apply(output: Path, check: bool) -> dict[str, object]:
    payload = accepted_payload()
    if check:
        require(output.read_bytes() == payload,
                "authoritative PCB-PWR is not the exact accepted buck placement candidate")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    return {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_PLACEMENT_APPLICATION",
        "approval_commit": APPROVAL_COMMIT,
        "approval_sha256": APPROVAL_SHA256,
        "predecessor_sha256": BASE_SHA256,
        "applied_sha256": CANDIDATE_SHA256,
        "moved_footprints": ["C4", "C6", "L1", "L2"],
        "copper_changed": False,
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
