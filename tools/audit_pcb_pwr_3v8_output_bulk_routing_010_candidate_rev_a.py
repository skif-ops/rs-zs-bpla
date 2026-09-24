#!/usr/bin/env python3
"""Audit the isolated PCB-PWR 3V8 output bulk routing candidate 010."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from kiutils.board import Board

from audit_pcb_pwr_buck_input_hot_loop_routing_006_candidate_rev_a import (
    copper_clearance_screen, drc_inventory, pad_rectangle, point,
)
from audit_pcb_pwr_routing_authority_rev_a import ref_of, semantic_board_sha256
from generate_pcb_pwr_3v8_output_bulk_routing_010_candidate_rev_a import (
    BASE, BASE_SHA256, CANDIDATE, ROOT, ROUTES, SOURCE, generate,
)

REVIEW = ROOT / "hardware/reviews/PCB_PWR_3V8_OUTPUT_BULK_ROUTING_010_CANDIDATE_REV_A.json"
CANDIDATE_SHA256 = "e46097f868a04bea0145c9cb10dac3d94ce2a81cee063224eb7840bffbceb469"
CANDIDATE_SEMANTIC_SHA256 = "d6810b6ea293bfd931f09e73ff64698d18d0a64b465db7b71c712f64a36b2980"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparative_drc(base_path: Path, candidate_path: Path) -> dict:
    base_fp, base_v, base_u = drc_inventory(base_path)
    candidate_fp, candidate_v, candidate_u = drc_inventory(candidate_path)
    assert candidate_fp == base_fp
    assert candidate_v == base_v
    assert candidate_u < base_u
    return {"status": "PASS_NO_DRC_FINGERPRINT_DELTA_UNCONNECTED_REDUCED",
            "violations": [base_v, candidate_v], "unconnected": [base_u, candidate_u],
            "new_drc_fingerprints": 0}


def audit(drc_base: Path | None = None, drc_candidate: Path | None = None) -> dict:
    assert digest(SOURCE) == digest(BASE) == BASE_SHA256
    assert digest(CANDIDATE) == CANDIDATE_SHA256
    generate(check=True)
    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    assert len(base.traceItems) == 43 and len(candidate.traceItems) == 53
    assert candidate.traceItems[:43] == base.traceItems
    assert candidate.zones == base.zones and len(candidate.zones) == 2
    assert candidate.footprints == base.footprints and len(base.footprints) == 66
    assert candidate.nets == base.nets
    assert semantic_board_sha256(candidate) == CANDIDATE_SEMANTIC_SHA256
    net_names = {int(net.number): net.name for net in candidate.nets}
    added = candidate.traceItems[43:]
    for item, (start, end, width) in zip(added, ROUTES, strict=True):
        assert type(item).__name__ == "Segment"
        assert net_names[int(item.net)] == "3V8_MODEM" and str(item.layer) == "F.Cu"
        assert point(item.start) == start and point(item.end) == end
        assert math.isclose(float(item.width), width, abs_tol=1e-9)
    pads = {(ref_of(f), str(p.number)): p for f in candidate.footprints for p in f.pads}
    footprints = {ref_of(f): f for f in candidate.footprints}
    for ref, pad_number in (("L1", "2"), ("C3", "1"), ("C14", "1"), ("C15", "1"), ("C16", "1")):
        pad = pads[(ref, pad_number)]
        assert pad.net.name == "3V8_MODEM"
        assert pad_rectangle(footprints[ref], pad)
    clearance = copper_clearance_screen(base, candidate, added, [])
    assert math.isclose(clearance["minimum_edge_clearance_mm"], 0.35, abs_tol=1e-6)
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    assert review["candidate"]["sha256"] == CANDIDATE_SHA256
    assert review["deferred_boundary"]["application_authorized"] is False
    assert review["routing_complete"] is review["review_b_complete"] is review["manufacturing_release"] is False
    result = {"status": "PASS_STATIC_PCB_PWR_3V8_OUTPUT_BULK_ROUTING_010_CANDIDATE",
              "base_sha256": BASE_SHA256, "candidate_sha256": CANDIDATE_SHA256,
              "candidate_semantic_sha256": CANDIDATE_SEMANTIC_SHA256,
              "added_segments": 10, "copper_clearance_screen": clearance,
              "authoritative_board_modified": False, "routing_complete": False,
              "manufacturing_release": False}
    assert (drc_base is None) == (drc_candidate is None)
    if drc_base is not None:
        result["comparative_drc"] = comparative_drc(drc_base, drc_candidate)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.drc_base, args.drc_candidate)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR 3V8 output bulk 010 candidate:", report["status"])
