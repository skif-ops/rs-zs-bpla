#!/usr/bin/env python3
"""Geometry of PCB-MAIN-GROUND-DOMAIN-ROUTING-002 (Review B R1, section 4, variant 1).

In4.Cu is re-partitioned: GND_MODEM stays under the cellular nodes and their routes, the rest
of In4.Cu becomes GND_DIGITAL so that B.Cu signals in digital areas get their nearest reference
(B.Cu <-> In4.Cu 0.0994 mm, JLC06161H-3313). In1.Cu, In2.Cu, In3.Cu, placement, nets and
outline are unchanged.

Rules (all derived from the board and the routing / mechanical authorities, nothing drawn by
hand):
  modem region = ZONE_CELL
               + pad hull (+0.6 mm) of every footprint that has a pad on GND_MODEM or on a net
                 whose Reference_Domain is GND_MODEM (J_PWR: only those pins)
               + every GND_MODEM / modem-domain track and via (+1.0 mm)
               + corridors of the future modem routes: minimum spanning tree between the pads
                 of each modem-domain net (+1.5 mm)
               closed by 1.5 mm, clipped to the previous In4 GND_MODEM outline (so GNSS, LoRa,
               BLE body and the audio quiet zone stay modem-free, as before);
  digital priority:
               - the U1 (MCU) pad hull + 1.0 mm stays digital,
               - every routed digital-domain B.Cu track keeps 0.8 mm of digital reference,
               - except islands of 0.35 mm around modem pads / modem copper located there
                 (TP_CELL_DBG fixture pads under U1, placement is fixed);
               slivers narrower than 0.4 mm dropped; a modem piece is kept only if it touches
               GND_MODEM copper (otherwise it would be dead copper, not a reference);
  zones:       GND_DIGITAL In4.Cu = the In1.Cu GND_DIGITAL outline (priority 0),
               GND_MODEM   In4.Cu = one zone per modem-region piece (priority 1, filled first);
  stitching:   every digital-domain signal via whose nearest GND_DIGITAL via is farther than
               STITCH_TARGET_MM gets a GND_DIGITAL through via 0.5/0.3 at the nearest free spot,
               only if that spot is closer than the existing nearest GND_DIGITAL via,
               inside the new In4 digital copper (0.2 mm copper clearance on all six layers,
               0.25 mm hole-to-hole, outside pads, rule areas and 0.6 mm from the edge).
"""

from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
AUTHORITY = ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv"
CELL = (10.0, 34.0, 36.0, 74.0)
PROTECTED_ZONES = {"ZONE_GNSS": (44.0, 51.0, 63.0, 72.0), "ZONE_LORA": (64.0, 46.0, 85.5, 74.0),
                   "ZONE_BLE_BODY": (94.5, 30.0, 110.0, 40.5), "ZONE_AUDIO_DIGITAL": (37.0, 39.0, 66.0, 50.0)}
DIGITAL_PRIORITY_REFS = ("U1",)
STITCH_TARGET_MM, STITCH_SEARCH_MM = 1.5, 2.5
VIA_SIZE, VIA_DRILL = 0.5, 0.3
CLEARANCE, HOLE_CLEARANCE, EDGE = 0.2, 0.25, 0.6
LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu")


def _shapely():
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely.ops import unary_union
    return LineString, Point, Polygon, box, unary_union


def reference(fp) -> str:
    props = fp.properties
    if isinstance(props, dict) and props.get("Reference"):
        return props["Reference"]
    for item in fp.graphicItems:
        if type(item).__name__ == "FpText" and item.type == "reference":
            return item.text
    return "?"


def pad_geometry(fp, pad):
    sys.path.insert(0, str(ROOT / "tools"))
    from pcb_return_resistance_rev_a import _pad_geometry
    return _pad_geometry(fp, pad)


def pad_layers(pad) -> set:
    layers = set()
    for layer in pad.layers:
        if layer == "*.Cu":
            layers |= set(LAYERS)
        elif layer in LAYERS:
            layers.add(layer)
    return layers


