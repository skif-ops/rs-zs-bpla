#!/usr/bin/env python3
"""Return-path resistance of a ground domain between two pads (PCB-PWR ECO-005 evidence).

Finite-difference solution of the Laplace equation on the rasterised same-net copper of F.Cu
and B.Cu (zone fills, tracks, pads; 0.05 mm cells). Vias join the layers with a fixed barrel
resistance; THT pads are equipotential on both layers. The source pad is held at 1 V, the sink
pad at 0 V; R = 1 V / total source current.

Assumptions (stated in every result): outer copper 35 um finished (1 oz, ECO-004 stack-up),
rho = 1.724e-8 ohm*m at 20 C (x1.20 at 70 C), via barrel 1.75093 mOhm (0.6/0.3 mm, 20 um wall,
Review B R1 finding 1 figure). Net-tie bridges are not part of the path (the sink is the domain pad).
"""

from __future__ import annotations

import math

RHO_20C = 1.724e-8
T_OUTER_M = 35e-6
R_VIA_OHM = 1.75093e-3
TEMP_FACTOR_70C = 1.197
CELL_MM = 0.05


def _pad_geometry(fp, pad):
    from shapely.geometry import Point, Polygon

    angle = math.radians(fp.position.angle or 0)
    x = fp.position.X + pad.position.X * math.cos(angle) + pad.position.Y * math.sin(angle)
    y = fp.position.Y - pad.position.X * math.sin(angle) + pad.position.Y * math.cos(angle)
    w, h = pad.size.X / 2, pad.size.Y / 2
    if pad.shape == "circle":
        return Point(x, y).buffer(w)
    return Polygon([(x + dx * math.cos(angle) + dy * math.sin(angle), y - dx * math.sin(angle) + dy * math.cos(angle))
                    for dx, dy in ((-w, -h), (w, -h), (w, h), (-w, h))])


def _reference(fp) -> str:
    props = fp.properties
    if isinstance(props, dict):
        return props.get("Reference", "")
    return next((p.value for p in props if getattr(p, "key", None) == "Reference"), "")


def resistance(board_path: str, net: str, source: tuple[str, str], sink: tuple[str, str],
               window: tuple[float, float, float, float]) -> dict:
    import numpy as np
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl
    from kiutils.board import Board
    from shapely import prepared
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union

    board = Board.from_file(board_path)
    names = {n.number: n.name for n in board.nets}
    x0, y0, x1, y1 = window
    nx, ny = int(round((x1 - x0) / CELL_MM)), int(round((y1 - y0) / CELL_MM))
    layers = ("F.Cu", "B.Cu")
    pads = {layer: [] for layer in layers}
    index: dict = {}
    for li, layer in enumerate(layers):
        parts = []
        for zone in board.zones:
            if zone.netName == net:
                parts += [Polygon([(c.X, c.Y) for c in f.coordinates]).buffer(0)
                          for f in (zone.filledPolygons or []) if f.layer == layer]
        for item in board.traceItems:
            if names.get(item.net) != net:
                continue
            if type(item).__name__ == "Via":
                parts.append(Point(item.position.X, item.position.Y).buffer(item.size / 2))
            elif item.layer == layer:
                parts.append(LineString([(item.start.X, item.start.Y), (item.end.X, item.end.Y)]).buffer(item.width / 2))
        for fp in board.footprints:
            for pad in fp.pads:
                if (pad.net.name if pad.net else None) == net and (layer in pad.layers or "*.Cu" in pad.layers):
                    geometry = _pad_geometry(fp, pad)
                    parts.append(geometry)
                    pads[layer].append(((_reference(fp), str(pad.number)), geometry))
        copper = prepared.prep(unary_union(parts))
        for j in range(ny):
            for i in range(nx):
                if copper.contains(Point(x0 + (i + 0.5) * CELL_MM, y0 + (j + 0.5) * CELL_MM)):
                    index[(li, j, i)] = len(index)
    n = len(index)
    rows, cols, vals = [], [], []

    def link(a: int, b: int, g: float) -> None:
        rows.extend((a, b, a, b))
        cols.extend((a, b, b, a))
        vals.extend((g, g, -g, -g))

    g_sheet = T_OUTER_M / RHO_20C
    for (li, j, i), k in index.items():
        for dj, di in ((0, 1), (1, 0)):
            other = index.get((li, j + dj, i + di))
            if other is not None:
                link(k, other, g_sheet)

    def cells(geometry, li: int) -> list[int]:
        box = geometry.bounds
        found = []
        prep = prepared.prep(geometry)
        for j in range(max(0, int((box[1] - y0) / CELL_MM)), min(ny, int((box[3] - y0) / CELL_MM) + 1)):
            for i in range(max(0, int((box[0] - x0) / CELL_MM)), min(nx, int((box[2] - x0) / CELL_MM) + 1)):
                k = index.get((li, j, i))
                if k is not None and prep.contains(Point(x0 + (i + 0.5) * CELL_MM, y0 + (j + 0.5) * CELL_MM)):
                    found.append(k)
        return found

    vias = 0
    for item in board.traceItems:
        if type(item).__name__ != "Via" or names.get(item.net) != net:
            continue
        if not (x0 < item.position.X < x1 and y0 < item.position.Y < y1):
            continue
        ring = Point(item.position.X, item.position.Y).buffer(item.size / 2)
        top, bottom = cells(ring, 0), cells(ring, 1)
        for group in (top, bottom):
            for k in group[1:]:
                link(group[0], k, 1e3)  # annular ring: equipotential
        if top and bottom:
            link(top[0], bottom[0], 1 / R_VIA_OHM)
            vias += 1
    src, snk = [], []
    for li, layer in enumerate(layers):
        for key, geometry in pads[layer]:
            if key == source:
                src += cells(geometry, li)
            if key == sink:
                snk += cells(geometry, li)
    assert src and snk, f"{net}: source/sink pad has no copper cells"
    matrix = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))
    fixed = np.zeros(n, bool)
    volts = np.zeros(n)
    fixed[src] = True
    volts[src] = 1.0
    fixed[snk] = True
    free = ~fixed
    rhs = -matrix[free][:, fixed] @ volts[fixed]
    volts[free] = spl.spsolve(matrix[free][:, free].tocsc(), rhs)
    current = float((matrix @ volts)[src].sum())
    r20 = 1.0 / current
    return {"net": net, "from": f"{source[0]}.{source[1]}", "to": f"{sink[0]}.{sink[1]}",
            "vias_in_path_region": vias, "r_mohm_20c": round(r20 * 1e3, 3),
            "r_mohm_70c": round(r20 * TEMP_FACTOR_70C * 1e3, 3)}


def load_case(result: dict, i_peak_a: float, i_cont_a: float | None = None) -> dict:
    r = result["r_mohm_70c"] / 1e3
    out = dict(result)
    out.update({"i_peak_a": i_peak_a, "du_peak_mv_70c": round(i_peak_a * r * 1e3, 2),
                "p_peak_mw_70c": round(i_peak_a ** 2 * r * 1e3, 2)})
    if i_cont_a is not None:
        out.update({"i_cont_a": i_cont_a, "p_cont_mw_70c": round(i_cont_a ** 2 * r * 1e3, 2)})
    return out
