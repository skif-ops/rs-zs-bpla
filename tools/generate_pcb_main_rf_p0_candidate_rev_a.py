#!/usr/bin/env python3
"""Generate the isolated PCB-MAIN P0 RF-routing candidate.

The candidate is a proposal only.  It preserves every accepted footprint,
zone, track and via in the authoritative OctoSPI R8 baseline, then routes the
seven RF_50OHM nets on F.Cu with the bounded public JLC06161H-3313 engineering
width.  Final job stackup, tolerance, coupon, SI, Review B and manufacturing
release remain external blocking gates.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pcbnew
import route_pcb_release_candidate_rev_a as release_router

from route_pcb_release_candidate_rev_a import (
    GridRouter,
    NetPolicy,
    load_board_compat,
    vec,
)


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-RF-P0-001"
    / "PCB-MAIN_RF_P0_BASE_REV_A.kicad_pcb"
)
DEFAULT_OUTPUT = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-RF-P0-001"
    / "PCB-MAIN_RF_P0_CANDIDATE_REV_A.kicad_pcb"
)
BASE_SHA256 = "04a0c7e37068d00fbe53b48fd19063b015b6b5c04e9aaafb3b01bbced0d7a99f"
RF_WIDTH_MM = 0.1509
GRID_STEP_MM = 0.0625
UUID_SEED = 0x52465030
_ROUTER_MM = release_router.mm
GUIDED_NET = "GNSS_RF_FILTERED"
ROUTED_NETS = (
    "CELL_RF",
    "CELL_RF_ANT",
    "GNSS_RF_ANT_BIASED",
    "GNSS_RF_DC_BLOCK",
    GUIDED_NET,
    "LORA_RF_ANT",
    "LORA_RF_MODULE",
)
PRIORITY = ("LORA_RF_MODULE", "LORA_RF_ANT")
GNSS_GUIDE = (
    (56.800, 53.250),
    (56.800, 51.000),
    (59.500, 51.000),
    (63.200, 54.700),
    (63.200, 67.000),
    (61.950, 68.250),
    (60.875, 68.250),
)
CELL_RF_CLEARANCE_VERTEX_FIXUPS = (
    ((24.1625, 67.6000), (24.2250, 67.6625)),
    ((24.1625, 67.7875), (24.2250, 67.8500)),
    ((25.9125, 68.1625), (25.9750, 68.1000)),
    ((25.9125, 68.4125), (25.9750, 68.3500)),
)


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def item_uuid(item: object) -> str:
    return str(item.m_Uuid.AsString())


def require_unique_trace_uuids(board: pcbnew.BOARD, label: str) -> None:
    uuids = [item_uuid(item) for item in board.GetTracks()]
    require(len(uuids) == len(set(uuids)), f"{label}: duplicate track/via UUID")


def enable_kicad9_router_compatibility() -> None:
    """Normalize KiCad 9's unset pad-clearance value for this proposal only."""
    def mm_compat(value: object) -> float:
        return 0.0 if value is None else _ROUTER_MM(value)

    release_router.mm = mm_compat


def add_gnss_guide(board: pcbnew.BOARD) -> int:
    net_code = board.FindNet(GUIDED_NET).GetNetCode()
    require(bool(net_code), f"missing native net: {GUIDED_NET}")
    count = 0
    for start, end in zip(GNSS_GUIDE, GNSS_GUIDE[1:]):
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(vec(*start))
        track.SetEnd(vec(*end))
        track.SetWidth(pcbnew.FromMM(RF_WIDTH_MM))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNetCode(net_code)
        board.Add(track)
        count += 1
    return count


def apply_cell_rf_clearance_fixups(board: pcbnew.BOARD) -> int:
    """Move four internal route vertices one grid step clear of adjacent pads."""
    net_code = board.FindNet("CELL_RF").GetNetCode()
    require(bool(net_code), "missing native net: CELL_RF")
    targets = {
        (vec(*old).x, vec(*old).y): vec(*new)
        for old, new in CELL_RF_CLEARANCE_VERTEX_FIXUPS
    }
    touches = {key: 0 for key in targets}
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA) or item.GetNetCode() != net_code:
            continue
        for getter, setter in (
            (item.GetStart, item.SetStart),
            (item.GetEnd, item.SetEnd),
        ):
            point = getter()
            key = (point.x, point.y)
            if key not in targets:
                continue
            setter(targets[key])
            touches[key] += 1
    require(all(count == 2 for count in touches.values()),
            f"CELL_RF clearance-fixup topology drift: {touches}")
    return len(touches)


def generate(output: Path) -> dict[str, object]:
    require(BASE.is_file(), f"missing controlled RF base: {BASE}")
    require(sha256(BASE) == BASE_SHA256, "RF base SHA-256 drift")
    board = load_board_compat(BASE)
    require_unique_trace_uuids(board, "base")

    # This candidate-specific seed is intentionally distinct from the generic
    # router's historical seed, whose output is already present in the base.
    pcbnew.KIID.SeedGenerator(UUID_SEED)
    guide_segments = add_gnss_guide(board)
    enable_kicad9_router_compatibility()
    router = GridRouter(board, "PCB-MAIN", GRID_STEP_MM)
    preserved = router.index_existing_copper()
    policy = NetPolicy(
        RF_WIDTH_MM,
        0.50,
        0.30,
        (pcbnew.F_Cu,),
        200,
        0,
    )

    explicit_priority = {name: index for index, name in enumerate(PRIORITY)}
    candidates: list[tuple[int, int, float, int, str]] = []
    for code, endpoints in router.pad_endpoints.items():
        if len(endpoints) < 2:
            continue
        name = board.FindNet(code).GetNetname()
        if name not in ROUTED_NETS or name == GUIDED_NET:
            continue
        xs = [endpoint.x_mm for endpoint in endpoints]
        ys = [endpoint.y_mm for endpoint in endpoints]
        span = (max(xs) - min(xs)) + (max(ys) - min(ys))
        group = 0 if name in explicit_priority else 1
        rank = explicit_priority.get(name, 0)
        candidates.append((group, rank, -span, code, name))
    candidates.sort()
    require({item[4] for item in candidates} == set(ROUTED_NETS) - {GUIDED_NET},
            "RF candidate net selection drift")

    failures: list[str] = []
    for index, (_, _, _, code, name) in enumerate(candidates, 1):
        print(f"[{index:02d}/{len(candidates):02d}] {name}: START", flush=True)
        if not router.route_net(code, name, policy):
            failures.extend(router.last_failed or [f"{name}:UNROUTED"])
        print(
            f"[{index:02d}/{len(candidates):02d}] {name}: "
            f"{'PASS' if not router.last_failed else 'FAIL'}",
            flush=True,
        )
    require(not failures, f"RF candidate routing failures: {failures}")

    clearance_fixups = apply_cell_rf_clearance_fixups(board)
    board.BuildListOfNets()
    board.BuildConnectivity()
    require_unique_trace_uuids(board, "candidate")
    output.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(output), board)
    return {
        "base_sha256": BASE_SHA256,
        "output": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
        "routed_nets": list(ROUTED_NETS),
        "guide_segments": guide_segments,
        "cell_rf_clearance_vertex_fixups": clearance_fixups,
        "router_segments": router.tracks_added,
        "added_segments": guide_segments + router.tracks_added,
        "added_vias": router.vias_added,
        "preserved_existing_copper": preserved,
        "grid_step_mm": GRID_STEP_MM,
        "rf_width_mm": RF_WIDTH_MM,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = generate(args.output.resolve())
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