def load(board_path: Path = BOARD):
    from kiutils.board import Board
    board = Board.from_file(str(board_path))
    domains = {r["Net_Name"]: r["Reference_Domain"] for r in csv.DictReader(AUTHORITY.open(encoding="utf-8"))}
    return board, domains


def zone_outline(board, net: str, layer: str):
    _, _, Polygon, _, _ = _shapely()
    for zone in board.zones:
        if zone.netName == net and zone.layers == [layer]:
            return Polygon([(c.X, c.Y) for c in zone.polygons[0].coordinates]).buffer(0)
    raise KeyError(f"{net} {layer}")


def _mst(points: list) -> list:
    if len(points) < 2:
        return []
    inside, edges = {0}, []
    while len(inside) < len(points):
        best = min(((math.dist(points[i], points[j]), i, j) for i in inside for j in range(len(points))
                    if j not in inside))
        inside.add(best[2])
        edges.append((points[best[1]], points[best[2]]))
    return edges


def items(board):
    """(net, kind, layer or None, geometry, raw) for every track and via."""
    LineString, Point, _, _, _ = _shapely()
    names = {n.number: n.name for n in board.nets}
    out = []
    for item in board.traceItems:
        net = names.get(item.net)
        if type(item).__name__ == "Via":
            out.append((net, "via", None, Point(item.position.X, item.position.Y), item))
        else:
            out.append((net, "track", item.layer, LineString([(item.start.X, item.start.Y),
                                                              (item.end.X, item.end.Y)]), item))
    return out


def split_in4(board, domains) -> dict:
    LineString, Point, Polygon, box, unary_union = _shapely()
    modem_nets = {n for n, d in domains.items() if d == "GND_MODEM"} | {"GND_MODEM"}
    digital_nets = {n for n, d in domains.items() if d == "GND_DIGITAL"}
    old4 = zone_outline(board, "GND_MODEM", "In4.Cu")
    digital_outline = zone_outline(board, "GND_DIGITAL", "In1.Cu")
    tracks = items(board)
    parts = [box(*CELL)]
    net_pads = defaultdict(list)
    modem_pad_geoms = []
    for fp in board.footprints:
        geoms, modem = [], False
        for pad in fp.pads:
            geom = pad_geometry(fp, pad)
            geoms.append(geom)
            net = pad.net.name if pad.net else None
            if net in modem_nets:
                modem = True
                net_pads[net].append(geom.centroid.coords[0])
                modem_pad_geoms.append(geom)
        if reference(fp) == "J_PWR":
            parts += [pad_geometry(fp, p).buffer(0.6) for p in fp.pads if p.net and p.net.name in modem_nets]
        elif modem:
            parts.append(unary_union(geoms).convex_hull.buffer(0.6))
    modem_copper = []
    for net, kind, layer, geom, raw in tracks:
        if net in modem_nets:
            width = raw.size / 2 if kind == "via" else raw.width / 2
            parts.append(geom.buffer(width + 1.0))
            modem_copper.append(geom.buffer(width))
    for net, pts in net_pads.items():
        if net != "GND_MODEM":
            parts += [LineString([a, c]).buffer(1.5) for a, c in _mst(pts)]
    region = unary_union(parts).buffer(1.5).buffer(-1.5).intersection(old4)
    keep = unary_union([unary_union([pad_geometry(fp, p) for p in fp.pads]).convex_hull.buffer(1.0)
                        for fp in board.footprints if reference(fp) in DIGITAL_PRIORITY_REFS])
    digital_tracks = unary_union([geom.buffer(raw.width / 2 + 0.8) for net, kind, layer, geom, raw in tracks
                                  if kind == "track" and layer == "B.Cu" and net in digital_nets])
    keep = keep.union(digital_tracks)
    islands = unary_union([g.buffer(0.35) for g in modem_pad_geoms + modem_copper if g.distance(keep) < 1.0])
    region = region.difference(keep).union(islands.intersection(old4)).buffer(0)
    region = region.buffer(-0.2).buffer(0.2).union(islands.intersection(old4)).buffer(0)
    # a modem piece must touch GND_MODEM copper, otherwise it is dead copper (no reference)
    gnd_modem = [pad_geometry(fp, p) for fp in board.footprints for p in fp.pads
                 if p.net and p.net.name == "GND_MODEM"]
    gnd_modem += [geom for net, kind, layer, geom, raw in tracks if net == "GND_MODEM"]
    anchors = unary_union(gnd_modem)
    pieces = []
    for piece in getattr(region, "geoms", [region]):
        if piece.is_empty or piece.geom_type != "Polygon":
            continue
        if not piece.intersects(anchors):
            continue
        pieces.append(Polygon(piece.exterior.coords))  # hole-free outline: holes fill as modem
    modem = unary_union(pieces)
    digital = digital_outline.difference(modem.buffer(CLEARANCE))
    return {"modem_pieces": pieces, "modem": modem, "digital_outline": digital_outline,
            "digital_effective": digital, "old_in4_modem": old4, "digital_keep": keep}


