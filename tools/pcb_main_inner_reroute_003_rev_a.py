#!/usr/bin/env python3
"""PCB-MAIN inner-signal reroute 003 (option (a) of the ground-domain 002 record): geometry.

Moves every OCTOSPI / SDIO / EN_MODEM run that candidate 002 leaves on In2.Cu / In3.Cu (no GND_DIGITAL
reference) to the outer layers, each used only where its reference plane is GND_DIGITAL:
  F.Cu over In1.Cu (outside the In1 GND_MODEM zone), B.Cu over In4.Cu (outside the In4 GND_MODEM pieces).
Per net the In2/In3 segments are removed and the two remaining copper groups are joined between the
through vias / through-hole pad the inner run used. A layer change away from a terminal adds a through
via 0.5/0.3 mm (the size these nets already use) where it clears other-net copper on all six layers and
both references are digital. Every F.Cu<->B.Cu transition of a rerouted net gets a GND_DIGITAL return via
within RETURN_VIA_MM (existing or added). The OCTOSPI signals CLK, IO0-IO3 are then length-matched end to
end (U1 pin -> series resistor -> U2 pin: track length + BOARD_THICKNESS per F.Cu<->B.Cu transition) to
MATCH_TOL_MM with U-shaped serpentines on straight segments of the rerouted runs.

Search: minimum-cost path (skimage.graph.MCP_Geometric) on a 0.05 mm raster with three planes
F.Cu / via / B.Cu; the via plane costs VIA_COST_MM and is open only where a via fits. Rasters are built
once from exact shapely geometry (shapely.contains_xy); every produced segment and via is re-checked
against exact geometry: 0.20 mm to other-net copper on its layer(s), 0.25 mm to every other-net hole,
keep-outs, the reference boundary (REF_MARGIN) and the 0.5 mm board-edge band.
Plan construction (the result is hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/REROUTE_PLAN.json, applied
and re-verified by tools/apply_pcb_main_inner_reroute_003_candidate_rev_a.py): negotiated routing of all nets
(route_negotiated: PathFinder present/history costs), legalize() + improve(), then the four U1-side runs re-made
along LANES (plan_lanes), return_vias() and tune_lengths().
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pcb_main_ground_domain_002_rev_a as geo  # noqa: E402

NETS = ["NOR_CLK_U1", "NOR_IO0_U1", "NOR_IO1_U1", "NOR_IO2_U1", "NOR_CLK_U2", "NOR_IO0_U2", "NOR_IO1_U2",
        "NOR_IO2_U2", "NOR_IO3_U2", "SD_D2_U1", "EN_MODEM", "NOR_NCS_U2"]
# NOR_NCS_U2 has no inner run, but its F.Cu run from U1.39 inside the U1 body to the R7/U2.7 junction cuts the IO0-IO2
# pins off the body interior; that part is re-routed (the short R7.2 / U2.7 stubs at the junction stay)
PARTIAL_REROUTE = {"NOR_NCS_U2": ("U1.39", (69.97, 33.85))}
SIGNALS = ["CLK", "IO0", "IO1", "IO2", "IO3"]
# nets whose fan-out at this footprint (F.Cu stub + via to the old inner run) is removed as well: the run
# starts at the pad itself, so the router chooses the escape and the layer change under the U1 body
FREE_FANOUT = {"NOR_CLK_U1": ("U1",), "NOR_IO0_U1": ("U1", "R9"), "NOR_IO1_U1": ("U1", "R10"),
               "NOR_IO2_U1": ("U1", "R11"), "NOR_IO0_U2": ("R9",), "NOR_IO1_U2": ("R10", "U2"),
               "NOR_IO2_U2": ("R11",), "NOR_CLK_U2": ("R8",), "NOR_NCS_U2": ("U1",)}  # R8 stays; its old U2-side stub crossed the new row
# R9, R10, R11 (22 ohm 0402, all equal) are re-placed so the resistor row above U1 has the U1 pin order:
# R8 CLK (unchanged, ECO-002 position), R9 IO0, R10 IO1, R11 IO2 (placement authority rows updated); rotated
# 90 deg so pin 1 (U1 side) faces down towards U1 and pin 2 (U2 side) faces up: no interleaving in the row
RESISTOR_MOVES = {"R9": (60.5, 19.75, 90), "R10": (62.0, 19.75, 90), "R11": (63.5, 19.75, 90)}
# U1 side: the F.Cu area under the U1 body is closed by the pad ring (0.5 mm pitch) except at the corners, and the
# BOOT0 B.Cu track cuts the body diagonally. Each U1-side run is an F.Cu stub under the body to a via in the
# triangle above BOOT0, B.Cu through its own gap of the TP_EOL test-pad row (B.Cu, 1.7 mm pads, 2.54 mm pitch) and
# a via under its resistor (LANES); the layer is restricted to B.Cu outside the U1 body and the ends.
LAYER_BIAS = {"NOR_CLK_U1": "B.Cu", "NOR_IO0_U1": "B.Cu", "NOR_IO1_U1": "B.Cu", "NOR_IO2_U1": "B.Cu",
              "NOR_NCS_U2": "B.Cu"}  # NCS (U1.39, between CLK and IO0) drops to B.Cu at its pin and passes under IO0-IO2
ESCAPE_REF, ESCAPE_MM = "U1", 1.5  # F.Cu and layer changes allowed only within the U1 pad hull + ESCAPE_MM,
ESCAPE_END_MM = 3.0                 # within this distance of either end of the run, and where B.Cu has no reference
# U1-side lanes (triangle via target, via target under the resistor), routed left to right with route_legs()
LANES = {"NOR_CLK_U1": ((55.2, 24.3), (54.7, 19.75)), "NOR_IO0_U1": ((56.9, 24.2), (60.5, 20.95)),
         "NOR_IO1_U1": ((57.6, 24.9), (62.0, 20.95)), "NOR_IO2_U1": ((58.4, 26.5), (63.5, 20.95))}
# the area right of the series resistors belongs to the U2-side runs (they leave R8.2/R9.2/R11.2 towards U2):
# the U1-side runs and EN_MODEM (which goes left, to J_PWR) must not use it
ROW_ABOVE, ROW_BELOW = (59.9, 14.0, 80.0, 19.65), (59.9, 19.85, 64.3, 30.0)
NET_KEEPOUT = {**{n: [ROW_ABOVE, (64.3, 19.65, 80.0, 30.0)]
                  for n in ("NOR_CLK_U1", "NOR_IO0_U1", "NOR_IO1_U1")},
               # IO2 (R11, right end of the row) passes the TP_EOL.13 test pad on its right side
               "NOR_IO2_U1": [ROW_ABOVE, (66.5, 19.65, 80.0, 30.0)],
               **{n: [ROW_BELOW] for n in ("NOR_IO0_U2", "NOR_IO1_U2", "NOR_IO2_U2")},
               "EN_MODEM": [(56.0, 14.0, 80.0, 30.0)]}
# EN_MODEM (U1.85, top row) leaves to the left, NOR_CLK_U1 comes from the bottom row to R8 above the top row;
# In4 above the top row and left of U1 is GND_MODEM, so neither can cross the other on B.Cu there. NOR_CLK_U1
# therefore changes to F.Cu at the top-RIGHT U1 corner and reaches R8.1 from the right; EN_MODEM keeps the left.
NET_VIA_KEEPOUT = {"NOR_CLK_U1": [(30.0, 14.0, 47.5, 42.0)]}
INNER = ("In2.Cu", "In3.Cu")
ROUTE_LAYERS = ("F.Cu", "B.Cu")
REFERENCE_PLANE = {"F.Cu": "In1.Cu", "B.Cu": "In4.Cu"}
CLEARANCE, HOLE_CLEARANCE, EDGE, REF_MARGIN = 0.20, 0.25, 0.5, 0.3
VIA_SIZE, VIA_DRILL, VIA_COST_MM = 0.5, 0.3, 6.0
STEP = 0.05
RASTER_MARGIN = 0.005       # raster obstacles grown by this much: covers the chord sag between grid points
RETURN_VIA_MM = 2.0
BOARD_THICKNESS = 1.6
MATCH_TOL_MM = 1.0
MEANDER_PITCH = 0.6          # centre-to-centre spacing of adjacent serpentine legs (0.45 mm gap at 0.15 mm)
MEANDER_AMPLITUDES = (2.0, 1.5, 1.25, 1.0, 0.75, 0.5)


def shp():
    return geo._shapely()


# ------------------------------------------------------------------------------------------ board model
def net_items(board, net):
    return [(k, layer, g, raw) for n, k, layer, g, raw in geo.items(board) if n == net]


def groups_after_removal(board, net):
    """Copper groups of `net` once its In2/In3 segments are gone, and the inner-run end points."""
    pads = [(f"{geo.reference(fp)}.{p.number}", geo.pad_geometry(fp, p), geo.pad_layers(p))
            for fp in board.footprints for p in fp.pads if p.net and p.net.name == net]
    kept, inner, vias = [], [], []
    partial = partial_path(board, net) if net in PARTIAL_REROUTE else []
    for kind, layer, g, raw in net_items(board, net):
        if kind == "via":
            vias.append((f"via@{g.x:.4f},{g.y:.4f}", g, set(geo.LAYERS)))
        elif layer in INNER or any(g.equals_exact(q, 1e-6) for q in partial):
            inner.append(g)
        else:
            kept.append((f"trk@{layer}", g, {layer}))
    nodes = [("pad",) + p for p in pads] + [("trk",) + t for t in kept] + [("via",) + v for v in vias]
    parent = list(range(len(nodes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if nodes[i][3] & nodes[j][3] and nodes[i][2].distance(nodes[j][2]) < 1e-3:
                parent[find(i)] = find(j)
    comps: dict = {}
    for i, node in enumerate(nodes):
        comps.setdefault(find(i), []).append(node)
    terminals = []
    for comp in comps.values():
        refs = FREE_FANOUT.get(net, ())
        if refs and not any(nd[0] == "pad" for nd in comp):
            # fan-out left behind by a re-placed resistor: no pad any more, removed with the fan-out
            removed = [{"kind": "via" if k == "via" else "track", "layer": None if k == "via" else n.split("@")[1],
                        "wkt": gg.wkt} for k, n, gg, _ in comp if k in ("via", "trk")]
            terminals.append({"members": [], "removed": removed, "ends": [], "dangling": True})
            continue
        pad_nodes = [nd for nd in comp if nd[0] == "pad" and nd[1].split(".")[0] in refs]
        if pad_nodes:
            kind, name, g, layers = pad_nodes[0]
            removed = [{"kind": "via" if k == "via" else "track", "layer": None if k == "via" else n.split("@")[1],
                        "wkt": gg.wkt} for k, n, gg, _ in comp if k in ("via", "trk")]
            terminals.append({"members": [name], "removed": removed,
                              "ends": [{"name": name, "x": round(g.centroid.x, 4), "y": round(g.centroid.y, 4),
                                        "kind": "smd", "layer": sorted(layers & set(ROUTE_LAYERS))[0]}]})
            continue
        ends = []
        if net in PARTIAL_REROUTE:
            jx, jy = junction_point(board, net)
            Point = shp()[1]
            if any(k == "trk" and g.distance(Point(jx, jy)) < 1e-3 for k, _, g, _ in comp):
                ends.append({"name": f"{net}@{jx},{jy}", "x": jx, "y": jy, "kind": "smd", "layer": "F.Cu"})
        for kind, name, g, layers in comp:
            if kind == "trk" or not any(seg.distance(g) < 1e-3 for seg in inner):
                continue
            if kind == "via" or (kind == "pad" and set(geo.LAYERS) <= layers):
                point = g if kind == "via" else g.centroid
                ends.append({"name": name, "x": round(point.x, 4), "y": round(point.y, 4), "kind": kind})
        terminals.append({"members": sorted(n for k, n, _, _ in comp if k != "trk"), "ends": ends, "removed": []})
    return [t for t in terminals if not t.get("dangling")] + [t for t in terminals if t.get("dangling")], \
        sum(s.length for s in inner)


def board_outline(board):
    box = shp()[3]
    xs, ys = [], []
    for item in board.graphicItems:
        if getattr(item, "layer", None) == "Edge.Cuts":
            for attr in ("start", "end"):
                p = getattr(item, attr, None)
                if p is not None:
                    xs.append(p.X)
                    ys.append(p.Y)
    return box(min(xs), min(ys), max(xs), max(ys))


def modem_reference(board, plane):
    Polygon, unary_union = shp()[2], shp()[4]
    parts = [Polygon([(c.X, c.Y) for c in z.polygons[0].coordinates]).buffer(0)
             for z in board.zones if z.netName == "GND_MODEM" and plane in z.layers and not z.keepoutSettings]
    return unary_union(parts) if parts else Polygon()


def keepouts(board):
    Polygon, unary_union = shp()[2], shp()[4]
    parts = [Polygon([(c.X, c.Y) for c in z.polygons[0].coordinates]).buffer(0)
             for z in board.zones if z.keepoutSettings]
    return unary_union(parts) if parts else Polygon()


def junction_point(board, net):
    """The exact track end point nearest to the PARTIAL_REROUTE junction (given to 0.02 mm)."""
    tx, ty = PARTIAL_REROUTE[net][1]
    pts = [c for k, layer, g, raw in net_items(board, net) if k == "track" for c in (g.coords[0], g.coords[-1])]
    best = min(pts, key=lambda c: math.dist(c, (tx, ty)))
    assert math.dist(best, (tx, ty)) < 0.02, f"{net}: junction {tx, ty} not found"
    return round(best[0], 4), round(best[1], 4)


def partial_path(board, net):
    """Track segments of `net` on the path from the pad named in PARTIAL_REROUTE to its junction point."""
    Point = shp()[1]
    pad_name = PARTIAL_REROUTE[net][0]
    jx, jy = junction_point(board, net)
    pad = next(geo.pad_geometry(fp, p) for fp in board.footprints for p in fp.pads
               if f"{geo.reference(fp)}.{p.number}" == pad_name)
    segs = [g for k, layer, g, raw in net_items(board, net) if k == "track"]
    start = [i for i, g in enumerate(segs) if g.distance(pad) < 1e-3]
    goal = Point(jx, jy)
    prev, frontier, seen = {}, list(start), set(start)
    found = None
    while frontier:
        i = frontier.pop(0)
        if segs[i].distance(goal) < 1e-3:
            found = i
            break
        for j, g in enumerate(segs):
            if j not in seen and g.distance(segs[i]) < 1e-3:
                seen.add(j)
                prev[j] = i
                frontier.append(j)
    assert found is not None, f"{net}: no track path from {pad_name} to {(jx, jy)}"
    path = [found]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    return [segs[i] for i in path]


def removed_items(board):
    """(net, kind, layer, geometry) of the fan-out copper removed by FREE_FANOUT."""
    from shapely import wkt
    out = []
    for net in FREE_FANOUT:
        for term in groups_after_removal(board, net)[0]:
            for item in term["removed"]:
                out.append((net, item["kind"], item["layer"], wkt.loads(item["wkt"])))
    for net in PARTIAL_REROUTE:
        for g in partial_path(board, net):
            layer = next(lay for k, lay, gg, raw in net_items(board, net) if k == "track" and gg.equals_exact(g, 1e-6))
            out.append((net, "track", layer, g))
    return out


def is_removed(removed, net, kind, layer, g):
    return any(n == net and k == kind and (kind == "via" or lay == layer) and g.equals_exact(rg, 1e-6)
               for n, k, lay, rg in removed)


def copper_by_net(board):
    """{"F.Cu"|"B.Cu"|"ALL": {net: [geometry]}} and {net: [hole]}; the In2/In3 runs of the rerouted nets
    are excluded (they are removed by this candidate)."""
    Point = shp()[1]
    per = {"F.Cu": {}, "B.Cu": {}, "ALL": {}}
    holes: dict = {}
    for fp in board.footprints:
        for pad in fp.pads:
            net = pad.net.name if pad.net else f"__nc_{geo.reference(fp)}_{pad.number}"
            g = geo.pad_geometry(fp, pad)
            layers = geo.pad_layers(pad)
            for layer in ROUTE_LAYERS:
                if layer in layers:
                    per[layer].setdefault(net, []).append(g)
            if layers & set(geo.LAYERS):
                per["ALL"].setdefault(net, []).append(g)
            if pad.drill is not None and getattr(pad.drill, "diameter", 0):
                holes.setdefault(net, []).append(Point(g.centroid).buffer(pad.drill.diameter / 2))
    removed = removed_items(board)
    for net, kind, layer, g, raw in geo.items(board):
        if (net in FREE_FANOUT or net in PARTIAL_REROUTE) and is_removed(removed, net, kind, layer, g):
            continue
        if kind == "via":
            body = g.buffer(raw.size / 2)
            for key in ("F.Cu", "B.Cu", "ALL"):
                per[key].setdefault(net, []).append(body)
            holes.setdefault(net, []).append(g.buffer(raw.drill / 2))
        elif not (net in NETS and layer in INNER):
            body = g.buffer(raw.width / 2)
            if layer in ROUTE_LAYERS:
                per[layer].setdefault(net, []).append(body)
            per["ALL"].setdefault(net, []).append(body)
    return per, holes


# ------------------------------------------------------------------------------------------ In4 split with corridor
def split_in4_corridor(board, domains, corridor_refs: tuple) -> dict:
    """tools/pcb_main_ground_domain_002_rev_a.split_in4 with one addition: the joint convex hull of the
    corridor_refs pads (+1.0 mm) is kept GND_DIGITAL as one region (the OCTOSPI chain U1 - R9..R12 - U2), so the
    runs between them have a GND_DIGITAL reference on In4. Everything else is the 002 construction verbatim."""
    LineString, Point, Polygon, box, unary_union = geo._shapely()
    modem_nets = {n for n, d in domains.items() if d == "GND_MODEM"} | {"GND_MODEM"}
    digital_nets = {n for n, d in domains.items() if d == "GND_DIGITAL"}
    old4 = geo.zone_outline(board, "GND_MODEM", "In4.Cu")
    digital_outline = geo.zone_outline(board, "GND_DIGITAL", "In1.Cu")
    tracks = geo.items(board)
    parts = [box(*geo.CELL)]
    net_pads = defaultdict(list)
    modem_pad_geoms = []
    for fp in board.footprints:
        geoms, modem = [], False
        for pad in fp.pads:
            geom = geo.pad_geometry(fp, pad)
            geoms.append(geom)
            net = pad.net.name if pad.net else None
            if net in modem_nets:
                modem = True
                net_pads[net].append(geom.centroid.coords[0])
                modem_pad_geoms.append(geom)
        if geo.reference(fp) == "J_PWR":
            parts += [geo.pad_geometry(fp, p).buffer(0.6) for p in fp.pads if p.net and p.net.name in modem_nets]
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
            parts += [LineString([a, c]).buffer(1.5) for a, c in geo._mst(pts)]
    region = unary_union(parts).buffer(1.5).buffer(-1.5).intersection(old4)
    keep = unary_union([unary_union([geo.pad_geometry(fp, p) for p in fp.pads]).convex_hull.buffer(1.0)
                        for fp in board.footprints if geo.reference(fp) in geo.DIGITAL_PRIORITY_REFS])
    digital_tracks = unary_union([geom.buffer(raw.width / 2 + 0.8) for net, kind, layer, geom, raw in tracks
                                  if kind == "track" and layer == "B.Cu" and net in digital_nets])
    keep = keep.union(digital_tracks)
    if corridor_refs:
        keep = keep.union(unary_union([geo.pad_geometry(fp, p) for fp in board.footprints if geo.reference(fp) in corridor_refs
                                       for p in fp.pads]).convex_hull.buffer(1.0))
    islands = unary_union([g.buffer(0.35) for g in modem_pad_geoms + modem_copper if g.distance(keep) < 1.0])
    region = region.difference(keep).union(islands.intersection(old4)).buffer(0)
    region = region.buffer(-0.2).buffer(0.2).union(islands.intersection(old4)).buffer(0)
    # a modem piece must touch GND_MODEM copper, otherwise it is dead copper (no reference)
    gnd_modem = [geo.pad_geometry(fp, p) for fp in board.footprints for p in fp.pads
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
    digital = digital_outline.difference(modem.buffer(geo.CLEARANCE))
    return {"modem_pieces": pieces, "modem": modem, "digital_outline": digital_outline,
            "digital_effective": digital, "old_in4_modem": old4, "digital_keep": keep}


# ------------------------------------------------------------------------------------------ rasters
class Grid:
    def __init__(self, bounds):
        self.x0, self.y0, x1, y1 = bounds
        self.w = int(round((x1 - self.x0) / STEP)) + 1
        self.h = int(round((y1 - self.y0) / STEP)) + 1

    def xy(self, i, j):
        return round(self.x0 + i * STEP, 4), round(self.y0 + j * STEP, 4)

    def ij(self, x, y):
        return int(round((x - self.x0) / STEP)), int(round((y - self.y0) / STEP))

    def mask(self, g):
        """(row slice, column slice, bool array) of grid points covered by g, over g's window only."""
        import shapely
        if g.is_empty:
            return None
        minx, miny, maxx, maxy = g.bounds
        i0 = max(0, int(math.floor((minx - self.x0) / STEP)))
        j0 = max(0, int(math.floor((miny - self.y0) / STEP)))
        i1 = min(self.w - 1, int(math.ceil((maxx - self.x0) / STEP)))
        j1 = min(self.h - 1, int(math.ceil((maxy - self.y0) / STEP)))
        if i1 < i0 or j1 < j0:
            return None
        xx, yy = np.meshgrid(self.x0 + np.arange(i0, i1 + 1) * STEP, self.y0 + np.arange(j0, j1 + 1) * STEP)
        return slice(j0, j1 + 1), slice(i0, i1 + 1), shapely.contains_xy(g, xx, yy)

    def full(self, g):
        out = np.zeros((self.h, self.w), bool)
        r = self.mask(g)
        if r:
            out[r[0], r[1]] |= r[2]
        return out


