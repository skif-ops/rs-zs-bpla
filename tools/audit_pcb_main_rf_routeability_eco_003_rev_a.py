#!/usr/bin/env python3
"""Audit the bounded PCB-MAIN RF routeability ECO-003 proposal.

The proposal is deliberately isolated from the authoritative native board.  It may
prove placement and RF-route feasibility, but it may not complete Review B or create
a manufacturing release.  Static checks use kiutils; the native KiCad connectivity
check is optional so the portable CI job can run without a KiCad installation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kiutils.board import Board
from kiutils.utils import sexpr


ROOT = Path(__file__).resolve().parents[1]
BASE_BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
CANDIDATE_BOARD = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-RF-ECO-003/PCB-MAIN_RF_ECO_003.kicad_pcb"
)
PROPOSAL = ROOT / "hardware/reviews/PCB_MAIN_RF_ROUTEABILITY_ECO_003_CANDIDATE_REV_A.json"
PROPOSAL_RECORD = ROOT / "hardware/reviews/PCB_MAIN_RF_ROUTEABILITY_ECO_003_CANDIDATE_REV_A.md"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_RF_ROUTEABILITY_ECO_003_APPROVAL.json"
MAPPING = ROOT / "hardware/reviews/PCB_MAIN_RF_ROUTEABILITY_ECO_003_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_RF_ROUTEABILITY_ECO_003_APPLICATION.json"

HISTORICAL_BASE_SHA256 = "e81daf6d8cf0220f762c64f1fc637f65d71d6bc99128ab8c4993a540431e461e"
APPLIED_BASE_SHA256 = "dfcd8780cb3f189fe89cca98f32e3ee9693947a9a28d25e0154f7cce65d51684"
APPLIED_PLACEMENT_SHA256 = "34abe08f925ec03f045b295d5c40a0391e0597a09ecdad5a7e563c93f53a62c4"
CANDIDATE_SHA256 = "3561f334476259f4e2aa6143a49dcc945da7eb1a292400449b60d204ac421c5d"
PROPOSAL_SHA256 = "81c71958796e816fd28360562c1034a96c67d1c314bc645210ebc249065dc831"
PROPOSAL_RECORD_SHA256 = "72904af934e7ee41050a660d47fd59916ed798a9ee1183c5df0b828e509303ae"
REVIEWED_LOCAL_COMMIT = "dc7921fa08714ae9ad997b9c54ce24491e9672da"
REVIEWED_GITHUB_COMMIT = "23d4195c15a380f4e12337094be0d09d022be065"
REVIEWED_TREE = "82467c29399fddec21458e169ed00c6d02a1e856"
APPROVAL_COMMIT = "ac7439dce989915f4a56a52168ef426d8cfc9700"
TRACE_WIDTH_MM = 0.1509
TRACK_SEGMENTS = 89
TOTAL_LENGTH_MM = 103.481866172679
EXPECTED_CONNECTIVITY_REDUCTION = 15

EXPECTED_POSES = {
    "FL1": ((61.0, 69.5, 0.0), (60.5, 68.0, 0.0)),
    "D4": ((61.0, 68.0, 0.0), (58.25, 70.0, 90.0)),
    "L2": ((59.25, 69.5, 0.0), (59.75, 70.25, 90.0)),
}
EXPECTED_ROUTES = {
    "CELL_RF": (15, 31.713834471939),
    "CELL_RF_ANT": (23, 17.631727983645),
    "GNSS_RF_ANT_BIASED": (13, 10.340990257670),
    "GNSS_RF_DC_BLOCK": (1, 1.0),
    "GNSS_RF_FILTERED": (12, 18.644291116569),
    "LORA_RF_ANT": (15, 13.088836886152),
    "LORA_RF_MODULE": (10, 11.062185456703),
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_text(commit: str, path: Path) -> str:
    relative = str(path.relative_to(ROOT))
    completed = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, f"cannot read {relative} from {commit}")
    return completed.stdout


def git_tree(commit: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", f"{commit}^{{tree}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, f"cannot resolve reviewed tree for {commit}")
    return completed.stdout.strip()


def bytes_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git_blob_sha(payload: bytes) -> str:
    return hashlib.sha1(f"blob {len(payload)}\0".encode("ascii") + payload).hexdigest()


def ref_of(footprint: Any) -> str:
    property_ref = str(footprint.properties.get("Reference", ""))
    graphic_refs = [
        str(item.text)
        for item in footprint.graphicItems
        if getattr(item, "type", None) == "reference"
    ]
    require(len(graphic_refs) <= 1, f"duplicate footprint reference graphics: {graphic_refs}")
    if property_ref:
        require(not graphic_refs or graphic_refs[0] == property_ref,
                f"footprint reference disagreement: {property_ref!r} vs {graphic_refs!r}")
        return property_ref
    require(len(graphic_refs) == 1 and graphic_refs[0], "footprint reference is missing")
    return graphic_refs[0]


def normalized_angle(value: Any) -> float:
    return float(value or 0.0) % 360.0


def pose_of(footprint: Any) -> tuple[float, float, float]:
    return (
        float(footprint.position.X),
        float(footprint.position.Y),
        normalized_angle(footprint.position.angle),
    )


def close(first: float, second: float, tolerance: float = 1e-6) -> bool:
    return math.isclose(float(first), float(second), rel_tol=0.0, abs_tol=tolerance)


def pose_matches(actual: tuple[float, float, float], expected: tuple[float, float, float]) -> bool:
    return all(close(first, second) for first, second in zip(actual, expected))


def parse_drc(path: Path) -> dict[str, Any]:
    require(path.is_file() and path.stat().st_size > 0, f"missing DRC report: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    parts = re.split(r"(?m)^\[([^]]+)\]:[^\n]*\n", text)
    counts: Counter[tuple[str, str]] = Counter()
    for index in range(1, len(parts), 2):
        category = parts[index]
        body = parts[index + 1]
        match = re.search(r"Severity:\s*([A-Za-z]+)", body)
        severity = match.group(1).lower() if match else "unknown"
        counts[(category, severity)] += 1
    require(counts, f"DRC report contains no parseable violation blocks: {path}")
    return {
        "path": str(path),
        "counts": {
            f"{category}:{severity}": count
            for (category, severity), count in sorted(counts.items())
        },
        "error_counts": {
            category: count
            for (category, severity), count in sorted(counts.items())
            if severity == "error"
        },
    }


def compare_drc(base_path: Path, candidate_path: Path) -> dict[str, Any]:
    base = parse_drc(base_path)
    candidate = parse_drc(candidate_path)
    base_errors = base["error_counts"]
    candidate_errors = candidate["error_counts"]
    added = {
        category: candidate_count - base_errors.get(category, 0)
        for category, candidate_count in candidate_errors.items()
        if candidate_count > base_errors.get(category, 0)
    }
    require(not added, f"candidate introduces KiCad DRC errors: {added}")
    return {
        "status": "PASS_NO_NEW_ERROR",
        "base": base,
        "candidate": candidate,
        "new_error_counts": added,
    }


def native_connectivity() -> dict[str, Any]:
    try:
        import pcbnew  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on KiCad system Python
        raise AssertionError("--kicad-connectivity requires the KiCad pcbnew module") from exc

    counts: dict[str, int] = {}
    versions: list[str] = []
    for label, path in (("baseline", BASE_BOARD), ("candidate", CANDIDATE_BOARD)):
        board = pcbnew.LoadBoard(str(path))
        require(board is not None, f"KiCad cannot load {path}")
        board.BuildConnectivity()
        counts[label] = int(board.GetConnectivity().GetUnconnectedCount(False))
        versions.append(str(pcbnew.GetBuildVersion()))
    reduction = counts["baseline"] - counts["candidate"]
    require(reduction == EXPECTED_CONNECTIVITY_REDUCTION,
            f"RF connectivity reduction is {reduction}, expected {EXPECTED_CONNECTIVITY_REDUCTION}")
    return {
        "status": "PASS_EXACT_SEVEN_RF_NET_REDUCTION",
        "kicad_build_versions": sorted(set(versions)),
        "baseline_unconnected_count": counts["baseline"],
        "candidate_unconnected_count": counts["candidate"],
        "reduction": reduction,
        "expected_reduction": EXPECTED_CONNECTIVITY_REDUCTION,
    }


def static_audit() -> dict[str, Any]:
    for path in (
        BASE_BOARD,
        CANDIDATE_BOARD,
        PROPOSAL,
        PROPOSAL_RECORD,
        APPROVAL,
        MAPPING,
        APPLICATION,
    ):
        require(path.is_file() and path.stat().st_size > 0, f"missing ECO-003 input: {path}")
    require(sha256(BASE_BOARD) == APPLIED_BASE_SHA256,
            "PCB-MAIN ECO-003 applied authoritative board SHA-256 drift")
    require(sha256(CANDIDATE_BOARD) == CANDIDATE_SHA256, "PCB-MAIN ECO-003 candidate SHA-256 drift")
    require(sha256(PROPOSAL) == PROPOSAL_SHA256,
            "PCB-MAIN ECO-003 reviewed proposal SHA-256 drift")
    require(sha256(PROPOSAL_RECORD) == PROPOSAL_RECORD_SHA256,
            "PCB-MAIN ECO-003 reviewed proposal record SHA-256 drift")

    require(git_tree(REVIEWED_GITHUB_COMMIT) == REVIEWED_TREE,
            "PCB-MAIN ECO-003 reviewed GitHub tree drift")
    if subprocess.run(
        ["git", "cat-file", "-e", f"{REVIEWED_LOCAL_COMMIT}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    ).returncode == 0:
        require(git_tree(REVIEWED_LOCAL_COMMIT) == REVIEWED_TREE,
                "PCB-MAIN ECO-003 reviewed local tree drift")
    historical_text = git_text(REVIEWED_GITHUB_COMMIT, BASE_BOARD)
    require(bytes_sha256(historical_text.encode("utf-8")) == HISTORICAL_BASE_SHA256,
            "PCB-MAIN ECO-003 historical baseline SHA-256 drift")

    base = Board.from_sexpr(sexpr.parse_sexp(historical_text))
    applied_base = Board.from_file(str(BASE_BOARD), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE_BOARD), encoding="utf-8")
    base_footprints = {ref_of(item): item for item in base.footprints}
    applied_footprints = {ref_of(item): item for item in applied_base.footprints}
    candidate_footprints = {ref_of(item): item for item in candidate.footprints}
    require(len(base.footprints) == len(base_footprints) == 251,
            "baseline footprint identity/count drift")
    require(len(applied_base.footprints) == len(applied_footprints) == 251,
            "applied-board footprint identity/count drift")
    require(len(candidate.footprints) == len(candidate_footprints) == 251,
            "candidate footprint identity/count drift")
    require(base_footprints.keys() == candidate_footprints.keys(),
            "candidate footprint set differs from baseline")
    require(applied_footprints.keys() == candidate_footprints.keys(),
            "applied footprint set differs from candidate")

    require(base.nets == candidate.nets, "candidate net table differs from baseline")
    require(applied_base.nets == candidate.nets,
            "applied board net table differs from candidate")
    require(len([item for item in candidate.nets if item.name]) == 186,
            "candidate named-net count drift")
    for field in ("general", "layers", "setup", "properties", "graphicItems",
                  "dimensions", "groups", "targets"):
        require(getattr(base, field) == getattr(candidate, field),
                f"candidate board-level field differs from baseline: {field}")
        require(getattr(applied_base, field) == getattr(candidate, field),
                f"applied board-level field differs from candidate: {field}")
    require(len(getattr(base, "traceItems", [])) == 0 and len(getattr(base, "zones", [])) == 0,
            "authoritative baseline unexpectedly contains routing or zones")
    require(len(getattr(applied_base, "traceItems", [])) == 0 and
            len(getattr(applied_base, "zones", [])) == 0,
            "ECO-003 applied authoritative board contains routing or zones")
    require(len(getattr(candidate, "zones", [])) == 0,
            "ECO-003 candidate unexpectedly contains copper zones")

    changed = {
        ref for ref in base_footprints
        if base_footprints[ref] != candidate_footprints[ref]
    }
    require(changed == set(EXPECTED_POSES), f"unexpected footprint delta: {sorted(changed)}")
    for ref, (before, after) in EXPECTED_POSES.items():
        source = base_footprints[ref]
        target = candidate_footprints[ref]
        require(pose_matches(pose_of(source), before), f"{ref}: baseline pose drift")
        require(pose_matches(pose_of(target), after), f"{ref}: candidate pose drift")
        require(source.locked is False and target.locked is False,
                f"{ref}: ECO attempts to move a locked footprint")
        require(source.properties == target.properties and
                target.properties.get("DIONEA_PLACEMENT_CLASS") == "UNLOCKED_LAYOUT_CANDIDATE",
                f"{ref}: placement class or footprint properties drift")
        require([(pad.number, pad.net.number, pad.net.name) for pad in source.pads] ==
                [(pad.number, pad.net.number, pad.net.name) for pad in target.pads],
                f"{ref}: pad/net identity drift")

    applied_changed = {
        ref for ref in applied_footprints
        if applied_footprints[ref] != candidate_footprints[ref]
    }
    require(not applied_changed,
            f"applied placement differs from reviewed candidate: {sorted(applied_changed)}")

    net_names = {item.number: item.name for item in candidate.nets}
    route_stats: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"segments": 0, "length_mm": 0.0}
    )
    trace_items = list(getattr(candidate, "traceItems", []))
    require(len(trace_items) == TRACK_SEGMENTS, "ECO-003 track-segment count drift")
    for item in trace_items:
        require(type(item).__name__ == "Segment", "ECO-003 contains a via or non-segment trace item")
        require(item.layer == "F.Cu", "ECO-003 contains a track outside F.Cu")
        require(close(item.width, TRACE_WIDTH_MM, 1e-9),
                f"ECO-003 contains a non-authorized trace width: {item.width}")
        require(item.net in net_names and net_names[item.net] in EXPECTED_ROUTES,
                f"ECO-003 routes an unauthorized net code: {item.net}")
        length = math.hypot(float(item.end.X) - float(item.start.X),
                            float(item.end.Y) - float(item.start.Y))
        require(length > 0.0, "ECO-003 contains a zero-length segment")
        name = net_names[item.net]
        route_stats[name]["segments"] = int(route_stats[name]["segments"]) + 1
        route_stats[name]["length_mm"] = float(route_stats[name]["length_mm"]) + length

    require(set(route_stats) == set(EXPECTED_ROUTES),
            f"ECO-003 routed-net set drift: {sorted(route_stats)}")
    for name, (expected_segments, expected_length) in EXPECTED_ROUTES.items():
        actual = route_stats[name]
        require(actual["segments"] == expected_segments,
                f"{name}: segment-count drift")
        require(close(float(actual["length_mm"]), expected_length, 1e-6),
                f"{name}: routed-length drift")
    actual_total = sum(float(item["length_mm"]) for item in route_stats.values())
    require(close(actual_total, TOTAL_LENGTH_MM, 1e-6), "ECO-003 total routed-length drift")

    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    boundary = proposal.get("decision_boundary", {})
    proposal_candidate = proposal.get("candidate", {})
    proposal_basis = proposal.get("routing_basis", {})
    expected_proposal_routes = [
        {"net": name, "segments": segments, "length_mm": length}
        for name, (segments, length) in EXPECTED_ROUTES.items()
    ]
    expected_proposal_moves = [
        {
            "refdes": ref,
            "placement_class": "UNLOCKED_LAYOUT_CANDIDATE",
            "from": {"x_mm": before[0], "y_mm": before[1], "rotation_deg": before[2]},
            "to": {"x_mm": after[0], "y_mm": after[1], "rotation_deg": after[2]},
        }
        for ref, (before, after) in EXPECTED_POSES.items()
    ]
    require(proposal.get("proposal_id") == "PCB-MAIN-RF-ROUTEABILITY-ECO-003" and
            proposal.get("status") == "READY_FOR_MACHINE_GATE_AND_INDEPENDENT_HUMAN_REVIEW" and
            proposal.get("baseline", {}).get("board_sha256") == HISTORICAL_BASE_SHA256 and
            proposal_candidate.get("board_sha256") == CANDIDATE_SHA256 and
            proposal_candidate.get("track_segments") == TRACK_SEGMENTS and
            close(proposal_candidate.get("track_length_mm", -1.0), TOTAL_LENGTH_MM, 1e-12) and
            proposal_candidate.get("vias") == 0 and proposal_candidate.get("zones") == 0 and
            proposal_candidate.get("routed_nets") == expected_proposal_routes and
            proposal.get("bounded_placement_delta") == expected_proposal_moves and
            proposal_basis.get("stackup_id") == "JLC06161H-3313" and
            proposal_basis.get("signal_layer") == "F.Cu" and
            proposal_basis.get("reference_layer") == "In1.Cu" and
            proposal_basis.get("trace_width_mm") == TRACE_WIDTH_MM and
            proposal_basis.get("signal_vias") == 0,
            "ECO-003 proposal identity, hash or routing basis drift")
    require(boundary == {
                "proposal_only": True,
                "applied_to_authoritative_board": False,
                "placement_authority_changed": False,
                "routing_authority_changed": False,
                "routing_complete": False,
                "return_path_review_complete": False,
                "si_review_complete": False,
                "review_b_complete": False,
                "manufacturing_release": False,
            }, "ECO-003 decision boundary drift")

    reviewed_payloads = {
        PROPOSAL: (PROPOSAL_SHA256, "d138577fd9d00c666df20918985949b09c59ebc1"),
        PROPOSAL_RECORD: (PROPOSAL_RECORD_SHA256, "afdd14ec54936632a642158d4da05b1217b5458e"),
        CANDIDATE_BOARD: (CANDIDATE_SHA256, "57698e1bac83b468ef82031314e20931bc838c8e"),
    }
    for path, (expected_sha256, expected_blob) in reviewed_payloads.items():
        payload = git_text(REVIEWED_GITHUB_COMMIT, path).encode("utf-8")
        require(bytes_sha256(payload) == expected_sha256 and
                git_blob_sha(payload) == expected_blob,
                f"reviewed ECO-003 blob drift: {path.relative_to(ROOT)}")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    require(approval.get("proposal_id") == "PCB-MAIN-RF-ROUTEABILITY-ECO-003" and
            approval.get("reviewer") == "Скиф" and
            approval.get("date") == "2026-09-19" and
            approval.get("decision") == "ACCEPT_LIMITED_RF_ROUTEABILITY_ECO" and
            approval.get("reviewed_proposal_sha256") == PROPOSAL_SHA256 and
            approval.get("reviewed_proposal_record_sha256") == PROPOSAL_RECORD_SHA256 and
            approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256 and
            approval.get("reviewed_baseline_board_sha256") == HISTORICAL_BASE_SHA256 and
            approval.get("reviewed_local_commit_sha") == REVIEWED_LOCAL_COMMIT and
            approval.get("github_equivalent_commit_sha") == REVIEWED_GITHUB_COMMIT and
            approval.get("reviewed_tree_sha") == REVIEWED_TREE and
            approval.get("placement_implementation_authorized") is True and
            approval.get("routing_engineering_continuation_authorized") is True and
            approval.get("candidate_copper_final_authorized") is False and
            approval.get("routing_complete") is False and
            approval.get("review_b_complete") is False and
            approval.get("manufacturing_release") is False,
            "ECO-003 approval binding or release boundary drift")
    require(approval.get("approved_placement_delta") == [
                {"refdes": ref, "from": list(before), "to": list(after)}
                for ref, (before, after) in EXPECTED_POSES.items()
            ], "ECO-003 approved placement delta drift")

    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    require(mapping.get("reviewed_local_commit_sha") == REVIEWED_LOCAL_COMMIT and
            mapping.get("github_equivalent_commit_sha") == REVIEWED_GITHUB_COMMIT and
            mapping.get("reviewed_tree_sha") == REVIEWED_TREE and
            mapping.get("proposal_blob_sha") == "d138577fd9d00c666df20918985949b09c59ebc1" and
            mapping.get("proposal_record_blob_sha") == "afdd14ec54936632a642158d4da05b1217b5458e" and
            mapping.get("candidate_board_blob_sha") == "57698e1bac83b468ef82031314e20931bc838c8e" and
            mapping.get("equivalence") == "EXACT_TREE_AND_REVIEWED_BLOBS" and
            mapping.get("placement_implementation_authorized") is True and
            mapping.get("routing_engineering_continuation_authorized") is True and
            mapping.get("candidate_copper_final_authorized") is False and
            mapping.get("review_b_complete") is False and
            mapping.get("manufacturing_release") is False,
            "ECO-003 review-commit mapping drift")

    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    applied = application.get("applied", {})
    require(application.get("proposal_id") == "PCB-MAIN-RF-ROUTEABILITY-ECO-003" and
            application.get("decision") == "ACCEPT_LIMITED_RF_ROUTEABILITY_ECO" and
            application.get("reviewed_proposal_commit_sha") == REVIEWED_GITHUB_COMMIT and
            application.get("approval_commit_sha") == APPROVAL_COMMIT and
            application.get("reviewed_proposal_sha256") == PROPOSAL_SHA256 and
            application.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256 and
            application.get("status") ==
            "APPLIED_PLACEMENT_ONLY_STRICT_2D_CLEARANCE_PASS_ROUTING_ENGINEERING_CONTINUES" and
            application.get("placement_implementation_authorized") is True and
            application.get("routing_engineering_continuation_authorized") is True and
            application.get("candidate_copper_final_authorized") is False and
            application.get("routing_complete") is False and
            application.get("review_b_complete") is False and
            application.get("manufacturing_release") is False,
            "ECO-003 application binding or release boundary drift")
    require(applied.get("board_sha256") == APPLIED_BASE_SHA256 and
            applied.get("placement_repack_sha256") == APPLIED_PLACEMENT_SHA256 and
            applied.get("changed_references") == ["D4", "FL1", "L2"] and
            applied.get("track_segments") == 0 and
            applied.get("vias") == 0 and
            applied.get("copper_zones") == 0,
            "ECO-003 applied source/hash record drift")

    return {
        "schema_version": "dioneya.pcb-main-rf-routeability-eco-003-audit.v1",
        "proposal_id": "PCB-MAIN-RF-ROUTEABILITY-ECO-003",
        "status": "PASS_APPROVED_APPLIED_PLACEMENT_ONLY",
        "historical_base_board_sha256": HISTORICAL_BASE_SHA256,
        "applied_board_sha256": APPLIED_BASE_SHA256,
        "applied_placement_sha256": APPLIED_PLACEMENT_SHA256,
        "candidate_board_sha256": CANDIDATE_SHA256,
        "changed_footprints": sorted(changed),
        "routed_nets": {
            name: {
                "segments": int(route_stats[name]["segments"]),
                "length_mm": round(float(route_stats[name]["length_mm"]), 12),
            }
            for name in sorted(route_stats)
        },
        "track_segments": TRACK_SEGMENTS,
        "track_length_mm": round(actual_total, 12),
        "trace_width_mm": TRACE_WIDTH_MM,
        "signal_vias": 0,
        "candidate_copper_final_authorized": False,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--base-drc", type=Path)
    parser.add_argument("--candidate-drc", type=Path)
    parser.add_argument("--kicad-connectivity", action="store_true")
    args = parser.parse_args()
    require((args.base_drc is None) == (args.candidate_drc is None),
            "--base-drc and --candidate-drc must be supplied together")

    report = static_audit()
    if args.kicad_connectivity:
        report["native_connectivity"] = native_connectivity()
    if args.base_drc is not None and args.candidate_drc is not None:
        report["comparative_drc"] = compare_drc(args.base_drc, args.candidate_drc)

    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    print("PCB-MAIN RF routeability ECO-003 audit: PASS_APPROVED_APPLIED_PLACEMENT_ONLY")
    print("changed_footprints=['D4', 'FL1', 'L2'] routed_nets=7 segments=89 vias=0")
    if args.kicad_connectivity:
        connectivity = report["native_connectivity"]
        print(
            "native_connectivity="
            f"{connectivity['baseline_unconnected_count']}->"
            f"{connectivity['candidate_unconnected_count']} "
            f"expected_reduction={EXPECTED_CONNECTIVITY_REDUCTION} PASS"
        )
    if args.base_drc is not None:
        print("comparative_drc=PASS_NO_NEW_ERROR")
    print("routing_complete=false review_b=false manufacturing_release=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
