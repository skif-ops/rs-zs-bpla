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

from kiutils.items.common import Effects, Font, Justify, Position, Property, TitleBlock
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
STUB_MM = 10.16
ROOT_LABEL_FONT_MM = 0.01
LABEL_FONT_MM = 1.10
PROPERTY_FONT_MM = 1.00


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
            "U3", "L1", "C3", "C4", "C11", "C14", "C15", "C16", "C20",
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
            "U4", "L2", "C5", "C6", "C12", "C17", "C18", "C19", "C21",
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

COMPACT_TITLES = {
    "input": "Input protection + monitor",
    "modem": "3V8 modem rail",
    "digital": "3V3 AON rail",
    "harness": "1V8 + MAIN harness",
}


# Functional pin geometry for the manufacturer-specific devices represented by
# project-local generic bodies.  Coordinates are relative to the instance origin.
SYMBOL_GEOMETRY: dict[str, tuple[tuple[float, float, float, float], dict[str, tuple[float, float, int]]]] = {
    "DioneyaPWR:Conn_01x02": ((-10.16, 5.08, 10.16, -5.08), {
        "1": (-12.70, 2.54, 0), "2": (-12.70, -2.54, 0),
    }),
    "DioneyaPWR:Conn_01x06": ((-15.24, 8.89, 15.24, -8.89), {
        "1": (-17.78, -5.08, 0), "2": (0.0, -11.43, 90),
        "3": (-17.78, 0.0, 0), "4": (17.78, 5.08, 180),
        "5": (17.78, 0.0, 180), "6": (-17.78, 5.08, 0),
    }),
    "DioneyaPWR:Conn_01x08": ((-12.70, 10.16, 12.70, -10.16), {
        "1": (-15.24, 7.62, 0), "2": (-15.24, 2.54, 0),
        "3": (-15.24, -2.54, 0), "4": (0.0, -12.70, 90),
        "5": (15.24, 7.62, 180), "6": (15.24, 2.54, 180),
        "7": (15.24, -2.54, 180), "8": (15.24, -7.62, 180),
    }),
    "DioneyaPWR:Conn_01x10": ((-17.78, 12.70, 17.78, -12.70), {
        "1": (-10.16, -15.24, 90), "2": (0.0, -15.24, 90),
        "3": (20.32, 0.0, 180), "4": (-20.32, -5.08, 0),
        "5": (-20.32, 0.0, 0), "6": (0.0, 15.24, 270),
        "7": (10.16, -15.24, 90), "8": (-20.32, 5.08, 0),
        "9": (20.32, 7.62, 180), "10": (-20.32, 7.62, 0),
    }),
    "DioneyaPWR:Conn_01x09": ((-15.24, 12.70, 15.24, -12.70), {
        "1": (-17.78, 7.62, 0), "2": (7.62, -15.24, 90),
        "3": (17.78, 7.62, 180), "4": (17.78, 2.54, 180),
        "5": (17.78, -2.54, 180), "6": (17.78, -7.62, 180),
        "7": (-17.78, -5.08, 0), "8": (-7.62, -15.24, 90),
        "9": (-17.78, 0.0, 0),
    }),
    "DioneyaPWR:Conn_01x05": ((-12.70, 8.89, 12.70, -8.89), {
        "1": (-15.24, 5.08, 0), "2": (0.0, -11.43, 90),
        "3": (-15.24, 0.0, 0), "4": (15.24, -5.08, 180),
        "5": (15.24, 5.08, 180),
    }),
    "DioneyaPWR:Conn_01x04": ((-25.40, 7.62, 25.40, -7.62), {
        "1": (-27.94, 5.08, 0), "2": (27.94, 5.08, 180),
        "3": (-27.94, -5.08, 0), "4": (27.94, -5.08, 180),
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
    "J1": (55.88, 48.26), "F1": (152.40, 48.26),
    "U1": (251.46, 50.80), "Q1": (350.52, 50.80),
    "D1": (55.88, 96.52), "C1": (152.40, 96.52),
    "C9": (251.46, 96.52), "C10": (350.52, 96.52),
    "RSH1": (68.58, 147.32), "U2": (205.74, 147.32),
    "C2": (304.80, 147.32), "C13": (370.84, 147.32),
    "TP1": (55.88, 198.12), "TP2": (152.40, 198.12),
    "TP3": (251.46, 198.12), "TP8": (350.52, 198.12),
    "TP9": (55.88, 238.76), "TP10": (152.40, 238.76),
    "#FLG01": (251.46, 238.76), "#FLG02": (350.52, 238.76),
    # 3V8 modem rail.
    "U3": (60.96, 50.80), "L1": (157.48, 50.80),
    "C11": (254.00, 50.80), "C4": (350.52, 50.80),
    "R1": (60.96, 99.06), "R2": (157.48, 99.06),
    "C3": (254.00, 99.06), "C14": (350.52, 99.06),
    "C15": (60.96, 147.32), "C16": (157.48, 147.32),
    "R3": (254.00, 147.32), "R4": (350.52, 147.32),
    "R5": (60.96, 195.58), "R6": (157.48, 195.58),
    "R15": (254.00, 195.58), "TP4": (350.52, 195.58),
    "TP5": (60.96, 238.76), "C20": (157.48, 238.76),
    # 3V3 digital rail.
    "U4": (60.96, 50.80), "L2": (157.48, 50.80),
    "C12": (254.00, 50.80), "C6": (350.52, 50.80),
    "R10": (60.96, 99.06), "C5": (157.48, 99.06),
    "C17": (254.00, 99.06), "C18": (350.52, 99.06),
    "C19": (60.96, 147.32), "R7": (157.48, 147.32),
    "R8": (254.00, 147.32), "R9": (350.52, 147.32),
    "R12": (60.96, 195.58), "R13": (157.48, 195.58),
    "R14": (254.00, 195.58), "TP6": (350.52, 195.58),
    "#FLG03": (60.96, 238.76), "C21": (157.48, 238.76),
    # 1V8 rail, net ties and MAIN harness connector.
    "U5": (76.20, 60.96), "C7": (208.28, 60.96), "C8": (340.36, 60.96),
    "R11": (76.20, 129.54), "NT1": (208.28, 129.54),
    "NT2": (340.36, 129.54), "NT3": (76.20, 198.12),
    "J2": (208.28, 198.12), "TP7": (340.36, 198.12),
}


# Rotate vertical two-terminal glyphs so their wire stubs and net names read
# left-to-right.  This is a schematic presentation choice only; pin numbers and
# their authoritative net assignment are unchanged.
HORIZONTAL_SYMBOLS = {"Device:C", "Device:Fuse", "Device:L", "Device:R"}
HEADER_PROPERTY_SYMBOLS = {
    "DioneyaPWR:Conn_01x05",
    "DioneyaPWR:Conn_01x06",
    "DioneyaPWR:Conn_01x08",
    "DioneyaPWR:Conn_01x09",
}
SIDE_PROPERTY_SYMBOLS = {"DioneyaPWR:Conn_01x10"}


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


def set_position(instance, x: float, y: float, angle: int = 0) -> None:
    dx = float(x) - float(instance.position.X)
    dy = float(y) - float(instance.position.Y)
    instance.position = Position(X=x, Y=y, angle=angle)
    for item in instance.properties:
        item.position = Position(
            X=round(float(item.position.X) + dx, 4),
            Y=round(float(item.position.Y) + dy, 4),
            angle=item.position.angle or 0,
        )


def layout_properties(instance, symbol) -> None:
    """Keep visible reference/value fields clear of pins and their net stubs."""
    pins = selected_pins(symbol, instance.unit or 1).values()
    vertical_extent = max((abs(float(pin.position.Y)) for pin in pins), default=2.54)
    if int(instance.position.angle or 0) % 180:
        # Rotated passives have horizontal pins; only the glyph height matters.
        clearance = 7.62
    else:
        clearance = vertical_extent + 5.08
    x = float(instance.position.X)
    y = float(instance.position.Y)
    # KiCad composes field rotation with the parent symbol rotation.  Counter-
    # rotate fields so long MPN/value strings remain horizontal even when a
    # passive glyph is rotated 90 degrees for left-to-right connectivity.
    property_angle = (-int(instance.position.angle or 0)) % 360
    for item in instance.properties:
        if instance.libId in HEADER_PROPERTY_SYMBOLS and item.key == "Reference":
            item.position = Position(
                X=x, Y=round(y - clearance - 3.05, 4), angle=property_angle)
        elif instance.libId in HEADER_PROPERTY_SYMBOLS and item.key == "Value":
            item.position = Position(
                X=x, Y=round(y - clearance, 4), angle=property_angle)
        elif instance.libId in SIDE_PROPERTY_SYMBOLS and item.key == "Reference":
            item.position = Position(
                X=round(x + 33.02, 4), Y=round(y + 15.24, 4), angle=property_angle)
        elif instance.libId in SIDE_PROPERTY_SYMBOLS and item.key == "Value":
            item.position = Position(
                X=round(x + 33.02, 4), Y=round(y + 18.29, 4), angle=property_angle)
        elif item.key == "Reference":
            item.position = Position(
                X=x, Y=round(y - clearance, 4), angle=property_angle)
        elif item.key == "Value":
            item.position = Position(
                X=x, Y=round(y + clearance, 4), angle=property_angle)
        if item.key in {"Reference", "Value"}:
            item.effects.font = Font(height=PROPERTY_FONT_MM, width=PROPERTY_FONT_MM)
            item.effects.hide = False
        else:
            # Footprint and datasheet strings remain in the native design, but
            # do not belong on the human hierarchy drawing.
            item.effects.hide = True


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
    font_size: float = LABEL_FONT_MM,
) -> LocalLabel:
    return LocalLabel(
        text=net,
        position=Position(X=at[0], Y=at[1], angle=angle),
        effects=Effects(
            font=Font(height=font_size, width=font_size),
            justify=Justify(vertically="bottom"),
            hide=hidden,
        ),
        uuid=stable_uuid(f"label:{token}"),
    )


def hierarchy_label(net: str, at: tuple[float, float], angle: int, token: str) -> HierarchicalLabel:
    return HierarchicalLabel(
        text=net,
        shape="passive",
        position=Position(X=at[0], Y=at[1], angle=angle),
        effects=Effects(
            font=Font(height=LABEL_FONT_MM, width=LABEL_FONT_MM),
            justify=Justify(vertically="bottom"),
        ),
        uuid=stable_uuid(f"hier-label:{token}"),
    )


def title_block(title: str, page_note: str) -> TitleBlock:
    return TitleBlock(
        title=title,
        date="2026-09-17",
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
        COMPACT_TITLES[spec.key],
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
        target = SCHEMATIC_POSITIONS[ref]
        angle = 90 if instance.libId in HORIZONTAL_SYMBOLS else 0
        set_position(instance, *target, angle=angle)
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
            pin_angle = (int(pin.position.angle or 0) + angle) % 360
            end, label_angle = stub_endpoint(pin_at, pin_angle)
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
                effects=Effects(
                    font=Font(height=0.9, width=0.9),
                    justify=Justify(vertically="bottom"),
                ),
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
        "PCB-PWR system overview",
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
            # KiCad 9's PDF plotter emits local-label text even when its `hide`
            # flag is set.  Keep the label as the machine-auditable electrical
            # net authority, while making that duplicate text sub-print.  The
            # visible 0.9 mm sheet-pin name remains the human-facing net name.
            root.labels.append(local_label(
                str(pin.name), end, label_angle, f"root:{spec.key}:{pin.name}",
                hidden=True, font_size=ROOT_LABEL_FONT_MM,
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