class Occupancy:
    """Per-kind counters of how many owners block a cell, with per-owner masks for subtraction."""

    def __init__(self, grid, kinds):
        self.grid = grid
        self.count = {k: np.zeros((grid.h, grid.w), np.int16) for k in kinds}
        self.masks: dict = {}

    def add(self, kind, owner, g):
        r = self.grid.mask(g)
        if r is None:
            return
        self.count[kind][r[0], r[1]] += r[2]
        self.masks.setdefault((kind, owner), []).append(r)

    def remove_owner(self, owner):
        for key in [k for k in self.masks if k[1] == owner]:
            for js, is_, m in self.masks[key]:
                self.count[key[0]][js, is_] -= m
            del self.masks[key]

    def blocked_except(self, kind, owners):
        c = self.count[kind].copy()
        for (k, own), rs in self.masks.items():
            if k == kind and own in owners:
                for js, is_, m in rs:
                    c[js, is_] -= m
        return c > 0


class Router:
    def __init__(self, board, log=print):
        LineString, Point, Polygon, box, unary_union = shp()
        self.board = board
        self.outline = board_outline(board)
        self.grid = Grid(self.outline.bounds)
        self.info = {n: groups_after_removal(board, n) for n in NETS}
        for n, (terms, _) in self.info.items():
            real = [t for t in terms if not t.get("dangling")]
            assert len(real) == 2 and all(t["ends"] for t in real), f"{n}: unexpected topology {terms}"
        self.width = {n: max([raw.width for k, layer, g, raw in net_items(board, n) if k == "track" and layer in INNER]
                             or [raw.width for k, layer, g, raw in net_items(board, n) if k == "track"])
                      for n in NETS}
        self.w = max(self.width.values())
        self.copper, self.holes = copper_by_net(board)
        self.keepout = keepouts(board)
        self.modem = {layer: modem_reference(board, REFERENCE_PLANE[layer]) for layer in ROUTE_LAYERS}
        self.occ = Occupancy(self.grid, ["trk_F.Cu", "trk_B.Cu", "via"])
        for layer in ROUTE_LAYERS:
            for net, geoms in self.copper[layer].items():
                self.occ.add(f"trk_{layer}", ("net", net), unary_union(geoms).buffer(CLEARANCE + self.w / 2 + RASTER_MARGIN))
        for net, geoms in self.holes.items():
            u = unary_union(geoms)
            for layer in ROUTE_LAYERS:
                self.occ.add(f"trk_{layer}", ("hole", net), u.buffer(HOLE_CLEARANCE + self.w / 2 + RASTER_MARGIN))
            self.occ.add("via", ("hole", net), u.buffer(HOLE_CLEARANCE + VIA_DRILL / 2 + RASTER_MARGIN))
        for net, geoms in self.copper["ALL"].items():
            self.occ.add("via", ("net", net), unary_union(geoms).buffer(CLEARANCE + VIA_SIZE / 2 + RASTER_MARGIN))
        outside = box(-1e3, -1e3, 1e3, 1e3)
        self.static = {}
        for layer in ROUTE_LAYERS:
            self.static[f"trk_{layer}"] = self.grid.full(unary_union([
                self.keepout.buffer(self.w / 2 + RASTER_MARGIN), self.modem[layer].buffer(REF_MARGIN + RASTER_MARGIN),
                outside.difference(self.outline.buffer(-(EDGE + self.w / 2)))]))
        self.static["via"] = self.grid.full(unary_union([
            self.keepout.buffer(VIA_SIZE / 2), self.modem["F.Cu"].buffer(REF_MARGIN + VIA_SIZE / 2),
            self.modem["B.Cu"].buffer(REF_MARGIN + VIA_SIZE / 2),
            outside.difference(self.outline.buffer(-(EDGE + VIA_SIZE / 2)))]))
        self.occ_runs = Occupancy(self.grid, ["trk_F.Cu", "trk_B.Cu", "via"])
        self.history = {k: np.zeros((self.grid.h, self.grid.w), np.float32) for k in self.occ.count}
        self.paths: dict = {}
        self.routed: dict = {}
        log("rasters ready")

    # ---- occupancy of 003 copper
    def _add_run(self, run):
        LineString, Point = shp()[0], shp()[1]
        owner = ("run", run["net"])
        for t in run["tracks"]:
            body = LineString(t["points"]).buffer(t["width"] / 2)
            self.occ_runs.add(f"trk_{t['layer']}", owner, body.buffer(CLEARANCE + self.w / 2 + RASTER_MARGIN))
            self.occ_runs.add("via", owner, body.buffer(CLEARANCE + VIA_SIZE / 2 + RASTER_MARGIN))
        for v in run["vias"]:
            body, hole = Point(v["at"]).buffer(VIA_SIZE / 2), Point(v["at"]).buffer(VIA_DRILL / 2)
            for layer in ROUTE_LAYERS:
                self.occ_runs.add(f"trk_{layer}", owner, body.buffer(CLEARANCE + self.w / 2 + RASTER_MARGIN))
                self.occ_runs.add(f"trk_{layer}", owner, hole.buffer(HOLE_CLEARANCE + self.w / 2 + RASTER_MARGIN))
            self.occ_runs.add("via", owner, body.buffer(CLEARANCE + VIA_SIZE / 2 + RASTER_MARGIN))
            self.occ_runs.add("via", owner, hole.buffer(HOLE_CLEARANCE + VIA_DRILL / 2 + RASTER_MARGIN))

    # ---- exact geometry for the final checks
    def strict(self, net, layer, runs, extra_vias=()):
        LineString, Point, unary_union = shp()[0], shp()[1], shp()[4]
        copper = [g for n, gs in self.copper[layer].items() if n != net for g in gs]
        holes = [g for n, gs in self.holes.items() if n != net for g in gs]
        for run in runs:
            if run["net"] == net:
                continue
            copper += [LineString(t["points"]).buffer(t["width"] / 2) for t in run["tracks"] if t["layer"] == layer]
            copper += [Point(v["at"]).buffer(VIA_SIZE / 2) for v in run["vias"]]
            holes += [Point(v["at"]).buffer(VIA_DRILL / 2) for v in run["vias"]]
        copper += [Point(v).buffer(VIA_SIZE / 2) for v in extra_vias]
        holes += [Point(v).buffer(VIA_DRILL / 2) for v in extra_vias]
        return unary_union([unary_union(copper).buffer(CLEARANCE - 1e-4),
                            unary_union(holes).buffer(HOLE_CLEARANCE - 1e-4), self.keepout,
                            self.modem[layer].buffer(REF_MARGIN - self.width.get(net, self.w) / 2 - 1e-4),
                            shp()[3](-1e3, -1e3, 1e3, 1e3).difference(self.outline.buffer(-EDGE))])

    def via_obstacles(self, net, runs, extra_vias=()):
        LineString, Point, unary_union = shp()[0], shp()[1], shp()[4]
        copper = [g for n, gs in self.copper["ALL"].items() if n != net for g in gs]
        holes = [g for n, gs in self.holes.items() if n != net for g in gs]
        for run in runs:
            if run["net"] == net:
                continue
            copper += [LineString(t["points"]).buffer(t["width"] / 2) for t in run["tracks"]]
            copper += [Point(v["at"]).buffer(VIA_SIZE / 2) for v in run["vias"]]
            holes += [Point(v["at"]).buffer(VIA_DRILL / 2) for v in run["vias"]]
        copper += [Point(v).buffer(VIA_SIZE / 2) for v in extra_vias]
        holes += [Point(v).buffer(VIA_DRILL / 2) for v in extra_vias]
        return unary_union(copper), unary_union(holes)

    # ---- search
    def search(self, net, a, b, use_runs=True, margin=10.0, soft=None):
        """use_runs: other 003 runs are hard obstacles; soft=(present_factor): they only add cost
        (negotiated congestion), together with the accumulated history cost."""
        from skimage.graph import MCP_Geometric
        own = {("net", net), ("hole", net), ("run", net)}
        g = self.grid
        (ia, ja), (ib, jb) = g.ij(a["x"], a["y"]), g.ij(b["x"], b["y"])
        m = int(margin / STEP)
        i0, i1 = max(0, min(ia, ib) - m), min(g.w, max(ia, ib) + m + 1)
        j0, j1 = max(0, min(ja, jb) - m), min(g.h, max(ja, jb) + m + 1)
        blocked = {k: (self.occ.blocked_except(k, own) | self.static[k])[j0:j1, i0:i1] for k in self.occ.count}
        if use_runs and soft is None:
            for k in blocked:
                blocked[k] |= self.occ_runs.blocked_except(k, {("run", net)})[j0:j1, i0:i1]
        force = getattr(self, "force_layer", None)
        if force:
            other = "trk_B.Cu" if force == "F.Cu" else "trk_F.Cu"
            blocked[other] = blocked[other] | True
            blocked["via"] = blocked["via"] | True
        elif net in LAYER_BIAS and getattr(self, "restrict", True):
            if not hasattr(self, "_escape"):
                hull = shp()[4]([geo.pad_geometry(fp, p) for fp in self.board.footprints
                                 if geo.reference(fp) == ESCAPE_REF for p in fp.pads]).convex_hull
                self._escape = self.grid.full(hull.buffer(ESCAPE_MM))
            near = self._escape[j0:j1, i0:i1].copy()
            jj, ii = np.mgrid[j0:j1, i0:i1]
            for t in (a, b):  # and around both ends
                ti, tj = g.ij(t["x"], t["y"])
                near |= (ii - ti) ** 2 + (jj - tj) ** 2 <= (ESCAPE_END_MM / STEP) ** 2
            near |= self.static["trk_B.Cu"][j0:j1, i0:i1]  # wherever B.Cu has no digital reference
            other = "trk_B.Cu" if LAYER_BIAS[net] == "F.Cu" else "trk_F.Cu"
            if LAYER_BIAS[net] == "F.Cu":
                blocked[other] = blocked[other] | True
                blocked["via"] = blocked["via"] | True
            else:
                blocked[other] = blocked[other] | ~near
                blocked["via"] = blocked["via"] | ~near
        if net in NET_VIA_KEEPOUT:
            vko = self.grid.full(shp()[4]([shp()[3](*bx) for bx in NET_VIA_KEEPOUT[net]]))[j0:j1, i0:i1]
            blocked["via"] = blocked["via"] | vko
        if net in NET_KEEPOUT:
            ko = self.grid.full(shp()[4]([shp()[3](*bx) for bx in NET_KEEPOUT[net]]))[j0:j1, i0:i1]
            for k in blocked:
                blocked[k] = blocked[k] | ko
        cost = np.full((3, j1 - j0, i1 - i0), np.inf)
        for plane, k, base in ((0, "trk_F.Cu", STEP), (2, "trk_B.Cu", STEP), (1, "via", VIA_COST_MM)):
            c = np.full(blocked[k].shape, base, np.float64)
            if soft is not None:
                others = self.occ_runs.blocked_except(k, {("run", net)})[j0:j1, i0:i1]
                c = c * (1.0 + self.history[k][j0:j1, i0:i1]) * (1.0 + soft * others)
            cost[plane][~blocked[k]] = c[~blocked[k]]
        r = 3
        yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
        disc = (xx ** 2 + yy ** 2) <= r * r
        static = {0: self.static["trk_F.Cu"][j0:j1, i0:i1], 2: self.static["trk_B.Cu"][j0:j1, i0:i1]}
        for (ic, jc) in ((ia, ja), (ib, jb)):  # the terminals are own copper on every layer
            jl, il = jc - j0, ic - i0
            term = a if (ic, jc) == (ia, ja) else b
            planes = (0, 2) if term["kind"] != "smd" else ((0,) if term["layer"] == "F.Cu" else (2,))
            for plane in planes:
                sub = cost[plane][jl - r:jl + r + 1, il - r:il + r + 1]
                forbidden = static[plane][jl - r:jl + r + 1, il - r:il + r + 1]
                if term["kind"] != "smd":
                    sub[disc[:sub.shape[0], :sub.shape[1]] & ~forbidden] = STEP
                cost[plane][jl, il] = STEP  # the terminal itself; leaving on a forbidden layer is not possible
            if term["kind"] != "smd" and not getattr(self, "force_layer", None):
                cost[1][jl, il] = 1e-3
        offsets = [(0, 0, 1), (0, 0, -1), (0, 1, 0), (0, -1, 0), (0, 1, 1), (0, 1, -1), (0, -1, 1), (0, -1, -1),
                   (1, 0, 0), (-1, 0, 0)]
        mcp = MCP_Geometric(cost, offsets=offsets, fully_connected=False)
        def planes_of(t):
            return (0, 2) if t["kind"] != "smd" else ((0,) if t["layer"] == "F.Cu" else (2,))
        starts = [(pl, ja - j0, ia - i0) for pl in planes_of(a)]
        ends = [(pl, jb - j0, ib - i0) for pl in planes_of(b)]
        cum, _ = mcp.find_costs(starts, ends, find_all_ends=True)
        end = min(ends, key=lambda e: cum[e])
        if not np.isfinite(cum[end]):
            return None
        return [(p[0], p[2] + i0, p[1] + j0) for p in mcp.traceback(end)]

    def to_run(self, net, a, b, path, runs):
        LineString, Point = shp()[0], shp()[1]
        g = self.grid
        width = self.width[net]
        term = {g.ij(a["x"], a["y"]): (a["x"], a["y"]), g.ij(b["x"], b["y"]): (b["x"], b["y"])}
        segs, vias, cur, pts = [], [], None, []
        for plane, i, j in path:
            if plane == 1:
                continue
            layer = ROUTE_LAYERS[0 if plane == 0 else 1]
            here = term.get((i, j), g.xy(i, j))
            if cur is None:
                cur = layer
            if layer != cur:
                segs.append((cur, pts))
                if (i, j) not in term:
                    vias.append(here)
                cur, pts = layer, [here]
                continue
            pts.append(here)
        segs.append((cur, pts))
        tracks = []
        exact = list(term.values())
        for layer, xy in segs:
            # grid points inside a terminal's own pad are dropped: the run leaves the exact terminal centre
            keep = [p for k, p in enumerate(xy)
                    if p in exact or k in (0, len(xy) - 1)
                    or min(math.dist(p, e) - (VIA_SIZE / 2 if t["kind"] != "smd" else 0.1)
                           for e, t in ((exact[0], a if exact[0] == (a["x"], a["y"]) else b),
                                        (exact[1], b if exact[1] == (b["x"], b["y"]) else a))) > 0]
            xy = [keep[0]] + [p for k, p in enumerate(keep[1:], 1) if p != keep[k - 1]]
            if len(xy) < 2:
                continue
            strict = self.strict(net, layer, runs)

            def clear(seg, strict=strict):
                return not seg.buffer(width / 2).intersects(strict)

            simple = geo._simplify(xy, clear)
            if any(not clear(LineString([p, q])) for p, q in zip(simple, simple[1:])):
                return None
            tracks.append({"net": net, "layer": layer, "width": width, "points": [list(p) for p in simple],
                           "length_mm": round(LineString(simple).length, 3)})
        copper, holes = self.via_obstacles(net, runs)
        for x, y in vias:
            p = Point(x, y)
            if p.buffer(VIA_SIZE / 2).distance(copper) < CLEARANCE - 1e-4 or \
                    p.buffer(VIA_DRILL / 2).distance(holes) < HOLE_CLEARANCE - 1e-4:
                return None
        return {"net": net, "from": a["name"], "to": b["name"], "tracks": tracks,
                "vias": [{"net": net, "at": [x, y]} for x, y in vias],
                "length_mm": round(sum(t["length_mm"] for t in tracks), 3)}

    def best(self, net, use_runs=True):
        terminals = self.info[net][0]
        pairs = sorted(((ea, eb) for ea in terminals[0]["ends"] for eb in terminals[1]["ends"]),
                       key=lambda p: math.dist((p[0]["x"], p[0]["y"]), (p[1]["x"], p[1]["y"])))
        runs = [r for n, r in self.routed.items() if r and n != net] if use_runs else []
        best = None
        for ea, eb in pairs[:2]:
            for margin in (8.0, 20.0):
                path = self.search(net, ea, eb, use_runs, margin)
                if not path:
                    continue
                run = self.to_run(net, ea, eb, path, runs)
                if run and (best is None or (len(run["vias"]), run["length_mm"]) < (len(best["vias"]), best["length_mm"])):
                    best = run
                break
        return best

    def conflicts(self, run):
        LineString, Point = shp()[0], shp()[1]
        hit = set()
        mine = [(t["layer"], LineString(t["points"]).buffer(t["width"] / 2 + CLEARANCE)) for t in run["tracks"]]
        mine_v = [Point(v["at"]).buffer(VIA_SIZE / 2 + CLEARANCE) for v in run["vias"]]
        for net, other in self.routed.items():
            if not other or net == run["net"]:
                continue
            for t in other["tracks"]:
                body = LineString(t["points"]).buffer(t["width"] / 2)
                if any(layer == t["layer"] and body.intersects(m) for layer, m in mine) or \
                        any(body.intersects(m) for m in mine_v):
                    hit.add(net)
            for v in other["vias"]:
                body = Point(v["at"]).buffer(VIA_SIZE / 2)
                if any(body.intersects(m) for _, m in mine) or any(body.intersects(m) for m in mine_v):
                    hit.add(net)
        return hit

    def save_state(self, path, extra):
        import json
        np.savez_compressed(str(path) + ".npz", **{k.replace(".", "_"): v for k, v in self.history.items()})
        Path(str(path) + ".json").write_text(json.dumps({"routed": self.routed,
                                                         "paths": {n: [list(map(int, q)) for q in p]
                                                                   for n, p in self.paths.items()}, **extra}))

    def load_state(self, path):
        import json
        if not Path(str(path) + ".json").exists():
            return None
        state = json.loads(Path(str(path) + ".json").read_text())
        arrays = np.load(str(path) + ".npz")
        for k in self.history:
            self.history[k] = arrays[k.replace(".", "_")]
        self.routed = state["routed"]
        self.paths = {n: [tuple(q) for q in p] for n, p in state["paths"].items()}
        for run in self.routed.values():
            if run:
                self._add_run(run)
        return state

    def route_negotiated(self, iterations=30, log=print, state_path=None, budget_s=None):
        """PathFinder-style negotiation: every iteration re-routes every net with the other 003 runs as a
        cost (present factor growing each iteration) plus a history cost on cells that stayed contested;
        stops when the exact pairwise check finds no conflict."""
        import time
        t0 = time.time()
        order = sorted(NETS, key=lambda n: -self.info[n][1])
        present, first = 0.5, 1
        if state_path:
            state = self.load_state(state_path)
            if state:
                present, first = state["present"], state["iteration"] + 1
                if state.get("done"):
                    return state["result"]
        pairs, unrouted = set(), []
        for it in range(first, iterations + 1):
            if budget_s and time.time() - t0 > budget_s:
                return {"paused_at": it, "conflicts": sorted(pairs), "unrouted": unrouted}
            for net in order:
                self.occ_runs.remove_owner(("run", net))
                self.routed.pop(net, None)
                terminals = self.info[net][0]
                pairs = sorted(((ea, eb) for ea in terminals[0]["ends"] for eb in terminals[1]["ends"]),
                               key=lambda p: math.dist((p[0]["x"], p[0]["y"]), (p[1]["x"], p[1]["y"])))
                best = None
                for ea, eb in pairs[:2]:
                    for margin in (8.0, 20.0):
                        path = self.search(net, ea, eb, True, margin, soft=present)
                        if not path:
                            continue
                        run = self.to_run(net, ea, eb, path, [])
                        if run and (best is None or run["length_mm"] < best[0]["length_mm"]):
                            best = (run, path)
                        break
                if best:
                    self.routed[net], self.paths[net] = best
                    self._add_run(best[0])
                else:
                    self.routed[net] = None
            conflicts = {n: self.conflicts(r) for n, r in self.routed.items() if r}
            pairs = {tuple(sorted((a, b))) for a, hits in conflicts.items() for b in hits}
            unrouted = [n for n in NETS if not self.routed.get(n)]
            log(f"iteration {it}: present {present:.2f}, conflicts {sorted(pairs)}, unrouted {unrouted}")
            if not pairs and not unrouted:
                result = {"iterations": it, "conflicts": [], "unrouted": []}
                if state_path:
                    self.save_state(state_path, {"present": present, "iteration": it, "done": True, "result": result})
                return result
            for net in {n for pair in pairs for n in pair}:
                for plane, i, j in self.paths.get(net, []):
                    k = ("trk_F.Cu", "via", "trk_B.Cu")[plane]
                    if self.occ_runs.count[k][j, i] > 0:
                        self.history[k][j, i] += 0.3
            present *= 1.6
            if state_path:
                self.save_state(state_path, {"present": present, "iteration": it, "done": False})
        return {"iterations": iterations, "conflicts": sorted(pairs), "unrouted": unrouted}

    def conflict_pairs(self):
        return sorted({tuple(sorted((a, b))) for a, r in self.routed.items() if r for b in self.conflicts(r)})

    def _hard(self, net):
        self.occ_runs.remove_owner(("run", net))
        old = self.routed.pop(net, None)
        run = self.best(net, use_runs=True)
        if run:
            self.routed[net] = run
            self._add_run(run)
            return True
        self.routed[net] = old
        if old:
            self._add_run(old)
        return False

    def legalize(self, rounds=12, log=print):
        """Resolve the conflicts left by negotiation: re-route one net of each conflicting pair with every
        other 003 run as a hard obstacle (then the other net; then both, in both orders)."""
        for _ in range(rounds):
            pairs = self.conflict_pairs()
            log(f"legalize: conflicts {pairs}")
            if not pairs:
                return []
            open_pairs = [pr for pr in pairs if pr not in getattr(self, "_skipped", set())]
            if not open_pairs:
                return pairs
            a, b = open_pairs[0]
            if self._hard(a) and not {tuple(sorted((a, x))) for x in self.conflicts(self.routed[a])}:
                continue
            if self._hard(b) and not {tuple(sorted((b, x))) for x in self.conflicts(self.routed[b])}:
                continue
            done = False
            for first, second in ((a, b), (b, a)):
                saved = {first: self.routed.get(first), second: self.routed.get(second)}
                for n in (first, second):
                    self.occ_runs.remove_owner(("run", n))
                    self.routed[n] = None
                ok = True
                for n in (first, second):
                    run = self.best(n, use_runs=True)
                    if not run:
                        ok = False
                        break
                    self.routed[n] = run
                    self._add_run(run)
                if ok and not any(self.conflicts(self.routed[n]) for n in (first, second)):
                    done = True
                    break
                for n in (first, second):
                    self.occ_runs.remove_owner(("run", n))
                    self.routed[n] = saved[n]
                    if saved[n]:
                        self._add_run(saved[n])
            if not done:
                log(f"legalize: pair {a}/{b} unresolved")
                skipped = getattr(self, "_skipped", set())
                skipped.add((a, b))
                self._skipped = skipped
                if all(pr in skipped for pr in self.conflict_pairs()):
                    return self.conflict_pairs()
        return self.conflict_pairs()

    def improve(self, log=print):
        """Hard re-route of every net; the new run is kept when shorter and conflict-free."""
        for net in sorted(NETS, key=lambda n: -(self.routed[n]["length_mm"] if self.routed.get(n) else 0)):
            old = self.routed.get(net)
            self.occ_runs.remove_owner(("run", net))
            self.routed[net] = None
            run = self.best(net, use_runs=True)
            if run and old and (len(run["vias"]), run["length_mm"]) < (len(old["vias"]), old["length_mm"]) \
                    and not self.conflicts(run):
                self.routed[net] = run
                log(f"improve: {net} {old['length_mm']} -> {run['length_mm']} mm, vias {len(old['vias'])} -> {len(run['vias'])}")
            else:
                self.routed[net] = old
            if self.routed[net]:
                self._add_run(self.routed[net])

    def via_candidates(self, net, target, radius=1.3, extra=()):
        """Grid points within `radius` of target where a through via of `net` fits (raster), nearest first."""
        own = {("net", net), ("hole", net), ("run", net)}
        blocked = self.occ.blocked_except("via", own) | self.static["via"] | \
            self.occ_runs.blocked_except("via", {("run", net)})
        g = self.grid
        ti, tj = g.ij(*target)
        m = int(radius / STEP)
        out = []
        for j in range(tj - m, tj + m + 1):
            for i in range(ti - m, ti + m + 1):
                x, y = g.xy(i, j)
                if math.dist((x, y), target) <= radius and not blocked[j, i] and \
                        all(math.dist((x, y), e) >= VIA_SIZE + CLEARANCE for e in extra):
                    out.append((x, y))
        return sorted(out, key=lambda q: math.dist(q, target))

    def route_legs(self, net, legs):
        """legs: [(start_terminal, end_terminal, layer)]; each leg on one layer; a layer change between legs is a
        via at the shared point. Returns a run, or None."""
        runs = [r for n, r in self.routed.items() if r and n != net]
        tracks, vias = [], []
        for a, b, layer in legs:
            self.force_layer = layer
            try:
                path = self.search(net, a, b, True, 6.0)
            finally:
                self.force_layer = None
            if not path:
                return None
            run = self.to_run(net, a, b, path, runs)
            if not run:
                return None
            tracks += run["tracks"]
        for (a, b, layer), (a2, b2, layer2) in zip(legs, legs[1:]):
            if layer != layer2:
                vias.append({"net": net, "at": [b["x"], b["y"]]})
        copper, holes = self.via_obstacles(net, runs)
        Point = shp()[1]
        for v in vias:
            p = Point(v["at"])
            if p.buffer(VIA_SIZE / 2).distance(copper) < CLEARANCE - 1e-4 or \
                    p.buffer(VIA_DRILL / 2).distance(holes) < HOLE_CLEARANCE - 1e-4:
                return None
        return {"net": net, "from": legs[0][0]["name"], "to": legs[-1][1]["name"], "tracks": tracks, "vias": vias,
                "length_mm": round(sum(t["length_mm"] for t in tracks), 3)}

    def plan_lanes(self, log=print):
        """Re-route the four U1-side nets along LANES (left to right): F.Cu stub -> via in the triangle above
        BOOT0 -> B.Cu -> via under the resistor -> F.Cu to its pin 1 (CLK: to the R8 via)."""
        def term(name, x, y):
            return {"name": name, "x": round(x, 4), "y": round(y, 4), "kind": "via"}
        for net in LANES:
            self.occ_runs.remove_owner(("run", net))
            self.routed[net] = None
        placed = []
        for net, (tri, top) in LANES.items():
            ends = [t["ends"][0] for t in self.info[net][0][:2]]
            start, end = sorted(ends, key=lambda e: not e["name"].startswith("U1"))
            best = None
            for vt in self.via_candidates(net, tri, 1.3, placed)[:10]:
                for vr in self.via_candidates(net, top, 1.0, placed + [vt])[:8]:
                    run = self.route_legs(net, [(start, term("v1", *vt), "F.Cu"), (term("v1", *vt), term("v2", *vr), "B.Cu"),
                                                (term("v2", *vr), end, "F.Cu")])
                    if run and not self.conflicts(run):
                        best = run
                        break
                if best:
                    break
            log(f"lane {net}: {best and (best['length_mm'], best['vias'])}")
            if best:
                best["from"], best["to"] = start["name"], end["name"]
                self.routed[net] = best
                self._add_run(best)
                placed += [tuple(v["at"]) for v in best["vias"]]
        return [n for n in LANES if not self.routed.get(n)]

    def runs(self):
        return [r for r in self.routed.values() if r]


