#!/usr/bin/env python3
"""Audit the isolated PCB-MAIN hard-signal-net routing candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kiutils.board import Board


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-SIGNAL-HARD-NETS-001"
    / "PCB-MAIN_SIGNAL_HARD_NETS_BASE_REV_A.kicad_pcb"
)
CANDIDATE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-SIGNAL-HARD-NETS-001"
    / "PCB-MAIN_SIGNAL_HARD_NETS_CANDIDATE_REV_A.kicad_pcb"
)
ACTIVE = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_SIGNAL_HARD_NETS_ROUTING_APPROVAL_REV_A.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_SIGNAL_HARD_NETS_ROUTING_APPLICATION_REV_A.json"
OCTOSPI_CANDIDATE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-OCTOSPI-R8-ECO-002"
    / "PCB-MAIN_OCTOSPI_R8_ECO_CANDIDATE_REV_A.kicad_pcb"
)
OCTOSPI_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_OCTOSPI_R8_ECO_002_APPLICATION_REV_A.json"
)
RF_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-P0-001/"
    "PCB-MAIN_RF_P0_CANDIDATE_REV_A.kicad_pcb"
)
RF_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_RF_P0_ROUTING_APPLICATION_REV_A.json"
RF_REMEDIATION_COMPOSED = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-REMEDIATION-APPLICATION-001/"
    "PCB-MAIN_RF_REMEDIATION_COMPOSED_REV_A.kicad_pcb"
)
BASE_SHA256 = "9c8abfabc18fa22b53c94b6b4d7946dbe1dfab797fbff9d00d7c3408aece1b9e"
CANDIDATE_SHA256 = "7dea2fdce607dbf7df2205e74b188d45e2def07c5329bacb4f9503ddcf7ae6f3"
OCTOSPI_SHA256 = "04a0c7e37068d00fbe53b48fd19063b015b6b5c04e9aaafb3b01bbced0d7a99f"
RF_SHA256 = "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
ACTIVE_SHA256 = "d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e"
GNSS_AUTHORIZED_REMOVED_GROUND_TSTAMPS = {
    "8bb16eba-0c23-436c-83cb-15711942aa13",
    "97b4ffd7-640c-458b-a674-df70012edd9e",
    "e4d5b871-eae5-40c8-bc94-33070afaccfd",
    "ed333547-457e-4a27-b04c-76eefac1703b",
    "f0cf6fbe-b2d3-49cb-ac31-38e0b70d131a",
    "1b0fbb03-8a78-4e3f-b887-5b3096c609de",
    "3b6e7ac6-f2af-49e1-bbb9-dd1c158f1517",
    "72553cba-285e-40e8-afa0-669c5c279833",
}
EXPECTED = {
    "BLE_RX_U1": (17, 0, 50.571067811865, {"F.Cu": 17}),
    "BOOT0": (14, 2, 19.038582233138, {"B.Cu": 9, "F.Cu": 5}),
    "CELL_RX_U16": (26, 0, 41.006096654410, {"F.Cu": 26}),
    "EN_MODEM": (7, 1, 43.517766952966, {"F.Cu": 3, "In2.Cu": 4}),
    "NOR_IO0_U1": (11, 2, 20.028174593052, {"F.Cu": 5, "In2.Cu": 6}),
    "NOR_IO2_U1": (5, 2, 20.785533905933, {"F.Cu": 3, "In3.Cu": 2}),
    "SD_CMD_U1": (13, 0, 30.992640687119, {"F.Cu": 13}),
    "SD_D2_U1": (9, 2, 35.889087296526, {"F.Cu": 4, "In2.Cu": 5}),
}
EXPECTED_CONNECTIVITY = {"baseline": 464, "candidate": 454, "reduction": 10}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_drc(path: Path) -> dict[str, Any]:
    require(path.is_file() and path.stat().st_size > 0, f"missing DRC report: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    parts = re.split(r"(?m)^\[([^]]+)\]:[^\n]*\n", text)
    counts: Counter[tuple[str, str]] = Counter()
    for index in range(1, len(parts), 2):
        category, body = parts[index], parts[index + 1]
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
        "category_counts": {
            category: sum(count for (name, _), count in counts.items() if name == category)
            for category in sorted({name for name, _ in counts})
        },
    }


def compare_drc(base_path: Path, candidate_path: Path) -> dict[str, Any]:
    base, candidate = parse_drc(base_path), parse_drc(candidate_path)
    added_errors = {
        category: count - base["error_counts"].get(category, 0)
        for category, count in candidate["error_counts"].items()
        if count > base["error_counts"].get(category, 0)
        and category != "unconnected_items"
    }
    geometry_categories = {
        "clearance", "hole_clearance", "items_not_allowed", "track_dangling",
        "via_dangling", "shorting_items", "isolated_copper",
    }
    added_geometry = {
        category: candidate["category_counts"].get(category, 0)
        - base["category_counts"].get(category, 0)
        for category in geometry_categories
        if candidate["category_counts"].get(category, 0)
        > base["category_counts"].get(category, 0)
    }
    require(not added_errors, f"candidate introduces KiCad DRC errors: {added_errors}")
    require(not added_geometry,
            f"candidate introduces signal-copper geometry violations: {added_geometry}")
    return {
        "status": "PASS_NO_NEW_ERROR_OR_SIGNAL_COPPER_GEOMETRY_VIOLATION",
        "base": base,
        "candidate": candidate,
        "new_error_counts": added_errors,
        "new_geometry_category_counts": added_geometry,
    }


def native_connectivity(base_path: Path, candidate_path: Path) -> dict[str, Any]:
    try:
        import pcbnew  # type: ignore
    except ImportError as exc:  # pragma: no cover - KiCad system Python only
        raise AssertionError("--kicad-connectivity requires pcbnew") from exc
    counts: dict[str, int] = {}
    versions: set[str] = set()
    for label, path in (("baseline", base_path), ("candidate", candidate_path)):
        board = pcbnew.LoadBoard(str(path))
        require(board is not None, f"KiCad cannot load {path}")
        board.BuildListOfNets()
        board.BuildConnectivity()
        counts[label] = int(board.GetConnectivity().GetUnconnectedCount(False))
        versions.add(str(pcbnew.GetBuildVersion()))
    reduction = counts["baseline"] - counts["candidate"]
    require(counts["baseline"] == EXPECTED_CONNECTIVITY["baseline"] and
            counts["candidate"] == EXPECTED_CONNECTIVITY["candidate"] and
            reduction == EXPECTED_CONNECTIVITY["reduction"],
            f"signal candidate connectivity drift: {counts}, reduction={reduction}")
    return {
        "status": "PASS_EXACT_10_CONNECTION_REDUCTION",
        "kicad_build_versions": sorted(versions),
        "baseline_unconnected_count": counts["baseline"],
        "candidate_unconnected_count": counts["candidate"],
        "reduction": reduction,
    }


def static_audit() -> dict[str, Any]:
    require(sha256(BASE) == BASE_SHA256, "authoritative base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "candidate SHA-256 drift")
    require(sha256(OCTOSPI_CANDIDATE) == OCTOSPI_SHA256 and
            sha256(RF_CANDIDATE) == RF_SHA256 and
            sha256(ACTIVE) == ACTIVE_SHA256 and
            sha256(RF_REMEDIATION_COMPOSED) ==
            "f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9",
            "authoritative PCB-MAIN RF-remediation successor identity drift")
    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    active = Board.from_file(str(ACTIVE), encoding="utf-8")
    for field in (
        "general", "layers", "setup", "properties", "graphicItems", "dimensions",
        "groups", "targets", "nets", "footprints", "zones",
    ):
        require(getattr(base, field) == getattr(candidate, field),
                f"candidate changes non-signal-routing field: {field}")

    base_items = {item.tstamp: item for item in base.traceItems}
    candidate_items = {item.tstamp: item for item in candidate.traceItems}
    active_items = {item.tstamp: item for item in active.traceItems}
    require(not (set(base_items) - set(candidate_items)), "candidate removes accepted copper")
    require(all(base_items[key] == candidate_items[key] for key in base_items),
            "candidate modifies accepted ground copper")
    missing_candidate_items = set(candidate_items) - set(active_items)
    require(
        missing_candidate_items == GNSS_AUTHORIZED_REMOVED_GROUND_TSTAMPS
        and all(
            candidate_items[key] == active_items[key]
            for key in set(candidate_items) & set(active_items)
        ),
        "accepted signal/ground copper changed outside the authorized GNSS delta",
    )
    candidate_zones = {str(item.tstamp): item for item in candidate.zones}
    active_zones = {str(item.tstamp): item for item in active.zones}
    require(
        set(candidate_zones) <= set(active_zones)
        and all(candidate_zones[key] == active_zones[key] for key in candidate_zones),
        "accepted ground zones or rule areas changed outside cellular L2 composition",
    )
    additions = [item for key, item in candidate_items.items() if key not in base_items]
    require(len(additions) == 111, "candidate added-copper item count drift")

    net_names = {net.number: net.name for net in candidate.nets}
    segments = Counter()
    vias = Counter()
    lengths = defaultdict(float)
    layers = Counter()
    for item in additions:
        net = net_names[item.net]
        require(net in EXPECTED, f"candidate routes unauthorized net: {net}")
        if type(item).__name__ == "Segment":
            require(math.isclose(item.width, 0.15, abs_tol=1e-9),
                    f"{net}: unexpected track width")
            require(item.layer in {"F.Cu", "In2.Cu", "In3.Cu", "B.Cu"},
                    f"{net}: unexpected signal layer {item.layer}")
            segments[net] += 1
            layers[(net, item.layer)] += 1
            lengths[net] += math.hypot(
                float(item.end.X) - float(item.start.X),
                float(item.end.Y) - float(item.start.Y),
            )
        else:
            require(type(item).__name__ == "Via", "unsupported added copper item")
            require(math.isclose(item.size, 0.5, abs_tol=1e-9) and
                    math.isclose(item.drill, 0.3, abs_tol=1e-9) and
                    list(item.layers) == ["F.Cu", "B.Cu"],
                    f"{net}: unexpected via geometry")
            vias[net] += 1

    for net, (segment_count, via_count, length, expected_layers) in EXPECTED.items():
        require(segments[net] == segment_count, f"{net}: segment-count drift")
        require(vias[net] == via_count, f"{net}: via-count drift")
        require(math.isclose(lengths[net], length, abs_tol=1e-6),
                f"{net}: route-length drift")
        actual_layers = {
            layer: count for (name, layer), count in layers.items() if name == net
        }
        require(actual_layers == expected_layers, f"{net}: layer inventory drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    require(approval.get("reviewer") == "Скиф" and
            approval.get("decision") == "ACCEPT_SIGNAL_HARD_NETS_ROUTING_SUBGATE" and
            approval.get("reviewed_github_commit_sha") ==
            "4f3e5b18a49ebe2d11a33fcb833e57e18c56e34d" and
            approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256 and
            approval.get("machine_gate", {}).get("pcb_native_run_id") == 35446985180 and
            approval.get("machine_gate", {}).get("ci_run_id") == 35446985202,
            "signal routing approval identity or machine evidence drift")
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    require(application.get("decision") == "ACCEPT_SIGNAL_HARD_NETS_ROUTING_SUBGATE" and
            application.get("approval_commit_sha") ==
            "9a6a5c0f86b2a6cbf597e9d0dcba57c394c42033" and
            application.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256 and
            application.get("status") ==
            "APPLIED_ACCEPTED_SIGNAL_HARD_NETS_SUBGATE_ROUTING_ENGINEERING_CONTINUES" and
            application.get("review_b_complete") is False and
            application.get("cam_or_manufacturing_release") is False,
            "signal routing application binding or release boundary drift")
    octospi_application = json.loads(OCTOSPI_APPLICATION.read_text(encoding="utf-8"))
    require(octospi_application.get("historical_baseline", {}).get("board_sha256") ==
            CANDIDATE_SHA256 and
            octospi_application.get("applied", {}).get("board_sha256") == OCTOSPI_SHA256 and
            octospi_application.get("applied", {}).get("exact_candidate_byte_identity") is True and
            octospi_application.get("routing_complete") is False and
            octospi_application.get("review_b_complete") is False and
            octospi_application.get("cam_or_manufacturing_release") is False,
            "OctoSPI successor application binding or release boundary drift")
    rf_application = json.loads(RF_APPLICATION.read_text(encoding="utf-8"))
    require(rf_application.get("historical_baseline", {}).get("board_sha256") ==
            OCTOSPI_SHA256 and
            rf_application.get("applied", {}).get("board_sha256") == RF_SHA256 and
            rf_application.get("applied", {}).get("exact_candidate_byte_identity") is True and
            rf_application.get("routing_complete") is False and
            rf_application.get("review_b_complete") is False and
            rf_application.get("cam_or_manufacturing_release") is False,
            "RF successor application binding or release boundary drift")

    return {
        "schema_version": "dioneya.pcb-main-signal-hard-nets-candidate-audit.v1",
        "status": "PASS_ACCEPTED_SIGNAL_SUBGATE_APPLIED",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "added_segments": sum(segments.values()),
        "added_vias": sum(vias.values()),
        "routed_nets": sorted(EXPECTED),
        "applied_to_authoritative_board": True,
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--base-drc", type=Path)
    parser.add_argument("--candidate-drc", type=Path)
    parser.add_argument("--kicad-connectivity", action="store_true")
    parser.add_argument("--connectivity-base", type=Path)
    parser.add_argument("--connectivity-candidate", type=Path)
    args = parser.parse_args()
    require((args.base_drc is None) == (args.candidate_drc is None),
            "--base-drc and --candidate-drc must be supplied together")
    require((args.connectivity_base is None) == (args.connectivity_candidate is None),
            "connectivity board paths must be supplied together")
    report = static_audit()
    if args.kicad_connectivity:
        report["native_connectivity"] = native_connectivity(
            args.connectivity_base or BASE,
            args.connectivity_candidate or CANDIDATE,
        )
    if args.base_drc is not None and args.candidate_drc is not None:
        report["comparative_drc"] = compare_drc(args.base_drc, args.candidate_drc)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    print("PCB-MAIN signal hard-nets candidate audit: PASS")
    print(f"base_sha256={BASE_SHA256}")
    print(f"candidate_sha256={CANDIDATE_SHA256}")
    print("added_segments=102 added_vias=9 routed_nets=8")
    if args.kicad_connectivity:
        connectivity = report["native_connectivity"]
        print(
            "native_connectivity="
            f"{connectivity['baseline_unconnected_count']}->"
            f"{connectivity['candidate_unconnected_count']} reduction=10 PASS"
        )
    if args.base_drc is not None:
        print("comparative_drc=PASS_NO_NEW_ERROR_OR_SIGNAL_COPPER_GEOMETRY_VIOLATION")
    print("release_boundary=PENDING_REVIEW_B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
