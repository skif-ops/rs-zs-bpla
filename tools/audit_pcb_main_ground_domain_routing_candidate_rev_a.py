#!/usr/bin/env python3
"""Audit the bounded PCB-MAIN ground-domain routing candidate.

The candidate is isolated from the authoritative board.  Static checks use
kiutils and remain portable; optional native checks refill the three zones with
pcbnew before connectivity and consume KiCad DRC reports produced by CI.
Nothing in this audit signs Review B or authorizes manufacture.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kiutils.board import Board


ROOT = Path(__file__).resolve().parents[1]
BASE_BOARD = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-GROUND-DOMAIN-001"
    / "PCB-MAIN_GROUND_DOMAIN_BASE_REV_A.kicad_pcb"
)
ACTIVE_BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
CANDIDATE_BOARD = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-GROUND-DOMAIN-001"
    / "PCB-MAIN_GROUND_DOMAIN_CANDIDATE_REV_A.kicad_pcb"
)
PROPOSAL = ROOT / "hardware/reviews/PCB_MAIN_GROUND_DOMAIN_ROUTING_CANDIDATE_REV_A.json"
PROPOSAL_RECORD = ROOT / "hardware/reviews/PCB_MAIN_GROUND_DOMAIN_ROUTING_CANDIDATE_REV_A.md"
APPROVAL = ROOT / "hardware/reviews/PCB_MAIN_GROUND_DOMAIN_ROUTING_APPROVAL_REV_A.json"
APPROVAL_RECORD = ROOT / "hardware/reviews/PCB_MAIN_GROUND_DOMAIN_ROUTING_APPROVAL_REV_A.md"
REVIEW_MAPPING = ROOT / "hardware/reviews/PCB_MAIN_GROUND_DOMAIN_ROUTING_REVIEW_COMMIT_MAPPING.json"
APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_GROUND_DOMAIN_ROUTING_APPLICATION_REV_A.json"
MECHANICAL = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
LAYER_AUTHORITY = ROOT / "hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv"

BASE_SHA256 = "a50aa153d1dad2ccc9f0759213932767c9950c441a887aaf5ab2d3d9fb59a2d8"
CANDIDATE_SHA256 = "9c8abfabc18fa22b53c94b6b4d7946dbe1dfab797fbff9d00d7c3408aece1b9e"
ACTIVE_BOARD_SHA256 = "f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9"
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
PROPOSAL_SHA256 = "6ad0446ea98a44863cef91be137da3e5dcff92303ac9e395e260773e8cebc314"
PROPOSAL_RECORD_SHA256 = "12f5ffafaa90cf3d796e08f17c333ac7701d0b17f286af487c31b8410673cb19"
REVIEWED_GITHUB_COMMIT = "830139e8875e4e67738cf88b938a8d0ff91e2798"
REVIEWED_TREE = "7670dea776097a70381792ad4efadc349d6537df"
PROPOSAL_BLOB = "406857fb53f4ea0f46f6a91cba3b0ee27b4e2433"
PROPOSAL_RECORD_BLOB = "093e023575b6ab45b20b674d0e3405edda6a36ae"
CANDIDATE_BLOB = "ab8e886297b1f611be6f20225d600556af97555f"
AUDIT_BLOB = "4cbeca9dbb3194643c7d2652827b91b2165086d3"
GROUND_NETS = {"GND_DIGITAL", "GND_MODEM", "GND_MIC"}
ALL_COPPER_LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
TRACK_WIDTH_MM = 0.15
VIA_DIAMETER_MM = 0.50
VIA_DRILL_MM = 0.30
EDGE_CLEARANCE_MM = 0.50
MOUNTING_KEEP_OUT_RADIUS_MM = 4.0
EXPECTED_CONNECTIVITY = {"baseline": 718, "candidate": 464, "reduction": 254}

EXPECTED_SEGMENTS = {"GND_DIGITAL": 187, "GND_MODEM": 106, "GND_MIC": 26}
EXPECTED_VIAS = {"GND_DIGITAL": 138, "GND_MODEM": 95, "GND_MIC": 21}
EXPECTED_LENGTHS_MM = {
    "GND_DIGITAL": 120.386307181560,
    "GND_MODEM": 88.636931803688,
    "GND_MIC": 17.492640687119,
}
EXPECTED_SEGMENT_LAYERS = {
    ("GND_DIGITAL", "F.Cu"): 182,
    ("GND_DIGITAL", "B.Cu"): 5,
    ("GND_MODEM", "F.Cu"): 103,
    ("GND_MODEM", "B.Cu"): 3,
    ("GND_MIC", "F.Cu"): 26,
}

GROUND_ZONE_SPECS = {
    "PCB_MAIN_GND_DIGITAL_In1_Cu": {
        "net": "GND_DIGITAL",
        "layers": ["In1.Cu"],
        "points": [
            (0.65, 0.65), (109.35, 0.65), (109.35, 74.35),
            (36.20, 74.35), (36.20, 33.80), (9.80, 33.80),
            (9.80, 74.35), (0.65, 74.35),
        ],
    },
    "PCB_MAIN_GND_MODEM_In4_Cu": {
        "net": "GND_MODEM",
        "layers": ["In4.Cu"],
        "points": [
            (0.65, 0.65), (109.35, 0.65), (109.35, 33.80),
            (36.80, 33.80), (36.80, 50.20), (43.80, 50.20),
            (43.80, 74.35), (0.65, 74.35),
        ],
    },
    "PCB_MAIN_GND_MIC_In2_Cu": {
        "net": "GND_MIC",
        "layers": ["In2.Cu"],
        "points": [
            (0.65, 0.65), (109.35, 0.65), (109.35, 29.80),
            (94.30, 29.80), (94.30, 40.70), (109.35, 40.70),
            (109.35, 74.35), (85.70, 74.35), (85.70, 45.80),
            (63.20, 45.80), (63.20, 50.80), (43.80, 50.80),
            (43.80, 74.35), (36.20, 74.35), (36.20, 33.80),
            (9.80, 33.80), (9.80, 74.35), (0.65, 74.35),
        ],
    },
}

FORBIDDEN_ZONE_OWNERS = {
    "GND_DIGITAL": {"ZONE_CELL"},
    "GND_MODEM": {"ZONE_GNSS", "ZONE_LORA", "ZONE_BLE_BODY", "ZONE_AUDIO_DIGITAL"},
    "GND_MIC": {"ZONE_CELL", "ZONE_GNSS", "ZONE_LORA", "ZONE_BLE_BODY"},
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def close(first: float, second: float, tolerance: float = 1e-6) -> bool:
    return math.isclose(float(first), float(second), rel_tol=0.0, abs_tol=tolerance)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_polygon(points: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    rounded = tuple((round(float(x), 6), round(float(y), 6)) for x, y in points)
    variants = []
    for sequence in (rounded, tuple(reversed(rounded))):
        variants.extend(sequence[index:] + sequence[:index] for index in range(len(sequence)))
    return min(variants)


def zone_points(zone: Any) -> list[tuple[float, float]]:
    require(len(zone.polygons) == 1, f"{zone.name}: expected one polygon")
    return [(float(point.X), float(point.Y)) for point in zone.polygons[0].coordinates]


def point_segment_distance(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float,
) -> float:
    dx, dy = x2 - x1, y2 - y1
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - x1, py - y1)
    fraction = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + fraction * dx), py - (y1 + fraction * dy))


def segment_intersects_expanded_rect(
    x1: float, y1: float, x2: float, y2: float,
    rectangle: tuple[float, float, float, float], expansion: float,
) -> bool:
    xmin, ymin, xmax, ymax = rectangle
    xmin -= expansion
    ymin -= expansion
    xmax += expansion
    ymax += expansion
    dx, dy = x2 - x1, y2 - y1
    start, end = 0.0, 1.0
    for coefficient, offset in (
        (-dx, x1 - xmin), (dx, xmax - x1),
        (-dy, y1 - ymin), (dy, ymax - y1),
    ):
        if abs(coefficient) < 1e-12:
            if offset < 0.0:
                return False
            continue
        fraction = offset / coefficient
        if coefficient < 0.0:
            start = max(start, fraction)
        else:
            end = min(end, fraction)
        if start > end:
            return False
    return True


def authority_geometry() -> tuple[
    dict[str, tuple[float, float]],
    dict[str, tuple[float, float, float, float]],
]:
    mounting: dict[str, tuple[float, float]] = {}
    regions: dict[str, tuple[float, float, float, float]] = {}
    with MECHANICAL.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            reference = row["RefDes"]
            if reference in {"H1", "H2", "H3", "H4"}:
                require(row["Layer_Scope"] == "ALL_COPPER" and
                        row["Clearance_Rule"] == "NO_COPPER_D8.0_NO_COMPONENT_D10.0",
                        f"{reference}: mounting copper authority drift")
                mounting[reference] = (float(row["X_mm"]), float(row["Y_mm"]))
            if reference in {
                "ZONE_CELL", "ZONE_GNSS", "ZONE_LORA", "ZONE_BLE_BODY",
                "ZONE_AUDIO_DIGITAL", "KO_BLE_ANT_BOARD",
            }:
                x, y = float(row["X_mm"]), float(row["Y_mm"])
                regions[reference] = (
                    x, y, x + float(row["Extent_X_mm"]), y + float(row["Extent_Y_mm"]),
                )
    require(set(mounting) == {"H1", "H2", "H3", "H4"},
            "mounting-hole authority set drift")
    require(set(regions) == {
                "ZONE_CELL", "ZONE_GNSS", "ZONE_LORA", "ZONE_BLE_BODY",
                "ZONE_AUDIO_DIGITAL", "KO_BLE_ANT_BOARD",
            }, "exclusive-zone authority set drift")
    return mounting, regions


def trace_intersects_rectangle(item: Any, rectangle: tuple[float, float, float, float]) -> bool:
    if type(item).__name__ == "Segment":
        return segment_intersects_expanded_rect(
            float(item.start.X), float(item.start.Y),
            float(item.end.X), float(item.end.Y), rectangle, float(item.width) / 2.0,
        )
    x, y, radius = float(item.position.X), float(item.position.Y), float(item.size) / 2.0
    xmin, ymin, xmax, ymax = rectangle
    return xmin - radius < x < xmax + radius and ymin - radius < y < ymax + radius


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
    forbidden_categories = {
        "clearance", "hole_clearance", "solder_mask_bridge", "items_not_allowed",
        "isolated_copper", "track_dangling", "via_dangling",
    }
    added_forbidden = {
        category: candidate["category_counts"][category] - base["category_counts"].get(category, 0)
        for category in forbidden_categories
        if candidate["category_counts"].get(category, 0)
        > base["category_counts"].get(category, 0)
    }
    require(not added_errors, f"candidate introduces KiCad DRC errors: {added_errors}")
    require(not added_forbidden,
            f"candidate introduces forbidden ground-geometry DRC categories: {added_forbidden}")
    return {
        "status": "PASS_NO_NEW_ERROR_AND_NO_NEW_GROUND_GEOMETRY_VIOLATION",
        "base": base,
        "candidate": candidate,
        "new_error_counts": added_errors,
        "new_forbidden_candidate_categories": added_forbidden,
    }


def native_connectivity() -> dict[str, Any]:
    try:
        import pcbnew  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on KiCad system Python
        raise AssertionError("--kicad-connectivity requires the KiCad pcbnew module") from exc

    counts: dict[str, int] = {}
    versions: set[str] = set()
    for label, path in (("baseline", BASE_BOARD), ("candidate", CANDIDATE_BOARD)):
        board = pcbnew.LoadBoard(str(path))
        require(board is not None, f"KiCad cannot load {path}")
        if label == "candidate":
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.BuildListOfNets()
        board.BuildConnectivity()
        counts[label] = int(board.GetConnectivity().GetUnconnectedCount(False))
        versions.add(str(pcbnew.GetBuildVersion()))
    reduction = counts["baseline"] - counts["candidate"]
    require(counts == {
                "baseline": EXPECTED_CONNECTIVITY["baseline"],
                "candidate": EXPECTED_CONNECTIVITY["candidate"],
            } and reduction == EXPECTED_CONNECTIVITY["reduction"],
            f"ground candidate connectivity drift: {counts}, reduction={reduction}")
    return {
        "status": "PASS_EXACT_254_FANOUT_REDUCTION",
        "kicad_build_versions": sorted(versions),
        "baseline_unconnected_count": counts["baseline"],
        "candidate_unconnected_count": counts["candidate"],
        "reduction": reduction,
    }


def static_audit() -> dict[str, Any]:
    for path in (
        BASE_BOARD, ACTIVE_BOARD, CANDIDATE_BOARD, PROPOSAL, PROPOSAL_RECORD,
        APPROVAL, APPROVAL_RECORD, REVIEW_MAPPING, APPLICATION, MECHANICAL,
        LAYER_AUTHORITY,
    ):
        require(path.is_file() and path.stat().st_size > 0, f"missing candidate input: {path}")
    require(sha256(BASE_BOARD) == BASE_SHA256, "PCB-MAIN authoritative baseline SHA-256 drift")
    require(sha256(CANDIDATE_BOARD) == CANDIDATE_SHA256,
            "PCB-MAIN ground candidate SHA-256 drift")
    require(sha256(ACTIVE_BOARD) == ACTIVE_BOARD_SHA256,
            "authoritative PCB-MAIN is not the accepted RF-routing successor")
    require(sha256(PROPOSAL) == PROPOSAL_SHA256 and
            sha256(PROPOSAL_RECORD) == PROPOSAL_RECORD_SHA256,
            "PCB-MAIN ground proposal record SHA-256 drift")

    base = Board.from_file(str(BASE_BOARD), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE_BOARD), encoding="utf-8")
    active = Board.from_file(str(ACTIVE_BOARD), encoding="utf-8")
    require(len(base.footprints) == len(candidate.footprints) == 251,
            "PCB-MAIN footprint count drift")
    require(len([net for net in candidate.nets if net.name]) == 186,
            "PCB-MAIN named-net count drift")
    for field in (
        "general", "layers", "setup", "properties", "graphicItems", "dimensions",
        "groups", "targets", "nets", "footprints",
    ):
        require(getattr(base, field) == getattr(candidate, field),
                f"candidate changes non-routing board field: {field}")
    require(not list(getattr(base, "traceItems", [])) and not list(getattr(base, "zones", [])),
            "authoritative baseline unexpectedly contains routing or zones")
    candidate_items = {item.tstamp: item for item in candidate.traceItems}
    active_items = {item.tstamp: item for item in active.traceItems}
    missing_candidate_items = set(candidate_items) - set(active_items)
    require(
        missing_candidate_items == GNSS_AUTHORIZED_REMOVED_GROUND_TSTAMPS
        and all(
            candidate_items[key] == active_items[key]
            for key in set(candidate_items) & set(active_items)
        ),
        "accepted ground copper changed outside the authorized GNSS fanout delta",
    )
    candidate_zones = {str(item.tstamp): item for item in candidate.zones}
    active_zones = {str(item.tstamp): item for item in active.zones}
    require(
        set(candidate_zones) <= set(active_zones)
        and all(candidate_zones[key] == active_zones[key] for key in candidate_zones),
        "accepted ground zones or rule areas changed outside cellular L2 composition",
    )

    with LAYER_AUTHORITY.open(encoding="utf-8", newline="") as stream:
        main_rows = [row for row in csv.DictReader(stream) if row["Board"] == "PCB-MAIN"]
    require(len(main_rows) == 1 and main_rows[0]["Copper_Layers"] == "6" and
            main_rows[0]["Native_Layer_Order"] == ";".join(ALL_COPPER_LAYERS) and
            main_rows[0]["Layer_Function_Intent"] ==
            "SIGNAL_RF;REFERENCE;POWER_DOMAINS;SIGNAL;REFERENCE;SIGNAL",
            "PCB-MAIN layer-function authority drift")

    net_names = {net.number: net.name for net in candidate.nets}
    segments: Counter[str] = Counter()
    vias: Counter[str] = Counter()
    segment_layers: Counter[tuple[str, str]] = Counter()
    lengths: defaultdict[str, float] = defaultdict(float)
    trace_items = list(candidate.traceItems)
    require(len(trace_items) == 573, "candidate trace/via item count drift")
    for item in trace_items:
        require(item.net in net_names and net_names[item.net] in GROUND_NETS,
                f"candidate routes unauthorized net code: {item.net}")
        net = net_names[item.net]
        if type(item).__name__ == "Segment":
            require(item.layer in {"F.Cu", "B.Cu"},
                    f"{net}: fanout segment outside outer copper layers")
            require(close(item.width, TRACK_WIDTH_MM, 1e-9),
                    f"{net}: unauthorized fanout width {item.width}")
            length = math.hypot(
                float(item.end.X) - float(item.start.X),
                float(item.end.Y) - float(item.start.Y),
            )
            require(length > 0.0, f"{net}: zero-length fanout segment")
            segments[net] += 1
            segment_layers[(net, item.layer)] += 1
            lengths[net] += length
        else:
            require(type(item).__name__ == "Via", "candidate contains unsupported trace item")
            require(close(item.size, VIA_DIAMETER_MM, 1e-9) and
                    close(item.drill, VIA_DRILL_MM, 1e-9) and
                    list(item.layers) == ["F.Cu", "B.Cu"],
                    f"{net}: unauthorized through-via geometry")
            vias[net] += 1
    require(dict(segments) == EXPECTED_SEGMENTS, f"segment-count drift: {segments}")
    require(dict(vias) == EXPECTED_VIAS, f"via-count drift: {vias}")
    require(dict(segment_layers) == EXPECTED_SEGMENT_LAYERS,
            f"fanout-layer inventory drift: {segment_layers}")
    for net, expected in EXPECTED_LENGTHS_MM.items():
        require(close(lengths[net], expected, 1e-6), f"{net}: fanout length drift")
    zones = {zone.name: zone for zone in candidate.zones}
    expected_keepout_names = {
        f"PCB_MAIN_{reference}_NO_COPPER_D8_AUTHORITY"
        for reference in ("H1", "H2", "H3", "H4")
    }
    require(len(candidate.zones) == len(zones) == 7 and
            set(zones) == set(GROUND_ZONE_SPECS) | expected_keepout_names,
            f"candidate zone/rule-area set drift: {sorted(zones)}")
    for name, spec in GROUND_ZONE_SPECS.items():
        zone = zones[name]
        require(zone.netName == spec["net"] and zone.layers == spec["layers"] and
                zone.connectPads == "yes" and close(zone.clearance, 0.10) and
                close(zone.minThickness, 0.15) and zone.keepoutSettings is None and
                not zone.filledPolygons,
                f"{name}: zone settings or committed fill-state drift")
        require(canonical_polygon(zone_points(zone)) == canonical_polygon(spec["points"]),
                f"{name}: shaped boundary drift")

    mounting, regions = authority_geometry()
    for reference, centre in mounting.items():
        zone = zones[f"PCB_MAIN_{reference}_NO_COPPER_D8_AUTHORITY"]
        keepout = zone.keepoutSettings
        require(zone.net == 0 and zone.netName == "" and zone.layers == ALL_COPPER_LAYERS and
                keepout is not None and keepout.tracks == "not_allowed" and
                keepout.vias == "not_allowed" and keepout.pads == "allowed" and
                keepout.copperpour == "not_allowed" and keepout.footprints == "allowed" and
                not zone.filledPolygons,
                f"{reference}: D8 rule-area settings drift")
        points = zone_points(zone)
        require(len(points) == 64, f"{reference}: D8 rule-area vertex-count drift")
        for x, y in points:
            require(close(math.hypot(x - centre[0], y - centre[1]), 4.010, 2e-6),
                    f"{reference}: D8 rule-area vertex radius drift")
        minimum_apothem = min(
            point_segment_distance(
                centre[0], centre[1], points[index][0], points[index][1],
                points[(index + 1) % len(points)][0], points[(index + 1) % len(points)][1],
            )
            for index in range(len(points))
        )
        require(minimum_apothem >= 4.005 - 1e-6,
                f"{reference}: D8 rule area does not conservatively enclose radius 4.0 mm")

    antenna = regions["KO_BLE_ANT_BOARD"]
    forbidden_hits: list[str] = []
    antenna_hits: list[str] = []
    mounting_hits: list[str] = []
    edge_hits: list[str] = []
    for item in trace_items:
        net = net_names[item.net]
        for region_name in FORBIDDEN_ZONE_OWNERS[net]:
            if trace_intersects_rectangle(item, regions[region_name]):
                forbidden_hits.append(f"{net}:{region_name}:{type(item).__name__}")
        if trace_intersects_rectangle(item, antenna):
            antenna_hits.append(f"{net}:{type(item).__name__}")
        if type(item).__name__ == "Segment":
            radius = float(item.width) / 2.0
            for reference, (x, y) in mounting.items():
                distance = point_segment_distance(
                    x, y, float(item.start.X), float(item.start.Y),
                    float(item.end.X), float(item.end.Y),
                ) - radius
                if distance < MOUNTING_KEEP_OUT_RADIUS_MM - 1e-9:
                    mounting_hits.append(f"{net}:{reference}:Segment")
            left = min(float(item.start.X), float(item.end.X)) - radius
            top = min(float(item.start.Y), float(item.end.Y)) - radius
            right = 110.0 - max(float(item.start.X), float(item.end.X)) - radius
            bottom = 75.0 - max(float(item.start.Y), float(item.end.Y)) - radius
        else:
            radius = float(item.size) / 2.0
            x, y = float(item.position.X), float(item.position.Y)
            for reference, (hx, hy) in mounting.items():
                if math.hypot(x - hx, y - hy) - radius < MOUNTING_KEEP_OUT_RADIUS_MM - 1e-9:
                    mounting_hits.append(f"{net}:{reference}:Via")
            left, top, right, bottom = x - radius, y - radius, 110.0 - x - radius, 75.0 - y - radius
        if min(left, top, right, bottom) < EDGE_CLEARANCE_MM - 1e-9:
            edge_hits.append(f"{net}:{type(item).__name__}")
    require(not forbidden_hits, f"foreign ground copper enters exclusive regions: {forbidden_hits}")
    require(not antenna_hits, f"ground copper enters BLE antenna keepout: {antenna_hits}")
    require(not mounting_hits, f"ground copper enters mounting D8 keepouts: {mounting_hits}")
    require(not edge_hits, f"ground copper violates 0.50 mm edge clearance: {edge_hits}")

    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    candidate_record = proposal.get("candidate", {})
    fanout_record = proposal.get("fanout_geometry", {})
    plane_record = proposal.get("domain_plane_geometry", {})
    mounting_record = proposal.get("mounting_copper_keepouts", {})
    clean_rule_record = proposal.get("clean_rule_reroute", {})
    review_request = proposal.get("review_request", {})
    boundary = proposal.get("decision_boundary", {})
    expected_domain_records = [
        {
            "net": "GND_DIGITAL", "zone_layer": "In1.Cu",
            "layer_function": "REFERENCE", "endpoints": 139,
            "fanout_vias": 138, "direct_pads": 1, "track_segments": 187,
            "track_length_mm": 120.38630718156, "failed_endpoints": 0,
        },
        {
            "net": "GND_MODEM", "zone_layer": "In4.Cu",
            "layer_function": "REFERENCE", "endpoints": 96,
            "fanout_vias": 95, "direct_pads": 1, "track_segments": 106,
            "track_length_mm": 88.636931803688, "failed_endpoints": 0,
        },
        {
            "net": "GND_MIC", "zone_layer": "In2.Cu",
            "layer_function": "POWER_DOMAINS", "endpoints": 22,
            "fanout_vias": 21, "direct_pads": 1, "track_segments": 26,
            "track_length_mm": 17.492640687119, "failed_endpoints": 0,
        },
    ]
    require(proposal.get("proposal_id") == "PCB-MAIN-GROUND-DOMAIN-ROUTING-001" and
            proposal.get("status") == "READY_FOR_MACHINE_GATE_AND_INDEPENDENT_HUMAN_REVIEW" and
            proposal.get("baseline", {}).get("board_sha256") == BASE_SHA256 and
            candidate_record.get("board_sha256") == CANDIDATE_SHA256 and
            candidate_record.get("track_segments") == 319 and
            candidate_record.get("vias") == 254 and
            candidate_record.get("copper_zones") == 3 and
            candidate_record.get("rule_areas") == 4 and
            close(candidate_record.get("track_length_mm", -1), sum(EXPECTED_LENGTHS_MM.values()), 1e-9),
            "ground-domain proposal identity, hash or inventory drift")
    require(fanout_record.get("neck_width_mm") == TRACK_WIDTH_MM and
            fanout_record.get("through_via_diameter_mm") == VIA_DIAMETER_MM and
            fanout_record.get("through_via_drill_mm") == VIA_DRILL_MM and
            fanout_record.get("through_via_layers") == ["F.Cu", "B.Cu"] and
            fanout_record.get("domains") == expected_domain_records and
            fanout_record.get("explicit_plane_tree_tracks_added") is False,
            "ground-domain proposal fanout geometry drift")
    require(plane_record.get("zone_names") == {
                "GND_DIGITAL": "PCB_MAIN_GND_DIGITAL_In1_Cu",
                "GND_MODEM": "PCB_MAIN_GND_MODEM_In4_Cu",
                "GND_MIC": "PCB_MAIN_GND_MIC_In2_Cu",
            } and {
                net: set(regions)
                for net, regions in plane_record.get("exclusive_zone_exclusions", {}).items()
            } == FORBIDDEN_ZONE_OWNERS and
            plane_record.get("unintended_cross_domain_joins") == 0,
            "ground-domain proposal plane-geometry authority drift")
    require(mounting_record.get("references") == ["H1", "H2", "H3", "H4"] and
            mounting_record.get("layers") == ALL_COPPER_LAYERS and
            mounting_record.get("polygon_vertices") == 64 and
            mounting_record.get("vertex_radius_mm") == 4.01 and
            mounting_record.get("minimum_edge_apothem_mm", 0.0) >= 4.005 and
            mounting_record.get("tracks_forbidden") is True and
            mounting_record.get("vias_forbidden") is True and
            mounting_record.get("copper_pours_forbidden") is True,
            "ground-domain proposal mounting keepout drift")
    require(clean_rule_record == {
                "copper_clearance_mm": 0.2,
                "finished_hole_clearance_mm": 0.25,
                "previous_candidate_rejected": True,
                "previous_candidate_clearance_errors": 49,
                "previous_candidate_additional_hole_clearance_errors": 21,
                "baseline_hole_clearance_errors": 4,
                "candidate_hole_clearance_errors": 4,
                "new_clearance_errors": 0,
                "new_hole_clearance_errors": 0,
            }, "ground-domain clean-rule reroute evidence drift")
    require(review_request.get("accept_value") == "ACCEPT_GROUND_DOMAIN_ROUTING_SUBGATE" and
            review_request.get("reject_value") == "REJECT_GROUND_DOMAIN_ROUTING_SUBGATE",
            "ground-domain review decision vocabulary drift")
    require(boundary == {
                "proposal_only": True,
                "applied_to_authoritative_board": False,
                "routing_complete": False,
                "return_path_review_complete": False,
                "si_review_complete": False,
                "pi_review_complete": False,
                "review_b_complete": False,
                "manufacturing_release": False,
            }, "ground-domain decision boundary drift")

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    approval_record = APPROVAL_RECORD.read_text(encoding="utf-8")
    mapping = json.loads(REVIEW_MAPPING.read_text(encoding="utf-8"))
    expected_gate = {
        "pcb_native_run_id": 35439569309,
        "pcb_native_conclusion": "success",
        "ci_run_id": 35439569334,
        "ci_conclusion": "success",
    }
    require(approval.get("schema_version") ==
            "dioneya.pcb-main-ground-domain-routing-approval.v1" and
            approval.get("configuration") == "EVT-PRE-20 Rev.A" and
            approval.get("proposal_id") == "PCB-MAIN-GROUND-DOMAIN-ROUTING-001" and
            approval.get("reviewer") == "Скиф" and
            approval.get("decision_date") == "2026-09-19" and
            approval.get("decision") == "ACCEPT_GROUND_DOMAIN_ROUTING_SUBGATE" and
            approval.get("decision_input") == "подтверждаю и продолжаем" and
            approval.get("decision_input_interpretation") ==
            "ACCEPT_VALUE_REQUESTED_IN_IMMEDIATELY_PRECEDING_REVIEW_REQUEST" and
            approval.get("reviewed_github_commit_sha") == REVIEWED_GITHUB_COMMIT and
            approval.get("reviewed_tree_sha") == REVIEWED_TREE and
            approval.get("review_mapping") == str(REVIEW_MAPPING.relative_to(ROOT)) and
            approval.get("reviewed_proposal_sha256") == PROPOSAL_SHA256 and
            approval.get("reviewed_proposal_record_sha256") == PROPOSAL_RECORD_SHA256 and
            approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256 and
            approval.get("machine_gate") == expected_gate,
            "ground-domain approval identity or reviewed evidence drift")
    require(approval.get("authorization") == {
                "apply_exact_hash_bound_fanout_vias_rule_areas_and_shaped_planes": True,
                "continue_signal_and_power_routing_engineering": True,
                "alter_reviewed_ground_geometry_without_new_controlled_review": False,
                "routing_complete": False,
                "return_path_review_complete": False,
                "si_review_complete": False,
                "pi_review_complete": False,
                "review_b_complete": False,
                "cam_or_manufacturing_release": False,
            }, "ground-domain approval authorization boundary drift")
    for token in (
        "ACCEPT_GROUND_DOMAIN_ROUTING_SUBGATE",
        REVIEWED_GITHUB_COMMIT,
        REVIEWED_TREE,
        PROPOSAL_SHA256,
        PROPOSAL_RECORD_SHA256,
        CANDIDATE_SHA256,
        "PCB Native Gate `35439569309`: `success`",
        "CI `35439569334`: `success`",
        "does not close PCB-MAIN Review B",
    ):
        require(token in approval_record,
                f"ground-domain approval record missing binding token: {token}")
    require(mapping == {
                "schema_version": "dioneya.pcb-main-ground-domain-routing-review-commit-mapping.v1",
                "configuration": "EVT-PRE-20 Rev.A",
                "proposal_id": "PCB-MAIN-GROUND-DOMAIN-ROUTING-001",
                "reviewed_github_commit_sha": REVIEWED_GITHUB_COMMIT,
                "reviewed_tree_sha": REVIEWED_TREE,
                "proposal_path": str(PROPOSAL.relative_to(ROOT)),
                "proposal_blob_sha": PROPOSAL_BLOB,
                "proposal_sha256": PROPOSAL_SHA256,
                "proposal_record_path": str(PROPOSAL_RECORD.relative_to(ROOT)),
                "proposal_record_blob_sha": PROPOSAL_RECORD_BLOB,
                "proposal_record_sha256": PROPOSAL_RECORD_SHA256,
                "candidate_board_path": str(CANDIDATE_BOARD.relative_to(ROOT)),
                "candidate_board_blob_sha": CANDIDATE_BLOB,
                "candidate_board_sha256": CANDIDATE_SHA256,
                "audit_path": str(Path(__file__).resolve().relative_to(ROOT)),
                "audit_blob_sha": AUDIT_BLOB,
                "machine_gate": expected_gate,
                "equivalence": "EXACT_REVIEWED_TREE_AND_BLOBS",
                "transport": "GITHUB_APP_GIT_DATABASE_API",
                "review_b_complete": False,
                "manufacturing_release": False,
            }, "ground-domain reviewed commit mapping drift")

    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    require(application == {
                "schema_version": "dioneya.pcb-main-ground-domain-routing-application.v1",
                "configuration": "EVT-PRE-20 Rev.A",
                "proposal_id": "PCB-MAIN-GROUND-DOMAIN-ROUTING-001",
                "approval": str(APPROVAL.relative_to(ROOT)),
                "application_date": "2026-09-19",
                "reviewed_proposal_commit_sha": REVIEWED_GITHUB_COMMIT,
                "approval_commit_sha": "cf768952bb870c6284563908714d043274852354",
                "approval_sha256": "a3dbab5b0de1b5bc6a459f8d18d2ffafbe7da197170894839960d79dc5601c54",
                "reviewed_candidate_board_sha256": CANDIDATE_SHA256,
                "decision": "ACCEPT_GROUND_DOMAIN_ROUTING_SUBGATE",
                "scope": "EXACT_GROUND_DOMAIN_FANOUT_VIAS_RULE_AREAS_AND_SHAPED_PLANES_ONLY",
                "historical_baseline": {
                    "board": str(BASE_BOARD.relative_to(ROOT)),
                    "board_sha256": BASE_SHA256,
                    "track_segments": 0,
                    "vias": 0,
                    "copper_zones": 0,
                },
                "applied": {
                    "board": str(ACTIVE_BOARD.relative_to(ROOT)),
                    "board_sha256": CANDIDATE_SHA256,
                    "exact_candidate_byte_identity": True,
                    "track_segments": 319,
                    "track_length_mm": 226.515879672367,
                    "vias": 254,
                    "copper_zones": 3,
                    "mounting_rule_areas": 4,
                    "committed_zone_fill_state":
                    "UNFILLED_CI_AND_REVIEW_TOOLS_MUST_REFILL_BEFORE_DRC",
                    "native_connectivity_baseline_to_candidate": [718, 464],
                    "new_comparative_drc_error_counts": {},
                },
                "status":
                "APPLIED_ACCEPTED_GROUND_DOMAIN_SUBGATE_ROUTING_ENGINEERING_CONTINUES",
                "signal_and_power_routing_continuation_authorized": True,
                "routing_complete": False,
                "return_path_review_complete": False,
                "si_review_complete": False,
                "pi_review_complete": False,
                "review_b_complete": False,
                "cam_or_manufacturing_release": False,
            }, "ground-domain application binding or release boundary drift")

    return {
        "schema_version": "dioneya.pcb-main-ground-domain-routing-candidate-audit.v1",
        "proposal_id": "PCB-MAIN-GROUND-DOMAIN-ROUTING-001",
        "status": "PASS_ACCEPTED_SUBGATE_APPLIED",
        "base_board_sha256": BASE_SHA256,
        "candidate_board_sha256": CANDIDATE_SHA256,
        "active_board_sha256": ACTIVE_BOARD_SHA256,
        "track_segments": sum(segments.values()),
        "track_length_mm": round(sum(lengths.values()), 12),
        "vias": sum(vias.values()),
        "copper_zones": 3,
        "mounting_rule_areas": 4,
        "domain_segments": dict(sorted(segments.items())),
        "domain_vias": dict(sorted(vias.items())),
        "foreign_copper_in_exclusive_regions": len(forbidden_hits),
        "ground_copper_in_ble_keepout": len(antenna_hits),
        "ground_copper_in_mounting_keepouts": len(mounting_hits),
        "ground_copper_edge_violations": len(edge_hits),
        "approval": {
            "reviewer": approval["reviewer"],
            "decision_date": approval["decision_date"],
            "decision": approval["decision"],
            "reviewed_github_commit_sha": approval["reviewed_github_commit_sha"],
            "reviewed_tree_sha": approval["reviewed_tree_sha"],
        },
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
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("PCB-MAIN ground-domain routing candidate audit: PASS_ACCEPTED_SUBGATE_APPLIED")
    print("segments=319 vias=254 copper_zones=3 mounting_rule_areas=4")
    print("exclusive_zone_hits=0 ble_keepout_hits=0 mounting_keepout_hits=0 edge_hits=0")
    if args.kicad_connectivity:
        connectivity = report["native_connectivity"]
        print(
            "native_connectivity="
            f"{connectivity['baseline_unconnected_count']}->"
            f"{connectivity['candidate_unconnected_count']} reduction=254 PASS"
        )
    if args.base_drc is not None:
        print("comparative_drc=PASS_NO_NEW_ERROR_AND_NO_NEW_GROUND_GEOMETRY_VIOLATION")
    print("routing_complete=false review_b=false manufacturing_release=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