# ------------------------------------------------------------------------------------------ return vias
def transition_points(router, run):
    """Points where the rerouted net changes between F.Cu and B.Cu: every added via, and a terminal via
    whose kept fan-out copper is on the other outer layer than the new run."""
    Point = shp()[1]
    pts = [tuple(v["at"]) for v in run["vias"]]
    for tag in ("from", "to"):
        name = run[tag]
        if not name.startswith("via@"):
            continue
        p = Point(*map(float, name[4:].split(",")))
        fan = {layer for kind, layer, g, raw in net_items(router.board, run["net"])
               if kind == "track" and layer in ROUTE_LAYERS and g.distance(p) < 1e-3}
        mine = {t["layer"] for t in run["tracks"]
                if min(Point(q).distance(p) for q in (t["points"][0], t["points"][-1])) < 1e-3}
        if fan and mine and fan != mine:
            pts.append((p.x, p.y))
    return pts


def return_vias(router, log=print):
    Point = shp()[1]
    gnd = [g for n, k, _, g, _ in geo.items(router.board) if k == "via" and n == "GND_DIGITAL"]
    added, rows = [], []
    for run in router.runs():
        for p in transition_points(router, run):
            d = min(Point(p).distance(v) for v in gnd + [Point(q) for q in added])
            if d <= RETURN_VIA_MM:
                rows.append({"net": run["net"], "at": list(p), "return_via_mm": round(d, 2), "added": None})
                continue
            spot = place_gnd_via(router, p, added)
            rows.append({"net": run["net"], "at": list(p),
                         "return_via_mm": round(Point(p).distance(Point(spot)), 2) if spot else round(d, 2),
                         "added": list(spot) if spot else "NO_SPOT"})
            if spot:
                added.append(spot)
                log(f"return via for {run['net']} at {p}: {spot}")
    return added, rows


