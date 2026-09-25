#!/usr/bin/env python3
"""Grid A* gap-fill router for connections the autorouter left open.

Input geometry (mm, KiCad y-down) is dumped from the board by
tools/kicad_autoroute_stage_rev_a.py; open connections come from KiCad DRC
(unconnected_items). Each connection is routed on the routing layers with a
fixed width, clearance to all foreign copper, mounting-hole keepouts and the
board edge; layer changes use through vias. Routed items are returned in the
PREROUTE tuple format ('track', layer, net, width, points) / ('via', None, net,
size, [point]).
"""

from __future__ import annotations

import heapq
import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box

GRID_MM = 0.1


class GapFillRouter:
    def __init__(self, geometry: dict, layers: list[str], width: float, clearance: float,
                 via_size: float, via_drill: float, edge_keep: float, hole_keep: float,
                 net_clearance: dict | None = None) -> None:
        # clearance between two nets = max of both class clearances (KiCad rule)
        self.net_clearance = net_clearance or {}
        self.geometry = geometry
        self.layers = layers
        self.width = width
        self.clearance = clearance
        self.via_size = via_size
        self.via_drill = via_drill
        x0, y0, x1, y1 = geometry["outline"]
        self.origin = (x0, y0)
        self.nx = int(round((x1 - x0) / GRID_MM)) + 1
        self.ny = int(round((y1 - y0) / GRID_MM)) + 1
        self.edge_keep = edge_keep
        self.hole_keep = hole_keep
        self.items = self._items()
        self.routed: list[tuple] = []

    # --- geometry -----------------------------------------------------------------
    def _items(self) -> list[tuple[str, set, object]]:
        items = []
        all_layers = set(self.layers) | {"F.Cu", "B.Cu", "In1.Cu", "In2.Cu"}
        for track in self.geometry["tracks"]:
            shape = LineString([track["start"], track["end"]]).buffer(track["width"] / 2)
            items.append((track["net"], {track["layer"]}, shape))
        for via in self.geometry["vias"]:
            items.append((via["net"], all_layers, Point(via["pos"]).buffer(via["size"] / 2)))
        for pad in self.geometry["pads"]:
            if not pad["layers"]:
                continue  # paste/mask-only apertures carry no copper
            items.append((pad["net"], set(pad["layers"]), Polygon(pad["poly"]) if len(pad["poly"]) >= 3
                          else Point(pad["pos"]).buffer(0.3)))
        return items

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return (int(round((x - self.origin[0]) / GRID_MM)), int(round((y - self.origin[1]) / GRID_MM)))

    def _xy(self, i: int, j: int) -> tuple[float, float]:
        return (self.origin[0] + i * GRID_MM, self.origin[1] + j * GRID_MM)

    def _rasterize(self, grid: np.ndarray, shape, margin: float) -> None:
        grown = shape.buffer(margin) if margin > 0 else shape
        minx, miny, maxx, maxy = grown.bounds
        i0, j0 = self._cell(minx, miny)
        i1, j1 = self._cell(maxx, maxy)
        i0, j0 = max(i0 - 1, 0), max(j0 - 1, 0)
        i1, j1 = min(i1 + 1, self.nx - 1), min(j1 + 1, self.ny - 1)
        if i1 < i0 or j1 < j0:
            return
        xs = self.origin[0] + np.arange(i0, i1 + 1) * GRID_MM
        ys = self.origin[1] + np.arange(j0, j1 + 1) * GRID_MM
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        inside = shapely.contains_xy(grown, gx, gy)
        grid[i0:i1 + 1, j0:j1 + 1] |= inside

    def _blocked(self, net: str) -> tuple[np.ndarray, np.ndarray]:
        """Per-layer track-centre blocking and via-centre blocking for one net."""
        own = self.net_clearance.get(net, self.clearance)
        track_block = np.zeros((len(self.layers), self.nx, self.ny), dtype=bool)
        via_block = np.zeros((self.nx, self.ny), dtype=bool)
        foreign = [(n, ls, s) for n, ls, s in self.items if n != net]
        foreign += [(n, ls, s) for n, ls, s in self._routed_shapes() if n != net]
        for item_net, item_layers, shape in foreign:
            gap = max(own, self.net_clearance.get(item_net, self.clearance), self.clearance) + 0.005
            for index, layer in enumerate(self.layers):
                if layer in item_layers:
                    self._rasterize(track_block[index], shape, gap + self.width / 2)
            self._rasterize(via_block, shape, gap + self.via_size / 2)
        # no via in or next to any SMD pad, own net included (solder wicking); own
        # vias and plated holes keep >= 0.25 mm hole-to-hole
        for pad in self.geometry["pads"]:
            if pad["net"] != net or len(pad["poly"]) < 3 or not pad["layers"]:
                continue
            margin = self.via_size / 2 + (0.05 if pad["layers"] == ["F.Cu"] else 0.3)
            self._rasterize(via_block, Polygon(pad["poly"]), margin)
        for via in self.geometry["vias"]:
            if via["net"] == net:
                self._rasterize(via_block, Point(via["pos"]).buffer(via["size"] / 2), 0.55)
        x0, y0, x1, y1 = self.geometry["outline"]
        frame = box(x0, y0, x1, y1).exterior.buffer(0.001)
        for index in range(len(self.layers)):
            self._rasterize(track_block[index], frame, self.edge_keep + self.width / 2)
        self._rasterize(via_block, frame, self.edge_keep + self.via_size / 2)
        for hole in self.geometry["holes"]:
            disc = Point(hole).buffer(0.001)
            for index in range(len(self.layers)):
                self._rasterize(track_block[index], disc, self.hole_keep + self.width / 2)
            self._rasterize(via_block, disc, self.hole_keep + self.via_size / 2)
        return track_block, via_block

    def _routed_shapes(self):
        shapes = []
        for kind, layer, net, size, points in self.routed:
            if kind == "track":
                shapes.append((net, {layer}, LineString(points).buffer(size / 2)))
            else:
                shapes.append((net, set(self.layers) | {"In1.Cu"}, Point(points[0]).buffer(size / 2)))
        return shapes

    def _own_cells(self, net: str, anchor: tuple[float, float]) -> list[tuple[int, int, int]]:
        """Grid cells on the copper of `net` that contains the anchor point."""
        point = Point(anchor)
        cells = []
        for item_net, item_layers, shape in self.items + self._routed_shapes():
            if item_net != net or shape.distance(point) > 0.05:
                continue
            # land strictly on copper: erode rounded/approximated outlines
            eroded = shape.buffer(-0.12)
            shape = eroded if not eroded.is_empty else shape.centroid.buffer(0.05)
            minx, miny, maxx, maxy = shape.bounds
            i0, j0 = self._cell(minx, miny)
            i1, j1 = self._cell(maxx, maxy)
            for i in range(max(i0, 0), min(i1, self.nx - 1) + 1):
                for j in range(max(j0, 0), min(j1, self.ny - 1) + 1):
                    if shape.contains(Point(self._xy(i, j))):
                        for index, layer in enumerate(self.layers):
                            if layer in item_layers:
                                cells.append((index, i, j))
        return cells

    # --- search -------------------------------------------------------------------
    def route(self, net: str, anchor_a: tuple[float, float], anchor_b: tuple[float, float]) -> bool:
        track_block, via_block = self._blocked(net)
        starts = self._own_cells(net, anchor_a)
        goals = set(self._own_cells(net, anchor_b))
        if not starts or not goals:
            return False
        for layer, i, j in list(starts) + list(goals):
            track_block[layer, i, j] = False
        goal_xy = np.array([self._xy(i, j) for _, i, j in goals])
        gx, gy = goal_xy[:, 0].mean(), goal_xy[:, 1].mean()

        def heuristic(i: int, j: int) -> float:
            x, y = self._xy(i, j)
            return math.hypot(x - gx, y - gy) / GRID_MM

        steps = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                 (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]
        via_cost = 25.0
        best = {}
        parent = {}
        heap = []
        for start in starts:
            best[start] = 0.0
            heapq.heappush(heap, (heuristic(start[1], start[2]), 0.0, start))
        found = None
        expanded = 0
        while heap and expanded < 2_000_000:
            _, cost, node = heapq.heappop(heap)
            if cost > best.get(node, math.inf):
                continue
            expanded += 1
            if node in goals:
                found = node
                break
            layer, i, j = node
            for di, dj, weight in steps:
                ni, nj = i + di, j + dj
                if 0 <= ni < self.nx and 0 <= nj < self.ny and not track_block[layer, ni, nj]:
                    nxt = (layer, ni, nj)
                    new_cost = cost + weight
                    if new_cost < best.get(nxt, math.inf):
                        best[nxt] = new_cost
                        parent[nxt] = node
                        heapq.heappush(heap, (new_cost + heuristic(ni, nj), new_cost, nxt))
            if not via_block[i, j]:
                for other in range(len(self.layers)):
                    if other != layer and not track_block[other, i, j]:
                        nxt = (other, i, j)
                        new_cost = cost + via_cost
                        if new_cost < best.get(nxt, math.inf):
                            best[nxt] = new_cost
                            parent[nxt] = node
                            heapq.heappush(heap, (new_cost + heuristic(i, j), new_cost, nxt))
        if found is None:
            return False
        path = [found]
        while path[-1] in parent:
            path.append(parent[path[-1]])
        path.reverse()
        self._emit(net, path)
        return True

    def _emit(self, net: str, path: list[tuple[int, int, int]]) -> None:
        path = _merge_close_hops(path, int(round(0.6 / GRID_MM)))
        segment: list[tuple[float, float]] = []
        current_layer = path[0][0]
        for layer, i, j in path:
            point = tuple(round(v, 4) for v in self._xy(i, j))
            if layer != current_layer:
                if len(segment) >= 2:
                    self.routed.append(("track", self.layers[current_layer], net, self.width, _simplify(segment)))
                self.routed.append(("via", None, net, self.via_size, [point]))
                segment = [point]
                current_layer = layer
            else:
                segment.append(point)
        if len(segment) >= 2:
            self.routed.append(("track", self.layers[current_layer], net, self.width, _simplify(segment)))


