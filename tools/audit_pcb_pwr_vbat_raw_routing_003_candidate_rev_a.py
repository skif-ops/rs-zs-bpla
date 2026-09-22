#!/usr/bin/env python3
"""Audit PCB-PWR VBAT_RAW routing candidate 003."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from kiutils.board import Board

from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-RAW-ROUTING-003/PCB-PWR_VBAT_RAW_ROUTING_003_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-RAW-ROUTING-003/PCB-PWR_VBAT_RAW_ROUTING_003_CANDIDATE_REV_A.kicad_pcb"
ACTIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
REVIEW = ROOT / "hardware/reviews/PCB_PWR_VBAT_RAW_ROUTING_003_CANDIDATE_REV_A.json"
GENERATOR = ROOT / "tools/generate_pcb_pwr_vbat_raw_routing_003_candidate_rev_a.py"
ROUTING_RULES = ROOT / "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv"
STACKUP_BASIS = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"

BASE_SHA256 = "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5"
CANDIDATE_SHA256 = "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3"
BASE_SEMANTIC_SHA256 = "07ce41bb361e68dd3a5310a6879030f097e4498e9397f2506ea5b78f49c47234"
CANDIDATE_SEMANTIC_SHA256 = "4472097781d9dc58231a14c0fea67ad102e2e25b1e9e05e98481e7d6d3f3a93d"
GENERATOR_SHA256 = "b7a73f836ddbb74b7115f50a743d18bc98ac44ee1e5270eafd0cbc23f3ea7eaa"
ACTIVE_GENERATOR_SHA256 = "84a426f84789b5be5a0db64180e8689bc8ac14543d7fb844e7e91575239eed61"
REV_GATE_GENERATOR_SHA256 = "9721b1ecd9e0991a4f820aaf6c39e4bb90bcb493546a6b2a4dbe9c4b469c99d4"
ROUTING_RULES_SHA256 = "551a9691d51fd9451bf60193d79b8ed244d6b61fd5ec9c844a15050710f48988"
STACKUP_BASIS_SHA256 = "dbb41a7fb0ee5eea01f7bbebaa542061d1c9d7b102c0cb4a912a974b03ab3dc3"
ACTIVE_STACKUP_BASIS_SHA256 = "300c2c6998704fae554c6f30ddb7bcb6eabb2060973c90f2b1d2ecc4ab76b1fc"
REV_GATE_SUCCESSOR_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
REV_GATE_STACKUP_BASIS_SHA256 = "78ea37897803675337612eedbdcaf3922b53fbe2330cb8f12f09f48412b26531"
EXPECTED_START = (7.7, 31.25)
EXPECTED_END = (10.6, 31.25)


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
    require(not (candidate_fp - base_fp), "candidate introduces DRC fingerprints")
    require(not (base_fp - candidate_fp), "candidate removes unrelated DRC fingerprints")
    require(candidate_violations == base_violations, "candidate changes violation count")
    require(candidate_unconnected == base_unconnected - 1,
            "candidate must close exactly one unconnected item")
    return {
        "status": "PASS_ZERO_NEW_DRC_EXACT_ONE_CONNECTION_REDUCTION",
        "base_violations": base_violations,
        "candidate_violations": candidate_violations,
        "base_unconnected": base_unconnected,
        "candidate_unconnected": candidate_unconnected,
        "new_drc_fingerprints": 0,
        "removed_drc_fingerprints": 0,
    }


def audit(drc_base: Path | None = None, drc_candidate: Path | None = None) -> dict[str, object]:
    require(sha256(BASE) == BASE_SHA256 and
            sha256(ACTIVE) in {
                BASE_SHA256, CANDIDATE_SHA256, REV_GATE_SUCCESSOR_SHA256},
            "candidate-003 base or controlled authoritative board drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "candidate-003 SHA-256 drift")
    require(sha256(GENERATOR) in {
                GENERATOR_SHA256,
                ACTIVE_GENERATOR_SHA256,
                REV_GATE_GENERATOR_SHA256,
            } and
            sha256(ROUTING_RULES) == ROUTING_RULES_SHA256 and
            sha256(STACKUP_BASIS) in {
                STACKUP_BASIS_SHA256,
                ACTIVE_STACKUP_BASIS_SHA256,
                REV_GATE_STACKUP_BASIS_SHA256,
            },
            "candidate-003 source binding drift")
    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    require(semantic_board_sha256(base) == BASE_SEMANTIC_SHA256 and
            semantic_board_sha256(candidate) == CANDIDATE_SEMANTIC_SHA256,
            "candidate-003 semantic identity drift")
    require(len(base.traceItems) == 3 and len(candidate.traceItems) == 4 and
            len(base.zones) == len(candidate.zones) == 0,
            "candidate-003 copper inventory drift")
    require(candidate.traceItems[:3] == base.traceItems,
            "candidate-003 modifies accepted predecessor copper")
    net_names = {int(net.number): str(net.name) for net in candidate.nets}
    item = candidate.traceItems[-1]
    start = (float(item.start.X), float(item.start.Y))
    end = (float(item.end.X), float(item.end.Y))
    require(net_names[int(item.net)] == "VBAT_RAW" and
            str(item.layer) == "F.Cu" and float(item.width) == 4.0 and
            start == EXPECTED_START and end == EXPECTED_END and
            math.isclose(math.dist(start, end), 2.9, abs_tol=1e-6),
            "candidate-003 segment identity or geometry drift")
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    require(
        review["creation_authorization"] ==
        "ACCEPT_PCB_PWR_ROUTING_CANDIDATE_003_CREATION_SUBGATE"
        and review["candidate"]["sha256"] == CANDIDATE_SHA256
        and review["source_binding"]["generator_sha256"] == GENERATOR_SHA256
        and review["deferred_boundary"]["narrow_substitution_authorized"] is False
        and review["invariants"]["authoritative_board_modified"] is False
        and review["machine_gate"]["status"] in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_COMPARATIVE_DRC",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_COMPARATIVE_DRC",
        }
        and review["routing_complete"] is False
        and review["review_b_complete"] is False
        and review["cam_or_manufacturing_release"] is False,
        "candidate-003 proposal boundary drift",
    )
    report: dict[str, object] = {
        "status": "PASS_STATIC_PCB_PWR_VBAT_RAW_ROUTING_003_CANDIDATE",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "routed_nets": ["VBAT_RAW"],
        "trace_items": 4,
        "added_trace_items": 1,
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
    print("PCB-PWR VBAT_RAW routing 003 candidate audit:", report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