def place_gnd_via(router, p, already):
    """Nearest point within RETURN_VIA_MM of p where a GND_DIGITAL via clears everything (exact check)."""
    Point = shp()[1]
    copper, holes = router.via_obstacles("GND_DIGITAL", router.runs(), already)
    allowed = router.outline.buffer(-(EDGE + VIA_SIZE / 2)).difference(router.keepout.buffer(VIA_SIZE / 2))
    for r20 in range(8, int(RETURN_VIA_MM * 20) + 1):
        r = r20 * 0.05
        n = max(8, int(2 * math.pi * r / 0.05))
        for k in range(n):
            a = 2 * math.pi * k / n
            q = (round(p[0] + r * math.cos(a), 3), round(p[1] + r * math.sin(a), 3))
            pt = Point(q)
            if not allowed.contains(pt):
                continue
            if pt.buffer(VIA_SIZE / 2).distance(copper) < CLEARANCE or \
                    pt.buffer(VIA_DRILL / 2).distance(holes) < HOLE_CLEARANCE:
                continue
            return q
    return None


# ------------------------------------------------------------------------------------------ lengths
def kept_items(router, net):
    """Copper of `net` that stays after the reroute (inner runs and removed fan-out excluded)."""
    if not hasattr(router, "_removed"):
        router._removed = removed_items(router.board)
    return [(k, layer, g, raw) for k, layer, g, raw in net_items(router.board, net)
            if not (k == "track" and layer in INNER) and not is_removed(router._removed, net, k, layer, g)]


