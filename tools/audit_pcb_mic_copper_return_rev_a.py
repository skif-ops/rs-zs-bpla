#!/usr/bin/env python3
"""Measure PCB-MIC power/return topology for independent human Review B.

The parser in this tool is intentionally standard-library-only and does not use
pcbnew, kiutils, the board generator, or the CAM preflight parser.  It builds a
layer-aware graph directly from the committed KiCad S-expression, binds either a
signed Review-A board or an explicit post-ECO candidate, and optionally checks the
emitted B.Cu Gerber against the declared explicit-routing-only copper model.

A successful execution means that the topology was measured reproducibly.  It
does not sign Review B and it never grants manufacturing release.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import itertools
import json
import math
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_pcb"
STATUS = ROOT / "hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json"
REVIEW_PACKET = ROOT / "hardware/reviews/PCB_MIC_REVIEW_B_COPPER_RETURN_REV_A.md"
DEFAULT_OUTPUT = ROOT / "artifacts/kicad-native/PCB-MIC/copper_return_review_audit.json"
TDK_AUTHORITY = ROOT / "hardware/PCB_MAIN_AUDIO_LOGIC_AUTHORITY_REV_A.md"
GENERATOR = ROOT / "tools/generate_pcb_mic_clean_rev_a.py"
NATIVE_WORKFLOW = ROOT / ".github/workflows/pcb-native.yml"

TDK_DATASHEET = {
    "document": "TDK T5838 DS-000383 Revision 1.2",
    "release_date": "2025-09-04",
    "sha256": "5befb710bfe7a415cdc1aba41ebc18b484d7f9fc320ce15a7481507531cf58a4",
    "authority": str(TDK_AUTHORITY.relative_to(ROOT)),
}

Point = tuple[float, float]
GraphNode = tuple[Any, ...]


@dataclass(frozen=True)
class Segment:
    net: str
    layer: str
    start: Point
    end: Point
    width: float


@dataclass(frozen=True)
class Via:
    net: str
    point: Point
    layers: tuple[str, ...]
    size: float
    drill: float


@dataclass(frozen=True)
class Pad:
    reference: str
    number: str
    net: str
    layer: str
    center: Point
    orientation: float
    size: Point
    shape: str


@dataclass(frozen=True)
class Edge:
    neighbor: GraphNode
    length: float
    via_transitions: int
    width: float | None
    layer: str | None
    kind: str


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def git_bytes(commit: str, path: Path) -> bytes:
    return subprocess.check_output(
        ["git", "show", f"{commit}:{path.relative_to(ROOT)}"], cwd=ROOT
    )


def tokenize_sexpr(text: str) -> Iterable[str]:
    """Yield KiCad S-expression tokens without depending on a KiCad library."""
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "()":
            yield char
            index += 1
            continue
        if char == '"':
            index += 1
            value: list[str] = []
            while index < length:
                char = text[index]
                if char == '"':
                    index += 1
                    break
                if char == "\\" and index + 1 < length:
                    index += 1
                    value.append(text[index])
                    index += 1
                    continue
                value.append(char)
                index += 1
            else:
                raise RuntimeError("unterminated quoted string in KiCad source")
            yield "".join(value)
            continue
        end = index
        while end < length and not text[end].isspace() and text[end] not in "()":
            end += 1
        yield text[index:end]
        index = end


def parse_sexpr(text: str) -> list[Any]:
    roots: list[Any] = []
    stack: list[list[Any]] = []
    for token in tokenize_sexpr(text):
        if token == "(":
            node: list[Any] = []
            if stack:
                stack[-1].append(node)
            else:
                roots.append(node)
            stack.append(node)
        elif token == ")":
            require(bool(stack), "unexpected closing parenthesis in KiCad source")
            stack.pop()
        else:
            require(bool(stack), f"atom outside S-expression: {token!r}")
            stack[-1].append(token)
    require(not stack, "unterminated S-expression in KiCad source")
    require(len(roots) == 1 and roots[0] and roots[0][0] == "kicad_pcb",
            "expected one kicad_pcb root")
    return roots[0]


def children(node: list[Any], name: str) -> list[list[Any]]:
    return [
        child for child in node[1:]
        if isinstance(child, list) and child and child[0] == name
    ]


def child(node: list[Any], name: str) -> list[Any] | None:
    matches = children(node, name)
    return matches[0] if matches else None


def number(value: Any) -> float:
    return float(str(value))


def point_from(node: list[Any]) -> Point:
    require(len(node) >= 3, f"coordinate form is incomplete: {node}")
    return number(node[1]), number(node[2])


def rotate(point: Point, degrees: float) -> Point:
    radians = math.radians(degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return (
        point[0] * cosine - point[1] * sine,
        point[0] * sine + point[1] * cosine,
    )


def rounded(point: Point) -> Point:
    return round(point[0], 6), round(point[1], 6)


def parse_board(root: list[Any]) -> tuple[list[Segment], list[Via], list[Pad], list[list[Any]]]:
    net_names = {
        int(net[1]): str(net[2])
        for net in children(root, "net")
        if len(net) >= 3
    }

    segments: list[Segment] = []
    for form in children(root, "segment"):
        start = child(form, "start")
        end = child(form, "end")
        width = child(form, "width")
        layer = child(form, "layer")
        net = child(form, "net")
        require(all(item is not None for item in (start, end, width, layer, net)),
                f"incomplete segment: {form}")
        net_number = int(net[1])
        require(net_number in net_names, f"segment references unknown net {net_number}")
        segments.append(Segment(
            net=net_names[net_number],
            layer=str(layer[1]),
            start=rounded(point_from(start)),
            end=rounded(point_from(end)),
            width=number(width[1]),
        ))

    vias: list[Via] = []
    for form in children(root, "via"):
        at = child(form, "at")
        layers = child(form, "layers")
        size = child(form, "size")
        drill = child(form, "drill")
        net = child(form, "net")
        require(all(item is not None for item in (at, layers, size, drill, net)),
                f"incomplete via: {form}")
        net_number = int(net[1])
        require(net_number in net_names, f"via references unknown net {net_number}")
        vias.append(Via(
            net=net_names[net_number],
            point=rounded(point_from(at)),
            layers=tuple(str(item) for item in layers[1:]),
            size=number(size[1]),
            drill=number(drill[1]),
        ))

    pads: list[Pad] = []
    for footprint in children(root, "footprint"):
        reference_forms = [
            item for item in children(footprint, "property")
            if len(item) >= 3 and item[1] == "Reference"
        ]
        require(len(reference_forms) == 1, "footprint Reference property is missing/ambiguous")
        reference = str(reference_forms[0][2])
        fp_at = child(footprint, "at")
        require(fp_at is not None, f"{reference}: footprint position missing")
        fp_position = point_from(fp_at)
        fp_angle = number(fp_at[3]) if len(fp_at) >= 4 else 0.0

        for form in children(footprint, "pad"):
            net = child(form, "net")
            at = child(form, "at")
            size = child(form, "size")
            layers = child(form, "layers")
            if net is None or at is None or size is None or layers is None:
                continue
            net_number = int(net[1])
            require(net_number in net_names, f"{reference}: pad references unknown net {net_number}")
            local = point_from(at)
            offset = rotate(local, fp_angle)
            center = rounded((fp_position[0] + offset[0], fp_position[1] + offset[1]))
            pad_angle = number(at[3]) if len(at) >= 4 else 0.0
            copper_layers = []
            for layer in (str(item) for item in layers[1:]):
                if layer == "*.Cu":
                    copper_layers.extend(("F.Cu", "B.Cu"))
                elif layer in ("F.Cu", "B.Cu"):
                    copper_layers.append(layer)
            for layer in sorted(set(copper_layers)):
                pads.append(Pad(
                    reference=reference,
                    number=str(form[1]),
                    net=net_names[net_number],
                    layer=layer,
                    center=center,
                    orientation=fp_angle + pad_angle,
                    size=(number(size[1]), number(size[2])),
                    shape=str(form[3]),
                ))

    return segments, vias, pads, children(root, "zone")


def cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def subtract(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def point_on_segment(point: Point, start: Point, end: Point, tolerance: float = 1e-6) -> bool:
    segment = subtract(end, start)
    relative = subtract(point, start)
    if abs(cross(segment, relative)) > tolerance * max(1.0, math.hypot(*segment)):
        return False
    dot = relative[0] * segment[0] + relative[1] * segment[1]
    extent = segment[0] * segment[0] + segment[1] * segment[1]
    return -tolerance <= dot <= extent + tolerance


def segment_intersections(first: Segment, second: Segment) -> set[Point]:
    p = first.start
    q = second.start
    r = subtract(first.end, first.start)
    s = subtract(second.end, second.start)
    denominator = cross(r, s)
    q_minus_p = subtract(q, p)
    if abs(denominator) > 1e-12:
        t = cross(q_minus_p, s) / denominator
        u = cross(q_minus_p, r) / denominator
        if -1e-9 <= t <= 1.0 + 1e-9 and -1e-9 <= u <= 1.0 + 1e-9:
            return {rounded((p[0] + t * r[0], p[1] + t * r[1]))}
        return set()
    if abs(cross(q_minus_p, r)) > 1e-9:
        return set()
    candidates = (first.start, first.end, second.start, second.end)
    return {
        rounded(candidate) for candidate in candidates
        if point_on_segment(candidate, first.start, first.end)
        and point_on_segment(candidate, second.start, second.end)
    }


def pad_contains(pad: Pad, point: Point, tolerance: float = 2e-5) -> bool:
    local = rotate(subtract(point, pad.center), -pad.orientation)
    half_x = pad.size[0] / 2.0 + tolerance
    half_y = pad.size[1] / 2.0 + tolerance
    if pad.shape == "circle":
        return math.hypot(*local) <= min(half_x, half_y)
    return abs(local[0]) <= half_x and abs(local[1]) <= half_y


def closest_point(point: Point, start: Point, end: Point) -> Point:
    delta = subtract(end, start)
    extent = delta[0] * delta[0] + delta[1] * delta[1]
    if extent == 0:
        return start
    relative = subtract(point, start)
    parameter = max(0.0, min(1.0, (
        relative[0] * delta[0] + relative[1] * delta[1]
    ) / extent))
    return rounded((start[0] + parameter * delta[0], start[1] + parameter * delta[1]))


def point_to_segment_distance(point: Point, start: Point, end: Point) -> float:
    return math.dist(point, closest_point(point, start, end))


def segment_to_segment_distance(first: Segment, second: Segment) -> float:
    if segment_intersections(first, second):
        return 0.0
    return min(
        point_to_segment_distance(first.start, second.start, second.end),
        point_to_segment_distance(first.end, second.start, second.end),
        point_to_segment_distance(second.start, first.start, first.end),
        point_to_segment_distance(second.end, first.start, first.end),
    )


def point_node(net: str, layer: str, point: Point) -> GraphNode:
    return "point", net, layer, round(point[0], 6), round(point[1], 6)


def terminal_node(reference: str, number_: str) -> GraphNode:
    return "terminal", reference, number_


def add_edge(graph: dict[GraphNode, list[Edge]], left: GraphNode, right: GraphNode,
             *, length: float, via_transitions: int = 0, width: float | None = None,
             layer: str | None = None, kind: str) -> None:
    graph[left].append(Edge(right, length, via_transitions, width, layer, kind))
    graph[right].append(Edge(left, length, via_transitions, width, layer, kind))


def build_graph(segments: list[Segment], vias: list[Via], pads: list[Pad]) -> dict[GraphNode, list[Edge]]:
    graph: dict[GraphNode, list[Edge]] = defaultdict(list)
    split_points: list[set[Point]] = [{segment.start, segment.end} for segment in segments]

    grouped_segments: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, segment in enumerate(segments):
        grouped_segments[(segment.net, segment.layer)].append(index)
    for indexes in grouped_segments.values():
        for left, right in itertools.combinations(indexes, 2):
            intersections = segment_intersections(segments[left], segments[right])
            split_points[left].update(intersections)
            split_points[right].update(intersections)

    for via in vias:
        for index in grouped_segments.get((via.net, "F.Cu"), []):
            segment = segments[index]
            if point_on_segment(via.point, segment.start, segment.end):
                split_points[index].add(via.point)
        for index in grouped_segments.get((via.net, "B.Cu"), []):
            segment = segments[index]
            if point_on_segment(via.point, segment.start, segment.end):
                split_points[index].add(via.point)

    pad_attachments: list[tuple[Pad, Point]] = []
    for pad in pads:
        for index in grouped_segments.get((pad.net, pad.layer), []):
            segment = segments[index]
            candidates = {segment.start, segment.end, closest_point(pad.center, segment.start, segment.end)}
            for candidate in candidates:
                if pad_contains(pad, candidate):
                    split_points[index].add(candidate)
                    pad_attachments.append((pad, candidate))

    for index, segment in enumerate(segments):
        delta = subtract(segment.end, segment.start)
        extent = delta[0] * delta[0] + delta[1] * delta[1]
        require(extent > 0, f"zero-length segment: {segment}")
        ordered = sorted(
            split_points[index],
            key=lambda point: (
                (point[0] - segment.start[0]) * delta[0]
                + (point[1] - segment.start[1]) * delta[1]
            ) / extent,
        )
        for start, end in zip(ordered, ordered[1:]):
            length = math.dist(start, end)
            if length <= 1e-9:
                continue
            add_edge(
                graph,
                point_node(segment.net, segment.layer, start),
                point_node(segment.net, segment.layer, end),
                length=length,
                width=segment.width,
                layer=segment.layer,
                kind="trace",
            )

    for via in vias:
        require("F.Cu" in via.layers and "B.Cu" in via.layers,
                f"unsupported via layer span: {via}")
        add_edge(
            graph,
            point_node(via.net, "F.Cu", via.point),
            point_node(via.net, "B.Cu", via.point),
            length=0.0,
            via_transitions=1,
            kind="via",
        )

    seen_attachments: set[tuple[GraphNode, GraphNode]] = set()
    for pad, attachment in pad_attachments:
        terminal = terminal_node(pad.reference, pad.number)
        point = point_node(pad.net, pad.layer, attachment)
        key = terminal, point
        if key in seen_attachments:
            continue
        seen_attachments.add(key)
        add_edge(graph, terminal, point, length=0.0, kind="pad")
    return graph


def shortest_path(graph: dict[GraphNode, list[Edge]], source: GraphNode,
                  target: GraphNode) -> dict[str, Any]:
    require(source in graph, f"source terminal has no routed attachment: {source}")
    require(target in graph, f"target terminal has no routed attachment: {target}")
    counter = itertools.count()
    queue: list[tuple[float, int, int, GraphNode]] = [(0.0, 0, next(counter), source)]
    best: dict[GraphNode, tuple[float, int]] = {source: (0.0, 0)}
    previous: dict[GraphNode, tuple[GraphNode, Edge]] = {}
    while queue:
        distance, vias, _, node = heapq.heappop(queue)
        if (distance, vias) != best.get(node):
            continue
        if node == target:
            break
        for edge in graph[node]:
            candidate = (distance + edge.length, vias + edge.via_transitions)
            current = best.get(edge.neighbor)
            if current is None or candidate < current:
                best[edge.neighbor] = candidate
                previous[edge.neighbor] = node, edge
                heapq.heappush(queue, (*candidate, next(counter), edge.neighbor))
    require(target in best, f"no routed path between {source} and {target}")

    traversed: list[tuple[GraphNode, GraphNode, Edge]] = []
    node = target
    while node != source:
        parent, edge = previous[node]
        traversed.append((parent, node, edge))
        node = parent
    traversed.reverse()
    trace_edges = [edge for _, _, edge in traversed if edge.kind == "trace"]
    layer_lengths: dict[str, float] = defaultdict(float)
    for edge in trace_edges:
        require(edge.layer is not None, "trace edge lacks layer")
        layer_lengths[edge.layer] += edge.length
    widths = [edge.width for edge in trace_edges if edge.width is not None]
    vertices = []
    for left, _, edge in traversed:
        if left and left[0] == "point":
            vertices.append({"layer": left[2], "x_mm": left[3], "y_mm": left[4], "next": edge.kind})
    if target and target[0] == "point":
        vertices.append({"layer": target[2], "x_mm": target[3], "y_mm": target[4]})
    return {
        "connected": True,
        "trace_length_mm": round(best[target][0], 6),
        "via_transitions": best[target][1],
        "minimum_trace_width_mm": round(min(widths), 6) if widths else None,
        "layer_lengths_mm": {
            layer: round(length, 6) for layer, length in sorted(layer_lengths.items())
        },
        "trace_parts": len(trace_edges),
        "route_vertices": vertices,
    }


def descendant_count(node: list[Any], name: str) -> int:
    count = 0
    for item in node:
        if not isinstance(item, list) or not item:
            continue
        if item[0] == name:
            count += 1
        count += descendant_count(item, name)
    return count


def audit_zone(zones: list[list[Any]]) -> dict[str, Any]:
    require(not zones, f"explicit-routing-only ECO must contain zero zones, got {len(zones)}")
    return {
        "name": None,
        "source_zone_present": False,
        "cached_filled_polygon_count": 0,
        "source_zone_materialized": False,
        "copper_model": "EXPLICIT_ROUTING_ONLY",
    }


def audit_explicit_local_return(segments: list[Segment], vias: list[Via]) -> dict[str, Any]:
    expected_endpoints = ((15.25, 13.25), (15.0, 16.65))
    def endpoints_match(segment: Segment, expected: tuple[Point, Point]) -> bool:
        return (
            math.dist(segment.start, expected[0]) <= 2e-6
            and math.dist(segment.end, expected[1]) <= 2e-6
        ) or (
            math.dist(segment.start, expected[1]) <= 2e-6
            and math.dist(segment.end, expected[0]) <= 2e-6
        )

    direct = [
        segment for segment in segments
        if segment.net == "GND"
        and segment.layer == "B.Cu"
        and endpoints_match(segment, expected_endpoints)
    ]
    require(len(direct) == 1, f"expected one direct C1-to-microphone B.Cu return, got {direct}")
    segment = direct[0]
    require(abs(segment.width - 0.50) <= 1e-6,
            f"direct C1 return width {segment.width:.6f} mm != 0.500000 mm")
    legacy_endpoints = ((9.0, 13.25), (15.25, 13.25))
    require(not any(
        item.net == "GND" and item.layer == "B.Cu"
        and endpoints_match(item, legacy_endpoints)
        for item in segments
    ), "legacy remote C1-to-spine branch remains present")
    length = math.dist(segment.start, segment.end)
    require(abs(length - 3.4091787867461556) <= 1e-6,
            f"direct C1 return length drift: {length:.6f} mm")
    clearances = [
        segment_to_segment_distance(segment, item)
        - (segment.width + item.width) / 2.0
        for item in segments
        if item.layer == "B.Cu" and item.net != "GND"
    ]
    clearances.extend(
        point_to_segment_distance(item.point, segment.start, segment.end)
        - (segment.width + item.size) / 2.0
        for item in vias
        if "B.Cu" in item.layers and item.net != "GND"
    )
    require(clearances, "no other-net B.Cu copper found for local-return clearance audit")
    minimum_clearance = min(clearances)
    require(minimum_clearance >= 0.20,
            f"direct C1 return B.Cu clearance {minimum_clearance:.6f} mm < 0.200000 mm")
    acoustic_clearance = (
        point_to_segment_distance((12.0, 16.65), segment.start, segment.end)
        - segment.width / 2.0 - 0.4
    )
    require(acoustic_clearance >= 0.80,
            f"direct C1 return acoustic clearance {acoustic_clearance:.6f} mm < 0.800000 mm")
    return {
        "status": "PASS_DIRECT_BCU_C1_RETURN",
        "start_mm": list(segment.start),
        "end_mm": list(segment.end),
        "width_mm": segment.width,
        "length_mm": round(length, 6),
        "minimum_other_net_bcu_copper_edge_clearance_mm": round(minimum_clearance, 6),
        "project_minimum_copper_clearance_mm": 0.20,
        "acoustic_hole_edge_clearance_mm": round(acoustic_clearance, 6),
        "legacy_remote_branch_present": False,
    }


def audit_bcu_gerber(artifact_root: Path | None) -> dict[str, Any]:
    if artifact_root is None:
        return {
            "checked": False,
            "reason": "artifact root not supplied",
            "gnd_region_count": None,
            "materialized_gnd_region": None,
        }
    path = artifact_root / "gerber/PCB-MIC-B_Cu.gbr"
    require(path.is_file(), f"B.Cu Gerber missing: {path}")
    text = path.read_text(encoding="utf-8")
    current_net: str | None = None
    all_regions = 0
    gnd_regions = 0
    gnd_draws = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        net_match = re.fullmatch(r"%TO\.N,([^*]+)\*%", line)
        if net_match:
            current_net = net_match.group(1)
            continue
        if line == "%TD*%":
            current_net = None
            continue
        if line == "G36*":
            all_regions += 1
            if current_net == "GND":
                gnd_regions += 1
        if current_net == "GND" and line.endswith("D01*"):
            gnd_draws += 1
    require("%TF.FileFunction,Copper,L2,Bot*%" in text, "B.Cu Gerber file-function mismatch")
    require(gnd_draws > 0, "B.Cu Gerber contains no explicit GND conductor draws")
    return {
        "checked": True,
        "path": str(path.relative_to(artifact_root)),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "all_region_count": all_regions,
        "gnd_region_count": gnd_regions,
        "explicit_gnd_draw_count": gnd_draws,
        "materialized_gnd_region": gnd_regions > 0,
    }


def audit_commit_binding(commit_sha: str | None, require_clean_source: bool) -> dict[str, Any]:
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    require(status.get("assembly") == "PCB-MIC", "PCB-MIC status identity mismatch")
    require(status.get("manufacturing_release") is False,
            "manufacturing release must remain false")
    review_a = status.get("review_a", {})
    review_b = status.get("review_b", {})
    require(review_b.get("complete") is False and review_b.get("reviewer") is None,
            "Review B must remain open and unsigned")
    require(REVIEW_PACKET.is_file(), "copper-return human-review packet is missing")

    release_state = status.get("release_state")
    if release_state == "REVIEW_A_REQUIRED_AFTER_COPPER_ECO":
        require(review_a.get("complete") is False
                and review_a.get("status") == "REVIEW_REQUIRED_AFTER_COPPER_ECO",
                "post-ECO Review A must be open")
        require(all(review_a.get(field) is None for field in ("reviewer", "date", "commit_sha")),
                "post-ECO Review A unexpectedly retains an active signature")
        require(review_b.get("status") == "BLOCKED_PENDING_REPEAT_REVIEW_A_AFTER_COPPER_ECO",
                "Review B is not blocked on repeat Review A")
        gate = review_b.get("copper_return_gate", {})
        require(gate.get("decision") == "ECO_REQUIRED"
                and gate.get("reviewer") and gate.get("date"),
                "ECO_REQUIRED decision traceability is incomplete")
        prior = review_a.get("superseded_signature", {})
        prior_commit = str(prior.get("commit_sha", ""))
        require(prior.get("status") == "SUPERSEDED_BY_COPPER_ECO_BOARD_BYTE_CHANGE",
                "prior Review-A signature is not marked superseded")
        require(re.fullmatch(r"[0-9a-f]{40}", prior_commit) is not None,
                "superseded Review-A commit SHA is invalid")
        prior_board = git_bytes(prior_commit, BOARD)
        require(hashlib.sha256(prior_board).hexdigest() == prior.get("board_sha256"),
                "superseded Review-A board hash mismatch")
        require(prior_board != BOARD.read_bytes(),
                "post-ECO board does not differ from the superseded Review-A board")
        review_a_state = "ECO_CANDIDATE_REPEAT_REVIEW_A_REQUIRED"
        signed_commit: str | None = None
        previous_review_a = {
            "reviewer": prior.get("reviewer"),
            "date": prior.get("date"),
            "commit_sha": prior_commit,
            "board_sha256": prior.get("board_sha256"),
            "status": prior.get("status"),
        }
    else:
        require(release_state == "REVIEW_A_PASS", "unexpected PCB-MIC release state")
        require(review_a.get("complete") is True and review_a.get("status") == "PASS",
                "signed Review A is not complete/pass")
        signed_commit = str(review_a.get("commit_sha", ""))
        require(re.fullmatch(r"[0-9a-f]{40}", signed_commit) is not None,
                "signed Review-A commit SHA is invalid")
        signed_board = git_bytes(signed_commit, BOARD)
        require(signed_board == BOARD.read_bytes(),
                f"native board drifted from signed Review-A commit {signed_commit}")
        review_a_state = "SIGNED_PASS"
        previous_review_a = None

    head = git_head()
    if commit_sha is not None:
        require(re.fullmatch(r"[0-9a-f]{40}", commit_sha) is not None,
                f"invalid evidence commit SHA: {commit_sha!r}")
        require(commit_sha == head, f"evidence commit {commit_sha} != HEAD {head}")
    if require_clean_source:
        controlled = [
            BOARD, STATUS, REVIEW_PACKET, TDK_AUTHORITY, GENERATOR,
            NATIVE_WORKFLOW, Path(__file__).resolve()
        ]
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--", *[
                str(path.relative_to(ROOT)) for path in controlled
            ]],
            cwd=ROOT,
            text=True,
        ).strip()
        require(not dirty, f"copper-review source set is dirty: {dirty}")
    return {
        "evidence_commit_sha": commit_sha or head,
        "signed_review_a_commit_sha": signed_commit,
        "board_sha256": sha256(BOARD),
        "review_a_state": review_a_state,
        "signed_source_continuity": review_a_state == "SIGNED_PASS",
        "superseded_review_a_signature": previous_review_a,
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def trace_signature(segments: list[Segment], vias: list[Via]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for segment in segments:
        counts[f"{segment.net}:{segment.layer}"] += 1
    for via in vias:
        counts[f"{via.net}:via"] += 1
    return dict(sorted(counts.items()))


def run_audit(artifact_root: Path | None, commit_sha: str | None,
              require_clean_source: bool) -> dict[str, Any]:
    binding = audit_commit_binding(commit_sha, require_clean_source)
    authority_text = TDK_AUTHORITY.read_text(encoding="utf-8")
    require("TDK `T5838` datasheet DS-000383, Revision 1.2" in authority_text,
            "frozen T5838 datasheet revision is absent from authority")
    require(TDK_DATASHEET["sha256"] in authority_text,
            "frozen T5838 datasheet hash is absent from authority")
    root = parse_sexpr(BOARD.read_text(encoding="utf-8"))
    segments, vias, pads, zones = parse_board(root)
    graph = build_graph(segments, vias, pads)

    supply_feed = shortest_path(graph, terminal_node("J1", "1"), terminal_node("C1", "1"))
    supply_local = shortest_path(graph, terminal_node("C1", "1"), terminal_node("MK1", "7"))
    return_local = shortest_path(graph, terminal_node("C1", "2"), terminal_node("MK1", "2"))
    connector_return = shortest_path(graph, terminal_node("J1", "2"), terminal_node("MK1", "2"))
    zone = audit_zone(zones)
    explicit_local_return = audit_explicit_local_return(segments, vias)
    gerber = audit_bcu_gerber(artifact_root)

    require(supply_local["via_transitions"] == 0,
            "C1-to-MK1 VDD local path unexpectedly changes layers")
    require(supply_local["minimum_trace_width_mm"] is not None
            and supply_local["minimum_trace_width_mm"] >= 0.3,
            "C1-to-MK1 VDD local trace is below 0.3 mm")
    require(return_local["connected"], "C1-to-MK1 explicit GND return is not connected")
    require(return_local["via_transitions"] == 2,
            "C1-to-MK1 explicit GND return must use the two controlled vias")
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    baseline = status["review_b"]["copper_return_gate"]["baseline_machine_measurement"]
    baseline_return = float(baseline["c1_to_mk1_ground_return_trace_length_mm"])
    baseline_loop = float(baseline["decoupling_loop_trace_length_mm"])
    loop_length = supply_local["trace_length_mm"] + return_local["trace_length_mm"]
    require(return_local["trace_length_mm"] < baseline_return,
            "ECO candidate did not shorten the C1-to-MK1 return")
    require(loop_length < baseline_loop,
            "ECO candidate did not shorten the decoupling loop")
    if gerber.get("checked") is True:
        require(gerber.get("gnd_region_count") == 0,
                "explicit-routing-only CAM unexpectedly contains a GND region")

    findings: list[dict[str, Any]] = [{
        "id": "PCB-MIC-RB-CU-001",
        "severity": "RESOLVED_IN_ECO_CANDIDATE_PENDING_REPEAT_REVIEW_A",
        "finding": (
            "The non-materialized B.Cu GND zone was removed and the remote C1 branch was "
            "replaced by one direct, explicit 0.50 mm B.Cu return segment."
        ),
        "verification": (
            "Source and CAM use explicit routing only; repeat Review A is required because "
            "the native PCB bytes changed."
        ),
    }, {
        "id": "PCB-MIC-RB-CU-002",
        "severity": "HUMAN_ACCEPTANCE_REQUIRED",
        "finding": (
            "No project-controlled normative maximum is frozen for the C1-to-MK1 "
            "decoupling loop; measured supply and return lengths cannot self-authorize a PASS."
        ),
        "required_decision": "Reviewer accepts the loop or raises a routed-board ECO.",
    }]

    decision = (
        "ECO_CANDIDATE_EXPLICIT_LOCAL_RETURN_READY_FOR_REPEAT_REVIEW_A"
        if binding["review_a_state"] == "ECO_CANDIDATE_REPEAT_REVIEW_A_REQUIRED" else
        "READY_FOR_INDEPENDENT_HUMAN_COPPER_RETURN_REVIEW"
    )
    return {
        "schema": "dioneya-pcb-mic-copper-return-review-b-precheck-v2",
        "configuration": "EVT-PRE-20 Rev.A",
        "assembly": "PCB-MIC",
        "machine_status": "PASS_REPRODUCIBLE_ECO_TOPOLOGY_MEASUREMENT",
        "review_b_disposition": decision,
        "review_b_complete": False,
        "manufacturing_release": False,
        "commit_binding": binding,
        "datasheet_authority": TDK_DATASHEET,
        "parser_independence": {
            "implementation": "standard-library KiCad S-expression parser and layer graph",
            "pcbnew": False,
            "kiutils": False,
            "board_generator": False,
            "cam_preflight_parser": False,
        },
        "topology": {
            "segments": len(segments),
            "vias": len(vias),
            "trace_signature": trace_signature(segments, vias),
            "paths": {
                "J1.1_to_C1.1_supply_feed": supply_feed,
                "C1.1_to_MK1.7_vdd_local": supply_local,
                "C1.2_to_MK1.2_ground_return": return_local,
                "J1.2_to_MK1.2_connector_return": connector_return,
            },
            "measured_decoupling_loop_trace_length_mm": round(loop_length, 6),
            "baseline_c1_to_mk1_ground_return_trace_length_mm": baseline_return,
            "baseline_decoupling_loop_trace_length_mm": baseline_loop,
            "ground_return_reduction_mm": round(
                baseline_return - return_local["trace_length_mm"], 6
            ),
            "decoupling_loop_reduction_mm": round(baseline_loop - loop_length, 6),
            "normative_maximum_loop_length_mm": None,
            "normative_limit_status": "NOT_FROZEN_HUMAN_REVIEW_REQUIRED",
        },
        "ground_zone": {
            "source": zone,
            "cam": gerber,
        },
        "explicit_local_return": explicit_local_return,
        "findings": findings,
        "human_review_packet": str(REVIEW_PACKET.relative_to(ROOT)),
        "human_review_drawings": [
            "artifacts/kicad-native/PCB-MIC/PCB-MIC_F_Cu_review.svg",
            "artifacts/kicad-native/PCB-MIC/PCB-MIC_B_Cu_review.svg",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--commit-sha")
    parser.add_argument("--require-clean-source", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    artifact_root = args.artifact_root.resolve() if args.artifact_root else None
    try:
        report = run_audit(artifact_root, args.commit_sha, args.require_clean_source)
    except Exception as exc:
        report = {
            "schema": "dioneya-pcb-mic-copper-return-review-b-precheck-v2",
            "configuration": "EVT-PRE-20 Rev.A",
            "assembly": "PCB-MIC",
            "machine_status": "FAIL_TOPOLOGY_MEASUREMENT",
            "review_b_complete": False,
            "manufacturing_release": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"PCB-MIC copper-return precheck FAIL: {exc}")
        return 1

    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-MIC copper-return topology measurement PASS")
    print(f"Review-B disposition: {report['review_b_disposition']}")
    print("Review B remains OPEN; manufacturing release remains FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
