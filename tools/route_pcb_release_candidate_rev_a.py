#!/usr/bin/env python3
"""Deterministic, offline grid router for the Dioneya Rev.A PCB candidates.

This is intentionally a repository-owned implementation.  It never opens a
socket or invokes a hosted autorouter.  Its purpose is to turn the controlled
placement/net authorities into a reviewable copper candidate which is then
checked by native KiCad DRC in CI.  It is not a substitute for DRC, SI, PI,
thermal review or fabricator DFM.

The router uses four signal layers on PCB-MAIN (leaving In1/In4 available for
domain return and power pours) and F/B on PCB-PWR.  It incrementally connects
each net to a growing tree using an A* search on a 0.25 mm grid, while treating
pads, already-routed copper, vias and the board edge as hard obstacles.
"""
from __future__ import annotations

import argparse
import csv
import heapq
import math
import re
import shutil
import tempfile
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pcbnew


ROOT = Path(__file__).resolve().parents[1]
MAIN_AUTHORITY = ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv"
PWR_AUTHORITY = ROOT / "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv"


@dataclass(frozen=True)
class GridPoint:
    x: int
    y: int
    layer: int


@dataclass(frozen=True)
class NetPolicy:
    width_mm: float
    via_diameter_mm: float
    via_drill_mm: float
    layers: tuple[int, ...]
    via_cost: int
    priority: int


@dataclass
class PadEndpoint:
    reference: str
    number: str
    x_mm: float
    y_mm: float
    layers: tuple[int, ...]
    seeds: list[GridPoint]
    centre_link_required: bool


@dataclass
class RoutedBranch:
    path: list[GridPoint]
    endpoint: PadEndpoint
    policy: NetPolicy


def mm(value: int) -> float:
    return pcbnew.ToMM(value)


