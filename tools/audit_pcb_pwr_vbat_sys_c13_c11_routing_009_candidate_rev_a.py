#!/usr/bin/env python3
"""Independent scope, geometry and comparative DRC audit for PCB-PWR 009."""

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
from generate_pcb_pwr_vbat_sys_c13_c11_routing_009_candidate_rev_a import (
    BASE, BASE_SHA256, CANDIDATE, ROOT, ROUTES, SOURCE, generate,
)

REVIEW = ROOT / "hardware/reviews/PCB_PWR_VBAT_SYS_C13_C11_ROUTING_009_CANDIDATE_REV_A.json"
CANDIDATE_SHA256 = "9ad58d135bedfccc2acc59dfe6480f76730aa10bf3f526e9c3807159a06846bf"
CANDIDATE_SEMANTIC_SHA256 = "047dca85bb31d926bbd2228c985aa0a1c318b266fa8d68762613a9eec80f9550"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparative_drc(base_path: Path, candidate_path: Path) -> dict:
    base_fp, base_v, base_u = drc_inventory(base_path)
    candidate_fp, candidate_v, candidate_u = drc_inventory(candidate_path)
    assert base_v == candidate_v == 85
    assert base_fp == candidate_fp
    assert [base_u, candidate_u] == [106, 105]
    return {"status": "PASS_NO_DRC_FINGERPRINT_DELTA_UNCONNECTED_106_TO_105",
            "violations": [base_v, candidate_v], "unconnected": [base_u, candidate_u],
            "new_drc_fingerprints": 0}


def audit(drc_base: Path | None = None, drc_candidate: Path | None = None) -> dict:
    assert digest(SOURCE) == digest(BASE) == BASE_SHA256
    assert digest(CANDIDATE) == CANDIDATE_SHA256
    generate(check=True)
    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    assert len(base.traceItems) == 39 and len(candidate.traceItems) == 43
    assert candidate.traceItems[:39] == base.traceItems
    assert candidate.zones == base.zones and len(candidate.zones) == 2
    assert candidate.footprints == base.footprints and len(base.footprints) == 66
    assert candidate.nets == base.nets
    assert semantic_board_sha256(candidate) == CANDIDATE_SEMANTIC_SHA256
    net_names = {int(net.number): net.name for net in candidate.nets}
    added = candidate.traceItems[39:]
    for item, (start, end, width) in zip(added, ROUTES, strict=True):
        assert type(item).__name__ == "Segment"
        assert net_names[int(item.net)] == "VBAT_SYS" and str(item.layer) == "F.Cu"
        assert point(item.start) == start and point(item.end) == end
        assert math.isclose(float(item.width), width, abs_tol=1e-9)
    pads = {(ref_of(f), str(p.number)): p for f in candidate.footprints for p in f.pads}
    footprints = {ref_of(f): f for f in candidate.footprints}
    for ref, anchor in (("C13", ROUTES[0][0]), ("C11", ROUTES[-1][1])):
        pad = pads[(ref, "1")]
        assert pad.net.name == "VBAT_SYS"
        xmin, ymin, xmax, ymax = pad_rectangle(footprints[ref], pad)
        assert xmin <= anchor[0] <= xmax and ymin <= anchor[1] <= ymax
    clearance = copper_clearance_screen(base, candidate, added, [])
    assert math.isclose(clearance["minimum_edge_clearance_mm"], 0.575, abs_tol=1e-6)
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    assert review["base"]["sha256"] == BASE_SHA256
    assert review["candidate"]["sha256"] == CANDIDATE_SHA256
    assert review["candidate"]["semantic_sha256"] == CANDIDATE_SEMANTIC_SHA256
    assert review["deferred_boundary"]["application_authorized"] is False
    assert review["routing_complete"] is review["review_b_complete"] is review["manufacturing_release"] is False
    gate = review["machine_gate"]
    assert gate["status"] in {"PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_COMPARATIVE_DRC",
                              "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_COMPARATIVE_DRC"}
    if gate["status"].startswith("PASS_"):
        assert gate["candidate_source_commit_sha"] == "88121e99401c09ad37694cbfc7bee1473e4519a8"
        assert gate["candidate_source_tree_sha"] == "56337e9cdf4ec7e4f36246c1a2ed68d998fcfc08"
        assert gate["ci_run_number"] == 740 and gate["ci_run_id"] == 35979002894
        assert gate["pcb_pwr_schematic_run_number"] == 117 and gate["pcb_pwr_schematic_run_id"] == 35979002978
        assert gate["pcb_native_run_number"] == 379 and gate["pcb_native_run_id"] == 35979002864
        assert gate["pcb_native_job_id"] == 107566153325
        assert gate["artifact_id"] == 10799132722
        assert gate["artifact_digest"] == "sha256:5b8bb71eabfeb4503a89cd294beaa428318196368420609247dfa3a0d28cbcc8"
        assert gate["comparative_drc"] == "PASS_85_TO_85_VIOLATIONS_106_TO_105_UNCONNECTED_ZERO_DRC_FINGERPRINT_DELTA"
    result = {"status": "PASS_STATIC_PCB_PWR_VBAT_SYS_C13_C11_ROUTING_009_CANDIDATE",
              "base_sha256": BASE_SHA256, "candidate_sha256": CANDIDATE_SHA256,
              "candidate_semantic_sha256": CANDIDATE_SEMANTIC_SHA256,
              "added_segments": 4, "copper_clearance_screen": clearance,
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
    print("PCB-PWR C13-to-C11 009 candidate:", report["status"])
