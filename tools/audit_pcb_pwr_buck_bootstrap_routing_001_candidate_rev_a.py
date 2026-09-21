#!/usr/bin/env python3
"""Audit PCB-PWR dual-buck bootstrap routing candidate 001."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from kiutils.board import Board

from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-BOOTSTRAP-ROUTING-001/PCB-PWR_BUCK_BOOTSTRAP_ROUTING_001_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-BOOTSTRAP-ROUTING-001/PCB-PWR_BUCK_BOOTSTRAP_ROUTING_001_CANDIDATE_REV_A.kicad_pcb"
ACTIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
REVIEW = ROOT / "hardware/reviews/PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_CANDIDATE_REV_A.json"
GENERATOR = ROOT / "tools/generate_pcb_pwr_buck_bootstrap_routing_001_candidate_rev_a.py"
ROUTING_RULES = ROOT / "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv"
STACKUP_BASIS = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"

BASE_SHA256 = "b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957"
CANDIDATE_SHA256 = "a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236"
SEMANTIC_SHA256 = "b94eb0e53a714a2259e7362df7b96d1333c885f48399102b7ac279fb368d3276"
CANDIDATE_SEMANTIC_SHA256 = "d90ef0332ed5da798029a5cb580a0f3a5f68387068811eeb9e4c06d0681500ae"
GENERATOR_SHA256 = "b156b71cfb9ec712e7420dc4fdc0dee93daed1f6bc02fba13fbd97a84f6c081a"
ACTIVE_GENERATOR_SHA256 = "4ba8f1da54f605b9140b1a6f87d0ba55ee49f3a7e4089390da1a4e67e0ba2c8d"
ROUTING_RULES_SHA256 = "551a9691d51fd9451bf60193d79b8ed244d6b61fd5ec9c844a15050710f48988"
STACKUP_BASIS_SHA256 = "f420a20a7385cc9bd3d057e8d029246e8ebd64d7104511c677d628b7caf39230"
ACTIVE_STACKUP_BASIS_SHA256 = "dbb41a7fb0ee5eea01f7bbebaa542061d1c9d7b102c0cb4a912a974b03ab3dc3"
EXPECTED = {
    "BOOT_3V8": ((54.925, 15.125), (55.055, 16.4)),
    "BOOT_3V3": ((54.925, 43.125), (55.055, 44.4)),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drc_inventory(path: Path) -> tuple[Counter[tuple[str, str]], int, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fingerprints = Counter(
        (str(item.get("severity")), str(item.get("type")))
        for item in payload.get("violations", [])
    )
    return fingerprints, len(payload.get("violations", [])), len(payload.get("unconnected_items", []))


def audit_drc(base_path: Path, candidate_path: Path) -> dict[str, object]:
    base_fp, base_violations, base_unconnected = drc_inventory(base_path)
    candidate_fp, candidate_violations, candidate_unconnected = drc_inventory(candidate_path)
    added = candidate_fp - base_fp
    removed = base_fp - candidate_fp
    require(not added, f"bootstrap candidate introduces DRC fingerprints: {dict(added)}")
    require(not removed, f"bootstrap candidate removes unrelated DRC fingerprints: {dict(removed)}")
    require(candidate_violations == base_violations,
            "bootstrap candidate must preserve violation count")
    require(candidate_unconnected == base_unconnected - 2,
            "bootstrap candidate must close exactly two unconnected items")
    return {
        "status": "PASS_ZERO_NEW_DRC_EXACT_TWO_CONNECTION_REDUCTION",
        "base_violations": base_violations,
        "candidate_violations": candidate_violations,
        "base_unconnected": base_unconnected,
        "candidate_unconnected": candidate_unconnected,
        "new_drc_fingerprints": 0,
        "removed_drc_fingerprints": 0,
    }


def audit(drc_base: Path | None = None,
          drc_candidate: Path | None = None) -> dict[str, object]:
    require(sha256(BASE) == BASE_SHA256, "bootstrap base SHA-256 drift")
    require(sha256(ACTIVE) in {BASE_SHA256, CANDIDATE_SHA256,
            "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5"},
            "authoritative board is neither reviewed predecessor nor exact candidate")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "bootstrap candidate SHA-256 drift")
    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    require(semantic_board_sha256(base) == SEMANTIC_SHA256 and
            semantic_board_sha256(candidate) == CANDIDATE_SEMANTIC_SHA256,
            "placement/pad/net/layer/outline semantic drift")
    require(len(base.traceItems) == 0 and len(base.zones) == 0,
            "bootstrap base is not unrouted")
    require(len(candidate.traceItems) == 2 and len(candidate.zones) == 0,
            "bootstrap candidate copper inventory drift")
    net_names = {int(net.number): str(net.name) for net in candidate.nets}
    observed: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    total_length = 0.0
    for item in candidate.traceItems:
        require(str(item.layer) == "F.Cu" and float(item.width) == 0.5,
                "bootstrap route layer/width drift")
        name = net_names[int(item.net)]
        start = (float(item.start.X), float(item.start.Y))
        end = (float(item.end.X), float(item.end.Y))
        observed[name] = (start, end)
        total_length += math.dist(start, end)
    require(observed == EXPECTED, "bootstrap route endpoints or net identity drift")
    require(math.isclose(total_length, 2.563221, abs_tol=1e-6),
            "bootstrap total route length drift")
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    require(sha256(GENERATOR) in {GENERATOR_SHA256, ACTIVE_GENERATOR_SHA256} and
            sha256(ROUTING_RULES) == ROUTING_RULES_SHA256 and
            sha256(STACKUP_BASIS) in {STACKUP_BASIS_SHA256, ACTIVE_STACKUP_BASIS_SHA256},
            "bootstrap source binding drift")
    require(review["creation_authorization"] ==
            "ACCEPT_PCB_PWR_ROUTING_CANDIDATE_001_CREATION_SUBGATE" and
            review["candidate"]["sha256"] == CANDIDATE_SHA256 and
            review["source_binding"]["generator_sha256"] == GENERATOR_SHA256 and
            review["source_binding"]["routing_rules_sha256"] == ROUTING_RULES_SHA256 and
            review["source_binding"]["evt_stackup_basis_sha256"] == STACKUP_BASIS_SHA256 and
            review["invariants"]["authoritative_board_modified"] is False and
            review["machine_gate"]["status"] ==
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_COMPARATIVE_DRC" and
            review["routing_complete"] is False and
            review["review_b_complete"] is False and
            review["cam_or_manufacturing_release"] is False,
            "bootstrap proposal boundary drift")
    report: dict[str, object] = {
        "status": "PASS_STATIC_PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_CANDIDATE",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "routed_nets": sorted(EXPECTED),
        "trace_items": 2,
        "vias": 0,
        "authoritative_board_modified": False,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_candidate is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_candidate is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_candidate)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.drc_base, args.drc_candidate)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR buck bootstrap routing 001 candidate audit:", report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
