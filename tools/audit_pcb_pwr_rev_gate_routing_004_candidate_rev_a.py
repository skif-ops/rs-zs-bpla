#!/usr/bin/env python3
"""Audit PCB-PWR REV_GATE routing candidate 004."""

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
BASE = ROOT / "hardware/kicad/candidates/PCB-PWR-REV-GATE-ROUTING-004/PCB-PWR_REV_GATE_ROUTING_004_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-PWR-REV-GATE-ROUTING-004/PCB-PWR_REV_GATE_ROUTING_004_CANDIDATE_REV_A.kicad_pcb"
ACTIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
REVIEW = ROOT / "hardware/reviews/PCB_PWR_REV_GATE_ROUTING_004_CANDIDATE_REV_A.json"
GENERATOR = ROOT / "tools/generate_pcb_pwr_rev_gate_routing_004_candidate_rev_a.py"
ROUTING_RULES = ROOT / "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv"
STACKUP_BASIS = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"

BASE_SHA256 = "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3"
CANDIDATE_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
BASE_SEMANTIC_SHA256 = "4472097781d9dc58231a14c0fea67ad102e2e25b1e9e05e98481e7d6d3f3a93d"
CANDIDATE_SEMANTIC_SHA256 = "f7a659d0740e78d40eddae7016724bd8e616baf9fb425f06ace70ec9acca4d3d"
GENERATOR_SHA256 = "09bf8fad5220447de78cba70e2ebf5786089fc29e89ff2dfe001ba7826b6af36"
ACTIVE_GENERATOR_SHA256 = "eabf8aca015bb48447b211649cc26b7bc454a9560e6e1e59c906fc91645796f2"
ROUTING_RULES_SHA256 = "551a9691d51fd9451bf60193d79b8ed244d6b61fd5ec9c844a15050710f48988"
STACKUP_BASIS_SHA256 = "300c2c6998704fae554c6f30ddb7bcb6eabb2060973c90f2b1d2ecc4ab76b1fc"
ACTIVE_STACKUP_BASIS_SHA256 = "78ea37897803675337612eedbdcaf3922b53fbe2330cb8f12f09f48412b26531"
ENGINEERING_BASELINE_STACKUP_BASIS_SHA256 = "41733d7d27e2c3ab831e602ee81b072146944da0a5efe8a2c805eeed46ecd1ca"
EXPECTED_POINTS = (
    (21.3, 30.0),
    (22.6, 30.0),
    (22.6, 27.0),
    (29.77, 27.0),
    (29.77, 28.095),
)


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


def audit(drc_base: Path | None = None,
          drc_candidate: Path | None = None) -> dict[str, object]:
    require(sha256(BASE) == BASE_SHA256 and
            sha256(ACTIVE) in {BASE_SHA256, CANDIDATE_SHA256},
            "candidate-004 base or controlled authoritative board drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "candidate-004 SHA-256 drift")
    require(sha256(GENERATOR) in {GENERATOR_SHA256, ACTIVE_GENERATOR_SHA256} and
            sha256(ROUTING_RULES) == ROUTING_RULES_SHA256 and
            sha256(STACKUP_BASIS) in {
                STACKUP_BASIS_SHA256,
                ACTIVE_STACKUP_BASIS_SHA256,
                ENGINEERING_BASELINE_STACKUP_BASIS_SHA256,
            },
            "candidate-004 source binding drift")
    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    require(semantic_board_sha256(base) == BASE_SEMANTIC_SHA256 and
            semantic_board_sha256(candidate) == CANDIDATE_SEMANTIC_SHA256,
            "candidate-004 semantic identity drift")
    require(len(base.traceItems) == 4 and len(candidate.traceItems) == 8 and
            len(base.zones) == len(candidate.zones) == 0,
            "candidate-004 copper inventory drift")
    require(candidate.traceItems[:4] == base.traceItems,
            "candidate-004 modifies accepted predecessor copper")
    net_names = {int(net.number): str(net.name) for net in candidate.nets}
    added = candidate.traceItems[4:]
    route_length = 0.0
    for index, item in enumerate(added):
        start = (float(item.start.X), float(item.start.Y))
        end = (float(item.end.X), float(item.end.Y))
        require(net_names[int(item.net)] == "REV_GATE" and
                str(item.layer) == "F.Cu" and float(item.width) == 0.5 and
                start == EXPECTED_POINTS[index] and
                end == EXPECTED_POINTS[index + 1],
                f"candidate-004 segment {index + 1} identity or geometry drift")
        route_length += math.dist(start, end)
    require(math.isclose(route_length, 12.565, abs_tol=1e-6),
            "candidate-004 route length drift")
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    require(
        review["creation_authorization"] ==
        "ACCEPT_PCB_PWR_ROUTING_CANDIDATE_004_CREATION_SUBGATE"
        and review["candidate"]["sha256"] == CANDIDATE_SHA256
        and review["source_binding"]["generator_sha256"] == GENERATOR_SHA256
        and review["deferred_boundary"]["application_authorized"] is False
        and review["invariants"]["authoritative_board_modified"] is False
        and review["machine_gate"]["status"] in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_COMPARATIVE_DRC",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_COMPARATIVE_DRC",
        }
        and review["routing_complete"] is False
        and review["review_b_complete"] is False
        and review["cam_or_manufacturing_release"] is False,
        "candidate-004 proposal boundary drift",
    )
    report: dict[str, object] = {
        "status": "PASS_STATIC_PCB_PWR_REV_GATE_ROUTING_004_CANDIDATE",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "routed_nets": ["REV_GATE"],
        "connections": ["U1.5-Q1.4"],
        "trace_items": 8,
        "added_trace_items": 4,
        "route_length_mm": route_length,
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
    print("PCB-PWR REV_GATE routing 004 candidate audit:", report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
