#!/usr/bin/env python3
"""Independent scope, geometry and comparative DRC audit for PCB-PWR 007."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from kiutils.board import Board

from audit_pcb_pwr_buck_input_hot_loop_routing_006_candidate_rev_a import (
    copper_clearance_screen,
    drc_inventory,
    point,
)
from audit_pcb_pwr_routing_authority_rev_a import ref_of, semantic_board_sha256
from generate_pcb_pwr_vbat_sys_shunt_bulk_routing_007_candidate_rev_a import (
    BASE,
    BASE_SHA256,
    CANDIDATE,
    ROOT,
    ROUTES,
    SOURCE,
    generate,
)

REVIEW = ROOT / "hardware/reviews/PCB_PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_CANDIDATE_REV_A.json"
ROUTE_RULES = ROOT / "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv"
ROUTE_RULES_SHA256 = "551a9691d51fd9451bf60193d79b8ed244d6b61fd5ec9c844a15050710f48988"
STACKUP = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"
STACKUP_SHA256 = "c417669cab385eb702c53a1912ad5973bda3ca0fec8cbc5c3e331a511178afad"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparative_drc(base_path: Path, candidate_path: Path) -> dict:
    base_fp, base_violations, base_unconnected = drc_inventory(base_path)
    candidate_fp, candidate_violations, candidate_unconnected = drc_inventory(candidate_path)
    assert base_violations == candidate_violations == 85, "DRC violations changed"
    assert base_fp == candidate_fp, "DRC severity/type inventory changed"
    assert base_unconnected == 108, "authoritative predecessor unconnected count drift"
    assert 0 <= candidate_unconnected < base_unconnected, "candidate does not improve connectivity"
    return {
        "status": "PASS_NO_DRC_FINGERPRINT_DELTA_UNCONNECTED_REDUCED",
        "violations": [base_violations, candidate_violations],
        "unconnected": [base_unconnected, candidate_unconnected],
        "new_drc_fingerprints": 0,
    }


def audit(drc_base: Path | None = None, drc_candidate: Path | None = None) -> dict:
    assert digest(SOURCE) == digest(BASE) == BASE_SHA256
    generated = generate(check=True)
    assert digest(ROUTE_RULES) == ROUTE_RULES_SHA256
    assert digest(STACKUP) == STACKUP_SHA256
    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    assert len(base.traceItems) == 35 and len(candidate.traceItems) == 37
    assert candidate.traceItems[:35] == base.traceItems
    assert candidate.zones == base.zones and len(candidate.zones) == 2
    assert candidate.footprints == base.footprints and len(base.footprints) == 66
    assert candidate.nets == base.nets
    net_names = {int(n.number): n.name for n in candidate.nets}
    added = candidate.traceItems[35:]
    for item, (start, end, width) in zip(added, ROUTES, strict=True):
        assert type(item).__name__ == "Segment"
        assert net_names[int(item.net)] == "VBAT_SYS" and str(item.layer) == "F.Cu"
        assert point(item.start) == start and point(item.end) == end
        assert math.isclose(float(item.width), width, abs_tol=1e-9)

    # The two tracks touch both intended power pads but leave the separate
    # Kelvin contact unconnected. Check the pad IDs and measured geometry.
    pads = {(ref_of(f), str(p.number)): p for f in candidate.footprints for p in f.pads}
    for key in (("RSH1", "2"), ("C13", "1")):
        assert pads[key].net.name == "VBAT_SYS"
    assert pads[("RSH1", "4")].net.name == "SHUNT_LOAD_SENSE"
    from audit_pcb_pwr_buck_input_hot_loop_routing_006_candidate_rev_a import pad_rectangle
    footprints = {ref_of(f): f for f in candidate.footprints}
    for ref, pad_number, anchor in (("RSH1", "2", ROUTES[0][0]),
                                     ("C13", "1", ROUTES[-1][1])):
        xmin, ymin, xmax, ymax = pad_rectangle(footprints[ref], pads[(ref, pad_number)])
        assert xmin <= anchor[0] <= xmax and ymin <= anchor[1] <= ymax
    clearance = copper_clearance_screen(base, candidate, added, [])
    assert clearance["minimum_edge_clearance_mm"] >= 0.3

    # Conservative one-way shunt-to-bulk copper drop, with copper at the
    # lower-bound 35 um and resistivity at +70 C. Thermal/crowding is unproven.
    rho_70 = 2.062766e-8
    resistance = sum(rho_70 * (math.dist(start, end) * 0.001)
                     / ((width * 0.001) * 35e-6) for start, end, width in ROUTES)
    assert resistance * 5 < 0.05
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    assert review["base_sha256"] == BASE_SHA256
    assert review["candidate_sha256"] == generated["candidate_sha256"]
    assert review["route_rules_sha256"] == ROUTE_RULES_SHA256
    assert review["stackup_sha256"] == STACKUP_SHA256
    assert review["authoritative_board_modified"] is False
    assert review["manufacturing_release"] is False
    assert review["application_authorized"] is False
    result = {
        "status": "PASS_STATIC_PCB_PWR_VBAT_SYS_SHUNT_BULK_ROUTING_007_CANDIDATE",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": generated["candidate_sha256"],
        "base_semantic_sha256": semantic_board_sha256(base),
        "candidate_semantic_sha256": semantic_board_sha256(candidate),
        "added_segments": 2,
        "copper_clearance_screen": clearance,
        "one_way_drop_5a_70c_35um_mv": round(resistance * 5000, 6),
        "authoritative_board_modified": False,
        "routing_complete": False,
        "manufacturing_release": False,
    }
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
    print("PCB-PWR shunt-bulk 007 candidate:", report["status"])