def vec(x_mm: float, y_mm: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I_MM(float(x_mm), float(y_mm))


def read_authority(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {row["Net_Name"]: row for row in csv.DictReader(source)}


def load_board_compat(path: Path) -> pcbnew.BOARD:
    """Load KiCad-9 output in KiCad 7 by removing only its version annotation.

    KiCad 9 adds a top-level ``generator_version`` token which KiCad 7 does not
    know.  The underlying board syntax used by the current PCB-PWR source is
    otherwise readable by KiCad 7.  The temporary source is never committed.
    """
    try:
        return pcbnew.LoadBoard(str(path))
    except OSError as exc:
        if "generator_version" not in str(exc):
            raise
    text = path.read_text(encoding="utf-8")
    text, replacements = re.subn(r"^\s*\(generator_version\s+[^\n]+\)\s*$", "", text, flags=re.M)
    if replacements != 1:
        raise RuntimeError(f"{path}: expected one KiCad generator_version token")
    with tempfile.NamedTemporaryFile("w", suffix=".kicad_pcb", encoding="utf-8", delete=False) as temp:
        temp.write(text)
        temp_path = Path(temp.name)
    try:
        return pcbnew.LoadBoard(str(temp_path))
    finally:
        temp_path.unlink(missing_ok=True)


class GridRouter:
    def __init__(self, board: pcbnew.BOARD, board_name: str, step_mm: float = 0.25):
        self.board = board
        self.board_name = board_name
        self.step = step_mm
        bbox = board.GetBoardEdgesBoundingBox()
        edge = 0.65
        self.x0 = mm(bbox.GetX()) + edge
        self.y0 = mm(bbox.GetY()) + edge
        self.x1 = mm(bbox.GetRight()) - edge
        self.y1 = mm(bbox.GetBottom()) - edge
        self.nx = int(math.floor((self.x1 - self.x0) / step_mm)) + 1
        self.ny = int(math.floor((self.y1 - self.y0) / step_mm)) + 1
        if board_name == "PCB-MAIN":
            self.route_layers = (pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.B_Cu)
        else:
            self.route_layers = (pcbnew.F_Cu, pcbnew.B_Cu)
        self.layer_index = {layer: idx for idx, layer in enumerate(self.route_layers)}
        shape = (len(self.route_layers), self.ny, self.nx)
        # 0 free; positive value is a net code; -1 is conflicting/no-net copper.
        self.static_owner = np.zeros(shape, dtype=np.int32)
        self.dynamic_owner = np.zeros(shape, dtype=np.int32)
        # A through via cannot be placed on any SMD land, even when it belongs to
        # the net being routed; this prevents accidental unfilled via-in-pad.
        self.via_forbidden = np.zeros((self.ny, self.nx), dtype=np.bool_)
        # Through-via centres are blocked by copper on every routing layer.
        # This separate 2-D ownership map avoids trying to infer via clearance
        # from a trace-oriented, already-dilated 3-D occupancy grid.
        self.via_dynamic_owner = np.zeros((self.ny, self.nx), dtype=np.int32)
        # Drill-to-drill spacing applies even to two vias on the same net.  A
        # separate owner map is therefore required: normal copper occupancy
        # deliberately permits same-net reuse, whereas a second physical drill
        # may only reuse the exact centre of an already committed via.
        self.via_drill_owner = np.zeros((self.ny, self.nx), dtype=np.int32)
        # Incremental negotiated routing keeps the board's pre-existing copper
        # immutable while allowing only newly-created branches to be rolled
        # back.  index_existing_copper populates these snapshots.
        self.preserve_existing_copper = False
        self.preserved_dynamic_owner = np.zeros_like(self.dynamic_owner)
        self.preserved_via_dynamic_owner = np.zeros_like(self.via_dynamic_owner)
        self.preserved_via_drill_owner = np.zeros_like(self.via_drill_owner)
        self.pad_endpoints: dict[int, list[PadEndpoint]] = defaultdict(list)
        self.pad_core: dict[int, set[GridPoint]] = defaultdict(set)
        self.escape_channels: dict[tuple[int, str, str], list[tuple[int, int]]] = {}
        self.routed_cells: dict[int, set[GridPoint]] = defaultdict(set)
        self.via_cells: dict[int, set[tuple[int, int]]] = defaultdict(set)
        self.branches: dict[int, list[RoutedBranch]] = defaultdict(list)
        self.emit_copper = True
        self.tracks_added = 0
        self.vias_added = 0
        self.failed: list[str] = []
        self.last_failed: list[str] = []
        self._index_pads()
        self._carve_pad_escapes()

    def index_existing_copper(self) -> dict[str, int]:
        """Reserve already-routed native copper as immutable obstacles.

        This is used only by the incremental completion pass.  Existing
        tracks and vias stay in the BOARD and are rasterized into the same
        ownership maps used for newly committed routes.  A subsequent route
        may therefore use its own existing copper, but it cannot cross copper
        owned by another net or place a through-via through an existing item.
        """
        track_items = 0
        via_items = 0
        future_track_radius_mm = 0.075
        future_via_radius_mm = 0.25
        copper_clearance_mm = 0.25
        future_drill_radius_mm = 0.20
        drill_to_drill_mm = 0.2495

        def merge_2d(array: np.ndarray, gy: int, gx: int, code: int) -> None:
            old = int(array[gy, gx])
            array[gy, gx] = code if old in (0, code) else -1

        for item in self.board.GetTracks():
            code = int(item.GetNetCode()) or -1
            is_via = isinstance(item, pcbnew.PCB_VIA)
            if is_via:
                route_layer_indices = range(len(self.route_layers))
                via_items += 1
            else:
                layer = int(item.GetLayer())
                if layer not in self.layer_index:
                    continue
                route_layer_indices = (self.layer_index[layer],)
                track_items += 1

            # Track-centre clearance from existing copper.  HitTest already
            # includes the physical half-width/radius of the native item.
            margin_mm = copper_clearance_mm + future_track_radius_mm
            box = item.GetBoundingBox()
            bounds = self._grid_bounds(
                mm(box.GetX()) - margin_mm,
                mm(box.GetY()) - margin_mm,
                mm(box.GetRight()) + margin_mm,
                mm(box.GetBottom()) + margin_mm,
            )
            x0, y0, x1, y1 = bounds
            accuracy = pcbnew.FromMM(margin_mm)
            for gy in range(y0, y1 + 1):
                for gx in range(x0, x1 + 1):
                    if not item.HitTest(vec(*self.xy(gx, gy)), accuracy):
                        continue
                    for layer_idx in route_layer_indices:
                        old = int(self.dynamic_owner[layer_idx, gy, gx])
                        self.dynamic_owner[layer_idx, gy, gx] = (
                            code if old in (0, code) else -1
                        )

            # A new through-via must clear every existing track/via in the
            # XY plane because it spans all copper layers.
            via_margin_mm = copper_clearance_mm + future_via_radius_mm
            via_bounds = self._grid_bounds(
                mm(box.GetX()) - via_margin_mm,
                mm(box.GetY()) - via_margin_mm,
                mm(box.GetRight()) + via_margin_mm,
                mm(box.GetBottom()) + via_margin_mm,
            )
            x0, y0, x1, y1 = via_bounds
            accuracy = pcbnew.FromMM(via_margin_mm)
            for gy in range(y0, y1 + 1):
                for gx in range(x0, x1 + 1):
                    if item.HitTest(vec(*self.xy(gx, gy)), accuracy):
                        merge_2d(self.via_dynamic_owner, gy, gx, code)

            if is_via:
                position = item.GetPosition()
                px, py = mm(position.x), mm(position.y)
                drill_radius_mm = (
                    mm(item.GetDrillValue()) / 2
                    + drill_to_drill_mm
                    + future_drill_radius_mm
                )
                x0, y0, x1, y1 = self._grid_bounds(
                    px - drill_radius_mm,
                    py - drill_radius_mm,
                    px + drill_radius_mm,
                    py + drill_radius_mm,
                )
                radius_grid = drill_radius_mm / self.step
                centre_x, centre_y = self.ix(px), self.iy(py)
                for gy in range(y0, y1 + 1):
                    for gx in range(x0, x1 + 1):
                        if (
                            (gx - centre_x) ** 2 + (gy - centre_y) ** 2
                            < radius_grid * radius_grid - 1e-9
                        ):
                            merge_2d(self.via_drill_owner, gy, gx, code)

        self.preserve_existing_copper = True
        self.preserved_dynamic_owner = self.dynamic_owner.copy()
        self.preserved_via_dynamic_owner = self.via_dynamic_owner.copy()
        self.preserved_via_drill_owner = self.via_drill_owner.copy()
        return {"tracks": track_items, "vias": via_items}

    def ix(self, x_mm: float) -> int:
        return int(round((x_mm - self.x0) / self.step))

    def iy(self, y_mm: float) -> int:
        return int(round((y_mm - self.y0) / self.step))

    def xy(self, x: int, y: int) -> tuple[float, float]:
        return self.x0 + x * self.step, self.y0 + y * self.step

    def inside(self, x: int, y: int) -> bool:
        return 0 <= x < self.nx and 0 <= y < self.ny

    def _grid_bounds(self, left: float, top: float, right: float, bottom: float) -> tuple[int, int, int, int]:
        return (
            max(0, int(math.floor((left - self.x0) / self.step))),
            max(0, int(math.floor((top - self.y0) / self.step))),
            min(self.nx - 1, int(math.ceil((right - self.x0) / self.step))),
            min(self.ny - 1, int(math.ceil((bottom - self.y0) / self.step))),
        )

    def _grid_core_bounds(self, left: float, top: float, right: float, bottom: float) -> tuple[int, int, int, int]:
        """Return only grid nodes physically inside a rectangular pad bound.

        Obstacle rasterization intentionally rounds outward, but pad connection
        seeds must round inward.  Using outward bounds for both left track ends
        as much as one grid step outside small lands, which KiCad correctly
        reported as dangling/unconnected copper.
        """
        return (
            max(0, int(math.ceil((left - self.x0) / self.step))),
            max(0, int(math.ceil((top - self.y0) / self.step))),
            min(self.nx - 1, int(math.floor((right - self.x0) / self.step))),
            min(self.ny - 1, int(math.floor((bottom - self.y0) / self.step))),
        )

    @staticmethod
    def _merge_owner(old: np.ndarray, code: int) -> np.ndarray:
        return np.where((old == 0) | (old == code), code, -1)

    def _mark_rect(self, array: np.ndarray, layer_idx: int, bounds: tuple[int, int, int, int], code: int) -> None:
        x0, y0, x1, y1 = bounds
        if x0 > x1 or y0 > y1:
            return
        view = array[layer_idx, y0:y1 + 1, x0:x1 + 1]
        view[:] = self._merge_owner(view, code)

    def _pad_copper_layers(self, pad: pcbnew.PAD) -> tuple[int, ...]:
        return tuple(layer for layer in self.route_layers if pad.IsOnLayer(layer))

    def _index_pads(self) -> None:
        # Pad geometry is exact, so retain the board-rule clearance here.  The
        # additional raster guard is required only between grid-routed copper.
        clearance = 0.20
        track_radius = 0.075
        for footprint in self.board.GetFootprints():
            ref = footprint.GetReference()
            for pad in footprint.Pads():
                code = int(pad.GetNetCode())
                copper_layers = self._pad_copper_layers(pad)
                # KiCad reports NPTH mechanical pads as present on copper
                # layers in some footprints.  Classify by pad attribute first,
                # otherwise they receive only copper clearance and a track can
                # violate the stricter finished-hole clearance.
                if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    box = pad.GetBoundingBox()
                    left, top = mm(box.GetX()), mm(box.GetY())
                    right, bottom = mm(box.GetRight()), mm(box.GetBottom())
                    hole_track_margin = 0.15 + track_radius
                    bounds = self._grid_bounds(
                        left - hole_track_margin,
                        top - hole_track_margin,
                        right + hole_track_margin,
                        bottom + hole_track_margin,
                    )
                    x0, y0, x1, y1 = bounds
                    for gy in range(y0, y1 + 1):
                        for gx in range(x0, x1 + 1):
                            point = vec(*self.xy(gx, gy))
                            if pad.HitTest(
                                point,
                                pcbnew.FromMM(hole_track_margin),
                            ):
                                for layer_idx in range(len(self.route_layers)):
                                    self.static_owner[layer_idx, gy, gx] = -1
                            if pad.HitTest(point, pcbnew.FromMM(0.40)):
                                self.via_forbidden[gy, gx] = True
                    continue
                if not copper_layers:
                    continue
                box = pad.GetBoundingBox()
                left, top = mm(box.GetX()), mm(box.GetY())
                right, bottom = mm(box.GetRight()), mm(box.GetBottom())
                pad_clearance = max(clearance, mm(pad.GetLocalClearance()))
                obstacle_margin = pad_clearance + track_radius
                expanded = self._grid_bounds(
                    left - obstacle_margin,
                    top - obstacle_margin,
                    right + obstacle_margin,
                    bottom + obstacle_margin,
                )
                core = self._grid_core_bounds(left, top, right, bottom)
                owner = code if code else -1
                for layer in copper_layers:
                    layer_idx = self.layer_index[layer]
                    x0, y0, x1, y1 = expanded
                    for gy in range(y0, y1 + 1):
                        for gx in range(x0, x1 + 1):
                            if not pad.HitTest(
                                vec(*self.xy(gx, gy)),
                                pcbnew.FromMM(obstacle_margin),
                            ):
                                continue
                            old = int(self.static_owner[layer_idx, gy, gx])
                            self.static_owner[layer_idx, gy, gx] = (
                                owner if old in (0, owner) else -1
                            )

                # Block a default 0.50 mm through-via around every copper pad.
                # PTH pads already connect their own layers through the pad
                # seeds, so placing a second drill in them is unnecessary.
                via_keepout = 0.25 + pad_clearance
                x0, y0, x1, y1 = self._grid_bounds(
                    left - via_keepout,
                    top - via_keepout,
                    right + via_keepout,
                    bottom + via_keepout,
                )
                for gy in range(y0, y1 + 1):
                    for gx in range(x0, x1 + 1):
                        if pad.HitTest(
                            vec(*self.xy(gx, gy)),
                            pcbnew.FromMM(via_keepout),
                        ):
                            self.via_forbidden[gy, gx] = True

                if not code:
                    continue
                px, py = mm(pad.GetPosition().x), mm(pad.GetPosition().y)
                seed_layers = copper_layers
                seeds: list[GridPoint] = []
                x0, y0, x1, y1 = core
                for layer in seed_layers:
                    layer_idx = self.layer_index[layer]
                    for gy in range(y0, y1 + 1):
                        for gx in range(x0, x1 + 1):
                            # Bounding boxes are not copper for circular,
                            # oval, round-rect or custom lands.  Using their
                            # corner nodes as connection goals creates tracks
                            # which end visibly close to a pad but are still
                            # electrically dangling in KiCad.
                            if not pad.HitTest(vec(*self.xy(gx, gy))):
                                continue
                            point = GridPoint(gx, gy, layer_idx)
                            seeds.append(point)
                if seeds:
                    centred_seeds: list[GridPoint] = []
                    for layer_idx in sorted({point.layer for point in seeds}):
                        layer_seeds = [
                            point for point in seeds if point.layer == layer_idx
                        ]
                        nearest = min(
                            layer_seeds,
                            key=lambda point: (
                                (self.xy(point.x, point.y)[0] - px) ** 2
                                + (self.xy(point.x, point.y)[1] - py) ** 2
                            ),
                        )
                        centred_seeds.append(nearest)
                    seeds = centred_seeds
                    self.pad_core[code].update(seeds)
                centre_link_required = not seeds
                if centre_link_required:
                    # Edge connector lands may be centred outside Edge.Cuts.
                    gx = min(self.nx - 1, max(0, self.ix(px)))
                    gy = min(self.ny - 1, max(0, self.iy(py)))
                    seeds = [GridPoint(gx, gy, self.layer_index[layer]) for layer in seed_layers]
                    self.pad_core[code].update(seeds)
                self.pad_endpoints[code].append(
                    PadEndpoint(
                        ref,
                        pad.GetNumber(),
                        px,
                        py,
                        seed_layers,
                        seeds,
                        centre_link_required,
                    )
                )

        # Merge pads which share a net and exact physical centre (common on USB
        # receptacles and modules with duplicate ground lands).
        for code, endpoints in list(self.pad_endpoints.items()):
            unique: dict[tuple[int, int, tuple[int, ...]], PadEndpoint] = {}
            for endpoint in endpoints:
                key = (
                    int(round(endpoint.x_mm * 1000)),
                    int(round(endpoint.y_mm * 1000)),
                    endpoint.layers,
                )
                unique.setdefault(key, endpoint)
            self.pad_endpoints[code] = list(unique.values())

    def _carve_pad_escapes(self) -> None:
        """Restore legal neck-out channels from dense SMD land patterns.

        The outward obstacle raster is intentionally conservative and can make
        adjacent fine-pitch pad halos overlap.  That overlap must not imprison
        every pad.  This pass restores only the physical pad core plus a 1 mm
        centre-line neck-out directed away from the footprint centre.  It never
        crosses another pad core; final track width/clearance is still checked
        by native KiCad DRC.
        """
        core_owner = np.zeros_like(self.static_owner)
        pad_records: list[tuple[int, pcbnew.FOOTPRINT, pcbnew.PAD, tuple[int, int, int, int], tuple[int, ...]]] = []
        for footprint in self.board.GetFootprints():
            for pad in footprint.Pads():
                code = int(pad.GetNetCode())
                layers = self._pad_copper_layers(pad)
                if not code or not layers:
                    continue
                box = pad.GetBoundingBox()
                core = self._grid_core_bounds(
                    mm(box.GetX()), mm(box.GetY()), mm(box.GetRight()), mm(box.GetBottom())
                )
                pad_records.append((code, footprint, pad, core, layers))
                x0, y0, x1, y1 = core
                if x0 > x1 or y0 > y1:
                    continue
                for layer in layers:
                    layer_idx = self.layer_index[layer]
                    for gy in range(y0, y1 + 1):
                        for gx in range(x0, x1 + 1):
                            if not pad.HitTest(vec(*self.xy(gx, gy))):
                                continue
                            old = int(core_owner[layer_idx, gy, gx])
                            core_owner[layer_idx, gy, gx] = (
                                code if old in (0, code) else -1
                            )

        # A cell belonging to exactly one physical pad is legal for that net.
        unique = core_owner > 0
        self.static_owner[unique] = core_owner[unique]

        escape_steps = max(1, int(math.ceil(1.0 / self.step)))
        board_box = self.board.GetBoardEdgesBoundingBox()
        board_cx = mm(board_box.GetCenter().x)
        board_cy = mm(board_box.GetCenter().y)
        for code, footprint, pad, core, layers in pad_records:
            px, py = mm(pad.GetPosition().x), mm(pad.GetPosition().y)
            ref = footprint.GetReference()
            if ref.startswith("J"):
                # Board-edge connectors must neck inward, irrespective of an
                # asymmetric library origin or the card/receptacle body.
                dx, dy = board_cx - px, board_cy - py
                half_width = half_height = 1.0
            else:
                body = footprint.GetBoundingBox(False, False)
                fx, fy = mm(body.GetCenter().x), mm(body.GetCenter().y)
                dx, dy = px - fx, py - fy
                half_width = max(0.01, mm(body.GetWidth()) / 2)
                half_height = max(0.01, mm(body.GetHeight()) / 2)
            x_score = abs(dx) / half_width
            y_score = abs(dy) / half_height
            if x_score >= y_score and abs(dx) > 1e-6:
                sx, sy = (1 if dx > 0 else -1), 0
            elif abs(dy) > 1e-6:
                sx, sy = 0, (1 if dy > 0 else -1)
            else:
                continue
            x0, y0, x1, y1 = core
            physical_core = [
                (gx, gy)
                for gy in range(y0, y1 + 1)
                for gx in range(x0, x1 + 1)
                if pad.HitTest(vec(*self.xy(gx, gy)))
            ]
            if not physical_core:
                continue

            preferred = (sx, sy)
            directions = (
                [preferred, (0, -1), (0, 1), (-sx, 0)]
                if sx else
                [preferred, (-1, 0), (1, 0), (0, -sy)]
            )
            best_channel: list[tuple[int, int]] = []
            for candidate_sx, candidate_sy in directions:
                if candidate_sx:
                    edge = (
                        max(gx for gx, _ in physical_core)
                        if candidate_sx > 0 else
                        min(gx for gx, _ in physical_core)
                    )
                    edge_cells = [
                        (gx, gy) for gx, gy in physical_core if gx == edge
                    ]
                    gx, gy = min(
                        edge_cells,
                        key=lambda point: abs(point[1] - self.iy(py)),
                    )
                else:
                    edge = (
                        max(gy for _, gy in physical_core)
                        if candidate_sy > 0 else
                        min(gy for _, gy in physical_core)
                    )
                    edge_cells = [
                        (gx, gy) for gx, gy in physical_core if gy == edge
                    ]
                    gx, gy = min(
                        edge_cells,
                        key=lambda point: abs(point[0] - self.ix(px)),
                    )

                trial: list[tuple[int, int]] = []
                for step in range(escape_steps + 1):
                    xx = gx + candidate_sx * step
                    yy = gy + candidate_sy * step
                    if not self.inside(xx, yy):
                        break
                    blocked = False
                    for layer in layers:
                        layer_idx = self.layer_index[layer]
                        physical = int(core_owner[layer_idx, yy, xx])
                        occupied = int(self.static_owner[layer_idx, yy, xx])
                        if physical not in (0, code) or occupied not in (0, code):
                            blocked = True
                            break
                    if blocked:
                        break
                    trial.append((xx, yy))
                if len(trial) > len(best_channel):
                    best_channel = trial

            # Never overwrite another pad's clearance halo.  If the preferred
            # escape is obstructed, the longest legal perpendicular or reverse
            # neck-out is used instead and remains subject to native DRC.
            for cx, cy in best_channel:
                for layer in layers:
                    self.static_owner[self.layer_index[layer], cy, cx] = code
            if best_channel:
                self.escape_channels[(code, ref, pad.GetNumber())] = best_channel

    def _cell_clear(self, point: GridPoint, code: int, radius: float = 0.0) -> bool:
        extent = int(math.ceil(radius))
        radius_squared = radius * radius
        for yy in range(max(0, point.y - extent), min(self.ny, point.y + extent + 1)):
            for xx in range(max(0, point.x - extent), min(self.nx, point.x + extent + 1)):
                # Exact design-rule equality is legal.  The tiny epsilon also
                # prevents floating-point noise from blocking a grid node
                # exactly at the requested centre-line separation.
                if radius and (xx - point.x) ** 2 + (yy - point.y) ** 2 >= radius_squared - 1e-9:
                    continue
                static = int(self.static_owner[point.layer, yy, xx])
                dynamic = int(self.dynamic_owner[point.layer, yy, xx])
                if static not in (0, code) or dynamic not in (0, code):
                    return False
        return True

    def _via_clear(self, point: GridPoint, code: int, radius: float) -> bool:
        # A committed via may be reused by its own net at the exact same grid
        # point.  Any new drill centre inside another via's expanded drill
        # keepout is illegal, including when both vias share a net.
        if (
            (point.x, point.y) not in self.via_cells[code]
            and self.via_drill_owner[point.y, point.x] != 0
        ):
            return False
        extent = int(math.ceil(radius))
        radius_squared = radius * radius
        for yy in range(max(0, point.y - extent), min(self.ny, point.y + extent + 1)):
            for xx in range(max(0, point.x - extent), min(self.nx, point.x + extent + 1)):
                if radius and (xx - point.x) ** 2 + (yy - point.y) ** 2 >= radius_squared - 1e-9:
                    continue
                if self.via_forbidden[yy, xx]:
                    return False
                owner = int(self.via_dynamic_owner[yy, xx])
                if owner not in (0, code):
                    return False
        return True

    def _nearest_pad_order(self, endpoints: list[PadEndpoint]) -> list[PadEndpoint]:
        if len(endpoints) <= 2:
            return endpoints
        # Start with the endpoint nearest the net centroid; this reduces the
        # total tree growth for high-fanout power and return nets.
        cx = sum(p.x_mm for p in endpoints) / len(endpoints)
        cy = sum(p.y_mm for p in endpoints) / len(endpoints)
        root = min(endpoints, key=lambda p: abs(p.x_mm - cx) + abs(p.y_mm - cy))
        ordered = [root]
        remaining = [p for p in endpoints if p is not root]
        while remaining:
            nxt = min(
                remaining,
                key=lambda p: min(abs(p.x_mm - q.x_mm) + abs(p.y_mm - q.y_mm) for q in ordered),
            )
            ordered.append(nxt)
            remaining.remove(nxt)
        return ordered

    @staticmethod
    def _grid_line(start: GridPoint, end: GridPoint) -> list[GridPoint]:
        """Return an 8-connected grid line including both endpoints."""
        points = [start]
        x, y = start.x, start.y
        while x != end.x or y != end.y:
            x += 0 if x == end.x else 1 if end.x > x else -1
            y += 0 if y == end.y else 1 if end.y > y else -1
            points.append(GridPoint(x, y, start.layer))
        return points

    def fanout_endpoints(
        self,
        codes: set[int],
        references: set[str],
        policies: dict[int, NetPolicy],
    ) -> int:
        """Commit short, ordered escape stubs before global net routing.

        Dense packages must fan out all pins before long routes claim the area
        around the body.  Each selected endpoint is moved logically from its
        pad-centre seed to the tip of the already DRC-aware escape channel; the
        copper stub keeps the new seed electrically connected to the pad.
        """
        stubs = 0
        front_layer = self.layer_index.get(pcbnew.F_Cu)
        if front_layer is None:
            return stubs
        for code in sorted(codes):
            policy = policies[code]
            if pcbnew.F_Cu not in policy.layers:
                continue
            for endpoint in self.pad_endpoints[code]:
                if endpoint.reference not in references:
                    continue
                channel = self.escape_channels.get(
                    (code, endpoint.reference, endpoint.number)
                )
                if not channel:
                    continue
                starts = [
                    seed for seed in endpoint.seeds if seed.layer == front_layer
                ]
                if not starts:
                    continue
                tip = GridPoint(channel[-1][0], channel[-1][1], front_layer)
                start = min(
                    starts,
                    key=lambda point: (
                        abs(point.x - channel[0][0])
                        + abs(point.y - channel[0][1])
                    ),
                )
                edge = GridPoint(channel[0][0], channel[0][1], front_layer)
                path = self._grid_line(start, edge)
                path.extend(
                    GridPoint(x, y, front_layer)
                    for x, y in channel[1:]
                )
                if any(
                    not self._cell_clear(point, code)
                    for point in path[1:]
                ):
                    continue
                self._commit_path(code, path, endpoint, policy)
                endpoint.seeds = [tip]
                stubs += 1
        return stubs

    @staticmethod
    def _bbox_heuristic(point: GridPoint, goal_bbox: tuple[int, int, int, int], goal_layers: set[int]) -> int:
        xmin, ymin, xmax, ymax = goal_bbox
        dx = xmin - point.x if point.x < xmin else point.x - xmax if point.x > xmax else 0
        dy = ymin - point.y if point.y < ymin else point.y - ymax if point.y > ymax else 0
        layer_penalty = 0 if point.layer in goal_layers else 30
        return 10 * (dx + dy) + layer_penalty

    def _search(
        self,
        code: int,
        starts: list[GridPoint],
        goals: set[GridPoint],
        policy: NetPolicy,
        margin_mm: float,
    ) -> list[GridPoint] | None:
        permitted = {self.layer_index[layer] for layer in policy.layers if layer in self.layer_index}
        starts = [point for point in starts if point.layer in permitted]
        goals = {point for point in goals if point.layer in permitted}
        if not starts or not goals:
            return None
        if any(point in goals for point in starts):
            return [next(point for point in starts if point in goals)]

        # Once a multi-drop net has grown, its tree can contain thousands of
        # grid nodes.  Using that broad tree as the heuristic target makes the
        # bounding-box heuristic zero over much of the board and degenerates
        # A* into a flood fill.  Search from the tree toward the small endpoint
        # instead, then reverse the physical path before committing it.
        reverse_result = len(goals) > len(starts)
        if reverse_result:
            starts, goals = list(goals), set(starts)

        xs = [p.x for p in goals]
        ys = [p.y for p in goals]
        goal_bbox = (min(xs), min(ys), max(xs), max(ys))
        goal_layers = {p.layer for p in goals}
        all_x = xs + [point.x for point in starts]
        all_y = ys + [point.y for point in starts]
        margin = int(math.ceil(margin_mm / self.step))
        search_x0 = max(0, min(all_x) - margin)
        search_x1 = min(self.nx - 1, max(all_x) + margin)
        search_y0 = max(0, min(all_y) - margin)
        search_y1 = min(self.ny - 1, max(all_y) + margin)
        # Static and dynamic via keepouts are built for a 0.50 mm baseline via.
        # Only a larger candidate's radius increment is applied here.
        via_radius = max(
            0.0,
            (policy.via_diameter_mm / 2 - 0.25) / self.step,
        )
        # Static pad halos and committed dynamic copper are rasterized for a
        # future 0.15 mm trace (0.075 mm radius).  Wider candidates need only
        # the incremental centre-line exclusion; adding the full width again
        # would double-count the baseline clearance.
        width_extra = max(0.0, policy.width_mm / 2.0 - 0.075)
        candidate_radius = max(0.0, width_extra / self.step)

        queue: list[tuple[int, int, GridPoint]] = []
        distance: dict[GridPoint, int] = {}
        parent: dict[GridPoint, GridPoint | None] = {}
        serial = 0
        for start in starts:
            # A pad core is always a legal source for its own net.  Subsequent
            # moves must satisfy the normal clearance checks.
            distance[start] = 0
            parent[start] = None
            heapq.heappush(
                queue,
                (self._bbox_heuristic(start, goal_bbox, goal_layers), serial, start),
            )
            serial += 1

        directions = ((1, 0, 10), (-1, 0, 10), (0, 1, 10), (0, -1, 10),
                      (1, 1, 14), (1, -1, 14), (-1, 1, 14), (-1, -1, 14))
        expansions = 0
        window_cells = (search_x1 - search_x0 + 1) * (search_y1 - search_y0 + 1)
        limit = min(60_000, max(8_000, window_cells * max(1, len(permitted))))
        while queue and expansions < limit:
            _, _, current = heapq.heappop(queue)
            current_distance = distance[current]
            if current in goals:
                path: list[GridPoint] = []
                node: GridPoint | None = current
                while node is not None:
                    path.append(node)
                    node = parent[node]
                path.reverse()
                if reverse_result:
                    path.reverse()
                return path
            expansions += 1

            for dx, dy, cost in directions:
                nx, ny = current.x + dx, current.y + dy
                if not self.inside(nx, ny):
                    continue
                if nx < search_x0 or nx > search_x1 or ny < search_y0 or ny > search_y1:
                    continue
                candidate = GridPoint(nx, ny, current.layer)
                # Static pad obstacles and committed dynamic copper are already
                # expanded by their required centre-line exclusion.  Expanding
                # the candidate a second time would double the clearance and
                # falsely eliminate legal 0.25 mm-centre differential routes.
                if not self._cell_clear(candidate, code, candidate_radius):
                    continue
                if dx and dy:
                    # Do not cut a diagonal between two blocked orthogonal cells.
                    if not self._cell_clear(
                        GridPoint(current.x + dx, current.y, current.layer),
                        code, candidate_radius,
                    ):
                        continue
                    if not self._cell_clear(
                        GridPoint(current.x, current.y + dy, current.layer),
                        code, candidate_radius,
                    ):
                        continue
                new_distance = current_distance + cost
                if new_distance < distance.get(candidate, 1 << 60):
                    distance[candidate] = new_distance
                    parent[candidate] = current
                    score = new_distance + self._bbox_heuristic(candidate, goal_bbox, goal_layers)
                    heapq.heappush(queue, (score, serial, candidate))
                    serial += 1

            if len(permitted) > 1 and self._via_clear(current, code, via_radius):
                for layer in permitted:
                    if layer == current.layer:
                        continue
                    candidate = GridPoint(current.x, current.y, layer)
                    new_distance = current_distance + policy.via_cost
                    if new_distance < distance.get(candidate, 1 << 60):
                        distance[candidate] = new_distance
                        parent[candidate] = current
                        score = new_distance + self._bbox_heuristic(candidate, goal_bbox, goal_layers)
                        heapq.heappush(queue, (score, serial, candidate))
                        serial += 1
        return None

    @staticmethod
    def _collinear(a: GridPoint, b: GridPoint, c: GridPoint) -> bool:
        if not (a.layer == b.layer == c.layer):
            return False
        return (b.x - a.x) * (c.y - b.y) == (b.y - a.y) * (c.x - b.x)

    def _add_track(self, code: int, layer_idx: int, a: tuple[float, float], b: tuple[float, float], width: float) -> None:
        if a == b:
            return
        if not self.emit_copper:
            self.tracks_added += 1
            return
        track = pcbnew.PCB_TRACK(self.board)
        track.SetStart(vec(*a)); track.SetEnd(vec(*b))
        track.SetWidth(pcbnew.FromMM(width))
        track.SetLayer(self.route_layers[layer_idx])
        track.SetNetCode(code)
        self.board.Add(track)
        self.tracks_added += 1

    def _add_via(self, code: int, point: GridPoint, policy: NetPolicy) -> None:
        key = (point.x, point.y)
        if key in self.via_cells[code]:
            return
        if not self.emit_copper:
            self.via_cells[code].add(key)
            self.vias_added += 1
            return
        x_mm, y_mm = self.xy(point.x, point.y)
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(vec(x_mm, y_mm))
        via.SetWidth(pcbnew.FromMM(policy.via_diameter_mm))
        via.SetDrill(pcbnew.FromMM(policy.via_drill_mm))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(code)
        self.board.Add(via)
        self.via_cells[code].add(key)
        self.vias_added += 1

    def _commit_path(
        self,
        code: int,
        path: list[GridPoint],
        endpoint: PadEndpoint,
        policy: NetPolicy,
        record: bool = True,
    ) -> None:
        if not path:
            return
        # Join the exact pad centre to the first grid node on a copper layer the
        # pad owns.  Edge connector pads may start just outside Edge.Cuts.
        first = path[0]
        if (
            endpoint.centre_link_required
            and self.route_layers[first.layer] in endpoint.layers
        ):
            self._add_track(code, first.layer, (endpoint.x_mm, endpoint.y_mm), self.xy(first.x, first.y), policy.width_mm)

        simplified: list[GridPoint] = []
        for point in path:
            if len(simplified) >= 2 and self._collinear(simplified[-2], simplified[-1], point):
                simplified[-1] = point
            else:
                simplified.append(point)
        via_positions: set[tuple[int, int]] = set()
        for left, right in zip(simplified, simplified[1:]):
            if left.layer == right.layer:
                self._add_track(
                    code,
                    left.layer,
                    self.xy(left.x, left.y),
                    self.xy(right.x, right.y),
                    policy.width_mm,
                )
            else:
                key = (left.x, left.y)
                if key not in via_positions:
                    self._add_via(code, left, policy)
                    via_positions.add(key)

        # Reserve enough centre-line space for the committed trace plus the
        # 0.25 mm routing guard and a future default 0.15 mm trace.  The extra
        # 0.05 mm absorbs diagonal grid rasterization while exceeding the
        # board-rule 0.20 mm clearance.
        # floor with a tiny epsilon permits an exactly-on-limit grid node.
        width_radius = max(
            0.0,
            (policy.width_mm / 2 + 0.25 + 0.075) / self.step,
        )
        via_radius = max(
            1.0,
            (policy.via_diameter_mm / 2 + 0.25 + 0.075) / self.step,
        )
        via_points = {
            (point.x, point.y)
            for point in path
            if any(
                point.x == other.x
                and point.y == other.y
                and point.layer != other.layer
                for other in path
            )
        }
        for point in path:
            radius = via_radius if (point.x, point.y) in via_points else width_radius
            extent = int(math.ceil(radius))
            radius_squared = radius * radius
            for yy in range(max(0, point.y - extent), min(self.ny, point.y + extent + 1)):
                for xx in range(max(0, point.x - extent), min(self.nx, point.x + extent + 1)):
                    if radius and (xx - point.x) ** 2 + (yy - point.y) ** 2 >= radius_squared - 1e-9:
                        continue
                    layers = (
                        range(len(self.route_layers))
                        if radius == via_radius else (point.layer,)
                    )
                    for layer in layers:
                        old = int(self.dynamic_owner[layer, yy, xx])
                        self.dynamic_owner[layer, yy, xx] = (
                            code if old in (0, code) else old
                        )
            self.routed_cells[code].add(point)

        # Reserve through-via centre positions independently of layer.  A
        # future 0.50 mm via needs 0.425 mm from a 0.15 mm trace centre and
        # 0.750 mm from another 0.50 mm via centre with the routing guard.
        for point in path:
            is_via = (point.x, point.y) in via_points
            centre_radius = (
                policy.via_diameter_mm / 2 + 0.25 + 0.25
                if is_via else
                policy.width_mm / 2 + 0.25 + 0.25
            ) / self.step
            extent = int(math.ceil(centre_radius))
            radius_squared = centre_radius * centre_radius
            for yy in range(max(0, point.y - extent), min(self.ny, point.y + extent + 1)):
                for xx in range(max(0, point.x - extent), min(self.nx, point.x + extent + 1)):
                    if (xx - point.x) ** 2 + (yy - point.y) ** 2 >= radius_squared - 1e-9:
                        continue
                    old = int(self.via_dynamic_owner[yy, xx])
                    self.via_dynamic_owner[yy, xx] = (
                        code if old in (0, code) else old
                    )

        # The board rule requires roughly 0.25 mm between finished drill
        # edges.  Reserve against the largest default future drill used by
        # this router (0.40 mm on PCB-PWR), so signal-via centres are kept at
        # least 0.60 mm apart even on the same net.
        for point in path:
            if (point.x, point.y) not in via_points:
                continue
            drill_radius = (
                policy.via_drill_mm / 2 + 0.2495 + 0.25
            ) / self.step
            extent = int(math.ceil(drill_radius))
            radius_squared = drill_radius * drill_radius
            for yy in range(max(0, point.y - extent), min(self.ny, point.y + extent + 1)):
                for xx in range(max(0, point.x - extent), min(self.nx, point.x + extent + 1)):
                    if (xx - point.x) ** 2 + (yy - point.y) ** 2 >= radius_squared - 1e-9:
                        continue
                    old = int(self.via_drill_owner[yy, xx])
                    self.via_drill_owner[yy, xx] = (
                        code if old in (0, code) else old
                    )

        if record:
            self.branches[code].append(
                RoutedBranch(list(path), endpoint, policy)
            )

    def rebuild_dynamic_copper(self) -> None:
        """Recreate routed copper and occupancy from retained branches."""
        retained = {
            code: list(branches) for code, branches in self.branches.items()
        }
        if self.emit_copper and not self.preserve_existing_copper:
            remove_existing_copper(self.board)
        self.dynamic_owner[:] = self.preserved_dynamic_owner
        self.via_dynamic_owner[:] = self.preserved_via_dynamic_owner
        self.via_drill_owner[:] = self.preserved_via_drill_owner
        self.routed_cells = defaultdict(set)
        self.via_cells = defaultdict(set)
        self.tracks_added = 0
        self.vias_added = 0
        self.branches = defaultdict(list)
        for code, branches in retained.items():
            for branch in branches:
                self._commit_path(
                    code,
                    branch.path,
                    branch.endpoint,
                    branch.policy,
                    record=False,
                )
                self.branches[code].append(branch)

    def rollback_net(self, code: int) -> None:
        self.branches.pop(code, None)
        self.rebuild_dynamic_copper()

    def rollback_nets(self, codes: Iterable[int]) -> None:
        changed = False
        for code in codes:
            if code in self.branches:
                self.branches.pop(code, None)
                changed = True
        if changed:
            self.rebuild_dynamic_copper()

    @staticmethod
    def _via_points(path: list[GridPoint]) -> set[tuple[int, int]]:
        layers_by_xy: dict[tuple[int, int], set[int]] = defaultdict(set)
        for point in path:
            layers_by_xy[(point.x, point.y)].add(point.layer)
        return {
            xy for xy, layers in layers_by_xy.items() if len(layers) > 1
        }

    def soft_blockers_for_net(
        self,
        code: int,
        name: str,
        policy: NetPolicy,
        protected_codes: set[int] | None = None,
    ) -> tuple[list[int], list[str]]:
        """Find a static-legal route and report routed nets occupying it."""
        saved_dynamic = self.dynamic_owner.copy()
        saved_via_dynamic = self.via_dynamic_owner.copy()
        saved_via_drill = self.via_drill_owner.copy()
        protected = protected_codes or set()
        if protected:
            protected_values = np.array(sorted(protected), dtype=np.int32)
            self.dynamic_owner[:] = np.where(
                self.preserved_dynamic_owner != 0,
                self.preserved_dynamic_owner,
                np.where(
                    np.isin(saved_dynamic, protected_values), saved_dynamic, 0
                ),
            )
            self.via_dynamic_owner[:] = np.where(
                self.preserved_via_dynamic_owner != 0,
                self.preserved_via_dynamic_owner,
                np.where(
                    np.isin(saved_via_dynamic, protected_values),
                    saved_via_dynamic,
                    0,
                ),
            )
            self.via_drill_owner[:] = np.where(
                self.preserved_via_drill_owner != 0,
                self.preserved_via_drill_owner,
                np.where(
                    np.isin(saved_via_drill, protected_values),
                    saved_via_drill,
                    0,
                ),
            )
        else:
            self.dynamic_owner[:] = self.preserved_dynamic_owner
            self.via_dynamic_owner[:] = self.preserved_via_dynamic_owner
            self.via_drill_owner[:] = self.preserved_via_drill_owner
        ok = self.route_net(code, name, policy, record_failures=False)
        failures = list(self.last_failed)
        counts: dict[int, int] = defaultdict(int)
        if ok:
            for branch in self.branches.get(code, []):
                via_points = self._via_points(branch.path)
                for point in branch.path:
                    owner = int(saved_dynamic[point.layer, point.y, point.x])
                    if owner > 0 and owner != code and owner not in protected:
                        counts[owner] += 1
                    if (point.x, point.y) in via_points:
                        owner = int(saved_via_dynamic[point.y, point.x])
                        if owner > 0 and owner != code and owner not in protected:
                            counts[owner] += 4
                        owner = int(saved_via_drill[point.y, point.x])
                        if owner > 0 and owner != code and owner not in protected:
                            counts[owner] += 4
        self.rollback_net(code)
        blockers = [
            owner for owner, _ in sorted(
                counts.items(), key=lambda item: (-item[1], item[0])
            )
        ]
        return blockers, failures

    def route_net(
        self,
        code: int,
        name: str,
        policy: NetPolicy,
        record_failures: bool = True,
    ) -> bool:
        self.last_failed = []
        endpoints = self._nearest_pad_order(self.pad_endpoints[code])
        if len(endpoints) < 2:
            return True
        root = endpoints[0]
        tree = set(root.seeds)
        self.routed_cells[code].update(tree)
        success = True
        for endpoint in endpoints[1:]:
            if any(seed in tree for seed in endpoint.seeds):
                tree.update(endpoint.seeds)
                continue
            path = None
            # Keep local nets local.  The wider retries are deterministic and
            # are only used when placement obstacles block the direct channel.
            for margin_mm in (4.0, 10.0, 22.0):
                path = self._search(code, endpoint.seeds, tree, policy, margin_mm)
                if path is not None:
                    break
            if path is None:
                detail = f"{name}:{endpoint.reference}.{endpoint.number}"
                self.last_failed.append(detail)
                if record_failures:
                    self.failed.append(detail)
                success = False
                continue
            self._commit_path(code, path, endpoint, policy)
            tree.update(path)
            tree.update(endpoint.seeds)
        return success


def policy_for(
    board_name: str,
    net_name: str,
    authority: dict[str, dict[str, str]],
    router: GridRouter,
) -> NetPolicy:
    row = authority.get(net_name, {})
    route_class = row.get("Route_Class", "LOW_SPEED_CONTROL")
    priority = {"P0": 0, "P1": 1, "P2": 2}.get(row.get("Priority", "P2"), 2)
    if board_name == "PCB-MAIN":
        normal = router.route_layers
        if route_class == "RF_50OHM":
            return NetPolicy(0.28, 0.50, 0.30, (pcbnew.F_Cu,), 200, priority)
        if route_class == "USB_90OHM_DIFF":
            return NetPolicy(0.15, 0.50, 0.30, normal, 120, priority)
        if "MODEM_BURST_POWER" in route_class:
            width = 1.00 if net_name == "3V8_MODEM_BB" else 2.70 if net_name == "3V8_MODEM_RF" else 0.60
            return NetPolicy(width, 0.60, 0.30, normal, 100, priority)
        if route_class == "POWER_RAIL":
            return NetPolicy(0.45, 0.60, 0.30, normal, 90, priority)
        if net_name.startswith("GND_"):
            return NetPolicy(0.35, 0.60, 0.30, normal, 80, priority)
        return NetPolicy(0.15, 0.50, 0.30, normal, 100, priority)

    normal = router.route_layers
    if route_class in {"SWITCH_NODE", "BOOTSTRAP_LOOP", "FEEDBACK_SENSE", "KELVIN_SENSE", "GATE_DRIVE"}:
        width = 0.80 if route_class == "SWITCH_NODE" else 0.20
        return NetPolicy(width, 0.60, 0.30, (pcbnew.F_Cu,), 200, priority)
    if "POWER" in route_class or route_class == "SEPARATE_HARNESS_RETURN":
        return NetPolicy(1.50, 0.80, 0.40, normal, 90, priority)
    if net_name == "GND_PWR":
        return NetPolicy(1.00, 0.80, 0.40, normal, 80, priority)
    return NetPolicy(0.20, 0.60, 0.30, normal, 100, priority)


def remove_existing_copper(board: pcbnew.BOARD) -> None:
    # Query/remove zones before invalidating a large number of SWIG track
    # proxies; see the matching deterministic session importer.
    for zone in list(board.Zones()):
        board.Remove(zone)
    for item in list(board.GetTracks()):
        board.Remove(item)


def add_main_octospi_clock_guide(board: pcbnew.BOARD) -> None:
    """Add the reviewed dense escape for the two R8 OctoSPI clocks.

    The two 0402 lands are only 0.65 mm apart.  Letting the negotiated router
    choose both escapes independently makes each clock select the same via
    corridor and oscillate during rip-up.  This deterministic guide sends U1
    to In2.Cu on the left and U2 to In3.Cu on the right while retaining the
    guarded 0.25 mm routing clearance used by the rest of the router.
    """
    def point(x_mm: float, y_mm: float) -> pcbnew.VECTOR2I:
        return vec(x_mm, y_mm)

    def add_track(net_name: str, layer: int, start: tuple[float, float], end: tuple[float, float]) -> None:
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(point(*start)); track.SetEnd(point(*end))
        track.SetWidth(pcbnew.FromMM(0.15))
        track.SetLayer(layer)
        track.SetNetCode(board.FindNet(net_name).GetNetCode())
        board.Add(track)

    def add_via(net_name: str, x_mm: float, y_mm: float) -> None:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(point(x_mm, y_mm))
        via.SetWidth(pcbnew.FromMM(0.50))
        via.SetDrill(pcbnew.FromMM(0.30))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(board.FindNet(net_name).GetNetCode())
        board.Add(via)

    u1 = "NOR_CLK_U1"
    add_track(u1, pcbnew.F_Cu, (54.675, 19.500), (54.600, 19.475))
    add_track(u1, pcbnew.F_Cu, (54.600, 19.475), (54.100, 18.975))
    add_via(u1, 54.100, 18.975)
    add_track(u1, pcbnew.In2_Cu, (54.100, 18.975), (52.725, 20.350))
    add_track(u1, pcbnew.In2_Cu, (52.725, 20.350), (52.725, 24.350))
    add_track(u1, pcbnew.In2_Cu, (52.725, 24.350), (51.975, 25.100))
    add_track(u1, pcbnew.In2_Cu, (51.975, 25.100), (51.975, 36.600))
    add_via(u1, 51.975, 36.600)
    add_track(u1, pcbnew.F_Cu, (51.975, 36.600), (52.000, 37.750))

    u2 = "NOR_CLK_U2"
    add_track(u2, pcbnew.F_Cu, (55.325, 19.500), (55.650, 19.175))
    add_track(u2, pcbnew.F_Cu, (55.650, 19.175), (56.000, 18.825))
    add_via(u2, 56.000, 18.825)
    add_track(u2, pcbnew.In3_Cu, (56.000, 18.825), (60.000, 22.825))
    add_track(u2, pcbnew.In3_Cu, (60.000, 22.825), (64.000, 26.825))
    add_track(u2, pcbnew.In3_Cu, (64.000, 26.825), (79.100, 26.825))
    add_via(u2, 79.100, 26.825)
    add_track(u2, pcbnew.F_Cu, (79.100, 26.825), (80.650, 27.055))


def apply_main_octospi_r8_eco(board: pcbnew.BOARD) -> None:
    """Move only R8 out of the escape trap at (55.0, 19.5) mm."""
    matches = [fp for fp in board.GetFootprints() if fp.GetReference() == "R8"]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one R8 footprint, found {len(matches)}")
    matches[0].SetPosition(vec(54.5, 16.0))


def route_board(
    board_name: str,
    input_path: Path,
    output_path: Path,
    only_nets: set[str] | None = None,
    excluded_nets: set[str] | None = None,
    max_fanout: int = 0,
    grid_step_mm: float = 0.25,
    max_track_width_mm: float = 0.0,
    priority_nets: list[str] | None = None,
    fanout_refs: set[str] | None = None,
    negotiate: bool = False,
    max_ripup_attempts: int = 4,
    max_blockers: int = 8,
    preserve_existing: bool = False,
    main_octospi_clock_guide: bool = False,
    main_octospi_r8_eco: bool = False,
) -> dict[str, object]:
    board = load_board_compat(input_path)
    if not preserve_existing:
        remove_existing_copper(board)
    authority_path = MAIN_AUTHORITY if board_name == "PCB-MAIN" else PWR_AUTHORITY
    authority = read_authority(authority_path)
    # New BOARD_ITEM UUIDs must be reproducible so a reviewed candidate can be
    # regenerated byte-for-byte from the same controlled base and arguments.
    pcbnew.KIID.SeedGenerator(0xD10E7EA)
    if main_octospi_clock_guide and main_octospi_r8_eco:
        raise ValueError("OctoSPI clock guide and R8 ECO are mutually exclusive")
    if main_octospi_r8_eco:
        if board_name != "PCB-MAIN" or not preserve_existing:
            raise ValueError("OctoSPI R8 ECO requires PCB-MAIN --preserve-existing")
        apply_main_octospi_r8_eco(board)
    if main_octospi_clock_guide:
        if board_name != "PCB-MAIN" or not preserve_existing:
            raise ValueError("OctoSPI clock guide requires PCB-MAIN --preserve-existing")
        add_main_octospi_clock_guide(board)
        guided = {"NOR_CLK_U1", "NOR_CLK_U2"}
        only_nets = (set(only_nets) - guided) if only_nets is not None else None
    router = GridRouter(board, board_name, grid_step_mm)
    existing_copper = (
        router.index_existing_copper()
        if preserve_existing else
        {"tracks": 0, "vias": 0}
    )

    explicit_priority = {
        name: index for index, name in enumerate(priority_nets or [])
    }
    candidates: list[tuple[int, int, int, float, int, str, NetPolicy]] = []
    for code, endpoints in router.pad_endpoints.items():
        if len(endpoints) < 2:
            continue
        name = board.FindNet(code).GetNetname()
        if only_nets is not None and name not in only_nets:
            continue
        if excluded_nets is not None and name in excluded_nets:
            continue
        if max_fanout and len(endpoints) > max_fanout:
            continue
        policy = policy_for(board_name, name, authority, router)
        if max_track_width_mm and policy.width_mm > max_track_width_mm:
            continue
        xs = [p.x_mm for p in endpoints]
        ys = [p.y_mm for p in endpoints]
        span = (max(xs) - min(xs)) + (max(ys) - min(ys))
        # P0 first, then large/long nets so they claim useful corridors early.
        # Route the positive member of each differential pair first so the
        # negative member can follow the adjacent remaining channel.
        pair_order = -1 if "_DP" in name else 0
        priority_group = 0 if name in explicit_priority else 1
        priority_rank = explicit_priority.get(name, policy.priority)
        candidates.append(
            (priority_group, priority_rank, pair_order, -span, code, name, policy)
        )
    candidates.sort()

    fanout_stubs = 0
    if fanout_refs:
        policies = {code: policy for _, _, _, _, code, _, policy in candidates}
        fanout_stubs = router.fanout_endpoints(
            set(policies), fanout_refs, policies
        )
        print(
            f"[FANOUT] refs={','.join(sorted(fanout_refs))} "
            f"stubs={fanout_stubs} tracks={router.tracks_added}",
            flush=True,
        )

    ripups = 0
    if not negotiate:
        for index, (_, _, _, _, code, name, policy) in enumerate(candidates, 1):
            print(
                f"[{index:03d}/{len(candidates):03d}] {name}: "
                f"START pads={len(router.pad_endpoints[code])}",
                flush=True,
            )
            ok = router.route_net(code, name, policy)
            print(
                f"[{index:03d}/{len(candidates):03d}] {name}: "
                f"{'ROUTED' if ok else 'PARTIAL'} pads={len(router.pad_endpoints[code])} "
                f"tracks={router.tracks_added} vias={router.vias_added}",
                flush=True,
            )
    else:
        if fanout_refs:
            raise ValueError("negotiated routing and pre-fanout stubs are mutually exclusive")
        router.emit_copper = False
        item_by_code = {
            code: item for item in candidates
            for code in (item[4],)
        }
        pending = deque(item[4] for item in candidates)
        visits: dict[int, int] = defaultdict(int)
        # Count only genuine failures which require negotiation.  A net that
        # was routed successfully and later displaced by a neighbour must not
        # exhaust its own retry budget merely by returning to the queue.
        fail_attempts: dict[int, int] = defaultdict(int)
        last_failures: dict[int, list[str]] = {}
        iteration = 0
        iteration_limit = max(
            len(candidates),
            len(candidates) * max(2, max_ripup_attempts + 1),
        )
        while pending and iteration < iteration_limit:
            code = pending.popleft()
            if code in router.branches:
                continue
            _, _, _, _, _, name, policy = item_by_code[code]
            iteration += 1
            visits[code] += 1
            print(
                f"[N{iteration:03d}] {name}: START "
                f"visit={visits[code]} failures={fail_attempts[code]} "
                f"routed={len(router.branches)}/{len(candidates)}",
                flush=True,
            )
            ok = router.route_net(code, name, policy, record_failures=False)
            if ok:
                last_failures.pop(code, None)
                print(
                    f"[N{iteration:03d}] {name}: ROUTED "
                    f"tracks={router.tracks_added} vias={router.vias_added}",
                    flush=True,
                )
                continue

            last_failures[code] = list(router.last_failed)
            fail_attempts[code] += 1
            router.rollback_net(code)
            blockers, soft_failures = router.soft_blockers_for_net(
                code, name, policy
            )
            blockers = [
                blocker for blocker in blockers
                if blocker in item_by_code and blocker in router.branches
            ][:max_blockers]
            if blockers and fail_attempts[code] >= 3:
                alternate, _ = router.soft_blockers_for_net(
                    code,
                    name,
                    policy,
                    protected_codes={blockers[0]},
                )
                alternate = [
                    blocker for blocker in alternate
                    if blocker in item_by_code and blocker in router.branches
                ][:max_blockers]
                if alternate:
                    blockers = alternate
            if not blockers or fail_attempts[code] > max_ripup_attempts:
                print(
                    f"[N{iteration:03d}] {name}: DEFER "
                    f"blockers={len(blockers)} failures={last_failures[code] or soft_failures}",
                    flush=True,
                )
                continue

            blocker_names = [item_by_code[blocker][5] for blocker in blockers]
            router.rollback_nets(blockers)
            ripups += len(blockers)
            print(
                f"[N{iteration:03d}] {name}: RIP "
                f"{','.join(blocker_names)}",
                flush=True,
            )
            ok = router.route_net(code, name, policy, record_failures=False)
            if ok:
                last_failures.pop(code, None)
                for blocker in reversed(blockers):
                    pending.appendleft(blocker)
                print(
                    f"[N{iteration:03d}] {name}: ROUTED_AFTER_RIP "
                    f"tracks={router.tracks_added} vias={router.vias_added}",
                    flush=True,
                )
            else:
                last_failures[code] = list(router.last_failed)
                router.rollback_net(code)
                for blocker in reversed(blockers):
                    pending.appendleft(blocker)
                if fail_attempts[code] <= max_ripup_attempts:
                    pending.append(code)

        # One final hard pass captures only the nets still absent after the
        # negotiated queue has settled.  Partial copper is always rolled back.
        router.failed = []
        for _, _, _, _, code, name, policy in candidates:
            if code in router.branches:
                continue
            ok = router.route_net(code, name, policy, record_failures=False)
            if not ok:
                details = list(router.last_failed) or last_failures.get(code, [])
                router.rollback_net(code)
                router.failed.extend(details or [f"{name}:UNROUTED"])

        # Materialize the settled branch graph exactly once.  Keeping SWIG
        # BOARD_ITEM creation out of the rip-up loop prevents allocator growth
        # during hundreds of transactional retries.
        router.emit_copper = True
        router.rebuild_dynamic_copper()

    board.BuildListOfNets()
    board.BuildConnectivity()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(output_path), board)
    return {
        "board": board_name,
        "nets_attempted": len(candidates),
        "tracks": router.tracks_added,
        "vias": router.vias_added,
        "failed_connections": router.failed,
        "fanout_stubs": fanout_stubs,
        "ripups": ripups,
        "preserved_existing_copper": existing_copper,
        "grid": {"step_mm": router.step, "nx": router.nx, "ny": router.ny},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", choices=("PCB-MAIN", "PCB-PWR"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--only-net", action="append", default=[],
        help="route only this native net; repeat for more than one net",
    )
    parser.add_argument(
        "--exclude-net", action="append", default=[],
        help="leave this native net for a controlled plane or manual route",
    )
    parser.add_argument(
        "--max-fanout", type=int, default=0,
        help="skip nets with more than this many physical endpoints (0 disables)",
    )
    parser.add_argument(
        "--grid-step", type=float, default=0.25,
        help="routing grid in millimetres; use 0.125 for dense fine-pitch escape",
    )
    parser.add_argument(
        "--max-track-width", type=float, default=0.0,
        help="skip policies wider than this many millimetres (0 disables)",
    )
    parser.add_argument(
        "--priority-net", action="append", default=[],
        help="route this native net before the standard authority order; repeat in desired order",
    )
    parser.add_argument(
        "--fanout-ref", action="append", default=[],
        help="pre-route short F.Cu escape stubs for this dense footprint reference",
    )
    parser.add_argument(
        "--negotiate", action="store_true",
        help="transactionally rip and reroute only nets blocking a failed route",
    )
    parser.add_argument(
        "--max-ripup-attempts", type=int, default=4,
        help="maximum negotiated rip-up attempts per net",
    )
    parser.add_argument(
        "--max-blockers", type=int, default=8,
        help="maximum blocking nets removed for one negotiated retry",
    )
    parser.add_argument(
        "--preserve-existing", action="store_true",
        help=(
            "keep and reserve existing native tracks/vias while completing "
            "explicit --only-net routes, including negotiated local rip-up"
        ),
    )
    parser.add_argument(
        "--main-octospi-clock-guide", action="store_true",
        help="apply the deterministic R8 clock escape used by the PCB-MAIN OctoSPI subgate",
    )
    parser.add_argument(
        "--main-octospi-r8-eco", action="store_true",
        help="move only R8 to (54.5, 16.0) mm before routing the PCB-MAIN OctoSPI subgate",
    )
    args = parser.parse_args()
    default = ROOT / f"hardware/kicad/native/{args.board}/{args.board}.kicad_pcb"
    input_path = args.input or default
    output_path = args.output or default
    result = route_board(
        args.board,
        input_path,
        output_path,
        set(args.only_net) if args.only_net else None,
        set(args.exclude_net) if args.exclude_net else None,
        args.max_fanout,
        args.grid_step,
        args.max_track_width,
        args.priority_net,
        set(args.fanout_ref) if args.fanout_ref else None,
        args.negotiate,
        args.max_ripup_attempts,
        args.max_blockers,
        args.preserve_existing,
        args.main_octospi_clock_guide,
        args.main_octospi_r8_eco,
    )
    print(result)
    return 1 if result["failed_connections"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
