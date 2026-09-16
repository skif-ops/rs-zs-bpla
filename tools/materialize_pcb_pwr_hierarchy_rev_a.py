#!/usr/bin/env python3
"""Convert the reviewed flat PCB-PWR capture into a readable four-sheet design.

The earlier capture intentionally put a local label directly on every pin.  That was
machine-auditable, but it was not a reviewable circuit drawing.  This deterministic
post-processor preserves the exact reference/pin/net map, gives the main ICs functional
pin geometry, adds an explicit wire stub for every connected pin, and creates a root
overview plus four bounded functional child sheets.

It is a presentation and hierarchy conversion only.  It neither routes the PCB nor
changes any component, footprint, population state, pin number, or electrical net.
"""
from __future__ import annotations

import argparse
import copy
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from kiutils.items.common import Effects, Font, Position, Property, TitleBlock
from kiutils.items.schitems import (
    Connection,
    HierarchicalLabel,
    HierarchicalPin,
    HierarchicalSheet,
    HierarchicalSheetInstance,
    HierarchicalSheetProjectInstance,
    HierarchicalSheetProjectPath,
    LocalLabel,
    NoConnect,
    SymbolProjectInstance,
    SymbolProjectPath,
    Text,
)
from kiutils.schematic import Schematic

from pcb_pwr_schematic_hierarchy import endpoint, property_value, ref_of, selected_pins


NAMESPACE = uuid.UUID("a8ab3f2c-21cf-41de-8639-8b1e11b6bf09")
ROOT_UUID = str(uuid.uuid5(NAMESPACE, "PCB-PWR:root"))
PROJECT = "PCB-PWR"
PAGE_SIZE = "A3"
GRID_MM = 2.54
STUB_MM = 7.62
PAGE_ORIGIN = (30.48, 38.10)
PAGE_SCALE = 1.5


@dataclass(frozen=True)
class SheetSpec:
    key: str
    name: str
    filename: str
    page: str
    refs: frozenset[str]
    position: tuple[float, float]
    size: tuple[float, float]


SHEETS = (
    SheetSpec(
        "input",
        "Input protection and monitor",
        "PCB-PWR_01_INPUT_PROTECTION.kicad_sch",
        "2",
        frozenset({
            "J1", "F1", "D1", "U1", "Q1", "C1", "C9", "C10", "C13",
            "RSH1", "U2", "C2", "TP1", "TP2", "TP3", "TP8", "TP9",
            "TP10", "#FLG01", "#FLG02",
        }),
        (40.64, 50.80),
        (91.44, 152.40),
    ),
    SheetSpec(
        "modem",
        "3V8 modem rail",
        "PCB-PWR_02_3V8_MODEM.kicad_sch",
        "3",
        frozenset({
            "U3", "L1", "C3", "C4", "C11", "C14", "C15", "C16",
            "R1", "R2", "R3", "R4", "R5", "R6", "R15", "TP4", "TP5",
        }),
        (157.48, 38.10),
        (91.44, 71.12),
    ),
    SheetSpec(
        "digital",
        "3V3 digital rail",
        "PCB-PWR_03_3V3_DIGITAL.kicad_sch",
        "4",
        frozenset({
            "U4", "L2", "C5", "C6", "C12", "C17", "C18", "C19",
            "R7", "R8", "R9", "R10", "R12", "R13", "R14", "TP6",
            "#FLG03",
        }),
        (157.48, 132.08),
        (91.44, 71.12),
    ),
    SheetSpec(
        "harness",
        "1V8 auxiliary and MAIN harness",
        "PCB-PWR_04_AUX_HARNESS.kicad_sch",
        "5",
        frozenset({"U5", "C7", "C8", "R11", "NT1", "NT2", "NT3", "J2", "TP7"}),
        (274.32, 50.80),
        (96.52, 152.40),
    ),
)


