#!/usr/bin/env python3
"""Audit the isolated PCB-MAIN P0 RF-routing proposal."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from kiutils.board import Board


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-RF-P0-001"
    / "PCB-MAIN_RF_P0_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-RF-P0-001"
    / "PCB-MAIN_RF_P0_CANDIDATE_REV_A.kicad_pcb"
)
ACTIVE = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
GENERATOR = ROOT / "tools/generate_pcb_main_rf_p0_candidate_rev_a.py"
PROPOSAL = ROOT / "hardware/reviews/PCB_MAIN_RF_P0_ROUTING_CANDIDATE_REV_A.json"
BASE_SHA256 = "04a0c7e37068d00fbe53b48fd19063b015b6b5c04e9aaafb3b01bbced0d7a99f"
CANDIDATE_SHA256 = "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
GENERATOR_SHA256 = "fe2051d54444d961cf3106b9a0b7862b3a929179c27d07fcd40232952ca2991a"
RF_WIDTH_MM = 0.1509
EXPECTED = {
    "CELL_RF": (38, 33.067387862532),
    "CELL_RF_ANT": (37, 18.436106588963),
    "GNSS_RF_ANT_BIASED": (17, 10.205266952966),
    "GNSS_RF_DC_BLOCK": (1, 1.000000000000),
    "GNSS_RF_FILTERED": (6, 25.325357133747),
    "LORA_RF_ANT": (26, 14.538138937276),
    "LORA_RF_MODULE": (13, 9.035535027254),
}
EXPECTED_CONNECTIVITY = (
    {"base": 697, "candidate": 682},  # KiCad 7 local pcbnew
    {"base": 444, "candidate": 429},  # KiCad 9 after deterministic zone refill
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trace_uuid(item: object) -> str:
    return str(item.tstamp)


def drc_counts(path: Path) -> tuple[Counter[str], int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = Counter(
        item.get("type", "UNKNOWN")
        for item in data.get("violations", [])
        if item.get("severity") == "error"
    )
    return errors, len(data.get("unconnected_items", []))


def audit_drc(base_path: Path, candidate_path: Path) -> dict[str, object]:
    base_errors, base_unconnected = drc_counts(base_path)
    candidate_errors, candidate_unconnected = drc_counts(candidate_path)
    added = {
        key: candidate_errors[key] - base_errors[key]
        for key in candidate_errors
        if candidate_errors[key] > base_errors[key]
    }
    require(not added, f"RF candidate introduces KiCad DRC errors: {added}")
    require(base_unconnected - candidate_unconnected == 15,
            "RF candidate does not close exactly 15 unconnected items")
    return {
        "status": "PASS_NO_NEW_KICAD9_DRC_ERRORS",
        "base_unconnected_items": base_unconnected,
        "candidate_unconnected_items": candidate_unconnected,
        "reduction": base_unconnected - candidate_unconnected,
        "new_error_counts": added,
    }


def native_connectivity(base_path: Path, candidate_path: Path) -> dict[str, object]:
    import pcbnew  # type: ignore

    counts: dict[str, int] = {}
    for label, path in (("base", base_path), ("candidate", candidate_path)):
        board = pcbnew.LoadBoard(str(path))
        board.BuildListOfNets()
        board.BuildConnectivity()
        counts[label] = int(board.GetConnectivity().GetUnconnectedCount(False))
    require(counts in EXPECTED_CONNECTIVITY and
            counts["base"] - counts["candidate"] == 15,
            f"RF candidate connectivity drift: {counts}")
    return {"status": "PASS_EXACT_15_CONNECTION_REDUCTION", **counts}


def static_audit() -> dict[str, object]:
    require(sha256(BASE) == BASE_SHA256, "RF base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "RF candidate SHA-256 drift")
    require(sha256(GENERATOR) == GENERATOR_SHA256, "RF generator SHA-256 drift")
    require(sha256(ACTIVE) == BASE_SHA256 and ACTIVE.read_bytes() == BASE.read_bytes(),
            "authoritative PCB-MAIN is not the exact accepted RF base")

    base = Board().from_file(str(BASE), encoding="utf-8")
    candidate = Board().from_file(str(CANDIDATE), encoding="utf-8")
    for field in (
        "general", "layers", "setup", "properties", "graphicItems",
        "dimensions", "groups", "targets", "nets", "footprints", "zones",
    ):
        require(getattr(base, field) == getattr(candidate, field),
                f"RF candidate changes non-routing field: {field}")

    base_uuids = [trace_uuid(item) for item in base.traceItems]
    candidate_uuids = [trace_uuid(item) for item in candidate.traceItems]
    require(len(base_uuids) == len(set(base_uuids)), "RF base has duplicate copper UUIDs")
    require(len(candidate_uuids) == len(set(candidate_uuids)),
            "RF candidate has duplicate copper UUIDs")
    base_items = {trace_uuid(item): item for item in base.traceItems}
    candidate_items = {trace_uuid(item): item for item in candidate.traceItems}
    require(set(base_items) <= set(candidate_items), "RF candidate removes accepted copper")
    require(all(base_items[key] == candidate_items[key] for key in base_items),
            "RF candidate modifies accepted copper")
    added = [candidate_items[key] for key in set(candidate_items) - set(base_items)]

    names = {int(net.number): net.name for net in candidate.nets}
    segments: Counter[str] = Counter()
    lengths: defaultdict[str, float] = defaultdict(float)
    for item in added:
        name = names[int(item.net)]
        require(name in EXPECTED, f"out-of-scope RF copper added on {name}")
        require(type(item).__name__ == "Segment", f"{name}: RF signal via is prohibited")
        require(item.layer == "F.Cu", f"{name}: RF route leaves F.Cu")
        require(math.isclose(float(item.width), RF_WIDTH_MM, abs_tol=1e-9),
                f"{name}: RF width drift")
        segments[name] += 1
        lengths[name] += math.hypot(
            float(item.end.X) - float(item.start.X),
            float(item.end.Y) - float(item.start.Y),
        )
    require(len(added) == 138 and sum(segments.values()) == 138,
            "RF added-copper inventory drift")
    for name, (expected_segments, expected_length) in EXPECTED.items():
        require(segments[name] == expected_segments, f"{name}: segment-count drift")
        require(math.isclose(lengths[name], expected_length, abs_tol=1e-6),
                f"{name}: route-length drift")

    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    machine_gate = proposal.get("commit_bound_machine_gate", {})
    comparative_drc = proposal.get("comparative_kicad9_drc", {})
    require(proposal.get("candidate_id") == "PCB-MAIN-RF-P0-001" and
            proposal.get("base_board_sha256") == BASE_SHA256 and
            proposal.get("candidate_board_sha256") == CANDIDATE_SHA256 and
            proposal.get("status") ==
            "PROPOSAL_KICAD9_COMPARATIVE_DRC_PASS_PENDING_HUMAN_REVIEW" and
            proposal.get("applied_to_authoritative_board") is False and
            proposal.get("review_b_complete") is False and
            proposal.get("cam_or_manufacturing_release") is False,
            "RF proposal identity or release boundary drift")
    require(machine_gate == {
        "head_commit_sha": "06ba3959abf71c40e78731f9b0f6beb12e04a1e7",
        "head_tree_sha": "7d85b7b20a698d3f94f559060e683061fdd7fe3e",
        "pcb_native_run_id": 35503166684,
        "pcb_native_run_number": 261,
        "pcb_native_conclusion": "success",
        "comparative_drc_step": "success",
        "ci_run_id": 35503166719,
        "ci_run_number": 533,
        "ci_conclusion": "success",
        "artifact_id": 10602564959,
        "artifact_name": "evt-pre-20-kicad-native-gate",
    }, "RF commit-bound machine-gate evidence drift")
    require(comparative_drc == {
        "status": "PASS_NO_NEW_KICAD9_DRC_ERRORS",
        "base_violations": 226,
        "candidate_violations": 226,
        "base_errors": 0,
        "candidate_errors": 0,
        "base_unconnected_items": 444,
        "candidate_unconnected_items": 429,
        "reduction": 15,
        "new_error_counts": {},
        "baseline_drc_sha256":
            "dc1c628e44d15893c9ca6af0da864a4721691d95f1d6b7236f32e8ff2ed0c54e",
        "candidate_drc_sha256":
            "79130958c0fa2d69724a60528263cf86d90ba92d28eb9271c0ae1b350060d9ff",
        "comparative_audit_sha256":
            "a489451be7ca4023fdf36d6b3ec4ebd0add47e13b73a366d706425f24a65ddd7",
    }, "RF comparative KiCad 9 evidence drift")
    return {
        "schema_version": "dioneya.pcb-main-rf-p0-candidate-audit.v1",
        "status": "PASS_STATIC_CANDIDATE_ISOLATION_MACHINE_EVIDENCE_BOUND",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "generator_sha256": GENERATOR_SHA256,
        "routed_nets": sorted(EXPECTED),
        "added_segments": 138,
        "added_vias": 0,
        "added_track_length_mm": sum(lengths.values()),
        "rf_width_mm": RF_WIDTH_MM,
        "applied_to_authoritative_board": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-candidate", type=Path)
    parser.add_argument("--connectivity-base", type=Path)
    parser.add_argument("--connectivity-candidate", type=Path)
    args = parser.parse_args()
    report = static_audit()
    if args.drc_base or args.drc_candidate:
        require(bool(args.drc_base and args.drc_candidate),
                "both DRC reports are required")
        report["comparative_drc"] = audit_drc(args.drc_base, args.drc_candidate)
    if args.connectivity_base or args.connectivity_candidate:
        require(bool(args.connectivity_base and args.connectivity_candidate),
                "both connectivity boards are required")
        report["native_connectivity"] = native_connectivity(
            args.connectivity_base, args.connectivity_candidate
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("PCB-MAIN P0 RF candidate audit: PASS")
    print("routed_nets=7 added_segments=138 added_vias=0 width_mm=0.1509")
    print("release_boundary=PENDING_HUMAN_RF_SI_RETURN_PATH_REVIEW_AND_REVIEW_B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