def fb_transitions(router, net):
    LineString, Point = shp()[0], shp()[1]
    segs = [(layer, g) for k, layer, g, raw in kept_items(router, net) if k == "track" and layer in ROUTE_LAYERS]
    vias = [g for k, layer, g, raw in kept_items(router, net) if k == "via"]
    run = router.routed.get(net)
    if run:
        segs += [(t["layer"], LineString(t["points"])) for t in run["tracks"]]
        vias += [Point(v["at"]) for v in run["vias"]]
    return sum(1 for v in vias if {layer for layer, g in segs if g.distance(v) < 1e-3} >= set(ROUTE_LAYERS))


def track_length(router, net, after=True):
    items = kept_items(router, net) if after else net_items(router.board, net)
    kept = sum(g.length for k, layer, g, raw in items if k == "track")
    run = router.routed.get(net) if after else None
    return kept + (sum(t["length_mm"] for t in run["tracks"]) if run else 0.0)


def signal_lengths(router, after=True):
    rows = {}
    for s in SIGNALS:
        total, parts = 0.0, {}
        for side in ("U1", "U2"):
            net = f"NOR_{s}_{side}"
            length = track_length(router, net, after)
            trans = fb_transitions(router, net) if after else None
            parts[net] = {"track_mm": round(length, 2), "fb_transitions": trans}
            total += length + (BOARD_THICKNESS * trans if after else 0.0)
        rows[s] = {"total_mm": round(total, 2), "parts": parts}
    return rows


