#!/usr/bin/env python3
"""Audit PCB-PWR dual-buck power-stage ECO-002 candidate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from kiutils.board import Board

import audit_pcb_pwr_buck_placement_eco_001_candidate_rev_a as placement_eco
from audit_pcb_pwr_routing_authority_rev_a import ref_of, semantic_board_sha256
from generate_pcb_pwr_buck_power_stage_eco_002_candidate_rev_a import (
    PLACEMENT_REPLACEMENTS,
    ROUTES,
)


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-POWER-STAGE-ECO-002"
BASE = CANDIDATE_DIR / "PCB-PWR_BUCK_POWER_STAGE_ECO_002_BASE_REV_A.kicad_pcb"
CANDIDATE = CANDIDATE_DIR / "PCB-PWR_BUCK_POWER_STAGE_ECO_002_CANDIDATE_REV_A.kicad_pcb"
ACTIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
REVIEW = ROOT / "hardware/reviews/PCB_PWR_BUCK_POWER_STAGE_ECO_002_CANDIDATE_REV_A.json"
GENERATOR = ROOT / "tools/generate_pcb_pwr_buck_power_stage_eco_002_candidate_rev_a.py"
ROUTING_RULES = ROOT / "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv"
STACKUP_BASIS = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"
CURRENT_BASIS = ROOT / "hardware/PCB_PWR_CURRENT_GEOMETRY_BASIS_REV_A.csv"

BASE_SHA256 = "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c"
CANDIDATE_SHA256 = "dd4c38c191b3087be8a58e9a4b7de4f7974de89797fba4583edbe674340ebda8"
BASE_SEMANTIC_SHA256 = "f7a659d0740e78d40eddae7016724bd8e616baf9fb425f06ace70ec9acca4d3d"
CANDIDATE_SEMANTIC_SHA256 = "78d8ac5b4ccf731f9d5de31a5e379a97e695d19fbed08fe6142f9a2a0e57fe40"
GENERATOR_SHA256 = "ef9de2a8bf576e2625b8ee0f680237ea2f3dd177fd82fcfa14c3c44e9be5dbfd"
ROUTING_RULES_SHA256 = "551a9691d51fd9451bf60193d79b8ed244d6b61fd5ec9c844a15050710f48988"
STACKUP_BASIS_SHA256 = "41733d7d27e2c3ab831e602ee81b072146944da0a5efe8a2c805eeed46ecd1ca"
CURRENT_BASIS_SHA256 = "4cecbe529987146078ce233d600ed047495a50d1228407e94b0380f88ca56cb2"

EXPECTED_POSES = {
    "U3": ((55.0, 14.0, 0.0), (55.0, 14.0, 90.0)),
    "U4": ((55.0, 42.0, 0.0), (55.0, 42.0, 90.0)),
    "C4": ((54.575, 16.4, 180.0), (57.8, 14.03, 270.0)),
    "C6": ((54.575, 44.4, 180.0), (57.8, 42.03, 270.0)),
    "C20": ((52.4, 14.0, 90.0), (52.35, 14.0, 90.0)),
    "C21": ((52.4, 42.0, 90.0), (52.35, 42.0, 90.0)),
    "L1": ((60.75, 14.0, 180.0), (62.5, 14.0, 180.0)),
    "L2": ((60.75, 42.0, 180.0), (62.5, 42.0, 180.0)),
}
CHANNELS = {
    "3V8": {"controller": "U3", "bootstrap": "C4", "input": "C20", "inductor": "L1"},
    "3V3": {"controller": "U4", "bootstrap": "C6", "input": "C21", "inductor": "L2"},
}
SW_LOWER_BOUND_PROFILE_MM = ((3.35, 2.1),)
CURRENT_A = 4.0
RESISTIVITY_70C_OHM_M = 2.062766e-8


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def point(value: Any) -> tuple[float, float]:
    return float(value.X), float(value.Y)


def pose_of(footprint: Any) -> tuple[float, float, float]:
    return (
        float(footprint.position.X),
        float(footprint.position.Y),
        float(footprint.position.angle or 0.0) % 360.0,
    )


def without_pose(footprint: Any) -> dict[str, Any]:
    return {key: value for key, value in footprint.__dict__.items() if key != "position"}


def rotate_clockwise(value: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    x, y = value
    return x * math.cos(angle) + y * math.sin(angle), -x * math.sin(angle) + y * math.cos(angle)


def pad_positions(board: Board, reference: str, number: str) -> list[tuple[float, float]]:
    footprint = next(item for item in board.footprints if ref_of(item) == reference)
    result: list[tuple[float, float]] = []
    for pad in footprint.pads:
        if str(pad.number) != number:
            continue
        local = rotate_clockwise(point(pad.position), float(footprint.position.angle or 0.0))
        result.append((float(footprint.position.X) + local[0], float(footprint.position.Y) + local[1]))
    require(result, f"{reference}.{number}: pad missing")
    return result


def minimum_pad_distance(board: Board, first_ref: str, first_pad: str,
                         second_ref: str, second_pad: str) -> float:
    return min(
        math.dist(first, second)
        for first in pad_positions(board, first_ref, first_pad)
        for second in pad_positions(board, second_ref, second_pad)
    )


def topology_metrics(candidate: Board) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, channel in CHANNELS.items():
        controller = channel["controller"]
        bootstrap = channel["bootstrap"]
        input_cap = channel["input"]
        inductor = channel["inductor"]
        metrics = {
            "boot_to_cboot_mm": minimum_pad_distance(candidate, controller, "4", bootstrap, "1"),
            "sw_to_cboot_mm": minimum_pad_distance(candidate, controller, "3", bootstrap, "2"),
            "sw_to_inductor_mm": minimum_pad_distance(candidate, controller, "3", inductor, "1"),
            "vin_to_input_cap_mm": minimum_pad_distance(candidate, controller, "1", input_cap, "1"),
            "gnd_to_input_cap_mm": minimum_pad_distance(candidate, controller, "2", input_cap, "2"),
        }
        limits = {
            "boot_to_cboot_mm": 1.80,
            "sw_to_cboot_mm": 1.75,
            "sw_to_inductor_mm": 4.25,
            "vin_to_input_cap_mm": 1.60,
            "gnd_to_input_cap_mm": 2.80,
        }
        for metric, limit in limits.items():
            require(metrics[metric] <= limit + 1e-9, f"{name}: {metric} exceeds {limit} mm")
        result[name] = {
            "candidate_mm": {key: round(value, 6) for key, value in metrics.items()},
            "maximum_mm": limits,
        }
    return result


def cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
    return (
        min(a[0], b[0]) - 1e-9 <= c[0] <= max(a[0], b[0]) + 1e-9
        and min(a[1], b[1]) - 1e-9 <= c[1] <= max(a[1], b[1]) + 1e-9
        and abs(cross(a, b, c)) <= 1e-9
    )


def segments_intersect(a: tuple[float, float], b: tuple[float, float],
                       c: tuple[float, float], d: tuple[float, float]) -> bool:
    values = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    proper = (
        ((values[0] > 0 > values[1]) or (values[1] > 0 > values[0]))
        and ((values[2] > 0 > values[3]) or (values[3] > 0 > values[2]))
    )
    return proper or any((
        abs(values[0]) <= 1e-9 and on_segment(a, b, c),
        abs(values[1]) <= 1e-9 and on_segment(a, b, d),
        abs(values[2]) <= 1e-9 and on_segment(c, d, a),
        abs(values[3]) <= 1e-9 and on_segment(c, d, b),
    ))


def point_segment_distance(value: tuple[float, float], start: tuple[float, float],
                           end: tuple[float, float]) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    magnitude = dx * dx + dy * dy
    if magnitude == 0:
        return math.dist(value, start)
    ratio = max(0.0, min(1.0, ((value[0] - start[0]) * dx + (value[1] - start[1]) * dy) / magnitude))
    return math.dist(value, (start[0] + ratio * dx, start[1] + ratio * dy))


def segment_distance(a: tuple[float, float], b: tuple[float, float],
                     c: tuple[float, float], d: tuple[float, float]) -> float:
    if segments_intersect(a, b, c, d):
        return 0.0
    return min(
        point_segment_distance(a, c, d), point_segment_distance(b, c, d),
        point_segment_distance(c, a, b), point_segment_distance(d, a, b),
    )


def pad_rectangle(footprint: Any, pad: Any) -> tuple[float, float, float, float]:
    footprint_angle = float(footprint.position.angle or 0.0)
    local_center = rotate_clockwise(point(pad.position), footprint_angle)
    center = (float(footprint.position.X) + local_center[0], float(footprint.position.Y) + local_center[1])
    pad_angle = footprint_angle + float(pad.position.angle or 0.0)
    half_x, half_y = float(pad.size.X) / 2.0, float(pad.size.Y) / 2.0
    corners = [rotate_clockwise((x, y), pad_angle) for x in (-half_x, half_x) for y in (-half_y, half_y)]
    xs = [center[0] + value[0] for value in corners]
    ys = [center[1] + value[1] for value in corners]
    return min(xs), min(ys), max(xs), max(ys)


def segment_rectangle_distance(start: tuple[float, float], end: tuple[float, float],
                               rectangle: tuple[float, float, float, float]) -> float:
    xmin, ymin, xmax, ymax = rectangle
    if any(xmin <= value[0] <= xmax and ymin <= value[1] <= ymax for value in (start, end)):
        return 0.0
    corners = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
    return min(segment_distance(start, end, first, second)
               for first, second in zip(corners, corners[1:] + corners[:1]))


def route_clearances() -> dict[str, float]:
    with ROUTING_RULES.open(encoding="utf-8-sig", newline="") as stream:
        return {row["Net_Name"]: float(row["Clearance_mm"]) for row in csv.DictReader(stream)}


def copper_clearance_screen(base: Board, candidate: Board, added: list[Any],
                            net_names: dict[int, str]) -> dict[str, object]:
    rules = route_clearances()
    minimum_margin = math.inf
    minimum_clearance = math.inf
    limiting_pair = ""
    by_route_family = {
        "SW": {"clearance": math.inf, "margin": math.inf},
        "BOOT": {"clearance": math.inf, "margin": math.inf},
    }
    for index, item in enumerate(added):
        net_name = net_names[int(item.net)]
        start, end, width = point(item.start), point(item.end), float(item.width)
        for footprint in candidate.footprints:
            for pad in footprint.pads:
                if not ({"F.Cu", "*.Cu"} & {str(layer) for layer in pad.layers}):
                    continue
                pad_net = str(pad.net.name) if pad.net is not None else ""
                if pad_net == net_name:
                    continue
                clearance = segment_rectangle_distance(start, end, pad_rectangle(footprint, pad)) - width / 2.0
                required = max(rules.get(net_name, 0.25), rules.get(pad_net, 0.25))
                margin = clearance - required
                family = "SW" if net_name.startswith("SW_") else "BOOT"
                by_route_family[family]["clearance"] = min(
                    by_route_family[family]["clearance"], clearance
                )
                by_route_family[family]["margin"] = min(
                    by_route_family[family]["margin"], margin
                )
                if margin < minimum_margin:
                    minimum_margin, minimum_clearance = margin, clearance
                    limiting_pair = f"{net_name} trace / {ref_of(footprint)}.{pad.number} {pad_net or 'NO_NET'}"
        retained_predecessor = [
            predecessor for predecessor in base.traceItems
            if net_names[int(predecessor.net)] not in {"BOOT_3V8", "BOOT_3V3"}
        ]
        foreign_tracks = retained_predecessor + added[index + 1:]
        for foreign in foreign_tracks:
            foreign_net = net_names[int(foreign.net)]
            if foreign_net == net_name:
                continue
            clearance = segment_distance(start, end, point(foreign.start), point(foreign.end)) - (width + float(foreign.width)) / 2.0
            required = max(rules.get(net_name, 0.25), rules.get(foreign_net, 0.25))
            margin = clearance - required
            family = "SW" if net_name.startswith("SW_") else "BOOT"
            by_route_family[family]["clearance"] = min(
                by_route_family[family]["clearance"], clearance
            )
            by_route_family[family]["margin"] = min(
                by_route_family[family]["margin"], margin
            )
            if margin < minimum_margin:
                minimum_margin, minimum_clearance = margin, clearance
                limiting_pair = f"{net_name} trace / {foreign_net} trace"
    require(minimum_margin >= -1e-6,
            f"candidate foreign-copper clearance margin {minimum_margin:.6f} mm")
    return {
        "status": "PASS_NETCLASS_AWARE_FOREIGN_COPPER_CLEARANCE",
        "minimum_edge_clearance_mm": round(minimum_clearance, 6),
        "minimum_margin_mm": round(max(0.0, minimum_margin), 6),
        "limiting_pair": limiting_pair,
        "switch_node_minimum_edge_clearance_mm": round(
            by_route_family["SW"]["clearance"], 6
        ),
        "switch_node_minimum_margin_mm": round(
            max(0.0, by_route_family["SW"]["margin"]), 6
        ),
        "bootstrap_minimum_edge_clearance_mm": round(
            by_route_family["BOOT"]["clearance"], 6
        ),
        "bootstrap_minimum_margin_mm": round(
            max(0.0, by_route_family["BOOT"]["margin"]), 6
        ),
    }


def track_signature(item: Any, net_names: dict[int, str]) -> tuple[object, ...]:
    return (net_names[int(item.net)], point(item.start), point(item.end), float(item.width), str(item.layer))


def pad_connection_screen(candidate: Board, added: list[Any],
                          net_names: dict[int, str]) -> dict[str, object]:
    required_pads = {
        "BOOT_3V8": (("U3", "4"), ("C4", "1")),
        "BOOT_3V3": (("U4", "4"), ("C6", "1")),
        "SW_3V8": (("U3", "3"), ("C4", "2"), ("L1", "1")),
        "SW_3V3": (("U4", "3"), ("C6", "2"), ("L2", "1")),
    }
    by_net: dict[str, list[Any]] = {name: [] for name in required_pads}
    for item in added:
        by_net[net_names[int(item.net)]].append(item)
    result: dict[str, object] = {}
    for net_name, pads in required_pads.items():
        tracks = by_net[net_name]
        require(tracks, f"{net_name}: route missing")
        contacts: dict[str, float] = {}
        for reference, pad_number in pads:
            footprint = next(
                item for item in candidate.footprints if ref_of(item) == reference
            )
            pad_items = [
                item for item in footprint.pads if str(item.number) == pad_number
            ]
            contact = min(
                segment_rectangle_distance(
                    point(track.start), point(track.end),
                    pad_rectangle(footprint, pad),
                ) - float(track.width) / 2.0
                for track in tracks for pad in pad_items
            )
            require(contact <= 1e-9,
                    f"{net_name}: no copper overlap with {reference}.{pad_number}")
            contacts[f"{reference}.{pad_number}"] = round(-contact, 6)
        for first, second in zip(tracks, tracks[1:]):
            require(
                segment_distance(
                    point(first.start), point(first.end),
                    point(second.start), point(second.end),
                ) <= (float(first.width) + float(second.width)) / 2.0 + 1e-9,
                f"{net_name}: route segments are not copper-connected",
            )
        if net_name.startswith("SW_"):
            require(len(tracks) == 1 and math.isclose(float(tracks[0].width), 2.1),
                    f"{net_name}: external routed width is not uniformly 2.1 mm")
        result[net_name] = {
            "segments": len(tracks),
            "pad_copper_overlap_mm": contacts,
        }
    return {
        "status": "PASS_ALL_REQUIRED_PADS_COPPER_CONNECTED_NO_EXTERNAL_SW_NECK",
        "nets": result,
    }


def current_screen() -> dict[str, object]:
    def resistance(copper_um: float) -> float:
        return sum(
            RESISTIVITY_70C_OHM_M * (length_mm * 1e-3)
            / ((width_mm * 1e-3) * (copper_um * 1e-6))
            for length_mm, width_mm in SW_LOWER_BOUND_PROFILE_MM
        )

    stackup = json.loads(STACKUP_BASIS.read_text(encoding="utf-8"))
    conservative_width = next(
        float(item["minimum_width_mm"])
        for item in stackup["current_width_screens"]
        if float(item["current_a"]) == CURRENT_A
    )
    selected_width = next(
        float(item["selected_width_mm"])
        for item in stackup["numeric_classes"]
        if item["name"] == "PWR_SWITCH_4A"
    )
    with CURRENT_BASIS.open(encoding="utf-8-sig", newline="") as stream:
        target_row = next(
            row for row in csv.DictReader(stream)
            if row["Path_class"] == "BUCK_RATED_4A"
        )
    target_minimum_width = float(target_row["Minimum_width_or_neck_mm"])
    screen_copper_um = float(
        stackup["calculation_assumptions"]["screen_finished_copper_um"]
    )
    target_copper_um = float(target_row["Copper_um"])
    screen_35 = resistance(screen_copper_um)
    target_70 = resistance(target_copper_um)
    require(
        SW_LOWER_BOUND_PROFILE_MM[0] == (3.35, 2.1)
        and math.isclose(sum(length for length, _ in SW_LOWER_BOUND_PROFILE_MM), 3.35, abs_tol=1e-9)
        and math.isclose(conservative_width, 2.032863, abs_tol=1e-9)
        and math.isclose(selected_width, 2.1, abs_tol=1e-9)
        and math.isclose(target_minimum_width, 1.5, abs_tol=1e-9)
        and min(width for _, width in SW_LOWER_BOUND_PROFILE_MM)
        >= max(conservative_width, target_minimum_width),
        "ECO-002 switch-node pad-entry EVT current screen failed",
    )
    return {
        "status": "PASS_EVT_CALCULATED_PAD_ENTRY_PHYSICAL_PLUS70C_VALIDATION_REQUIRED",
        "current_a": CURRENT_A,
        "temperature_c": 70.0,
        "lower_bound_series_profile": [
            {"length_mm": length, "width_mm": width}
            for length, width in SW_LOWER_BOUND_PROFILE_MM
        ],
        "minimum_routed_width_mm": 2.1,
        "narrowest_external_neck_length_mm": 0.0,
        "device_pad_limited_transition_only": True,
        "conservative_35um_minimum_width_mm": conservative_width,
        "project_selected_switch_width_mm": selected_width,
        "target_70um_minimum_width_or_neck_mm": target_minimum_width,
        "numeric_width_requirements_pass": True,
        "screen_35um": {
            "resistance_mohm": round(screen_35 * 1000.0, 6),
            "drop_mv": round(screen_35 * CURRENT_A * 1000.0, 6),
            "loss_mw": round(screen_35 * CURRENT_A * CURRENT_A * 1000.0, 6),
        },
        "target_70um": {
            "resistance_mohm": round(target_70 * 1000.0, 6),
            "drop_mv": round(target_70 * CURRENT_A * 1000.0, 6),
            "loss_mw": round(target_70 * CURRENT_A * CURRENT_A * 1000.0, 6),
        },
        "physical_plus70c_validation_required": True,
    }


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
    require(not (candidate_fp - base_fp), "ECO-002 introduces DRC fingerprint counts")
    require(base_unconnected == 121 and candidate_unconnected == 117,
            "ECO-002 must close exactly four switch-node unconnected items")
    require(candidate_violations <= base_violations,
            "ECO-002 increases total DRC violations")
    return {
        "status": "PASS_NO_NEW_DRC_FINGERPRINT_COUNTS_EXACT_FOUR_CONNECTION_REDUCTION",
        "base_violations": base_violations,
        "candidate_violations": candidate_violations,
        "base_unconnected": base_unconnected,
        "candidate_unconnected": candidate_unconnected,
        "new_drc_fingerprint_counts": 0,
    }


def audit(drc_base: Path | None = None, drc_candidate: Path | None = None) -> dict[str, object]:
    require(sha256(BASE) == BASE_SHA256 and sha256(ACTIVE) == BASE_SHA256,
            "ECO-002 base or authoritative PCB-PWR drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256, "ECO-002 candidate SHA-256 drift")
    require(
        sha256(GENERATOR) == GENERATOR_SHA256
        and sha256(ROUTING_RULES) == ROUTING_RULES_SHA256
        and sha256(STACKUP_BASIS) == STACKUP_BASIS_SHA256
        and sha256(CURRENT_BASIS) == CURRENT_BASIS_SHA256,
        "ECO-002 source binding drift",
    )
    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    require(semantic_board_sha256(base) == BASE_SEMANTIC_SHA256
            and semantic_board_sha256(candidate) == CANDIDATE_SEMANTIC_SHA256,
            "ECO-002 semantic identity drift")

    base_footprints = {ref_of(item): item for item in base.footprints}
    candidate_footprints = {ref_of(item): item for item in candidate.footprints}
    require(base_footprints.keys() == candidate_footprints.keys(), "footprint set drift")
    changed: set[str] = set()
    for reference, first in base_footprints.items():
        second = candidate_footprints[reference]
        require(without_pose(first) == without_pose(second), f"{reference}: non-pose data changed")
        if pose_of(first) != pose_of(second):
            changed.add(reference)
    require(changed == set(PLACEMENT_REPLACEMENTS) == set(EXPECTED_POSES),
            f"unexpected moved footprints: {sorted(changed)}")
    for reference, (old, new) in EXPECTED_POSES.items():
        require(pose_of(base_footprints[reference]) == old, f"{reference}: base pose drift")
        require(pose_of(candidate_footprints[reference]) == new, f"{reference}: candidate pose drift")

    for field in ("version", "generator", "general", "paper", "titleBlock", "layers",
                  "setup", "properties", "nets", "zones", "graphicItems", "dimensions",
                  "targets", "groups"):
        require(getattr(base, field) == getattr(candidate, field),
                f"candidate changes non-ECO board field {field}")
    require(len(base.traceItems) == 8 and len(candidate.traceItems) == 14
            and len(base.zones) == len(candidate.zones) == 0,
            "ECO-002 copper inventory drift")

    net_names = {int(net.number): str(net.name) for net in candidate.nets}
    base_signatures = [track_signature(item, net_names) for item in base.traceItems]
    removed = [item for item in base_signatures if item[0] in {"BOOT_3V8", "BOOT_3V3"}]
    require(len(removed) == 2, "accepted BOOT predecessor inventory drift")
    retained = [item for item in base_signatures if item[0] not in {"BOOT_3V8", "BOOT_3V3"}]
    require([track_signature(item, net_names) for item in candidate.traceItems[:6]] == retained,
            "ECO-002 changes unrelated accepted copper")

    expected = [
        (net_name, start, end, float(width), "F.Cu")
        for net_name, route in ROUTES.items()
        for start, end, width in route["segments"]
    ]
    added = candidate.traceItems[6:]
    require(len(added) == len(expected) == 8, "ECO-002 added-route inventory drift")
    for index, (item, identity) in enumerate(zip(added, expected, strict=True), start=1):
        require(track_signature(item, net_names) == identity,
                f"ECO-002 segment {index} identity or geometry drift")

    clearance = copper_clearance_screen(base, candidate, added, net_names)
    connections = pad_connection_screen(candidate, added, net_names)
    placement = placement_eco.fitted_clearance(candidate)
    require(placement["minimum_clearance_mm"] >= 0.2,
            "ECO-002 fitted placement clearance below 0.20 mm")
    topology = topology_metrics(candidate)
    thermal = current_screen()

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    require(
        review["proposal_id"] == "PCB-PWR-BUCK-POWER-STAGE-ECO-002"
        and review["status"] == "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_COMPARATIVE_DRC"
        and review["base"]["sha256"] == BASE_SHA256
        and review["candidate"]["sha256"] == CANDIDATE_SHA256
        and review["candidate"]["trace_items"] == 14
        and review["candidate"]["added_segments"] == 8
        and math.isclose(
            float(review["candidate"]["minimum_switch_node_foreign_copper_edge_clearance_mm"]),
            float(clearance["switch_node_minimum_edge_clearance_mm"]),
            abs_tol=1e-9,
        )
        and review["source_binding"]["generator_sha256"] == GENERATOR_SHA256
        and review["pad_entry_disposition"]["calculated_evt_screen_pass"] is True
        and review["pad_entry_disposition"]["external_neck_eliminated"] is True
        and math.isclose(
            float(review["pad_entry_disposition"]["eco_002_minimum_external_routed_width_mm"]),
            2.1,
            abs_tol=1e-9,
        )
        and review["pad_entry_disposition"]["numeric_width_requirements_pass"] is True
        and review["pad_entry_disposition"]["physical_plus70c_validation_required"] is True
        and review["invariants"]["authoritative_board_modified"] is False
        and review["machine_gate"]["complete"] is False
        and review["human_gate"]["accepted"] is False
        and review["application_authorized"] is False
        and review["manufacturing_release"] is False,
        "ECO-002 proposal boundary drift",
    )

    report: dict[str, object] = {
        "status": "PASS_STATIC_ECO_002_COMMIT_BOUND_KICAD9_GATE_PENDING",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "candidate_semantic_sha256": CANDIDATE_SEMANTIC_SHA256,
        "moved_footprints": sorted(changed),
        "removed_boot_segments": 2,
        "retained_predecessor_segments": 6,
        "added_segments": 8,
        "placement_clearance": placement,
        "topology_metrics": topology,
        "copper_clearance": clearance,
        "pad_connections": connections,
        "pad_entry_current_screen": thermal,
        "candidate_005_superseded": True,
        "authoritative_board_modified": False,
        "application_authorized": False,
        "physical_evt_validation_required": True,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_candidate is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_candidate is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_candidate)
        report["status"] = "PASS_COMMIT_BOUND_KICAD9_GATE_HUMAN_SUBGATE_PENDING"
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
    print("PCB-PWR buck power-stage ECO-002 candidate audit:", report["status"])
    print(json.dumps(report["pad_entry_current_screen"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
