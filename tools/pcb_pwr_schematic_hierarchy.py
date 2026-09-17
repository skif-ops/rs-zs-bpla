#!/usr/bin/env python3
"""Read PCB-PWR flat or hierarchical KiCad schematics with resolved pin nets.

The production audits must not infer connectivity from a label placed directly on a
pin.  This helper follows explicit wire segments and all KiCad label kinds on each
sheet, while keeping the coordinate spaces of child sheets separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kiutils.schematic import Schematic


Point = tuple[float, float]


def point(x: float, y: float) -> Point:
    return (round(float(x), 4), round(float(y), 4))


def ref_of(instance) -> str:
    return next((item.value for item in instance.properties if item.key == "Reference"), "")


def property_value(instance, key: str) -> str:
    return next((item.value for item in instance.properties if item.key == key), "")


def selected_pins(symbol, unit: int = 1) -> dict[str, object]:
    found: dict[str, object] = {}

    def visit(node, active: bool) -> None:
        node_active = active
        if node is not symbol:
            node_active = (
                active
                and node.unitId in (None, 0, unit)
                and node.styleId in (None, 1)
            )
        if node_active:
            for pin in node.pins:
                found[str(pin.number)] = pin
        for child in node.units:
            visit(child, node_active)

    visit(symbol, True)
    return found


def endpoint(instance, symbol, pin_number: str) -> Point:
    pin = selected_pins(symbol, instance.unit or 1)[str(pin_number)]
    return point(instance.position.X + pin.position.X,
                 instance.position.Y - pin.position.Y)


@dataclass(frozen=True)
class SheetDocument:
    path: Path
    schematic: Schematic
    sheet_uuid: str | None
    sheet_name: str


@dataclass(frozen=True)
class SymbolRecord:
    document: SheetDocument
    instance: object
    symbol: object


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[Point, Point] = {}

    def add(self, item: Point) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: Point) -> Point:
        self.add(item)
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: Point, right: Point) -> None:
        a = self.find(left)
        b = self.find(right)
        if a != b:
            self.parent[b] = a


class SheetConnectivity:
    def __init__(self, document: SheetDocument) -> None:
        self.document = document
        self._uf = _UnionFind()
        self._labels: dict[Point, set[str]] = {}
        self._nc = {
            point(item.position.X, item.position.Y)
            for item in document.schematic.noConnects
        }

        for connection in document.schematic.graphicalItems:
            if getattr(connection, "type", None) != "wire":
                continue
            points = [point(item.X, item.Y) for item in connection.points]
            for item in points:
                self._uf.add(item)
            for left, right in zip(points, points[1:]):
                self._uf.union(left, right)

        label_sets = (
            document.schematic.labels,
            document.schematic.hierarchicalLabels,
            document.schematic.globalLabels,
        )
        for labels in label_sets:
            for label in labels:
                at = point(label.position.X, label.position.Y)
                self._uf.add(at)
                self._labels.setdefault(at, set()).add(str(label.text))

    def nets_at(self, at: Point) -> set[str]:
        root = self._uf.find(at)
        found: set[str] = set()
        for label_at, names in self._labels.items():
            if self._uf.find(label_at) == root:
                found.update(names)
        return found

    def is_no_connect(self, at: Point) -> bool:
        return at in self._nc


class HierarchicalSchematic:
    def __init__(self, root_path: Path) -> None:
        self.root_path = root_path.resolve()
        root = Schematic.from_file(str(self.root_path), encoding="utf-8")
        self.root = SheetDocument(self.root_path, root, None, "Root")
        self.documents: list[SheetDocument] = [self.root]

        seen = {self.root_path}
        for sheet in root.sheets:
            child_path = (self.root_path.parent / str(sheet.fileName.value)).resolve()
            if child_path in seen:
                raise RuntimeError(f"duplicate/cyclic PCB-PWR sheet file: {child_path}")
            if not child_path.is_file():
                raise RuntimeError(f"PCB-PWR child sheet missing: {child_path}")
            seen.add(child_path)
            child = Schematic.from_file(str(child_path), encoding="utf-8")
            self.documents.append(SheetDocument(
                child_path,
                child,
                str(sheet.uuid),
                str(sheet.sheetName.value),
            ))

        self.connectivity = {
            document.path: SheetConnectivity(document)
            for document in self.documents
        }
        self.symbols: dict[str, SymbolRecord] = {}
        for document in self.documents:
            libraries = {item.libId: item for item in document.schematic.libSymbols}
            for instance in document.schematic.schematicSymbols:
                ref = ref_of(instance)
                if not ref:
                    raise RuntimeError(f"empty reference in {document.path}")
                if ref in self.symbols:
                    raise RuntimeError(f"duplicate hierarchical reference {ref}")
                if instance.libId not in libraries:
                    raise RuntimeError(
                        f"{ref}: embedded library {instance.libId} missing in {document.path}"
                    )
                self.symbols[ref] = SymbolRecord(document, instance, libraries[instance.libId])

    def pin_nets(self, ref: str, pin_number: str) -> set[str]:
        record = self.symbols[ref]
        at = endpoint(record.instance, record.symbol, pin_number)
        return self.connectivity[record.document.path].nets_at(at)

    def pin_net(self, ref: str, pin_number: str) -> str:
        found = self.pin_nets(ref, pin_number)
        if len(found) != 1:
            raise RuntimeError(
                f"{ref}.{pin_number}: expected exactly one resolved net, got {sorted(found)}"
            )
        return next(iter(found))

    def pin_is_no_connect(self, ref: str, pin_number: str) -> bool:
        record = self.symbols[ref]
        at = endpoint(record.instance, record.symbol, pin_number)
        return self.connectivity[record.document.path].is_no_connect(at)

    def all_label_texts(self) -> list[str]:
        result: list[str] = []
        for document in self.documents:
            for labels in (
                document.schematic.labels,
                document.schematic.hierarchicalLabels,
                document.schematic.globalLabels,
            ):
                result.extend(str(item.text) for item in labels)
        return result
