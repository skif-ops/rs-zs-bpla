#!/usr/bin/env python3
"""Convert the reviewed flat PCB-MAIN capture into nine readable sheets.

The signed Review-A pin/net authority remains unchanged.  This deterministic
post-processor only changes schematic presentation: every connected pin receives
one visible wire stub, functional blocks move to bounded A2 child sheets, and
cross-sheet nets pass through explicit hierarchical pins.  It does not authorize
PCB routing, fabrication, Review B, or manufacture.
"""
from __future__ import annotations

import argparse
import copy
import re
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

from pcb_main_schematic_hierarchy import endpoint, ref_of, selected_pins


NAMESPACE = uuid.UUID("6140d58d-e636-50f1-a28e-2ac08a9bc0a2")
ROOT_UUID = str(uuid.uuid5(NAMESPACE, "PCB-MAIN:root:RevA"))
PROJECT = "PCB-MAIN"
PAGE_SIZE = "A2"
GRID_MM = 2.54
STUB_MM = 6.35
ROOT_LABEL_FONT_MM = 0.01


def ref_range(prefix: str, first: int, last: int) -> set[str]:
    return {f"{prefix}{index}" for index in range(first, last + 1)}


@dataclass(frozen=True)
class SheetSpec:
    key: str
    name: str
    filename: str
    page: str
    refs: frozenset[str]


SHEETS = (
    SheetSpec(
        "power", "Power entry and rail interface", "PCB-MAIN_01_POWER.kicad_sch", "2",
        frozenset({"J_PWR", "C19", "C20", "R103"}),
    ),
    SheetSpec(
        "mcu", "MCU clocks reset and straps", "PCB-MAIN_02_MCU.kicad_sch", "3",
        frozenset({"U1", "X1", "L1"} | ref_range("C", 1, 18) | ref_range("R", 1, 6)),
    ),
    SheetSpec(
        "audio", "PDM audio AAD and microphone harnesses", "PCB-MAIN_03_AUDIO.kicad_sch", "4",
        frozenset(
            {"U7", "U17", "U18"}
            | {f"J_MIC{index}" for index in range(1, 5)}
            | ref_range("C", 27, 32)
            | ref_range("R", 17, 23)
            | ref_range("U", 19, 22)
        ),
    ),
    SheetSpec(
        "gnss", "GNSS timing antenna and supervisor", "PCB-MAIN_04_GNSS.kicad_sch", "5",
        frozenset(
            {"U9", "J9", "L2", "FL1", "U5", "Q4", "D4"}
            | ref_range("C", 60, 65)
            | ref_range("R", 56, 62)
        ),
    ),
    SheetSpec(
        "cellular", "Cellular modem dual SIM and recovery", "PCB-MAIN_05_CELLULAR.kicad_sch", "6",
        frozenset(
            {
                "U8", "U16", "Q1", "Q2", "U13", "U14", "U15", "Q3",
                "J6", "J7", "J8", "TP_CELL_USB", "TP_CELL_DBG", "FB1",
                "U26", "U27", "D1", "D2", "D3", "D10", "C79", "C80",
            }
            | ref_range("C", 33, 59)
            | ref_range("R", 24, 55)
        ),
    ),
    SheetSpec(
        "lora", "LoRa radio control and conducted RF", "PCB-MAIN_06_LORA.kicad_sch", "7",
        frozenset(
            {"U10", "J10", "D5"}
            | ref_range("C", 66, 70)
            | ref_range("R", 63, 73)
        ),
    ),
    SheetSpec(
        "ble", "BLE module reset DFU and SWD", "PCB-MAIN_07_BLE.kicad_sch", "8",
        frozenset(
            {"U11", "TP_BLE_SWD", "U6"}
            | ref_range("C", 71, 73)
            | ref_range("R", 74, 78)
        ),
    ),
    SheetSpec(
        "storage", "Storage sensors microSD and tamper", "PCB-MAIN_08_STORAGE_SENSORS.kicad_sch", "9",
        frozenset(
            {
                "U2", "U3", "U4", "U12", "J12", "J13", "U23", "U24",
                "D9", "D11", "C78", "R99", "R100",
            }
            | ref_range("C", 21, 26)
            | ref_range("C", 74, 76)
            | ref_range("R", 7, 16)
            | ref_range("R", 79, 90)
        ),
    ),
    SheetSpec(
        "connectors", "USB service debug and EOL fixture", "PCB-MAIN_09_CONNECTORS_TEST.kicad_sch", "10",
        frozenset(
            {"J11", "TP_MCU_SWD", "TP_EOL", "C77", "U25", "D6", "D7", "D8"}
            | ref_range("R", 91, 98)
            | ref_range("R", 101, 102)
        ),
    ),
)

