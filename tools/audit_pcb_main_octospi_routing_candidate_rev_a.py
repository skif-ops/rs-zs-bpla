#!/usr/bin/env python3
"""Audit the bounded PCB-MAIN OctoSPI routing proposal."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from kiutils.board import Board

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "hardware/kicad/candidates/PCB-MAIN-OCTOSPI-ROUTING-001/PCB-MAIN_OCTOSPI_BASE_REV_A.kicad_pcb"
CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-MAIN-OCTOSPI-ROUTING-001/PCB-MAIN_OCTOSPI_CANDIDATE_REV_A.kicad_pcb"
PROPOSAL = ROOT / "hardware/reviews/PCB_MAIN_OCTOSPI_ROUTING_CANDIDATE_REV_A.json"
ROUTER = ROOT / "tools/route_pcb_release_candidate_rev_a.py"
BASE_SHA256 = "7dea2fdce607dbf7df2205e74b188d45e2def07c5329bacb4f9503ddcf7ae6f3"
CANDIDATE_SHA256 = "758c9bfdf2d91a7dd4f69f00b94ac7d7cccff15f1415c6c72e68d5604ee67193"
ROUTER_SHA256 = "ee645376472edfe093447b306c6c85f68f2963ae2a0833a82060f7e7dd225a9b"
EXPECTED = {
    "NOR_CLK_U1": (7, 2), "NOR_CLK_U2": (6, 2),
    "NOR_IO0_U1": (14, 2), "NOR_IO0_U2": (13, 2),
    "NOR_IO1_U1": (15, 2), "NOR_IO1_U2": (8, 3),
    "NOR_IO2_U1": (12, 3), "NOR_IO2_U2": (17, 2),
    "NOR_IO3_U1": (9, 2), "NOR_IO3_U2": (9, 3),
    "NOR_NCS_U2": (11, 2),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drc_counts(path: Path) -> tuple[Counter[str], int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = Counter(
        item.get("type", "UNKNOWN") for item in data.get("violations", [])
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
    require(not added, f"candidate introduces KiCad DRC errors: {added}")
    require(candidate_unconnected <= base_unconnected,
            "candidate increases KiCad unconnected-item count")
    return {
        "status": "PASS_NO_NEW_KICAD9_DRC_ERRORS",
        "base_unconnected_items": base_unconnected,
        "candidate_unconnected_items": candidate_unconnected,
        "new_error_counts": added,
    }


def native_connectivity(base_path: Path, candidate_path: Path) -> dict[str, object]:
    import pcbnew  # type: ignore
    counts = {}
    for label, path in (("base", base_path), ("candidate", candidate_path)):
        board = pcbnew.LoadBoard(str(path))
        board.BuildListOfNets()
        board.BuildConnectivity()
        counts[label] = int(board.GetConnectivity().GetUnconnectedCount(False))
    require(counts == {"base": 707, "candidate": 697},
            f"native connectivity drift: {counts}")
    return {"status": "PASS_EXACT_10_CONNECTION_REDUCTION", **counts}


def static_audit() -> dict[str, object]:
    require(sha256(BASE) == BASE_SHA256, "OctoSPI base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "OctoSPI candidate SHA-256 drift")
    require(sha256(ROUTER) == ROUTER_SHA256, "routing generator SHA-256 drift")
    base = Board().from_file(str(BASE))
    candidate = Board().from_file(str(CANDIDATE))
    for field in (
        "version", "generator", "general", "paper", "titleBlock", "layers",
        "setup", "properties", "nets", "footprints", "graphicItems", "zones",
        "groups", "dimensions", "targets",
    ):
        require(getattr(base, field) == getattr(candidate, field),
                f"non-routing field changed: {field}")

    base_items = {str(item.tstamp): item for item in base.traceItems}
    candidate_items = {str(item.tstamp): item for item in candidate.traceItems}
    require(set(base_items) <= set(candidate_items), "accepted copper was removed")
    require(all(base_items[key] == candidate_items[key] for key in base_items),
            "accepted copper was modified")
    added = [candidate_items[key] for key in set(candidate_items) - set(base_items)]
    names = {int(net.number): net.name for net in candidate.nets}
    segments: Counter[str] = Counter()
    vias: Counter[str] = Counter()
    length = 0.0
    for item in added:
        name = names[int(item.net)]
        require(name in EXPECTED, f"out-of-scope copper added on {name}")
        if type(item).__name__ == "Segment":
            segments[name] += 1
            length += math.hypot(
                float(item.end.X) - float(item.start.X),
                float(item.end.Y) - float(item.start.Y),
            )
            require(abs(float(item.width) - 0.15) < 1e-9,
                    f"{name}: segment width drift")
        else:
            vias[name] += 1
            require(abs(float(item.size) - 0.50) < 1e-9 and
                    abs(float(item.drill) - 0.30) < 1e-9,
                    f"{name}: via geometry drift")
    require({name: (segments[name], vias[name]) for name in EXPECTED} == EXPECTED,
            "per-net OctoSPI copper inventory drift")
    require(sum(segments.values()) == 121 and sum(vias.values()) == 25,
            "total OctoSPI copper inventory drift")
    require(abs(length - 282.362979395) < 1e-6, "OctoSPI track length drift")
    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    require(proposal.get("candidate_board_sha256") == CANDIDATE_SHA256 and
            proposal.get("applied_to_authoritative_board") is False and
            proposal.get("review_b_complete") is False and
            proposal.get("cam_or_manufacturing_release") is False,
            "proposal identity or release boundary drift")
    return {
        "schema_version": "dioneya.pcb-main-octospi-routing-candidate-audit.v1",
        "status": "PASS_STATIC_CANDIDATE_ISOLATION",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "routed_nets": sorted(EXPECTED),
        "added_segments": 121,
        "added_vias": 25,
        "added_track_length_mm": length,
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
        require(bool(args.drc_base and args.drc_candidate), "both DRC reports are required")
        report["comparative_drc"] = audit_drc(args.drc_base, args.drc_candidate)
    if args.connectivity_base or args.connectivity_candidate:
        require(bool(args.connectivity_base and args.connectivity_candidate),
                "both connectivity boards are required")
        report["native_connectivity"] = native_connectivity(
            args.connectivity_base, args.connectivity_candidate)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("PCB-MAIN OctoSPI routing candidate audit: PASS")
    print(f"added_segments=121 added_vias=25 routed_nets={len(EXPECTED)}")
    print("release_boundary=PENDING_HUMAN_REVIEW_AND_REVIEW_B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
