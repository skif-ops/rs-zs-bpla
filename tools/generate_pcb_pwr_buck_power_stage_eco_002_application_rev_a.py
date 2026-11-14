#!/usr/bin/env python3
"""Apply/check the exact accepted PCB-PWR buck power-stage ECO-002 candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-POWER-STAGE-ECO-002"
BASE = CANDIDATE_DIR / "PCB-PWR_BUCK_POWER_STAGE_ECO_002_BASE_REV_A.kicad_pcb"
CANDIDATE = CANDIDATE_DIR / "PCB-PWR_BUCK_POWER_STAGE_ECO_002_CANDIDATE_REV_A.kicad_pcb"
BOARD = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_PWR_BUCK_POWER_STAGE_ECO_002_APPROVAL_REV_A.json"

BASE_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
CANDIDATE_SHA256 = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"
APPROVAL_SHA256 = "c1f5e11c6587c01d9b3f386e2316470029c2b7ba1566a9e3f7c91fd948ee08ae"
APPROVAL_COMMIT = "100f81230df8310d1d52e606aadb058b9179282a"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_payload() -> bytes:
    require(sha256(BASE) == BASE_SHA256, "ECO-002 predecessor SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "ECO-002 candidate SHA-256 drift")
    require(sha256(APPROVAL) == APPROVAL_SHA256, "ECO-002 approval SHA-256 drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    authorization = approval["authorization"]
    approved_delta = approval["approved_delta"]
    require(
        approval["decision"] == "ACCEPT_PCB_PWR_BUCK_POWER_STAGE_ECO_002_SUBGATE"
        and approval["reviewed_candidate_board_sha256"] == CANDIDATE_SHA256
        and authorization["apply_exact_hash_bound_buck_power_stage_candidate"] is True
        and authorization["expected_authoritative_predecessor_sha256"] == BASE_SHA256
        and authorization["authorized_applied_board_sha256"] == CANDIDATE_SHA256
        and authorization["preserve_unrelated_predecessor_copper"] is True
        and authorization["apply_only_the_reviewed_footprint_copper_and_silkscreen_delta"] is True
        and authorization["alter_reviewed_candidate_without_new_controlled_review"] is False
        and authorization["vin_pgnd_output_kelvin_or_feedback_routing_authorized"] is False
        and authorization["routing_complete"] is False
        and authorization["review_b_complete"] is False
        and authorization["cam_or_manufacturing_release"] is False
        and approved_delta["removed_bootstrap_segments"] == 2
        and approved_delta["retained_unrelated_predecessor_segments"] == 6
        and approved_delta["added_segments"] == 8
        and approved_delta["vias"] == 0
        and approved_delta["zones"] == 0
        and approved_delta["pad_geometry_or_nets_changed"] is False
        and approved_delta["drc_rules_relaxed"] is False,
        "ECO-002 approval identity or boundary drift",
    )
    return CANDIDATE.read_bytes()


def apply(output: Path, check: bool) -> dict[str, object]:
    payload = accepted_payload()
    if check:
        require(output.read_bytes() == payload,
                "authoritative PCB-PWR is not the exact accepted ECO-002 candidate")
    else:
        require(output.read_bytes() == BASE.read_bytes() and sha256(output) == BASE_SHA256,
                "authoritative PCB-PWR is not the approved ECO-002 predecessor")
        output.write_bytes(payload)
    return {
        "status": "PASS_EXACT_ACCEPTED_PCB_PWR_BUCK_POWER_STAGE_ECO_002_APPLICATION",
        "approval_commit": APPROVAL_COMMIT,
        "approval_sha256": APPROVAL_SHA256,
        "predecessor_sha256": BASE_SHA256,
        "applied_sha256": CANDIDATE_SHA256,
        "trace_items": 14,
        "vias": 0,
        "zones": 0,
        "physical_plus70c_first_article_validation_required": True,
        "routing_complete": False,
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