# Functional pin geometry for the manufacturer-specific devices represented by
# project-local generic bodies.  Coordinates are relative to the instance origin.
SYMBOL_GEOMETRY: dict[str, tuple[tuple[float, float, float, float], dict[str, tuple[float, float, int]]]] = {
    "DioneyaPWR:Conn_01x06": ((-5.08, 7.62, 5.08, -7.62), {
        "1": (-7.62, -5.08, 0), "2": (0.0, -10.16, 90),
        "3": (-7.62, 0.0, 0), "4": (7.62, 5.08, 180),
        "5": (7.62, 0.0, 180), "6": (-7.62, 5.08, 0),
    }),
    "DioneyaPWR:Conn_01x08": ((-5.08, 8.89, 5.08, -8.89), {
        "1": (-7.62, 6.35, 0), "2": (-7.62, 3.81, 0),
        "3": (-7.62, 1.27, 0), "4": (0.0, -11.43, 90),
        "5": (7.62, 6.35, 180), "6": (7.62, 3.81, 180),
        "7": (7.62, 1.27, 180), "8": (7.62, -1.27, 180),
    }),
    "DioneyaPWR:Conn_01x10": ((-6.35, 10.16, 6.35, -10.16), {
        "1": (-2.54, -12.70, 90), "2": (2.54, -12.70, 90),
        "3": (8.89, 0.0, 180), "4": (-8.89, -2.54, 0),
        "5": (-8.89, 0.0, 0), "6": (0.0, 12.70, 270),
        "7": (0.0, -12.70, 90), "8": (-8.89, 2.54, 0),
        "9": (8.89, 6.35, 180), "10": (-8.89, 6.35, 0),
    }),
    "DioneyaPWR:Conn_01x09": ((-6.35, 10.16, 6.35, -10.16), {
        "1": (-8.89, 6.35, 0), "2": (0.0, -12.70, 90),
        "3": (8.89, 6.35, 180), "4": (8.89, 3.81, 180),
        "5": (8.89, 0.0, 180), "6": (8.89, -5.08, 180),
        "7": (-8.89, -2.54, 0), "8": (-2.54, -12.70, 90),
        "9": (-8.89, 0.0, 0),
    }),
    "DioneyaPWR:Conn_01x05": ((-5.08, 7.62, 5.08, -7.62), {
        "1": (-7.62, 5.08, 0), "2": (0.0, -10.16, 90),
        "3": (-7.62, 0.0, 0), "4": (7.62, -2.54, 180),
        "5": (7.62, 5.08, 180),
    }),
    "DioneyaPWR:Conn_01x04": ((-10.16, 6.35, 10.16, -6.35), {
        "1": (-12.70, 2.54, 0), "2": (12.70, 2.54, 180),
        "3": (-12.70, -2.54, 0), "4": (12.70, -2.54, 180),
    }),
}

HIDE_PIN_NAMES = {
    # J2 pin names are identical to the visible authoritative net labels.  Hiding
    # the duplicate names retains pin numbers and removes twelve text collisions.
    "DioneyaPWR:Conn_01x12",
}