def _merge_close_hops(path: list[tuple[int, int, int]], min_cells: int) -> list[tuple[int, int, int]]:
    """Two layer changes closer than min_cells (a short excursion to another layer
    and back) are folded back onto the original layer."""
    changed = True
    while changed:
        changed = False
        changes = [k for k in range(1, len(path)) if path[k][0] != path[k - 1][0]]
        for first, second in zip(changes, changes[1:]):
            if path[first - 1][0] == path[second][0]:
                a, b = path[first], path[second - 1]
                if max(abs(a[1] - b[1]), abs(a[2] - b[2])) < min_cells:
                    layer = path[first - 1][0]
                    path = path[:first] + [(layer, i, j) for _, i, j in path[first:second]] + path[second:]
                    changed = True
                    break
    return path


def _simplify(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop repeated and collinear grid points so the track is a short polyline."""
    points = [p for k, p in enumerate(points) if k == 0 or p != points[k - 1]]
    if len(points) <= 2:
        return points
    kept = [points[0]]
    for previous, current, following in zip(points, points[1:], points[2:]):
        d1 = (round(current[0] - previous[0], 4), round(current[1] - previous[1], 4))
        d2 = (round(following[0] - current[0], 4), round(following[1] - current[1], 4))
        if d1 != d2:
            kept.append(current)
    kept.append(points[-1])
    return kept


def route_all(make_router, pairs: list[tuple[str, tuple, tuple]], attempts: int = 6):
    """Route every pair; on failure rip everything up and route the failed pairs
    first (a simple negotiated order). Returns (router, failed_pairs)."""
    order = list(pairs)
    best = None
    for _ in range(attempts):
        router = make_router()
        failed = [pair for pair in order if not router.route(*pair)]
        if best is None or len(failed) < len(best[1]):
            best = (router, failed)
        if not failed:
            break
        order = failed + [pair for pair in order if pair not in failed]
    return best
