#!/usr/bin/env python3
"""Generate and materialize the controlled PCB-MAIN Rev.A placement repack.

The signed MAIN-AUTH-011 connector/module anchors are immutable here.  Every
other top-side footprint is placed deterministically inside a functional region
with a 0.25 mm search grid, a 0.15 mm inter-courtyard planning gap, the locked
M3 component exclusions and the three D8 U.FL tool cylinders enforced.

This is still an unrouted engineering layout candidate.  The script deliberately
does not create tracks, zones or fabrication output and never asserts Review B or
manufacturing release.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kiutils.board import Board
from kiutils.items.common import Position
from kiutils.utils import sexpr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_pcb_main_native_schematic_rev_a import expected_components  # noqa: E402
from audit_pcb_main_placement_clearance_rev_a import (  # noqa: E402
    Envelope,
    envelope_of,
    load_authority,
    load_tool_clearances,
    pad_screening_points,
    ref_of,
    rotate,
)

BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
AUTHORITY = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
PASSIVE_AUTHORITY = ROOT / "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv"
PLACEMENT = ROOT / "hardware/PCB_MAIN_PLACEMENT_REPACK_REV_A.csv"
ECO002_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_MECH_ECO_002_APPLICATION.json"
ECO003_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_RF_ROUTEABILITY_ECO_003_APPLICATION.json"
)
ECO004_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_STTS22H_FOOTPRINT_ECO_004_APPLICATION.json"
)
GROUND_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_GROUND_DOMAIN_ROUTING_APPLICATION_REV_A.json"
)
GROUND_BASE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-GROUND-DOMAIN-001/"
    "PCB-MAIN_GROUND_DOMAIN_BASE_REV_A.kicad_pcb"
)
GROUND_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-GROUND-DOMAIN-001/"
    "PCB-MAIN_GROUND_DOMAIN_CANDIDATE_REV_A.kicad_pcb"
)
SIGNAL_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_SIGNAL_HARD_NETS_ROUTING_APPLICATION_REV_A.json"
)
SIGNAL_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-SIGNAL-HARD-NETS-001/"
    "PCB-MAIN_SIGNAL_HARD_NETS_CANDIDATE_REV_A.kicad_pcb"
)
OCTOSPI_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_OCTOSPI_R8_ECO_002_APPLICATION_REV_A.json"
)
OCTOSPI_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-OCTOSPI-R8-ECO-002/"
    "PCB-MAIN_OCTOSPI_R8_ECO_CANDIDATE_REV_A.kicad_pcb"
)
RF_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_RF_P0_ROUTING_APPLICATION_REV_A.json"
RF_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-P0-001/"
    "PCB-MAIN_RF_P0_CANDIDATE_REV_A.kicad_pcb"
)
RF_REMEDIATION_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_APPLICATION_REV_A.json"
)
RF_REMEDIATION_COMPOSED = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-REMEDIATION-APPLICATION-001/"
    "PCB-MAIN_RF_REMEDIATION_COMPOSED_REV_A.kicad_pcb"
)
USB_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_USB_PLACEMENT_ECO_001_APPLICATION_REV_A.json"
)
USB_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-PLACEMENT-ECO-001/"
    "PCB-MAIN_USB_PLACEMENT_ECO_001_CANDIDATE_REV_A.kicad_pcb"
)
USB_SOURCE_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_USB_SOURCE_ROUTING_001_APPLICATION_REV_A.json"
)
USB_SOURCE_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-SOURCE-ROUTING-001/"
    "PCB-MAIN_USB_SOURCE_CANDIDATE_REV_A.kicad_pcb"
)
USB_CELL_MODEM_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_MODEM_ROUTING_001_APPLICATION_REV_A.json"
)
USB_CELL_MODEM_CANDIDATE = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-USB-CELL-MODEM-ROUTING-001/"
    "PCB-MAIN_USB_CELL_MODEM_CANDIDATE_REV_A.kicad_pcb"
)

ACTIVE_APPROVED_POSES = {
    "FL1": (56.8, 51.6, 270.0),
    "C64": (58.3, 51.6, 180.0),
    "D4": (58.25, 70.0, 90.0),
    "L2": (59.75, 70.25, 90.0),
    "R91": (64.0, 25.25, 0.0),
    "R92": (64.0, 26.25, 0.0),
}

PLACEMENT_GRID_MM = 0.25
PLANNING_GAP_MM = 0.15
MOVABLE_EDGE_CLEARANCE_MM = 1.0
PASSIVE_COURTYARD_MARGIN_MM = 0.25
PLACEMENT_SOURCE = "PCB_MAIN_PLACEMENT_REPACK_REV_A"
PASSIVE_COURTYARD_STATUS = "CONTROLLED_PAD_ENVELOPE_PLUS_0.25_MM"
PASSIVE_COURTYARD_SOURCE = "PCB_MAIN_PASSIVE_COURTYARD_RULE_REV_A"
PASSIVE_PACKAGES = {"0402", "0603", "0805", "1206", "1210"}
EXCLUSIVE_ZONE_GROUPS = {
    "ZONE_CELL": "CELL",
    "ZONE_GNSS": "GNSS",
    "ZONE_LORA": "LORA",
    "ZONE_BLE_BODY": "BLE",
    "ZONE_AUDIO_DIGITAL": "AUDIO",
}
ANTENNA_BOARD_KEEP_OUT = "KO_BLE_ANT_BOARD"


@dataclass(frozen=True)
class Region:
    bounds: tuple[float, float, float, float]
    target: tuple[float, float]


# These positions are layout choices, not MAIN-AUTH-011 capture anchors.  They
# form the deterministic active-component skeleton around which the passives are
# packed.  Moving one requires a reviewed update of the generated manifest.
ACTIVE_POSITIONS: dict[str, tuple[float, float, float]] = {
    "U1": (52.0, 30.0, 0.0),
    "U2": (76.0, 31.5, 0.0),
    "U3": (66.0, 30.5, 0.0),
    "U4": (66.0, 36.5, 0.0),
    "U5": (61.0, 57.0, 0.0),
    "U6": (90.5, 35.5, 0.0),
    "U7": (59.75, 45.25, 0.0),
    "U13": (36.5, 18.0, 0.0),
    "U14": (27.5, 12.0, 0.0),
    "U15": (73.5, 12.0, 0.0),
    "U16": (24.0, 32.75, 0.0),
    "U17": (47.0, 46.0, 0.0),
    "U18": (53.5, 46.0, 0.0),
    "U19": (6.5, 42.5, 0.0),
    "U20": (40.0, 68.5, 0.0),
    "U21": (92.0, 68.0, 0.0),
    "U22": (104.0, 54.0, 0.0),
    "U23": (83.0, 13.0, 0.0),
    "U24": (88.0, 13.0, 0.0),
    "U25": (39.0, 6.5, 0.0),
    "U26": (44.0, 6.5, 0.0),
    "U27": (41.0, 65.0, 0.0),
    "Q1": (13.0, 32.0, 0.0),
    "Q2": (18.0, 32.0, 0.0),
    "Q3": (27.5, 18.0, 0.0),
    "Q4": (61.0, 65.0, 0.0),
}

REGIONS: dict[str, Region] = {
    "PWR": Region((10.0, 23.0, 29.0, 36.5), (16.0, 29.0)),
    "MCU": Region((27.0, 17.0, 69.0, 42.0), (52.0, 30.0)),
    "STORAGE": Region((62.0, 20.0, 86.0, 44.0), (76.0, 31.5)),
    "AUDIO": Region((36.75, 39.0, 66.0, 51.0), (54.0, 45.0)),
    "CELL": Region((9.5, 28.0, 47.0, 69.0), (25.0, 50.0)),
    "SIMCTRL": Region((26.0, 10.0, 50.0, 24.0), (36.5, 18.0)),
    "SIM1": Region((9.5, 9.5, 32.0, 24.0), (20.0, 13.0)),
    "SIM2": Region((54.0, 9.5, 78.0, 24.0), (65.0, 13.0)),
    "GNSS": Region((44.0, 50.0, 64.0, 71.0), (53.5, 58.0)),
    "LORA": Region((63.0, 44.0, 84.0, 71.0), (74.0, 55.0)),
    "BLE": Region((85.5, 27.0, 106.0, 46.0), (95.0, 36.0)),
    "MIC1": Region((4.0, 35.0, 12.0, 50.0), (6.5, 42.5)),
    "MIC2": Region((31.0, 63.0, 49.0, 71.0), (40.0, 68.0)),
    "MIC3": Region((83.0, 63.0, 101.0, 71.0), (92.0, 68.0)),
    "MIC4": Region((97.0, 45.0, 106.0, 63.0), (103.0, 54.0)),
    "USB": Region((30.0, 5.0, 54.0, 17.0), (42.0, 8.0)),
    "SD": Region((77.0, 11.0, 99.0, 28.0), (87.0, 14.0)),
    "TAMPER": Region((96.0, 10.0, 106.0, 28.0), (102.0, 18.0)),
    "EOL": Region((17.0, 23.0, 42.0, 39.0), (29.0, 31.0)),
}

# RF components must be close to their two endpoints while remaining outside
# the connector tool cylinder.  The points deliberately sit on the module side
# of the D8 service exclusion.
TARGET_OVERRIDES: dict[str, tuple[float, float, str]] = {
    "D3": (24.0, 68.0, "U8/J8 RF path"),
    "C79": (24.0, 68.0, "U8/J8 RF path"),
    "C80": (24.0, 68.0, "U8/J8 RF path"),
    "R43": (24.0, 68.0, "U8/J8 RF path"),
    "D4": (61.0, 68.0, "U9/J9 RF path"),
    "C64": (61.0, 68.0, "U9/J9 RF path"),
    "L2": (61.0, 68.0, "U9/J9 bias path"),
    "FL1": (61.0, 68.0, "U9/J9 RF path"),
    "D5": (67.0, 68.0, "U10/J10 RF path"),
    "C69": (67.0, 68.0, "U10/J10 RF path"),
    "C70": (67.0, 68.0, "U10/J10 RF path"),
    "R73": (67.0, 68.0, "U10/J10 RF path"),
    "C19": (11.0, 29.0, "J_PWR 3V3 entry"),
    "C20": (11.0, 27.0, "J_PWR 1V8 entry"),
    "R101": (38.0, 31.0, "TP_EOL UART"),
    "R102": (38.0, 33.0, "TP_EOL UART"),
}


def natural_key(value: str) -> tuple[Any, ...]:
    return tuple(int(item) if item.isdigit() else item
                 for item in re.split(r"(\d+)", value))


def number_of(ref: str) -> int:
    match = re.search(r"(\d+)$", ref)
    return int(match.group(1)) if match else -1


def functional_group(ref: str) -> str:
    """Map every unlocked PCB-MAIN reference into one routing region."""
    if ref in {"U1", "L1", "X1"}:
        return "MCU"
    if ref in {"U2", "U3", "U4"}:
        return "STORAGE"
    if ref in {"U7", "U17", "U18"}:
        return "AUDIO"
    if ref in {"U8", "U16", "Q1", "Q2", "U27"}:
        return "CELL"
    if ref in {"U13", "Q3"}:
        return "SIMCTRL"
    if ref == "U14":
        return "SIM1"
    if ref == "U15":
        return "SIM2"
    if ref in {"U9", "U5", "Q4"}:
        return "GNSS"
    if ref == "U10":
        return "LORA"
    if ref in {"U11", "U6"}:
        return "BLE"
    if ref in {"U19", "U20", "U21", "U22"}:
        return f"MIC{number_of(ref) - 18}"
    if ref in {"U23", "U24"}:
        return "SD"
    if ref in {"U25", "U26"}:
        return "USB"

    index = number_of(ref)
    if ref.startswith("C"):
        if 1 <= index <= 18:
            return "MCU"
        if 19 <= index <= 20:
            return "PWR"
        if 21 <= index <= 26:
            return "STORAGE"
        if 27 <= index <= 32:
            return "AUDIO"
        if 33 <= index <= 48 or index in {79, 80}:
            return "CELL"
        if index == 49:
            return "SIMCTRL"
        if index in {50, 52, 54, 55, 56}:
            return "SIM1"
        if index in {51, 53, 57, 58, 59}:
            return "SIM2"
        if 60 <= index <= 65:
            return "GNSS"
        if 66 <= index <= 70:
            return "LORA"
        if 71 <= index <= 73:
            return "BLE"
        if 74 <= index <= 76:
            return "SD"
        if index == 77:
            return "USB"
        if index == 78:
            return "TAMPER"

    if ref.startswith("R"):
        if index in set(range(1, 17)) | {57, 69, 70, 71, 75, 79, 91, 92, 96, 103}:
            return "MCU"
        if index in {17, 18, 23}:
            return "AUDIO"
        if 19 <= index <= 22:
            return f"MIC{index - 18}"
        if 24 <= index <= 43:
            return "CELL"
        if index in {44, 45, 46, 47}:
            return "SIMCTRL"
        if index in {48, 50, 51, 52}:
            return "SIM1"
        if index in {49, 53, 54, 55}:
            return "SIM2"
        if index in {56, 58, 59, 60, 61, 62}:
            return "GNSS"
        if index in {63, 64, 65, 66, 67, 68, 72, 73}:
            return "LORA"
        if index in {74, 76, 77, 78}:
            return "BLE"
        if 80 <= index <= 90:
            return "SD"
        if 93 <= index <= 98:
            return "USB"
        if index in {99, 100}:
            return "TAMPER"
        if index in {101, 102}:
            return "EOL"

    special = {
        "L2": "GNSS", "FL1": "GNSS", "D4": "GNSS",
        "D3": "CELL", "D5": "LORA",
        "D6": "USB", "D7": "USB", "D8": "USB",
        "D9": "TAMPER", "D10": "CELL", "D11": "SD",
        "D1": "CELL", "D2": "CELL", "FB1": "CELL",
    }
    if ref in special:
        return special[ref]
    raise AssertionError(f"{ref}: no functional placement group")


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def passive_rows() -> dict[str, dict[str, str]]:
    with PASSIVE_AUTHORITY.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return {row["RefDes"]: row for row in rows}


def placement_zones() -> tuple[dict[str, tuple[float, float, float, float]],
                               tuple[float, float, float, float]]:
    zones: dict[str, tuple[float, float, float, float]] = {}
    keepout: tuple[float, float, float, float] | None = None
    with AUTHORITY.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        x = float(row["X_mm"])
        y = float(row["Y_mm"])
        bounds = (x, y, x + float(row["Extent_X_mm"]),
                  y + float(row["Extent_Y_mm"]))
        if row["RefDes"] in EXCLUSIVE_ZONE_GROUPS:
            zones[EXCLUSIVE_ZONE_GROUPS[row["RefDes"]]] = bounds
        elif row["RefDes"] == ANTENNA_BOARD_KEEP_OUT:
            keepout = bounds
    require(set(zones) == set(EXCLUSIVE_ZONE_GROUPS.values()),
            "exclusive MAIN-AUTH-011 placement-zone set drift")
    require(keepout is not None, "BLE all-layer antenna keepout is missing")
    return zones, keepout


def owner_refs(text: str, footprints: dict[str, Any]) -> list[str]:
    candidates = re.findall(r"\b(?:U\d+|Q\d+|J\d+|J_MIC\d+|J_PWR)\b", text)
    result: list[str] = []
    for ref in candidates:
        if ref in footprints and ref not in result:
            result.append(ref)
    return result


def pad_target(footprint: Any, number: str) -> tuple[float, float] | None:
    pads = [pad for pad in footprint.pads if pad.number == number]
    if len(pads) != 1:
        return None
    pad = pads[0]
    local_x, local_y = rotate(
        (float(pad.position.X), float(pad.position.Y)),
        float(footprint.position.angle or 0.0),
    )
    return (local_x + float(footprint.position.X),
            local_y + float(footprint.position.Y))


def placement_target(
    ref: str,
    footprints: dict[str, Any],
    rows: dict[str, dict[str, str]],
) -> tuple[float, float, str]:
    if ref in TARGET_OVERRIDES:
        return TARGET_OVERRIDES[ref]
    row = rows.get(ref)
    if row:
        text = f"{row['Electrical_Path']} {row['Notes']}"
        owners = owner_refs(text, footprints)
        if len(owners) == 1:
            owner = owners[0]
            match = re.search(rf"\b{re.escape(owner)}\b[^.;]*?\bpin\s+(\d+)\b", text)
            if match:
                target = pad_target(footprints[owner], match.group(1))
                if target is not None:
                    return target[0], target[1], f"{owner}.{match.group(1)}"
            owner_fp = footprints[owner]
            return (float(owner_fp.position.X), float(owner_fp.position.Y), owner)
        if owners:
            x = sum(float(footprints[item].position.X) for item in owners) / len(owners)
            y = sum(float(footprints[item].position.Y) for item in owners) / len(owners)
            return x, y, "/".join(owners)
    region = REGIONS[functional_group(ref)]
    return region.target[0], region.target[1], functional_group(ref)


def footprints_by_ref(board: Any) -> dict[str, Any]:
    result = {ref_of(footprint): footprint for footprint in board.footprints}
    require(len(result) == len(board.footprints), "duplicate or blank footprint reference")
    return result


def expected_movable_refs(components: dict[str, Any], locked_refs: set[str]) -> set[str]:
    return {
        ref for ref, component in components.items()
        if component["on_board"]
        and ref not in locked_refs
        and not str(component["package"]).startswith("POGO_FIXTURE_")
    }


def overlaps(first: Envelope, second: Envelope, gap: float = PLANNING_GAP_MM) -> bool:
    return not (
        first.xmax + gap <= second.xmin
        or second.xmax + gap <= first.xmin
        or first.ymax + gap <= second.ymin
        or second.ymax + gap <= first.ymin
    )


def rectangle_intersects_circle(
    envelope: Envelope,
    center_x: float,
    center_y: float,
    radius: float,
    gap: float = PLANNING_GAP_MM,
) -> bool:
    nearest_x = max(envelope.xmin, min(center_x, envelope.xmax))
    nearest_y = max(envelope.ymin, min(center_y, envelope.ymax))
    return math.hypot(nearest_x - center_x, nearest_y - center_y) < radius + gap


def rectangle_intersects_rectangle(
    envelope: Envelope,
    bounds: tuple[float, float, float, float],
    gap: float = PLANNING_GAP_MM,
) -> bool:
    xmin, ymin, xmax, ymax = bounds
    return not (
        envelope.xmax + gap <= xmin
        or xmax + gap <= envelope.xmin
        or envelope.ymax + gap <= ymin
        or ymax + gap <= envelope.ymin
    )


def grid_candidates(region: Region, target: tuple[float, float]) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = region.bounds
    target_x, target_y = target
    candidates: list[tuple[float, float, float]] = []
    y = y0
    while y <= y1 + 1e-9:
        x = x0
        while x <= x1 + 1e-9:
            candidates.append((
                round(x, 3),
                round(y, 3),
                (x - target_x) ** 2 + (y - target_y) ** 2,
            ))
            x += PLACEMENT_GRID_MM
        y += PLACEMENT_GRID_MM
    candidates.sort(key=lambda item: (item[2], item[1], item[0]))
    return [(item[0], item[1]) for item in candidates]


def build_plan(board: Any) -> list[dict[str, str]]:
    components = expected_components()
    footprints = footprints_by_ref(board)
    locked_refs, mounting_holes = load_authority(AUTHORITY)
    tool_clearances = load_tool_clearances(AUTHORITY)
    exclusive_zones, antenna_keepout = placement_zones()
    rows = passive_rows()
    movable_refs = expected_movable_refs(components, locked_refs)
    require(set(ACTIVE_POSITIONS) <= movable_refs,
            "active placement skeleton contains a locked or off-board reference")

    for ref, (x, y, angle) in ACTIVE_POSITIONS.items():
        footprints[ref].position = Position(x, y, angle or None)

    occupied = [
        envelope_of(footprints[ref], locked_refs)
        for ref in sorted(locked_refs, key=natural_key)
        if footprints[ref].layer == "F.Cu"
    ]

    def valid(envelope: Envelope, group: str) -> bool:
        if (envelope.xmin < MOVABLE_EDGE_CLEARANCE_MM
                or envelope.xmax > 110.0 - MOVABLE_EDGE_CLEARANCE_MM
                or envelope.ymin < MOVABLE_EDGE_CLEARANCE_MM
                or envelope.ymax > 75.0 - MOVABLE_EDGE_CLEARANCE_MM):
            return False
        if any(overlaps(envelope, item) for item in occupied):
            return False
        for hole in mounting_holes:
            if rectangle_intersects_circle(
                envelope,
                hole["x_mm"],
                hole["y_mm"],
                hole["component_exclusion_diameter_mm"] / 2.0,
            ):
                return False
        for clearance in tool_clearances:
            if rectangle_intersects_circle(
                envelope,
                clearance["x_mm"],
                clearance["y_mm"],
                clearance["diameter_mm"] / 2.0,
            ):
                return False
        for owner_group, bounds in exclusive_zones.items():
            if group != owner_group and rectangle_intersects_rectangle(envelope, bounds):
                return False
        if (envelope.ref != "U11"
                and rectangle_intersects_rectangle(envelope, antenna_keepout)):
            return False
        return True

    plan: dict[str, dict[str, str]] = {}
    for ref, (x, y, angle) in sorted(ACTIVE_POSITIONS.items(), key=lambda item: natural_key(item[0])):
        group = functional_group(ref)
        envelope = envelope_of(footprints[ref], locked_refs)
        require(valid(envelope, group),
                f"{ref}: active skeleton placement violates a clearance or exclusive zone")
        occupied.append(envelope)
        plan[ref] = placement_row(ref, x, y, angle, group, group, "ACTIVE_SKELETON")

    remaining: list[tuple[str, float]] = []
    for ref in movable_refs - set(ACTIVE_POSITIONS):
        footprint = footprints[ref]
        require(footprint.layer == "F.Cu", f"{ref}: movable placement is not top-side")
        envelope = envelope_of(footprint, locked_refs)
        # Round before ordering so adding the equivalent explicit courtyard
        # cannot reshuffle equal-package parts through floating-point noise.
        area = round(
            (envelope.xmax - envelope.xmin) * (envelope.ymax - envelope.ymin),
            6,
        )
        remaining.append((ref, area))
    remaining.sort(key=lambda item: (
        functional_group(item[0]),
        -item[1],
        natural_key(item[0]),
    ))

    for ref, _area in remaining:
        footprint = footprints[ref]
        group = functional_group(ref)
        target_x, target_y, target_source = placement_target(ref, footprints, rows)
        found: tuple[float, float, Envelope] | None = None
        for x, y in grid_candidates(REGIONS[group], (target_x, target_y)):
            footprint.position = Position(x, y, None)
            envelope = envelope_of(footprint, locked_refs)
            if valid(envelope, group):
                found = (x, y, envelope)
                break
        require(found is not None,
                f"{ref}: functional region {group} has no collision-free placement")
        x, y, envelope = found
        occupied.append(envelope)
        plan[ref] = placement_row(
            ref, x, y, 0.0, group, target_source, "FUNCTIONAL_REGION_GREEDY",
        )

    require(set(plan) == movable_refs,
            f"placement set mismatch: missing={sorted(movable_refs - set(plan))} "
            f"extra={sorted(set(plan) - movable_refs)}")
    return [plan[ref] for ref in sorted(plan, key=natural_key)]


def placement_row(
    ref: str,
    x: float,
    y: float,
    angle: float,
    group: str,
    target: str,
    method: str,
) -> dict[str, str]:
    return {
        "RefDes": ref,
        "X_mm": decimal(x),
        "Y_mm": decimal(y),
        "Rotation_deg": decimal(angle),
        "Functional_Group": group,
        "Target": target,
        "Placement_Method": method,
        "Placement_Class": "UNLOCKED_LAYOUT_CANDIDATE",
        "Authority": "PCB-MAIN-PLACEMENT-REPACK-REV-A",
        "Status": "ENGINEERING_CANDIDATE_NOT_FOR_MANUFACTURE",
    }


PLACEMENT_FIELDS = [
    "RefDes", "X_mm", "Y_mm", "Rotation_deg", "Functional_Group", "Target",
    "Placement_Method", "Placement_Class", "Authority", "Status",
]


def placement_csv(rows: Iterable[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=PLACEMENT_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def decimal(value: float) -> str:
    rendered = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_sexpr_end(text: str, start: int) -> int:
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    raise AssertionError("unterminated s-expression")


def footprint_blocks(text: str) -> list[tuple[int, int, str]]:
    result: list[tuple[int, int, str]] = []
    cursor = 0
    marker = "  (footprint "
    while True:
        start = text.find(marker, cursor)
        if start < 0:
            return result
        end = find_sexpr_end(text, start + 2)
        block = text[start:end]
        match = re.search(r'^    \(fp_text reference "([^"]+)"', block, re.MULTILINE)
        require(match is not None, "footprint block has no reference")
        result.append((start, end, match.group(1)))
        cursor = end


def passive_courtyard_line(ref: str, footprint: Any) -> str:
    points = pad_screening_points(footprint)
    xmin = min(point[0] for point in points)
    ymin = min(point[1] for point in points)
    xmax = max(point[0] for point in points)
    ymax = max(point[1] for point in points)
    tstamp = uuid.uuid5(uuid.NAMESPACE_URL, f"dioneya:pcb-main:{ref}:passive-courtyard:v1")
    return (
        f"    (fp_rect (start {decimal(xmin)} {decimal(ymin)}) "
        f"(end {decimal(xmax)} {decimal(ymax)}) (layer \"F.CrtYd\") "
        f"(stroke (width 0.05) (type default)) (fill none) (tstamp {tstamp}))\n"
    )


def remove_front_courtyard_rects(block: str) -> str:
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"(?m)^    \(fp_rect(?:\s|$)", block):
        end = find_sexpr_end(block, match.start())
        expression = block[match.start():end]
        if re.search(r'\(layer "F\.CrtYd"\)', expression):
            if block[end:end + 1] == "\n":
                end += 1
            spans.append((match.start(), end))
    for start, end in reversed(spans):
        block = block[:start] + block[end:]
    return block


def transform_footprint_block(
    block: str,
    ref: str,
    row: dict[str, str] | None,
    footprint: Any,
) -> str:
    transformed = re.sub(
        r'^    \(property "DIONEA_(?:PLACEMENT_SOURCE|PLACEMENT_CLASS|COURTYARD_STATUS|COURTYARD_SOURCE)"[^\n]*\n',
        "",
        block,
        flags=re.MULTILINE,
    )
    package = footprint.properties.get("DIONEA_PACKAGE", "")
    if package in PASSIVE_PACKAGES:
        transformed = remove_front_courtyard_rects(transformed)

    additions = ""
    if row is not None:
        replacement = f"    (at {row['X_mm']} {row['Y_mm']}"
        if float(row["Rotation_deg"]) != 0.0:
            replacement += f" {row['Rotation_deg']}"
        replacement += ")"
        transformed, count = re.subn(
            r'^    \(at [^\n]+\)$', replacement, transformed,
            count=1, flags=re.MULTILINE,
        )
        require(count == 1, f"{ref}: footprint position is missing")
        additions += f"    (property \"DIONEA_PLACEMENT_SOURCE\" \"{PLACEMENT_SOURCE}\")\n"
        additions += "    (property \"DIONEA_PLACEMENT_CLASS\" \"UNLOCKED_LAYOUT_CANDIDATE\")\n"
    if package in PASSIVE_PACKAGES:
        additions += f"    (property \"DIONEA_COURTYARD_STATUS\" \"{PASSIVE_COURTYARD_STATUS}\")\n"
        additions += f"    (property \"DIONEA_COURTYARD_SOURCE\" \"{PASSIVE_COURTYARD_SOURCE}\")\n"
        additions += passive_courtyard_line(ref, footprint)

    if additions:
        population = re.search(
            r'^    \(property "DIONEA_POPULATION"[^\n]*\n', transformed, re.MULTILINE,
        )
        require(population is not None, f"{ref}: DIONEA_POPULATION property is missing")
        transformed = transformed[:population.end()] + additions + transformed[population.end():]
    return transformed


def materialized_board_text(source: str, rows: list[dict[str, str]]) -> str:
    board = Board.from_sexpr(sexpr.parse_sexp(source))
    footprints = footprints_by_ref(board)
    by_ref = {row["RefDes"]: row for row in rows}
    blocks = footprint_blocks(source)
    require({ref for _, _, ref in blocks} == set(footprints),
            "raw footprint block set differs from parsed board")
    output: list[str] = []
    cursor = 0
    for start, end, ref in blocks:
        output.append(source[cursor:start])
        output.append(transform_footprint_block(
            source[start:end], ref, by_ref.get(ref), footprints[ref],
        ))
        cursor = end
    output.append(source[cursor:])
    return "".join(output)


def verify_materialized(board_text: str, rows: list[dict[str, str]]) -> None:
    board = Board.from_sexpr(sexpr.parse_sexp(board_text))
    footprints = footprints_by_ref(board)
    for row in rows:
        footprint = footprints[row["RefDes"]]
        require(abs(float(footprint.position.X) - float(row["X_mm"])) < 0.001,
                f"{row['RefDes']}: materialized X differs from manifest")
        require(abs(float(footprint.position.Y) - float(row["Y_mm"])) < 0.001,
                f"{row['RefDes']}: materialized Y differs from manifest")
        actual_angle = float(footprint.position.angle or 0.0) % 360.0
        expected_angle = float(row["Rotation_deg"]) % 360.0
        require(abs(actual_angle - expected_angle) < 0.001,
                f"{row['RefDes']}: materialized rotation differs from manifest")
        require(footprint.properties.get("DIONEA_PLACEMENT_SOURCE") == PLACEMENT_SOURCE,
                f"{row['RefDes']}: placement source property is missing")
    for ref, footprint in footprints.items():
        if footprint.properties.get("DIONEA_PACKAGE") not in PASSIVE_PACKAGES:
            continue
        courtyard = [item for item in footprint.graphicItems
                     if getattr(item, "layer", None) == "F.CrtYd"]
        require(len(courtyard) == 1, f"{ref}: passive courtyard count differs from one")
        require(footprint.properties.get("DIONEA_COURTYARD_STATUS") ==
                PASSIVE_COURTYARD_STATUS, f"{ref}: passive courtyard status is missing")
        require(footprint.properties.get("DIONEA_COURTYARD_SOURCE") ==
                PASSIVE_COURTYARD_SOURCE, f"{ref}: passive courtyard source is missing")


def verify_approved_frozen_repack(board_text: str) -> tuple[int, str]:
    """Verify the latest exact hash-bound approved placement evidence.

    ECO-002 froze the manually optimized collision-free placement, ECO-003
    authorized only the FL1/D4/L2 pose delta, and ECO-004 changed only U4's
    internal land geometry.  Exact lineage hashes control this check; none of
    the approvals turns candidate copper into production routing.
    """
    if ECO003_APPLICATION.is_file():
        application = json.loads(ECO003_APPLICATION.read_text(encoding="utf-8"))
        proposal_id = "PCB-MAIN-RF-ROUTEABILITY-ECO-003"
        require(application.get("proposal_id") == proposal_id and
                application.get("decision") == "ACCEPT_LIMITED_RF_ROUTEABILITY_ECO" and
                application.get("placement_implementation_authorized") is True and
                application.get("routing_engineering_continuation_authorized") is True and
                application.get("candidate_copper_final_authorized") is False and
                application.get("routing_complete") is False and
                application.get("review_b_complete") is False and
                application.get("manufacturing_release") is False,
                "PCB-MAIN ECO-003 application identity or release boundary drift")
        applied = application.get("applied", {})
        require(applied.get("track_segments") == 0 and
                applied.get("vias") == 0 and
                applied.get("copper_zones") == 0 and
                applied.get("changed_references") == ["D4", "FL1", "L2"],
                "PCB-MAIN ECO-003 placement-only application drift")
        board_applied = applied
        if ECO004_APPLICATION.is_file():
            eco004 = json.loads(ECO004_APPLICATION.read_text(encoding="utf-8"))
            proposal_id = "PCB-MAIN-STTS22H-FOOTPRINT-ECO-004"
            require(eco004.get("proposal_id") == proposal_id and
                    eco004.get("decision") == "ACCEPT_STTS22H_FOOTPRINT_ECO_004" and
                    eco004.get("routing_engineering_continuation_authorized") is True and
                    eco004.get("candidate_or_future_copper_final_authorized") is False and
                    eco004.get("routing_complete") is False and
                    eco004.get("review_b_complete") is False and
                    eco004.get("cam_or_manufacturing_release") is False,
                    "PCB-MAIN ECO-004 application identity or release boundary drift")
            board_applied = eco004.get("applied", {})
            require(board_applied.get("changed_references") == ["U4"] and
                    board_applied.get("track_segments") == 0 and
                    board_applied.get("vias") == 0 and
                    board_applied.get("copper_zones") == 0,
                    "PCB-MAIN ECO-004 footprint-only application drift")
    else:
        application = json.loads(ECO002_APPLICATION.read_text(encoding="utf-8"))
        proposal_id = "PCB-MAIN-MECH-ECO-002"
        require(application.get("proposal_id") == proposal_id and
                application.get("decision") == "ACCEPT_LIMITED_MECHANICAL_ECO",
                "PCB-MAIN ECO-002 application identity drift")
        require(application.get("routing_authorized") is False and
                application.get("review_b_complete") is False and
                application.get("manufacturing_release") is False,
                "PCB-MAIN ECO-002 frozen repack crosses a release boundary")
        applied = application.get("applied", {})
        board_applied = applied
    require(applied.get("placement_repack") ==
            str(PLACEMENT.relative_to(ROOT)),
            "PCB-MAIN approved placement-repack path drift")
    if OCTOSPI_APPLICATION.is_file():
        octospi_placement = json.loads(
            OCTOSPI_APPLICATION.read_text(encoding="utf-8")
        )
        proposal_id = "PCB-MAIN-OCTOSPI-R8-ECO-002"
        octospi_applied = octospi_placement.get("applied", {})
        require(
            applied.get("placement_repack_sha256") ==
            "34abe08f925ec03f045b295d5c40a0391e0597a09ecdad5a7e563c93f53a62c4" and
            octospi_placement.get("proposal_id") == proposal_id and
            octospi_placement.get("decision") ==
            "ACCEPT_LIMITED_OCTOSPI_R8_PLACEMENT_ECO_AND_ROUTING_SUBGATE" and
            octospi_applied.get("placement_manifest") ==
            str(PLACEMENT.relative_to(ROOT)) and
            octospi_applied.get("placement_manifest_sha256") ==
            "70b453c77745580f16d571c999eeb0cde3f5581db69568668131dbe84ab20925" and
            octospi_applied.get("r8_position_mm") == [54.5, 16.0],
            "PCB-MAIN approved OctoSPI R8 placement successor drift",
        )
        remediation = json.loads(
            RF_REMEDIATION_APPLICATION.read_text(encoding="utf-8")
        )
        require(
            remediation.get("decision") ==
            "ACCEPT_GNSS_RF_PLACEMENT_ROUTEABILITY_SUBGATE"
            and remediation.get("applied", {}).get("placement_manifest") ==
            str(PLACEMENT.relative_to(ROOT))
            and remediation.get("applied", {}).get("placement_manifest_sha256") ==
            "0c32b3818ae1fbf9c0552d3734f1d6390f753e4f1b044d7c96dc8831d2d5f8a0",
            "PCB-MAIN accepted GNSS placement-manifest successor drift",
        )
        usb = json.loads(USB_APPLICATION.read_text(encoding="utf-8"))
        usb_source = json.loads(USB_SOURCE_APPLICATION.read_text(encoding="utf-8"))
        usb_cell_modem = json.loads(
            USB_CELL_MODEM_APPLICATION.read_text(encoding="utf-8")
        )
        require(
            usb.get("decision") ==
            "ACCEPT_USB_SOURCE_TERMINATION_PLACEMENT_SUBGATE"
            and usb.get("applied", {}).get("board_sha256") == sha256(USB_CANDIDATE)
            and usb.get("applied", {}).get("exact_candidate_byte_identity") is True
            and usb.get("applied", {}).get("placement_manifest_sha256") ==
            sha256(PLACEMENT)
            and usb.get("usb_pair_routing_complete") is False
            and usb.get("review_b_complete") is False
            and usb.get("cam_or_manufacturing_release") is False,
            "PCB-MAIN accepted USB placement-manifest successor drift",
        )
        require(
            usb_source.get("decision") == "ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE"
            and usb_source.get("applied", {}).get("board_sha256") ==
            sha256(USB_SOURCE_CANDIDATE)
            and usb_source.get("applied", {}).get("exact_candidate_byte_identity") is True
            and usb_source.get("review_b_complete") is False
            and usb_source.get("manufacturing_release") is False,
            "PCB-MAIN accepted USB source-routing successor drift",
        )
        require(
            usb_cell_modem.get("decision") ==
            "ACCEPT_USB_CELL_MODEM_ROUTING_SUBGATE"
            and usb_cell_modem.get("predecessor", {}).get("board_sha256") ==
            sha256(USB_SOURCE_CANDIDATE)
            and usb_cell_modem.get("applied", {}).get("board_sha256") ==
            sha256(USB_CELL_MODEM_CANDIDATE)
            and usb_cell_modem.get("applied", {}).get(
                "exact_candidate_byte_identity"
            ) is True
            and usb_cell_modem.get("review_b_complete") is False
            and usb_cell_modem.get("manufacturing_release") is False,
            "PCB-MAIN accepted cellular USB modem-routing successor drift",
        )
    else:
        require(applied.get("placement_repack_sha256") == sha256(PLACEMENT),
                "PCB-MAIN approved placement-repack SHA-256 drift")
    approved_board = GROUND_BASE if GROUND_APPLICATION.is_file() else BOARD
    require(board_applied.get("board") == str(BOARD.relative_to(ROOT)) and
            board_applied.get("board_sha256") == sha256(approved_board),
            "PCB-MAIN approved placement board SHA-256 drift")
    require(applied.get("mechanical_authority", applied.get("authority")) ==
            str(AUTHORITY.relative_to(ROOT)) and
            applied.get("mechanical_authority_sha256", applied.get("authority_sha256")) ==
            sha256(AUTHORITY),
            "PCB-MAIN approved mechanical authority SHA-256 drift")

    with PLACEMENT.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == PLACEMENT_FIELDS,
                "PCB-MAIN approved placement manifest schema drift")
        rows = list(reader)
    board = Board.from_sexpr(sexpr.parse_sexp(board_text))
    components = expected_components()
    locked_refs, _mounting_holes = load_authority(AUTHORITY)
    expected = expected_movable_refs(components, locked_refs)
    require(len(rows) == len(expected) and
            {row["RefDes"] for row in rows} == expected,
            "PCB-MAIN approved placement reference set drift")
    require(all(row["Placement_Class"] == "UNLOCKED_LAYOUT_CANDIDATE" and
                row["Authority"] == "PCB-MAIN-PLACEMENT-REPACK-REV-A" and
                row["Status"] == "ENGINEERING_CANDIDATE_NOT_FOR_MANUFACTURE"
                for row in rows),
            "PCB-MAIN approved placement release boundary drift")
    verify_materialized(board_text, rows)
    if GROUND_APPLICATION.is_file():
        ground = json.loads(GROUND_APPLICATION.read_text(encoding="utf-8"))
        signal = json.loads(SIGNAL_APPLICATION.read_text(encoding="utf-8"))
        octospi = json.loads(OCTOSPI_APPLICATION.read_text(encoding="utf-8"))
        rf = json.loads(RF_APPLICATION.read_text(encoding="utf-8"))
        require(ground.get("decision") == "ACCEPT_GROUND_DOMAIN_ROUTING_SUBGATE" and
                ground.get("status") ==
                "APPLIED_ACCEPTED_GROUND_DOMAIN_SUBGATE_ROUTING_ENGINEERING_CONTINUES" and
                ground.get("applied", {}).get("exact_candidate_byte_identity") is True and
                signal.get("decision") == "ACCEPT_SIGNAL_HARD_NETS_ROUTING_SUBGATE" and
                signal.get("applied", {}).get("exact_candidate_byte_identity") is True and
                octospi.get("decision") ==
                "ACCEPT_LIMITED_OCTOSPI_R8_PLACEMENT_ECO_AND_ROUTING_SUBGATE" and
                octospi.get("applied", {}).get("exact_candidate_byte_identity") is True and
                sha256(SIGNAL_CANDIDATE) ==
                octospi.get("historical_baseline", {}).get("board_sha256") and
                rf.get("decision") == "ACCEPT_RF_P0_ROUTING_SUBGATE" and
                rf.get("historical_baseline", {}).get("board_sha256") ==
                sha256(OCTOSPI_CANDIDATE) and
                rf.get("applied", {}).get("exact_candidate_byte_identity") is True and
                sha256(RF_REMEDIATION_COMPOSED) ==
                "f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9" and
                sha256(BOARD) == sha256(USB_CELL_MODEM_CANDIDATE) and
                BOARD.read_bytes() == USB_CELL_MODEM_CANDIDATE.read_bytes() and
                len(getattr(board, "traceItems", [])) == 994 and
                len(getattr(board, "zones", [])) == 8 and
                ground.get("routing_complete") is False and
                ground.get("review_b_complete") is False and
                ground.get("cam_or_manufacturing_release") is False and
                octospi.get("routing_complete") is False and
                octospi.get("review_b_complete") is False and
                octospi.get("cam_or_manufacturing_release") is False and
                rf.get("routing_complete") is False and
                rf.get("review_b_complete") is False and
                rf.get("cam_or_manufacturing_release") is False,
                "PCB-MAIN accepted routing-subgate application or copper inventory drift")
        proposal_id = "PCB-MAIN-RF-P0-001"
    else:
        require(len(getattr(board, "traceItems", [])) == 0 and
                len(getattr(board, "zones", [])) == 0,
                "PCB-MAIN approved placement board unexpectedly contains copper")
    if ECO003_APPLICATION.is_file():
        by_ref = {row["RefDes"]: row for row in rows}
        for ref, expected in ACTIVE_APPROVED_POSES.items():
            actual = (
                float(by_ref[ref]["X_mm"]),
                float(by_ref[ref]["Y_mm"]),
                float(by_ref[ref]["Rotation_deg"]) % 360.0,
            )
            require(all(abs(first - second) < 0.001
                        for first, second in zip(actual, expected)),
                    f"{ref}: approved placement-successor pose drift")
    return len(rows), proposal_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="verify that manifest and native PCB already match generated content")
    args = parser.parse_args()

    original = BOARD.read_text(encoding="utf-8")
    if args.check and (ECO003_APPLICATION.is_file() or ECO002_APPLICATION.is_file()):
        count, proposal_id = verify_approved_frozen_repack(original)
        print(f"PCB-MAIN placement repack: PASS / approved {proposal_id} hashes and board placement match")
        print(f"movable_placements={count} passive_courtyard_margin_mm={PASSIVE_COURTYARD_MARGIN_MM:.2f}")
        print("status=USB_PLACEMENT_SUBGATE_APPLIED / REMAINING_ROUTING_AND_REVIEW_B_PENDING")
        return 0
    board = Board.from_sexpr(sexpr.parse_sexp(original))
    rows = build_plan(board)
    manifest = placement_csv(rows)
    materialized = materialized_board_text(original, rows)
    verify_materialized(materialized, rows)

    if args.check:
        require(PLACEMENT.is_file(), "placement manifest is missing")
        require(PLACEMENT.read_text(encoding="utf-8") == manifest,
                "placement manifest differs from deterministic repack")
        require(original == materialized,
                "native PCB differs from deterministic placement materialization")
        print("PCB-MAIN placement repack: PASS / manifest and board are deterministic")
    else:
        PLACEMENT.write_text(manifest, encoding="utf-8")
        BOARD.write_text(materialized, encoding="utf-8")
        print(f"PCB-MAIN placement manifest: {PLACEMENT.relative_to(ROOT)}")
        print(f"PCB-MAIN placement materialized: {BOARD.relative_to(ROOT)}")
    print(f"movable_placements={len(rows)} passive_courtyard_margin_mm={PASSIVE_COURTYARD_MARGIN_MM:.2f}")
    print("status=PLACEMENT_ENGINEERING_CANDIDATE / ROUTING_AND_REVIEW_B_PENDING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