# Page-local placement only.  These coordinates do not affect PCB placement; they
# separate functional groups and prevent wire/label collisions in the review drawing.
SCHEMATIC_POSITIONS: dict[str, tuple[float, float]] = {
    # Input protection and current monitor.
    "J1": (25.40, 40.64), "F1": (45.72, 40.64), "D1": (55.88, 71.12),
    "U1": (83.82, 43.18), "C1": (83.82, 76.20), "C9": (55.88, 91.44),
    "Q1": (119.38, 43.18), "C10": (119.38, 76.20),
    "RSH1": (154.94, 43.18), "U2": (154.94, 96.52),
    "C2": (185.42, 96.52), "C13": (195.58, 50.80),
    "TP1": (226.06, 35.56), "TP2": (226.06, 50.80), "TP3": (226.06, 66.04),
    "TP8": (226.06, 111.76), "TP9": (226.06, 127.00), "TP10": (226.06, 142.24),
    "#FLG01": (30.48, 154.94), "#FLG02": (50.80, 154.94),
    # 3V8 modem rail.
    "U3": (68.58, 76.20), "L1": (101.60, 68.58), "C11": (38.10, 58.42),
    "C4": (101.60, 45.72), "R1": (132.08, 50.80), "R2": (132.08, 81.28),
    "C3": (149.86, 104.14), "C14": (165.10, 104.14),
    "C15": (180.34, 104.14), "C16": (195.58, 104.14),
    "R3": (48.26, 129.54), "R4": (68.58, 129.54), "R5": (88.90, 129.54),
    "R6": (35.56, 101.60), "R15": (111.76, 129.54),
    "TP4": (226.06, 58.42), "TP5": (226.06, 76.20),
    # 3V3 digital rail.
    "U4": (68.58, 76.20), "L2": (101.60, 68.58), "C12": (38.10, 58.42),
    "C6": (101.60, 45.72), "R10": (132.08, 50.80),
    "C5": (149.86, 104.14), "C17": (165.10, 104.14),
    "C18": (180.34, 104.14), "C19": (195.58, 104.14),
    "R7": (48.26, 129.54), "R8": (68.58, 129.54), "R9": (88.90, 129.54),
    "R12": (149.86, 129.54), "R13": (170.18, 129.54), "R14": (190.50, 129.54),
    "TP6": (226.06, 66.04), "#FLG03": (30.48, 154.94),
    # 1V8 rail, net ties and MAIN harness connector.
    "U5": (66.04, 55.88), "C7": (45.72, 86.36), "C8": (86.36, 86.36),
    "R11": (66.04, 111.76), "NT1": (114.30, 55.88),
    "NT2": (139.70, 55.88), "NT3": (165.10, 55.88),
    "J2": (205.74, 96.52), "TP7": (231.14, 50.80),
}


def stable_uuid(token: str) -> str:
    return str(uuid.uuid5(NAMESPACE, token))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def at_tuple(position: Position) -> tuple[float, float]:
    return (round(float(position.X), 4), round(float(position.Y), 4))


def flat_pin_map(flat: Schematic) -> tuple[dict[str, dict[str, str]], set[tuple[str, str]]]:
    labels: dict[tuple[float, float], set[str]] = defaultdict(set)
    for label in flat.labels:
        labels[at_tuple(label.position)].add(str(label.text))
    no_connects = {at_tuple(item.position) for item in flat.noConnects}
    libraries = {item.libId: item for item in flat.libSymbols}
    result: dict[str, dict[str, str]] = {}
    nc_pins: set[tuple[str, str]] = set()
    for instance in flat.schematicSymbols:
        ref = ref_of(instance)
        require(ref and ref not in result, f"flat PCB-PWR duplicate/empty reference: {ref!r}")
        symbol = libraries[instance.libId]
        result[ref] = {}
        for number in selected_pins(symbol, instance.unit or 1):
            pin_at = endpoint(instance, symbol, number)
            found = labels.get(pin_at, set())
            if pin_at in no_connects:
                require(not found, f"{ref}.{number}: NC pin also has a flat net label")
                nc_pins.add((ref, number))
            else:
                require(len(found) == 1,
                        f"{ref}.{number}: expected one flat net label, got {sorted(found)}")
                result[ref][number] = next(iter(found))
    return result, nc_pins


def set_position(instance, x: float, y: float) -> None:
    dx = float(x) - float(instance.position.X)
    dy = float(y) - float(instance.position.Y)
    instance.position = Position(X=x, Y=y, angle=instance.position.angle or 0)
    for item in instance.properties:
        item.position = Position(
            X=round(float(item.position.X) + dx, 4),
            Y=round(float(item.position.Y) + dy, 4),
            angle=item.position.angle or 0,
        )