def obstacles(board, extra_vias: list):
    """Per-layer other-net copper and all holes, for stitching-via placement."""
    LineString, Point, Polygon, box, unary_union = _shapely()
    per_layer = {layer: [] for layer in LAYERS}
    holes = []
    pads_all = []
    for fp in board.footprints:
        for pad in fp.pads:
            geom = pad_geometry(fp, pad)
            net = pad.net.name if pad.net else None
            pads_all.append(geom)
            for layer in pad_layers(pad):
                if net != "GND_DIGITAL":
                    per_layer[layer].append(geom)
            if pad.drill is not None and getattr(pad.drill, "diameter", 0):
                holes.append(Point(geom.centroid).buffer(pad.drill.diameter / 2))
    for net, kind, layer, geom, raw in items(board):
        if kind == "via":
            holes.append(geom.buffer(raw.drill / 2))
            if net != "GND_DIGITAL":
                for lay in LAYERS:
                    per_layer[lay].append(geom.buffer(raw.size / 2))
        elif net != "GND_DIGITAL":
            per_layer[layer].append(geom.buffer(raw.width / 2))
    for x, y in extra_vias:
        holes.append(Point(x, y).buffer(VIA_DRILL / 2))
    rules = []
    for zone in board.zones:
        if zone.keepoutSettings:
            rules.append(Polygon([(c.X, c.Y) for c in zone.polygons[0].coordinates]).buffer(0))
    return ({k: unary_union(v) for k, v in per_layer.items()}, unary_union(holes),
            unary_union(pads_all), unary_union(rules) if rules else Polygon())


def stitching_vias(board, domains, split: dict) -> tuple[list, list]:
    """New GND_DIGITAL vias near digital signal vias (placements, per-via report)."""
    _, Point, _, _, _ = _shapely()
    trackitems = items(board)
    gnd = [geom for net, kind, _, geom, _ in trackitems if kind == "via" and net == "GND_DIGITAL"]
    signal = [(net, geom) for net, kind, _, geom, _ in trackitems
              if kind == "via" and domains.get(net) == "GND_DIGITAL"]
    allowed = split["digital_effective"].buffer(-(VIA_SIZE / 2 + 0.1))
    edge = split["digital_outline"].buffer(-(EDGE - 0.65 + VIA_SIZE / 2))
    added, report = [], []
    for net, via in sorted(signal, key=lambda s: (s[1].x, s[1].y)):
        pool = gnd + [Point(p) for p in added]
        nearest = min(via.distance(g) for g in pool)
        row = {"net": net, "at_mm": [round(via.x, 3), round(via.y, 3)], "nearest_before_mm": round(nearest, 3)}
        if nearest <= STITCH_TARGET_MM:
            row["action"] = "EXISTING_GND_DIGITAL_VIA_WITHIN_TARGET"
            report.append(row)
            continue
        copper, holes, pads, rules = obstacles(board, added)
        best = None
        steps = int(STITCH_SEARCH_MM / 0.05)
        for i in range(-steps, steps + 1):
            for j in range(-steps, steps + 1):
                x, y = round(via.x + i * 0.05, 3), round(via.y + j * 0.05, 3)
                d = math.hypot(x - via.x, y - via.y)
                if d < 0.7 or d > STITCH_SEARCH_MM or (best and d >= best[0]):
                    continue
                p = Point(x, y)
                if not allowed.contains(p) or not edge.contains(p):
                    continue
                disk = p.buffer(VIA_SIZE / 2)
                if any(disk.distance(copper[layer]) < CLEARANCE for layer in LAYERS):
                    continue
                if p.buffer(VIA_DRILL / 2).distance(holes) < HOLE_CLEARANCE or disk.intersects(pads):
                    continue
                if not rules.is_empty and disk.intersects(rules):
                    continue
                best = (d, x, y)
        if best and best[0] < nearest:
            added.append((best[1], best[2]))
            row.update({"action": "STITCH_VIA_ADDED", "stitch_at_mm": [best[1], best[2]],
                        "nearest_after_mm": round(best[0], 3),
                        "within_target": best[0] <= STITCH_TARGET_MM})
        else:
            row["action"] = "NO_FREE_SPOT_CLOSER_THAN_EXISTING_WITHIN_SEARCH_RADIUS"
        report.append(row)
    return added, report