REVIEW_TITLES = {
    "power": "Power",
    "mcu": "MCU",
    "audio": "PDM audio",
    "gnss": "GNSS",
    "cellular": "Cellular + dual SIM",
    "lora": "LoRa",
    "ble": "BLE",
    "storage": "Storage + sensors",
    "connectors": "USB + debug",
}


def stable_uuid(token: str) -> str:
    return str(uuid.uuid5(NAMESPACE, token))


def natural(value: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part
                 for part in re.split(r"(\d+)", value))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def snap(value: float) -> float:
    return round(round(value / GRID_MM) * GRID_MM, 4)


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
        require(ref and ref not in result, f"flat PCB-MAIN duplicate/empty reference: {ref!r}")
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
    instance.position = Position(X=x, Y=y, angle=instance.position.angle or 0)


def symbol_half_height(symbol, unit: int = 1) -> float:
    pins = selected_pins(symbol, unit).values()
    return max((abs(float(pin.position.Y)) for pin in pins), default=5.08) + 2.54


def layout_properties(instance, symbol) -> None:
    half_height = symbol_half_height(symbol, instance.unit or 1)
    clearance = half_height + 7.62
    x = float(instance.position.X)
    y = float(instance.position.Y)
    for item in instance.properties:
        if str(item.key) == "Reference":
            item.position = Position(X=x, Y=round(y - clearance, 4), angle=0)
        elif str(item.key) == "Value":
            item.position = Position(X=x, Y=round(y + clearance, 4), angle=0)
        if str(item.key) in {"Reference", "Value"}:
            item.effects.font = Font(height=0.8, width=0.8)
            item.effects.hide = False