def review_position(position: tuple[float, float]) -> tuple[float, float]:
    """Expand the former A4 placement onto an A3 review grid."""
    x, y = position
    return (
        round(PAGE_ORIGIN[0] + (x - 25.40) * PAGE_SCALE, 4),
        round(PAGE_ORIGIN[1] + (y - 35.56) * PAGE_SCALE, 4),
    )


def layout_properties(instance, symbol) -> None:
    """Keep visible reference/value fields clear of pins and their net stubs."""
    pins = selected_pins(symbol, instance.unit or 1).values()
    vertical_extent = max((abs(float(pin.position.Y)) for pin in pins), default=2.54)
    clearance = vertical_extent + STUB_MM + 2.54
    x = float(instance.position.X)
    y = float(instance.position.Y)
    for item in instance.properties:
        if item.key == "Reference":
            item.position = Position(X=x, Y=round(y - clearance, 4), angle=0)
        elif item.key == "Value":
            item.position = Position(X=x, Y=round(y + clearance, 4), angle=0)
        if item.key in {"Reference", "Value"}:
            item.effects.font = Font(height=0.85, width=0.85)
            item.effects.hide = False


def reshape_library_symbol(symbol) -> None:
    if symbol.libId in HIDE_PIN_NAMES:
        symbol.pinNamesHide = True
    geometry = SYMBOL_GEOMETRY.get(symbol.libId)
    if geometry is None:
        return
    body, pin_geometry = geometry
    pins = selected_pins(symbol)
    require(set(pins) == set(pin_geometry), f"{symbol.libId}: geometry pin set drift")
    for number, (x, y, angle) in pin_geometry.items():
        pins[number].position = Position(X=x, Y=y, angle=angle)
        pins[number].length = 2.54

    active_units = [item for item in symbol.units
                    if item.unitId in (None, 0, 1) and item.styleId in (None, 1)]
    require(len(active_units) == 1, f"{symbol.libId}: expected one active graphics unit")
    unit = active_units[0]
    rectangles = [item for item in unit.graphicItems if item.__class__.__name__ == "SyRect"]
    require(rectangles, f"{symbol.libId}: source body rectangle missing")
    rectangle = rectangles[0]
    rectangle.start = Position(X=body[0], Y=body[1])
    rectangle.end = Position(X=body[2], Y=body[3])
    unit.graphicItems = [rectangle]


def stub_endpoint(pin_at: tuple[float, float], angle: int | float | None) -> tuple[tuple[float, float], int]:
    normalized = int(angle or 0) % 360
    x, y = pin_at
    if normalized == 0:
        return ((round(x - STUB_MM, 4), y), 180)
    if normalized == 180:
        return ((round(x + STUB_MM, 4), y), 0)
    if normalized == 90:
        return ((x, round(y + STUB_MM, 4)), 90)
    if normalized == 270:
        return ((x, round(y - STUB_MM, 4)), 270)
    raise RuntimeError(f"unsupported PCB-PWR symbol pin angle {normalized}")


def wire(start: tuple[float, float], end: tuple[float, float], token: str) -> Connection:
    return Connection(
        type="wire",
        points=[Position(X=start[0], Y=start[1]), Position(X=end[0], Y=end[1])],
        uuid=stable_uuid(f"wire:{token}"),
    )


def local_label(
    net: str,
    at: tuple[float, float],
    angle: int,
    token: str,
    *,
    hidden: bool = False,
) -> LocalLabel:
    return LocalLabel(
        text=net,
        position=Position(X=at[0], Y=at[1], angle=angle),
        effects=Effects(font=Font(height=0.9, width=0.9), hide=hidden),
        uuid=stable_uuid(f"label:{token}"),
    )


def hierarchy_label(net: str, at: tuple[float, float], angle: int, token: str) -> HierarchicalLabel:
    return HierarchicalLabel(
        text=net,
        shape="passive",
        position=Position(X=at[0], Y=at[1], angle=angle),
        effects=Effects(font=Font(height=0.9, width=0.9)),
        uuid=stable_uuid(f"hier-label:{token}"),
    )