def continuity_map(board, domains, references: dict) -> dict:
    """Share of every routed track length over reference copper of its own domain.
    references: {layer: {domain_net: polygon}} (filled copper, or outlines as a proxy)."""
    rows = defaultdict(lambda: {"length_mm": 0.0, "over_own_reference_mm": 0.0})
    per_net = defaultdict(lambda: {"length_mm": 0.0, "over_own_reference_mm": 0.0})
    for net, kind, layer, geom, raw in items(board):
        if kind != "track" or net in ("GND_DIGITAL", "GND_MODEM", "GND_MIC"):
            continue
        domain = domains.get(net, "UNKNOWN")
        ref_layer = {"F.Cu": "In1.Cu", "B.Cu": "In4.Cu"}.get(layer)
        key = f"{layer}|{domain}"
        own = references.get(ref_layer, {}).get(domain) if ref_layer else None
        over = geom.intersection(own).length if own is not None and not own.is_empty else 0.0
        for table, k in ((rows, key), (per_net, f"{net}|{layer}")):
            table[k]["length_mm"] += geom.length
            table[k]["over_own_reference_mm"] += over
    def fmt(table):
        return {k: {"length_mm": round(v["length_mm"], 2), "over_own_reference_mm": round(v["over_own_reference_mm"], 2),
                    "share": round(v["over_own_reference_mm"] / v["length_mm"], 4) if v["length_mm"] else None}
                for k, v in sorted(table.items())}
    return {"by_layer_domain": fmt(rows), "by_net_layer": fmt(per_net)}


TIE_LAYER, TIE_WIDTH = "In3.Cu", 0.3


def _astar(blocked, start, goal, box, step=0.05, snap=0.4):
    """8-connected grid A*; blocked(x, y) -> bool. Cells within `snap` of start/goal are free."""
    import heapq
    x0, y0, x1, y1 = box
    nx, ny = int((x1 - x0) / step), int((y1 - y0) / step)
    s = (round((start[0] - x0) / step), round((start[1] - y0) / step))
    g = (round((goal[0] - x0) / step), round((goal[1] - y0) / step))
    cost, prev, heap, seen = {s: 0.0}, {}, [(0.0, s)], {}
    while heap:
        _, cur = heapq.heappop(heap)
        if cur == g:
            path = [cur]
            while cur in prev:
                cur = prev[cur]
                path.append(cur)
            return [(round(x0 + i * step, 4), round(y0 + j * step, 4)) for i, j in reversed(path)]
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if not di and not dj:
                    continue
                n = (cur[0] + di, cur[1] + dj)
                if not (0 <= n[0] < nx and 0 <= n[1] < ny):
                    continue
                if n not in seen:
                    px, py = x0 + n[0] * step, y0 + n[1] * step
                    near = math.dist((px, py), start) < snap or math.dist((px, py), goal) < snap
                    seen[n] = near or not blocked(px, py)
                if not seen[n]:
                    continue
                c = cost[cur] + math.hypot(di, dj)
                if c < cost.get(n, 1e9):
                    cost[n], prev[n] = c, cur
                    heapq.heappush(heap, (c + math.dist(n, g), n))
    return None


