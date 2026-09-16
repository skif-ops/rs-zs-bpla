#!/usr/bin/env python3
"""Independent human-readability and electrical-equivalence audit for PCB-PWR."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from kiutils.board import Board
from kiutils.symbol import SymbolLib

from pcb_pwr_schematic_hierarchy import (
    HierarchicalSchematic,
    endpoint,
    point,
    property_value,
    selected_pins,
)


ROOT = Path(__file__).resolve().parents[1]
PCB = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
SYMBOL_LIBRARY = ROOT / "hardware/kicad/native/PCB-PWR/libs/DioneyaPWR.kicad_sym"
GRID_MM = 2.54
ROOT_LABEL_FONT_MAX_MM = 0.02

EXPECTED_SHEETS = {
    "Input protection and monitor": {
        "file": "PCB-PWR_01_INPUT_PROTECTION.kicad_sch",
        "page": "2",
        "refs": {
            "J1", "F1", "D1", "U1", "Q1", "C1", "C9", "C10", "C13",
            "RSH1", "U2", "C2", "TP1", "TP2", "TP3", "TP8", "TP9",
            "TP10", "#FLG01", "#FLG02",
        },
    },
    "3V8 modem rail": {
        "file": "PCB-PWR_02_3V8_MODEM.kicad_sch",
        "page": "3",
        "refs": {
            "U3", "L1", "C3", "C4", "C11", "C14", "C15", "C16",
            "R1", "R2", "R3", "R4", "R5", "R6", "R15", "TP4", "TP5",
        },
    },
    "3V3 digital rail": {
        "file": "PCB-PWR_03_3V3_DIGITAL.kicad_sch",
        "page": "4",
        "refs": {
            "U4", "L2", "C5", "C6", "C12", "C17", "C18", "C19",
            "R7", "R8", "R9", "R10", "R12", "R13", "R14", "TP6",
            "#FLG03",
        },
    },
    "1V8 auxiliary and MAIN harness": {
        "file": "PCB-PWR_04_AUX_HARNESS.kicad_sch",
        "page": "5",
        "refs": {"U5", "C7", "C8", "R11", "NT1", "NT2", "NT3", "J2", "TP7"},
    },
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def board_ref(footprint) -> str:
    if footprint.properties.get("Reference"):
        return str(footprint.properties["Reference"])
    return next((str(item.text) for item in footprint.graphicItems
                 if getattr(item, "type", None) == "reference"), "")


def root_pin_net(model: HierarchicalSchematic, sheet, pin) -> set[str]:
    at = point(pin.position.X, pin.position.Y)
    return model.connectivity[model.root.path].nets_at(at)


def on_grid(value: float, grid: float = GRID_MM) -> bool:
    return abs(float(value) / grid - round(float(value) / grid)) < 1e-6


def symbol_geometry_signature(symbol) -> tuple:
    pins = tuple(sorted(
        (
            str(number), str(pin.name), str(pin.electricalType), str(pin.graphicalStyle),
            round(float(pin.position.X), 4), round(float(pin.position.Y), 4),
            int(pin.position.angle or 0) % 360, round(float(pin.length), 4),
        )
        for number, pin in selected_pins(symbol).items()
    ))
    rectangles = []

    def visit(node) -> None:
        for item in getattr(node, "graphicItems", []):
            if item.__class__.__name__ == "SyRect":
                rectangles.append((
                    round(float(item.start.X), 4), round(float(item.start.Y), 4),
                    round(float(item.end.X), 4), round(float(item.end.Y), 4),
                ))
        for child in getattr(node, "units", []):
            visit(child)

    visit(symbol)
    return pins, tuple(sorted(rectangles))


def segments_intersect(a, b, c, d) -> bool:
    """Conservative intersection check for the generated axis-aligned stubs."""
    def between(value, left, right) -> bool:
        return min(left, right) <= value <= max(left, right)

    ab_horizontal = a[1] == b[1]
    cd_horizontal = c[1] == d[1]
    if ab_horizontal and cd_horizontal:
        return (
            a[1] == c[1]
            and max(min(a[0], b[0]), min(c[0], d[0]))
            <= min(max(a[0], b[0]), max(c[0], d[0]))
        )
    if not ab_horizontal and not cd_horizontal:
        return (
            a[0] == c[0]
            and max(min(a[1], b[1]), min(c[1], d[1]))
            <= min(max(a[1], b[1]), max(c[1], d[1]))
        )
    if ab_horizontal:
        return between(c[0], a[0], b[0]) and between(a[1], c[1], d[1])
    return between(a[0], c[0], d[0]) and between(c[1], a[1], b[1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--schematic",
        type=Path,
        default=ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_sch",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    model = HierarchicalSchematic(args.schematic)
    root = model.root.schematic
    require(root.generator == "dioneya-pcb-pwr-hierarchy",
            "PCB-PWR root is not the controlled hierarchy materialization")
    require(len(root.sheets) == 4 and not root.schematicSymbols,
            "root must contain four functional sheets and no physical symbols")
    require(len(root.sheetInstances) == 1 and root.sheetInstances[0].instancePath == "/" and
            root.sheetInstances[0].page == "1", "root sheet-instance/page contract drift")
    require(len(root.labels) == len(root.graphicalItems) and len(root.labels) > 0,
            "root overview pins must each have one explicit wire and label")
    require(all(item.effects.hide for item in root.labels),
            "root connectivity labels must be hidden to avoid duplicating visible sheet-pin names")
    require(all(float(item.effects.font.height) <= ROOT_LABEL_FONT_MAX_MM and
                float(item.effects.font.width) <= ROOT_LABEL_FONT_MAX_MM
                for item in root.labels),
            "root connectivity labels must remain sub-print because KiCad 9 plots hidden labels")
    require(not root.globalLabels and not root.hierarchicalLabels,
            "root overview must not bypass sheet pins with global/hierarchical labels")
    require(root.paper.paperSize == "A3" and not root.paper.portrait,
            "root overview must use the controlled A3 landscape review page")
    require(root.texts and all(100.0 <= float(item.position.X) <= 320.0 for item in root.texts),
            "root review note is not centered inside the printable area")

    document_by_name = {item.sheet_name: item for item in model.documents[1:]}
    require(set(document_by_name) == set(EXPECTED_SHEETS),
            f"functional sheet-name drift: {sorted(document_by_name)}")

    sheet_refs: dict[str, set[str]] = {}
    root_sheet_by_name = {str(item.sheetName.value): item for item in root.sheets}
    for name, expected in EXPECTED_SHEETS.items():
        document = document_by_name[name]
        require(document.path.name == expected["file"], f"{name}: file binding drift")
        refs = {property_value(item, "Reference") for item in document.schematic.schematicSymbols}
        require(refs == expected["refs"],
                f"{name}: ref allocation drift missing={sorted(expected['refs']-refs)} "
                f"extra={sorted(refs-expected['refs'])}")
        sheet_refs[name] = refs
        require(document.schematic.titleBlock is not None and
                "Human-readable hierarchy" in document.schematic.titleBlock.comments.get(1, ""),
                f"{name}: hierarchy/review title control missing")
        require(document.schematic.texts and document.schematic.graphicalItems,
                f"{name}: readable note or explicit wires missing")
        require(document.schematic.paper.paperSize == "A3" and
                not document.schematic.paper.portrait,
                f"{name}: child sheet must use the controlled A3 landscape review page")
        require(all(100.0 <= float(item.position.X) <= 320.0
                    for item in document.schematic.texts),
                f"{name}: review note is clipped outside the printable area")
        require(not document.schematic.globalLabels,
                f"{name}: global labels are forbidden in bounded hierarchy")
        require(all(not label.effects.hide
                    for labels in (document.schematic.labels,
                                   document.schematic.hierarchicalLabels)
                    for label in labels),
                f"{name}: functional pin/net labels must remain visible")

        root_sheet = root_sheet_by_name[name]
        instance_paths = [path for project in root_sheet.instances for path in project.paths]
        require(len(instance_paths) == 1 and instance_paths[0].page == expected["page"],
                f"{name}: root page instance drift")
        root_pin_names = {str(pin.name) for pin in root_sheet.pins}
        child_hier_names = {str(label.text) for label in document.schematic.hierarchicalLabels}
        require(root_pin_names == child_hier_names,
                f"{name}: root pins and child hierarchical labels differ")
        sheet_left = round(float(root_sheet.position.X), 4)
        sheet_right = round(sheet_left + float(root_sheet.width), 4)
        pin_y = []
        for pin in root_sheet.pins:
            x = round(float(pin.position.X), 4)
            y = round(float(pin.position.Y), 4)
            angle = int(pin.position.angle or 0) % 360
            require(x in {sheet_left, sheet_right},
                    f"{name}.{pin.name}: sheet pin is not on a vertical sheet edge")
            expected_angle = 180 if x == sheet_left else 0
            require(angle == expected_angle,
                    f"{name}.{pin.name}: KiCad sheet-pin orientation {angle} would move "
                    f"the electrical endpoint to the opposite edge (expected {expected_angle})")
            require(on_grid(y), f"{name}.{pin.name}: sheet pin is off the 2.54 mm review grid")
            pin_y.append(y)
            require(root_pin_net(model, root_sheet, pin) == {str(pin.name)},
                    f"{name}.{pin.name}: root sheet pin is not explicitly wired/labeled")
        require(len(pin_y) == len(set(pin_y)),
                f"{name}: opposite-side sheet pins share a Y coordinate and could hide a side swap")

        label_positions = {
            point(label.position.X, label.position.Y)
            for labels in (document.schematic.labels, document.schematic.hierarchicalLabels)
            for label in labels
        }
        label_nets_at: dict[tuple[float, float], set[str]] = defaultdict(set)
        for labels in (document.schematic.labels, document.schematic.hierarchicalLabels):
            for label in labels:
                label_nets_at[point(label.position.X, label.position.Y)].add(str(label.text))
        connected_pin_count = 0
        for ref in refs:
            record = model.symbols[ref]
            symbol_pins = selected_pins(record.symbol, record.instance.unit or 1)
            for number in symbol_pins:
                at = endpoint(record.instance, record.symbol, number)
                nets = model.pin_nets(ref, number)
                nc = model.pin_is_no_connect(ref, number)
                require((len(nets) == 1 and not nc) or (not nets and nc),
                        f"{ref}.{number}: must resolve to one net or one explicit NC")
                require(at not in label_positions,
                        f"{ref}.{number}: label remains directly on pin; explicit wire stub required")
                if nets:
                    connected_pin_count += 1
            visible = {item.key: item for item in record.instance.properties
                       if item.key in {"Reference", "Value"}}
            require(set(visible) == {"Reference", "Value"} and
                    all(not item.effects.hide for item in visible.values()),
                    f"{ref}: review reference/value visibility drift")
            require(all(12.7 <= float(item.position.X) <= 407.3 and
                        12.7 <= float(item.position.Y) <= 284.3
                        for item in visible.values()),
                    f"{ref}: visible property is outside the A3 printable review area")
        wire_count = sum(1 for item in document.schematic.graphicalItems
                         if getattr(item, "type", None) == "wire")
        require(wire_count == connected_pin_count,
                f"{name}: expected one explicit pin wire per connected pin "
                f"({connected_pin_count}), got {wire_count}")
        wire_records = []
        for item in document.schematic.graphicalItems:
            if getattr(item, "type", None) != "wire":
                continue
            start = point(item.points[0].X, item.points[0].Y)
            end = point(item.points[-1].X, item.points[-1].Y)
            names = label_nets_at.get(start, set()) | label_nets_at.get(end, set())
            require(len(names) == 1,
                    f"{name}: wire must terminate at exactly one net label, got {sorted(names)}")
            wire_records.append((start, end, next(iter(names))))
        for index, (a, b, net_a) in enumerate(wire_records):
            for c, d, net_b in wire_records[index + 1:]:
                require(net_a == net_b or not segments_intersect(a, b, c, d),
                        f"{name}: visible wire collision would join {net_a} and {net_b}")

    allocated = set().union(*sheet_refs.values())
    require(len(allocated) == sum(len(items) for items in sheet_refs.values()) == 63,
            "hierarchy must allocate 63 unique symbols exactly once")
    physical_refs = {ref for ref in allocated if not ref.startswith("#")}
    require(len(physical_refs) == 60, "hierarchy physical reference count drift")

    # Cross-sheet nets must be represented by one hierarchical label per participating sheet.
    net_sheets: dict[str, set[str]] = defaultdict(set)
    for name, refs in sheet_refs.items():
        for ref in refs:
            record = model.symbols[ref]
            for number in selected_pins(record.symbol, record.instance.unit or 1):
                for net in model.pin_nets(ref, number):
                    net_sheets[net].add(name)
    cross_nets = {net for net, names in net_sheets.items() if len(names) > 1}
    require(cross_nets == {
        "3V3_DIGITAL", "3V8_MODEM", "EN_MODEM", "FAULT", "GND_PWR",
        "I2C2_SCL", "I2C2_SDA", "PWR_GOOD", "VBAT_SYS",
    }, f"cross-sheet net set drift: {sorted(cross_nets)}")
    # Some expected cross nets may be present on only two sheets; every participation is exact.
    total_hier_labels = sum(len(item.schematic.hierarchicalLabels)
                            for item in model.documents[1:])
    require(total_hier_labels == sum(len(names) for net, names in net_sheets.items()
                                     if net in cross_nets),
            "hierarchical label count does not equal cross-sheet participation count")

    # The six project-local IC/power symbols must no longer be one-sided connector glyphs.
    for ref in ("U1", "Q1", "U2", "U3", "U4", "U5"):
        record = model.symbols[ref]
        angles = {int(pin.position.angle or 0) % 360
                  for pin in selected_pins(record.symbol, record.instance.unit or 1).values()}
        require(len(angles) >= 3, f"{ref}: functional pin geometry collapsed to connector glyph")
    rsh = model.symbols["RSH1"]
    require({int(pin.position.angle or 0) % 360
             for pin in selected_pins(rsh.symbol, rsh.instance.unit or 1).values()} == {0, 180},
            "RSH1: current/Kelvin terminals must be visibly split across both sides")
    rsh_rectangles = symbol_geometry_signature(rsh.symbol)[1]
    require(any(abs(left - right) >= 20.32 for left, _top, right, _bottom in rsh_rectangles),
            "RSH1: body is too narrow for distinct CURRENT/SENSE pin labels")
    require(model.symbols["J2"].symbol.pinNamesHide,
            "J2: duplicate connector pin names must be hidden; net labels and pin numbers remain")

    # Embedded functional glyphs and the project symbol library must have the
    # same pins and body rectangles.  KiCad otherwise reports lib_symbol_mismatch
    # even if the schematic-level electrical audit happens to pass.
    external_library = SymbolLib.from_file(str(SYMBOL_LIBRARY), encoding="utf-8")
    external_symbols = {str(item.entryName): item for item in external_library.symbols}
    checked_library_entries = set()
    for record in model.symbols.values():
        if record.instance.libraryNickname != "DioneyaPWR":
            continue
        entry = str(record.instance.entryName)
        require(entry in external_symbols, f"{entry}: project symbol library entry missing")
        require(symbol_geometry_signature(record.symbol) ==
                symbol_geometry_signature(external_symbols[entry]),
                f"{entry}: embedded/project-library symbol geometry mismatch")
        checked_library_entries.add(entry)
    require(checked_library_entries,
            "no DioneyaPWR embedded/project-library symbol geometry was checked")

    # Independent electrical equivalence: every physical schematic pin equals every PCB pad net.
    board = Board.from_file(str(PCB), encoding="utf-8")
    footprints = {board_ref(item): item for item in board.footprints}
    require(len(footprints) == len(board.footprints) == 60 and
            set(footprints) == physical_refs, "hierarchical schematic/PCB ref set mismatch")
    semantic_rows: list[str] = []
    for ref in sorted(physical_refs):
        record = model.symbols[ref]
        schematic_pins = selected_pins(record.symbol, record.instance.unit or 1)
        pads: dict[str, list[object]] = defaultdict(list)
        for pad in footprints[ref].pads:
            if pad.number:
                pads[str(pad.number)].append(pad)
        require(set(pads) == set(schematic_pins), f"{ref}: schematic/PCB pin set mismatch")
        for number in sorted(schematic_pins, key=lambda item: (len(item), item)):
            schematic_nets = model.pin_nets(ref, number)
            expected = next(iter(schematic_nets)) if schematic_nets else "NC"
            board_nets = {pad.net.name if pad.net is not None else "NC" for pad in pads[number]}
            require(board_nets == {expected},
                    f"{ref}.{number}: PCB {sorted(board_nets)} != schematic {expected}")
            semantic_rows.append(f"{ref}|{number}|{expected}")

    semantic_sha256 = hashlib.sha256(("\n".join(semantic_rows) + "\n").encode()).hexdigest()
    result = {
        "status": "PASS_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE",
        "root_sheets": 4,
        "pages": 5,
        "symbols": 63,
        "physical_symbols": 60,
        "wire_segments": sum(
            sum(1 for item in document.schematic.graphicalItems
                if getattr(item, "type", None) == "wire")
            for document in model.documents
        ),
        "cross_sheet_nets": len(cross_nets),
        "hierarchical_labels": total_hier_labels,
        "pin_net_semantic_sha256": semantic_sha256,
        "erc_native_kicad_9": "REQUIRED_SEPARATE_GATE",
        "pin_net_review_a": "RETAINED_BY_EXACT_ELECTRICAL_EQUIVALENCE",
        "hierarchy_human_review": "REQUIRED_BEFORE_ROUTING",
        "manufacturing_release": False,
    }
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    hierarchy = status.get("human_readable_hierarchy", {})
    control = hierarchy.get("control", {})
    require(hierarchy.get("generator") == "tools/materialize_pcb_pwr_hierarchy_rev_a.py" and
            hierarchy.get("connectivity_reader") == "tools/pcb_pwr_schematic_hierarchy.py" and
            hierarchy.get("independent_audit") == "tools/audit_pcb_pwr_hierarchy_rev_a.py",
            "PCB-PWR status does not bind the hierarchy toolchain")
    for key, expected in {
        "pages": 5,
        "functional_child_sheets": 4,
        "symbols": 63,
        "physical_symbols": 60,
        "wire_segments": 185,
        "cross_sheet_nets": 9,
        "hierarchical_labels": 26,
        "pin_net_semantic_sha256": semantic_sha256,
        "pin_net_review_a_retained": True,
        "native_kicad_9_erc_pass": False,
        "committed_erc_evidence": False,
        "committed_pdf_evidence": False,
        "independent_human_review_complete": False,
        "routing_authorized": False,
        "manufacturing_release": False,
    }.items():
        require(control.get(key) == expected,
                f"PCB-PWR hierarchy status {key} drift: {control.get(key)!r} != {expected!r}")
    require(control.get("state") ==
            "PASS_INTERNAL_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE_NATIVE_KICAD_9_AND_HUMAN_REVIEW_PENDING",
            "PCB-PWR hierarchy control state drift")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR human-readable hierarchy and electrical-equivalence audit PASS")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