def title_block(title: str, page_note: str) -> TitleBlock:
    return TitleBlock(
        title=title,
        date="2026-09-16",
        revision="A",
        company="Dioneya / ZS-BPLA",
        comments={
            1: "Human-readable hierarchy; exact pin/net equivalence enforced",
            2: page_note,
            3: "NOT FOR MANUFACTURE - routing/DRC/DFM/Review B pending",
        },
    )


def make_child(
    flat: Schematic,
    spec: SheetSpec,
    pin_map: dict[str, dict[str, str]],
    nc_pins: set[tuple[str, str]],
    cross_nets: set[str],
    sheet_uuid: str,
) -> Schematic:
    child = Schematic.create_new()
    child.version = flat.version
    child.generator = "dioneya-pcb-pwr-hierarchy"
    child.uuid = stable_uuid(f"file:{spec.filename}")
    child.paper = copy.deepcopy(flat.paper)
    child.paper.paperSize = PAGE_SIZE
    child.paper.portrait = False
    child.titleBlock = title_block(
        f"Dioneya EVT-PRE-20 PCB-PWR Rev.A - {spec.name}",
        f"Functional sheet {spec.page} of 5",
    )

    flat_instances = {ref_of(item): item for item in flat.schematicSymbols}
    used_lib_ids = {flat_instances[ref].libId for ref in spec.refs}
    child.libSymbols = [copy.deepcopy(item) for item in flat.libSymbols
                        if item.libId in used_lib_ids]
    for symbol in child.libSymbols:
        reshape_library_symbol(symbol)
    libraries = {item.libId: item for item in child.libSymbols}

    primary_cross_pin: dict[str, tuple[str, str]] = {}
    for ref in sorted(spec.refs):
        for number, net in sorted(pin_map[ref].items(), key=lambda item: (len(item[0]), item[0])):
            if net in cross_nets and net not in primary_cross_pin:
                primary_cross_pin[net] = (ref, number)

    for ref in sorted(spec.refs):
        instance = copy.deepcopy(flat_instances[ref])
        target = review_position(SCHEMATIC_POSITIONS[ref])
        set_position(instance, *target)
        instance.uuid = stable_uuid(f"symbol:{ref}")
        instance.pins = {
            number: stable_uuid(f"symbol:{ref}:pin:{number}")
            for number in sorted(instance.pins, key=lambda item: (len(item), item))
        }
        instance.instances = [SymbolProjectInstance(
            name=PROJECT,
            paths=[SymbolProjectPath(
                sheetInstancePath=f"/{ROOT_UUID}/{sheet_uuid}",
                reference=ref,
                unit=instance.unit or 1,
            )],
        )]
        child.schematicSymbols.append(instance)

        symbol = libraries[instance.libId]
        layout_properties(instance, symbol)
        for number, pin in selected_pins(symbol, instance.unit or 1).items():
            pin_at = endpoint(instance, symbol, number)
            if (ref, number) in nc_pins:
                child.noConnects.append(NoConnect(
                    position=Position(X=pin_at[0], Y=pin_at[1]),
                    uuid=stable_uuid(f"nc:{ref}:{number}"),
                ))
                continue
            net = pin_map[ref][number]
            end, label_angle = stub_endpoint(pin_at, pin.position.angle)
            child.graphicalItems.append(wire(pin_at, end, f"{ref}:{number}"))
            token = f"{ref}:{number}:{net}"
            if primary_cross_pin.get(net) == (ref, number):
                child.hierarchicalLabels.append(hierarchy_label(net, end, label_angle, token))
            else:
                child.labels.append(local_label(net, end, label_angle, token))

    child.texts.append(Text(
        text=("Explicit wire stubs expose every reviewed pin/net connection. "
              "Hierarchical labels are the only cross-sheet connections."),
        position=Position(X=210.0, Y=20.32, angle=0),
        effects=Effects(font=Font(height=1.2, width=1.2)),
        uuid=stable_uuid(f"note:{spec.key}"),
    ))
    return child