def _simplify(path, clear):
    out, i = [path[0]], 0
    LineString = _shapely()[0]
    while i < len(path) - 1:
        j = len(path) - 1
        while j > i + 1 and not clear(LineString([path[i], path[j]])):
            j -= 1
        out.append(path[j])
        i = j
    return out


def island_ties(board, split: dict, extra_vias: list = ()) -> list:
    """GND_MODEM In3.Cu ties from every modem piece other than the main one to the main piece:
    from a GND_MODEM via inside the piece to the nearest GND_MODEM via inside the main piece,
    0.3 mm track, 0.2 mm clearance to every other-net In3.Cu item (tracks, vias, *.Cu pads)."""
    LineString, Point, Polygon, box, unary_union = _shapely()
    from shapely import prepared
    pieces = sorted(split["modem_pieces"], key=lambda p: -p.area)
    if len(pieces) < 2:
        return []
    main = pieces[0]
    modem_vias = [geom for net, kind, _, geom, _ in items(board) if kind == "via" and net == "GND_MODEM"]
    obstacles_in3 = []
    for fp in board.footprints:
        for pad in fp.pads:
            if TIE_LAYER in pad_layers(pad) and not (pad.net and pad.net.name == "GND_MODEM"):
                obstacles_in3.append(pad_geometry(fp, pad))
    for net, kind, layer, geom, raw in items(board):
        if net == "GND_MODEM":
            continue
        if kind == "via":
            obstacles_in3.append(geom.buffer(raw.size / 2))
        elif layer == TIE_LAYER:
            obstacles_in3.append(geom.buffer(raw.width / 2))
    for x, y in extra_vias:  # stitching vias added by this candidate
        obstacles_in3.append(Point(x, y).buffer(VIA_SIZE / 2))
    for zone in board.zones:
        if zone.keepoutSettings:
            obstacles_in3.append(Polygon([(c.X, c.Y) for c in zone.polygons[0].coordinates]).buffer(0))
    grown = unary_union(obstacles_in3).buffer(CLEARANCE + TIE_WIDTH / 2)
    blocked_prep = prepared.prep(grown)
    edge = prepared.prep(split["digital_outline"].union(split["old_in4_modem"]).buffer(-0.3))
    ties = []
    for piece in pieces[1:]:
        starts = [v for v in modem_vias if piece.buffer(0.3).contains(v)]
        goals = sorted((v for v in modem_vias if main.contains(v)), key=lambda v: min(v.distance(s) for s in starts))
        for start in starts[:1]:
            for goal in goals[:8]:
                lo = (min(start.x, goal.x) - 6, min(start.y, goal.y) - 6, max(start.x, goal.x) + 6, max(start.y, goal.y) + 6)
                path = _astar(lambda x, y: blocked_prep.contains(Point(x, y)) or not edge.contains(Point(x, y)),
                              (start.x, start.y), (goal.x, goal.y), lo)
                if path:
                    clear = lambda seg: not seg.buffer(TIE_WIDTH / 2).intersects(  # noqa: E731
                        unary_union(obstacles_in3).buffer(CLEARANCE).difference(
                            unary_union([start.buffer(0.45), goal.buffer(0.45)])))
                    pts = _simplify([(start.x, start.y)] + path[1:-1] + [(goal.x, goal.y)], clear)
                    ties.append({"layer": TIE_LAYER, "width": TIE_WIDTH, "net": "GND_MODEM",
                                 "from_via": [start.x, start.y], "to_via": [goal.x, goal.y], "points": pts,
                                 "length_mm": round(LineString(pts).length, 2)})
                    break
            else:
                ties.append({"from_via": [start.x, start.y], "result": "NO_IN3_PATH_FOUND"})
    return ties