# ------------------------------------------------------------------------------------------ meanders
def meander_polyline(p, q, start_t, n, amp, side, pitch=MEANDER_PITCH):
    """Segment p->q with n U-bumps of height amp starting start_t mm from p (adds 2*amp per bump)."""
    (x1, y1), (x2, y2) = p, q
    length = math.dist(p, q)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    nx, ny = -uy * side, ux * side
    pts = [p]
    t = start_t
    for _ in range(n):
        a = (x1 + ux * t, y1 + uy * t)
        b = (x1 + ux * (t + pitch), y1 + uy * (t + pitch))
        pts += [a, (a[0] + nx * amp, a[1] + ny * amp), (b[0] + nx * amp, b[1] + ny * amp), b]
        t += 2 * pitch
    pts.append(q)
    return [(round(x, 4), round(y, 4)) for x, y in pts]


def tune_lengths(router, gnd_vias, log=print):
    """Serpentines on the rerouted runs of the shorter OCTOSPI signals until totals are within
    MATCH_TOL_MM of the longest; each accepted meander is checked against exact geometry."""
    LineString, Point, unary_union = shp()[0], shp()[1], shp()[4]
    before = signal_lengths(router)
    target = max(r["total_mm"] for r in before.values())
    changes = []
    for s in SIGNALS:
        need = round(target - signal_lengths(router)[s]["total_mm"], 3)
        while need > MATCH_TOL_MM / 2:
            placed = None
            for net in (f"NOR_{s}_U2", f"NOR_{s}_U1"):
                run = router.routed.get(net)
                if not run:
                    continue
                others = [r for n, r in router.routed.items() if r and n != net]
                for ti, t in sorted(enumerate(run["tracks"]), key=lambda it: -it[1]["length_mm"]):
                    strict = router.strict(net, t["layer"], others, gnd_vias)
                    own = [LineString(o["points"]).buffer(o["width"] / 2)
                           for k, o in enumerate(run["tracks"]) if k != ti and o["layer"] == t["layer"]]
                    own = unary_union(own) if own else None
                    pts = [tuple(p) for p in t["points"]]
                    for k in range(len(pts) - 1):
                        p, q = pts[k], pts[k + 1]
                        seg_len = math.dist(p, q)
                        for amp in MEANDER_AMPLITUDES:
                            n = max(1, math.ceil(need / (2 * amp)))
                            span = (2 * n - 1) * MEANDER_PITCH
                            if span + 1.0 > seg_len:
                                n = int((seg_len - 1.0 + MEANDER_PITCH) / (2 * MEANDER_PITCH))
                                if n < 1:
                                    continue
                                span = (2 * n - 1) * MEANDER_PITCH
                            a_use = min(amp, need / (2 * n))
                            for start in np.arange(0.5, seg_len - span - 0.5 + 1e-9, 0.25):
                                for side in (1, -1):
                                    poly = meander_polyline(p, q, float(start), n, a_use, side)
                                    body = LineString(poly).buffer(t["width"] / 2)
                                    if body.intersects(strict):
                                        continue
                                    if own is not None and own.distance(LineString(poly[1:-1])) < CLEARANCE + t["width"] / 2:
                                        continue
                                    placed = (net, run, t, k, poly, n, a_use)
                                    break
                                if placed:
                                    break
                            if placed:
                                break
                        if placed:
                            break
                    if placed:
                        break
                if placed:
                    break
            if not placed:
                changes.append({"signal": s, "result": "NO_ROOM", "remaining_mm": need})
                log(f"meander {s}: no room for {need:.2f} mm")
                break
            net, run, t, k, poly, n, a_use = placed
            old = t["length_mm"]
            pts = [list(p) for p in t["points"]]
            t["points"] = pts[:k] + [list(p) for p in poly] + pts[k + 2:]
            t["length_mm"] = round(LineString(t["points"]).length, 3)
            run["length_mm"] = round(sum(x["length_mm"] for x in run["tracks"]), 3)
            added = round(t["length_mm"] - old, 3)
            changes.append({"signal": s, "net": net, "layer": t["layer"], "added_mm": added, "bumps": n,
                            "amplitude_mm": round(a_use, 3)})
            log(f"meander {net}: +{added} mm ({n} x {a_use:.2f})")
            need = round(need - added, 3)
    return changes, before, signal_lengths(router)