def assign_positions(refs: frozenset[str], instances: dict[str, object], libraries: dict[str, object]) -> dict[str, tuple[float, float]]:
    large = [ref for ref in refs if len(selected_pins(
        libraries[instances[ref].libId], instances[ref].unit or 1)) > 2
        or ref.startswith(("J", "TP_"))]
    small = sorted(set(refs) - set(large), key=natural)

    positions: dict[str, tuple[float, float]] = {}
    columns = [60.96, 170.18, 279.40, 388.62, 497.84]
    column_bottom = [30.48] * len(columns)
    for ref in sorted(
        large,
        key=lambda item: (
            -len(selected_pins(libraries[instances[item].libId], instances[item].unit or 1)),
            natural(item),
        ),
    ):
        column = min(range(len(columns)), key=lambda index: column_bottom[index])
        symbol = libraries[instances[ref].libId]
        half = symbol_half_height(symbol, instances[ref].unit or 1) + 10.16
        y = snap(column_bottom[column] + half)
        positions[ref] = (columns[column], y)
        column_bottom[column] = y + half + 5.08

    small_y = snap(max(column_bottom) + 2.54) if large else 45.72
    small_columns = [38.10 + index * 68.58 for index in range(8)]
    row_pitch = 22.86
    for index, ref in enumerate(small):
        positions[ref] = (
            snap(small_columns[index % len(small_columns)]),
            snap(small_y + (index // len(small_columns)) * row_pitch),
        )

    for ref, (_x, y) in positions.items():
        symbol = libraries[instances[ref].libId]
        half = symbol_half_height(symbol, instances[ref].unit or 1) + 10.16
        require(20.32 <= y - half and y + half <= 403.86,
                f"{ref}: hierarchy placement escapes A2 review page at y={y}")
    return positions


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
    raise RuntimeError(f"unsupported PCB-MAIN symbol pin angle {normalized}")


def wire(start: tuple[float, float], end: tuple[float, float], token: str) -> Connection:
    return Connection(
        type="wire",
        points=[Position(X=start[0], Y=start[1]), Position(X=end[0], Y=end[1])],
        uuid=stable_uuid(f"wire:{token}"),
    )


def local_label(net: str, at: tuple[float, float], angle: int, token: str, *,
                hidden: bool = False, font_size: float = 0.75) -> LocalLabel:
    return LocalLabel(
        text=net,
        position=Position(X=at[0], Y=at[1], angle=angle),
        effects=Effects(font=Font(height=font_size, width=font_size), hide=hidden),
        uuid=stable_uuid(f"label:{token}"),
    )


def hierarchy_label(net: str, at: tuple[float, float], angle: int, token: str) -> HierarchicalLabel:
    return HierarchicalLabel(
        text=net,
        shape="passive",
        position=Position(X=at[0], Y=at[1], angle=angle),
        effects=Effects(font=Font(height=0.75, width=0.75)),
        uuid=stable_uuid(f"hier-label:{token}"),
    )


def title_block(title: str, page_note: str) -> TitleBlock:
    return TitleBlock(
        title=title,
        date="2026-09-16",
        revision="A",
        company="Dioneya / ZS-BPLA",
        comments={
            1: "Human-readable hierarchy candidate; exact Review-A pin/net equivalence enforced",
            2: page_note,
            3: "NOT FOR MANUFACTURE - hierarchy review/routing/DRC/DFM/Review B pending",
        },
    )


def make_child(flat: Schematic, spec: SheetSpec, pin_map: dict[str, dict[str, str]],
               nc_pins: set[tuple[str, str]], cross_nets: set[str],
               sheet_uuid: str) -> Schematic:
    child = Schematic.create_new()
    child.version = flat.version
    child.generator = "dioneya-pcb-main-hierarchy"
    child.uuid = stable_uuid(f"file:{spec.filename}")
    child.paper = copy.deepcopy(flat.paper)
    child.paper.paperSize = PAGE_SIZE
    child.paper.portrait = False
    child.titleBlock = title_block(
        f"Dioneya PCB-MAIN Rev.A - {REVIEW_TITLES[spec.key]}",
        f"Functional sheet {spec.page} of {len(SHEETS) + 1}",
    )

    flat_instances = {ref_of(item): item for item in flat.schematicSymbols}
    used_lib_ids = {flat_instances[ref].libId for ref in spec.refs}
    child.libSymbols = [copy.deepcopy(item) for item in flat.libSymbols
                        if item.libId in used_lib_ids]
    libraries = {item.libId: item for item in child.libSymbols}
    positions = assign_positions(spec.refs, flat_instances, libraries)

    primary_cross_pin: dict[str, tuple[str, str]] = {}
    for ref in sorted(spec.refs, key=natural):
        for number, net in sorted(pin_map[ref].items(), key=lambda item: natural(item[0])):
            if net in cross_nets and net not in primary_cross_pin:
                primary_cross_pin[net] = (ref, number)

    for ref in sorted(spec.refs, key=natural):
        instance = copy.deepcopy(flat_instances[ref])
        set_position(instance, *positions[ref])
        instance.uuid = stable_uuid(f"symbol:{ref}")
        instance.pins = {
            number: stable_uuid(f"symbol:{ref}:pin:{number}")
            for number in sorted(instance.pins, key=natural)
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
        text=("Every connected symbol pin has one explicit wire stub. "
              "Only hierarchical labels cross functional-sheet boundaries."),
        position=Position(X=297.0, Y=12.70, angle=0),
        effects=Effects(font=Font(height=1.1, width=1.1)),
        uuid=stable_uuid(f"note:{spec.key}"),
    ))
    return child


def pin_grid_indices(height: float, count: int) -> list[int]:
    units = int(round(height / GRID_MM))
    require(count <= units - 3,
            f"{count} hierarchical pins do not fit on {units - 3} root-sheet grid rows")
    if count == 0:
        return []
    if count == 1:
        return [units // 2]
    result = [
        int(round(2 + index * (units - 4) / (count - 1)))
        for index in range(count)
    ]
    require(len(result) == len(set(result)), "hierarchical pin grid collapsed")
    return result


def make_sheet(spec: SheetSpec, cross_nets: set[str], index: int) -> HierarchicalSheet:
    width, height = 165.10, 106.68
    # KiCad's hierarchy exporter traverses the root drawing by X and then Y.
    # Fill columns top-to-bottom so that exported PDF pages follow 2..10.
    column = index // 3
    row = index % 3
    x = 20.32 + column * 185.42
    y = 35.56 + row * 121.92
    sheet_uuid = stable_uuid(f"sheet:{spec.key}")
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
    # Left and right pins may share a Y row because their endpoints are on
    # opposite edges.  Each side remains strictly monotonic and collision-free.
    left_indices = pin_grid_indices(height, len(left))
    right_indices = pin_grid_indices(height, len(right))
    for side, items, indices in (
        ("left", left, left_indices),
        ("right", right, right_indices),
    ):
        for grid_index, net in zip(indices, items):
            pin_x = x if side == "left" else x + width
            pin_y = round(y + grid_index * GRID_MM, 4)
            angle = 180 if side == "left" else 0
            sheet.pins.append(HierarchicalPin(
                name=net,
                connectionType="passive",
                position=Position(X=pin_x, Y=pin_y, angle=angle),
                effects=Effects(font=Font(height=0.72, width=0.72)),
                uuid=stable_uuid(f"sheet-pin:{spec.key}:{net}"),
            ))
    return sheet


def make_root(flat: Schematic, sheet_nets: dict[str, set[str]]) -> Schematic:
    root = Schematic.create_new()
    root.version = flat.version
    root.generator = "dioneya-pcb-main-hierarchy"
    root.uuid = ROOT_UUID
    root.paper = copy.deepcopy(flat.paper)
    root.paper.paperSize = PAGE_SIZE
    root.paper.portrait = False
    root.titleBlock = title_block(
        "Dioneya PCB-MAIN Rev.A - System overview",
        f"Root sheet 1 of {len(SHEETS) + 1}",
    )
    root.sheetInstances = [HierarchicalSheetInstance(instancePath="/", page="1")]

    for index, spec in enumerate(SHEETS):
        sheet = make_sheet(spec, sheet_nets[spec.key], index)
        root.sheets.append(sheet)
        for pin in sheet.pins:
            pin_at = (round(float(pin.position.X), 4), round(float(pin.position.Y), 4))
            outward = -STUB_MM if int(pin.position.angle or 0) == 180 else STUB_MM
            end = (round(pin_at[0] + outward, 4), pin_at[1])
            label_angle = 180 if outward < 0 else 0
            root.graphicalItems.append(wire(pin_at, end, f"root:{spec.key}:{pin.name}"))
            root.labels.append(local_label(
                str(pin.name), end, label_angle, f"root:{spec.key}:{pin.name}",
                hidden=True, font_size=ROOT_LABEL_FONT_MM,
            ))

    root.texts.append(Text(
        text=("Hierarchy-only engineering candidate. Signed Review-A pin/net authority is retained; "
              "routing, DRC, DFM, Review B and manufacture remain prohibited."),
        position=Position(X=297.0, Y=15.24, angle=0),
        effects=Effects(font=Font(height=1.1, width=1.1)),
        uuid=stable_uuid("note:root"),
    ))
    return root


def materialize(schematic_path: Path) -> tuple[Path, ...]:
    flat = Schematic.from_file(str(schematic_path), encoding="utf-8")
    require(not flat.sheets,
            "PCB-MAIN hierarchy materializer requires the freshly generated flat source")
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
    children: list[Path] = []
    for spec in SHEETS:
        path = schematic_path.parent / spec.filename
        child = make_child(
            flat, spec, pin_map, nc_pins, sheet_nets[spec.key],
            stable_uuid(f"sheet:{spec.key}"),
        )
        child.to_file(str(path), encoding="utf-8")
        children.append(path)
    root.to_file(str(schematic_path), encoding="utf-8")

    reread = Schematic.from_file(str(schematic_path), encoding="utf-8")
    require(len(reread.sheets) == len(SHEETS), "hierarchical root lost child sheets")
    require(not reread.schematicSymbols, "physical symbols leaked onto root overview")
    child_symbol_count = 0
    child_wire_count = 0
    child_hier_count = 0
    for path in children:
        child = Schematic.from_file(str(path), encoding="utf-8")
        child_symbol_count += len(child.schematicSymbols)
        child_wire_count += sum(1 for item in child.graphicalItems
                                if getattr(item, "type", None) == "wire")
        child_hier_count += len(child.hierarchicalLabels)
    connected_pin_count = sum(len(pins) for pins in pin_map.values())
    require(child_symbol_count == len(pin_map), "hierarchical symbol count changed")
    require(child_wire_count == connected_pin_count,
            "not every connected PCB-MAIN pin received one explicit wire")
    require(child_hier_count == sum(len(items) for items in sheet_nets.values()),
            "hierarchical-label participation count changed")

    print(f"PCB-MAIN hierarchy materialized: root + {len(SHEETS)} functional sheets")
    print(f"symbols={child_symbol_count} child_wires={child_wire_count} "
          f"cross_nets={len(cross_nets)} hierarchical_labels={child_hier_count}")
    print("exact pin/net authority retained; routing, Review B and manufacture remain prohibited")
    return (schematic_path, *children)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schematic", type=Path, required=True)
    args = parser.parse_args()
    materialize(args.schematic.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