def pin_grid_indices(
    height: float,
    count: int,
    side: str,
    avoid: set[int] | None = None,
) -> list[int]:
    units = int(round(height / GRID_MM))
    shift = 0 if side == "left" else max(1, units // 20)
    unavailable = set(avoid or ())
    result = []
    for index in range(count):
        grid_index = int(round((index + 1) * units / (count + 1))) + shift
        grid_index = min(grid_index, units - 2)
        while grid_index in unavailable or grid_index in result:
            grid_index += 1
            require(grid_index <= units - 2,
                    "hierarchical pin grid cannot avoid an opposite-side Y collision")
        require(grid_index > 1, "hierarchical pin escaped the sheet review area")
        result.append(grid_index)
    require(len(result) == len(set(result)), "hierarchical pin grid collapsed")
    return result


def make_sheet(spec: SheetSpec, cross_nets: set[str], sheet_uuid: str) -> HierarchicalSheet:
    x, y = spec.position
    width, height = spec.size
    sheet = HierarchicalSheet(
        position=Position(X=x, Y=y),
        width=width,
        height=height,
        uuid=sheet_uuid,
        sheetName=Property(
            key="Sheet name", value=spec.name, id=0,
            position=Position(X=x, Y=y - 1.27, angle=0), effects=Effects(),
        ),
        fileName=Property(
            key="Sheet file", value=spec.filename, id=1,
            position=Position(X=x, Y=y + height + 1.27, angle=0), effects=Effects(),
        ),
        instances=[HierarchicalSheetProjectInstance(
            name=PROJECT,
            paths=[HierarchicalSheetProjectPath(
                sheetInstancePath=f"/{ROOT_UUID}/{sheet_uuid}",
                page=spec.page,
            )],
        )],
    )

    names = sorted(cross_nets)
    left = names[::2]
    right = names[1::2]
    left_indices = pin_grid_indices(height, len(left), "left")
    right_indices = pin_grid_indices(height, len(right), "right", set(left_indices))
    for side, items in (("left", left), ("right", right)):
        grid_indices = left_indices if side == "left" else right_indices
        for grid_index, net in zip(grid_indices, items):
            pin_x = x if side == "left" else x + width
            pin_y = round(y + grid_index * GRID_MM, 4)
            # KiCad sheet-pin orientation points into the sheet: 180 degrees on
            # the left edge and 0 degrees on the right edge.  Reversing these
            # angles makes KiCad relocate the electrical endpoint to the
            # opposite edge even though the serialized coordinate is unchanged.
            angle = 180 if side == "left" else 0
            sheet.pins.append(HierarchicalPin(
                name=net,
                connectionType="passive",
                position=Position(X=pin_x, Y=pin_y, angle=angle),
                effects=Effects(font=Font(height=0.9, width=0.9)),
                uuid=stable_uuid(f"sheet-pin:{spec.key}:{net}"),
            ))
    return sheet


def make_root(flat: Schematic, sheet_nets: dict[str, set[str]]) -> Schematic:
    root = Schematic.create_new()
    root.version = flat.version
    root.generator = "dioneya-pcb-pwr-hierarchy"
    root.uuid = ROOT_UUID
    root.paper = copy.deepcopy(flat.paper)
    root.paper.paperSize = PAGE_SIZE
    root.paper.portrait = False
    root.titleBlock = title_block(
        "Dioneya EVT-PRE-20 PCB-PWR Rev.A - System overview",
        "Root sheet 1 of 5",
    )
    root.sheetInstances = [HierarchicalSheetInstance(instancePath="/", page="1")]

    for spec in SHEETS:
        sheet_uuid = stable_uuid(f"sheet:{spec.key}")
        sheet = make_sheet(spec, sheet_nets[spec.key], sheet_uuid)
        root.sheets.append(sheet)
        for pin in sheet.pins:
            pin_at = (round(pin.position.X, 4), round(pin.position.Y, 4))
            outward = -STUB_MM if int(pin.position.angle or 0) == 180 else STUB_MM
            end = (round(pin_at[0] + outward, 4), pin_at[1])
            label_angle = 180 if outward < 0 else 0
            root.graphicalItems.append(wire(pin_at, end, f"root:{spec.key}:{pin.name}"))
            root.labels.append(local_label(
                str(pin.name), end, label_angle, f"root:{spec.key}:{pin.name}", hidden=True
            ))

    root.texts.append(Text(
        text=("Functional hierarchy for independent electrical review. "
              "PCB routing, DIM-003, stackup/copper, DRC and Review B remain open."),
        position=Position(X=210.0, Y=20.32, angle=0),
        effects=Effects(font=Font(height=1.2, width=1.2)),
        uuid=stable_uuid("note:root"),
    ))
    return root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schematic", type=Path, required=True)
    args = parser.parse_args()

    flat = Schematic.from_file(str(args.schematic), encoding="utf-8")
    require(not flat.sheets, "hierarchy materializer requires the freshly generated flat source")
    pin_map, nc_pins = flat_pin_map(flat)

    allocation: dict[str, str] = {}
    for spec in SHEETS:
        for ref in spec.refs:
            require(ref not in allocation, f"duplicate hierarchy allocation for {ref}")
            allocation[ref] = spec.key
    require(set(allocation) == set(pin_map),
            f"hierarchy ref allocation drift: missing={sorted(set(pin_map)-set(allocation))} "
            f"extra={sorted(set(allocation)-set(pin_map))}")

    net_sheets: dict[str, set[str]] = defaultdict(set)
    for ref, pins in pin_map.items():
        for net in pins.values():
            net_sheets[net].add(allocation[ref])
    cross_nets = {net for net, sheets in net_sheets.items() if len(sheets) > 1}
    sheet_nets = {
        spec.key: {net for net in cross_nets if spec.key in net_sheets[net]}
        for spec in SHEETS
    }

    root = make_root(flat, sheet_nets)
    for spec in SHEETS:
        child = make_child(
            flat,
            spec,
            pin_map,
            nc_pins,
            sheet_nets[spec.key],
            stable_uuid(f"sheet:{spec.key}"),
        )
        child.to_file(str(args.schematic.parent / spec.filename), encoding="utf-8")
    root.to_file(str(args.schematic), encoding="utf-8")

    # Pure-format round trip.  Native KiCad ERC/PDF is a separate required CI gate.
    reread = Schematic.from_file(str(args.schematic), encoding="utf-8")
    require(len(reread.sheets) == 4, "hierarchical root lost child sheets on round trip")
    require(len(reread.schematicSymbols) == 0, "physical symbols leaked onto root overview")
    child_symbol_count = 0
    child_wire_count = 0
    child_hier_count = 0
    for spec in SHEETS:
        child = Schematic.from_file(str(args.schematic.parent / spec.filename), encoding="utf-8")
        child_symbol_count += len(child.schematicSymbols)
        child_wire_count += sum(1 for item in child.graphicalItems if item.type == "wire")
        child_hier_count += len(child.hierarchicalLabels)
    require(child_symbol_count == len(pin_map), "hierarchical symbol count changed")
    require(child_wire_count == sum(len(pins) for pins in pin_map.values()),
            "not every connected/NC-aware pin received the expected wire accounting")

    print(f"PCB-PWR hierarchy materialized: root + {len(SHEETS)} functional sheets")
    print(f"symbols={child_symbol_count} wires={child_wire_count} cross_nets={len(cross_nets)} "
          f"hierarchical_labels={child_hier_count}")
    print("electrical intent unchanged; native KiCad ERC/PDF and human hierarchy review remain required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
