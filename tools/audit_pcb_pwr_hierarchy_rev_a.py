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
REVIEW_TEXT_FONT_MIN_MM = 1.0
REVIEW_STUB_LENGTH_MIN_MM = 10.0
HORIZONTAL_REVIEW_SYMBOLS = {"Device:C", "Device:Fuse", "Device:L", "Device:R"}
PRE_CINHF_SEMANTIC_SHA256 = "fb31a1880037c2d15873ef7a003b74967e0427ed767bc16de256a790b5320b5a"

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
            "U3", "L1", "C3", "C4", "C11", "C14", "C15", "C16", "C20",
            "R1", "R2", "R3", "R4", "R5", "R6", "R15", "TP4", "TP5",
        },
    },
    "3V3 digital rail": {
        "file": "PCB-PWR_03_3V3_DIGITAL.kicad_sch",
        "page": "4",
        "refs": {
            "U4", "L2", "C5", "C6", "C12", "C17", "C18", "C19", "C21",
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
        require(all(float(label.effects.font.height) >= REVIEW_TEXT_FONT_MIN_MM and
                    float(label.effects.font.width) >= REVIEW_TEXT_FONT_MIN_MM
                    for labels in (document.schematic.labels,
                                   document.schematic.hierarchicalLabels)
                    for label in labels),
                f"{name}: pin/net label font regressed below the legibility floor")

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
            require(all(float(item.effects.font.height) >= REVIEW_TEXT_FONT_MIN_MM and
                        float(item.effects.font.width) >= REVIEW_TEXT_FONT_MIN_MM
                        for item in visible.values()),
                    f"{ref}: reference/value font regressed below the legibility floor")
            require(all((int(item.position.angle or 0) +
                         int(record.instance.position.angle or 0)) % 180 == 0
                        for item in visible.values()),
                    f"{ref}: reference/value fields do not render horizontally")
            require(all(item.key in {"Reference", "Value"} or item.effects.hide
                        for item in record.instance.properties),
                    f"{ref}: footprint/datasheet field leaked onto the review drawing")
            if record.instance.libId in HORIZONTAL_REVIEW_SYMBOLS:
                require(int(record.instance.position.angle or 0) % 180 == 90,
                        f"{ref}: two-terminal review symbol must keep horizontal net labels")
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
            stub_length = abs(end[0] - start[0]) + abs(end[1] - start[1])
            require(stub_length >= REVIEW_STUB_LENGTH_MIN_MM,
                    f"{name}: {stub_length:.2f} mm wire stub is below the legibility floor")
            names = label_nets_at.get(start, set()) | label_nets_at.get(end, set())
            require(len(names) == 1,
                    f"{name}: wire must terminate at exactly one net label, got {sorted(names)}")
            wire_records.append((start, end, next(iter(names))))
        for index, (a, b, net_a) in enumerate(wire_records):
            for c, d, net_b in wire_records[index + 1:]:
                require(net_a == net_b or not segments_intersect(a, b, c, d),
                        f"{name}: visible wire collision would join {net_a} and {net_b}")

    allocated = set().union(*sheet_refs.values())
    require(len(allocated) == sum(len(items) for items in sheet_refs.values()) == 65,
            "hierarchy must allocate 65 unique symbols exactly once")
    physical_refs = {ref for ref in allocated if not ref.startswith("#")}
    require(len(physical_refs) == 62, "hierarchy physical reference count drift")

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
        rectangles = symbol_geometry_signature(record.symbol)[1]
        require(any(abs(left - right) >= 25.4
                    for left, _top, right, _bottom in rectangles),
                f"{ref}: body is too narrow for readable functional pin names")
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
    require(len(footprints) == len(board.footprints) == 62 and
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
        "symbols": 65,
        "physical_symbols": 62,
        "wire_segments": sum(
            sum(1 for item in document.schematic.graphicalItems
                if getattr(item, "type", None) == "wire")
            for document in model.documents
        ),
        "cross_sheet_nets": len(cross_nets),
        "hierarchical_labels": total_hier_labels,
        "pin_net_semantic_sha256": semantic_sha256,
        "readability_profile": "PASS_LARGER_TEXT_HORIZONTAL_PASSIVES_EXPANDED_FUNCTIONAL_BODIES",
        "erc_native_kicad_9": "PENDING_COMMIT_BOUND_POST_CINHF_ECO",
        "hierarchy_pdf_evidence": "PENDING_COMMIT_BOUND_POST_CINHF_ECO",
        "pin_net_review_a": "RETAINED_BY_EXACT_ELECTRICAL_EQUIVALENCE",
        "hierarchy_human_review": "PENDING_REPEAT_INDEPENDENT_REVIEW_POST_CINHF_ECO",
        "manufacturing_release": False,
    }
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    hierarchy = status.get("human_readable_hierarchy", {})
    control = hierarchy.get("control", {})
    require(hierarchy.get("generator") == "tools/materialize_pcb_pwr_hierarchy_rev_a.py" and
            hierarchy.get("connectivity_reader") == "tools/pcb_pwr_schematic_hierarchy.py" and
            hierarchy.get("independent_audit") == "tools/audit_pcb_pwr_hierarchy_rev_a.py",
            "PCB-PWR status does not bind the hierarchy toolchain")
    current_evidence = hierarchy.get("current_evidence", {})
    evidence_complete = current_evidence.get("status") == \
        "PASS_COMMIT_BOUND_KICAD_9_ERC_PDF_EVIDENCE_HUMAN_REVIEW_PENDING"
    for key, expected in {
        "pages": 5,
        "functional_child_sheets": 4,
        "symbols": 65,
        "physical_symbols": 62,
        "wire_segments": 189,
        "cross_sheet_nets": 9,
        "hierarchical_labels": 26,
        "pin_net_semantic_sha256": semantic_sha256,
        "pin_net_review_a_retained": True,
        "native_kicad_9_erc_pass": evidence_complete,
        "committed_erc_evidence": evidence_complete,
        "committed_pdf_evidence": evidence_complete,
        "independent_human_review_complete": False,
        "prior_evidence_superseded_by_f1_value_eco": True,
        "prior_evidence_superseded_by_legibility_remediation": True,
        "prior_evidence_superseded_by_cinhf_eco": True,
        "routing_authorized": False,
        "manufacturing_release": False,
    }.items():
        require(control.get(key) == expected,
                f"PCB-PWR hierarchy status {key} drift: {control.get(key)!r} != {expected!r}")
    expected_state = (
        "PASS_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE_CINHF_ECO_"
        "NATIVE_KICAD_9_ERC_PDF_EVIDENCE_PASS_HUMAN_REVIEW_PENDING"
        if evidence_complete else
        "PASS_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE_CINHF_ECO_"
        "NATIVE_KICAD_9_ERC_PDF_EVIDENCE_PENDING_HUMAN_REVIEW_PENDING"
    )
    require(control.get("state") == expected_state,
            "PCB-PWR hierarchy control state drift")
    expected_change = {
        "reason": "TI_LMR60440_TABLE_8_3_LOCAL_CIN_HF_ECO",
        "presentation_only": False,
        "electrical_change": True,
        "added_refs": ["C20", "C21"],
        "pin_net_semantic_sha256_before": PRE_CINHF_SEMANTIC_SHA256,
        "pin_net_semantic_sha256_after": semantic_sha256,
    }
    require(current_evidence.get("change") == expected_change,
            "PCB-PWR active CIN_HF ECO evidence change boundary drift")
    require(current_evidence.get("independent_human_review") is None and
            current_evidence.get("routing_authorized") is False and
            current_evidence.get("manufacturing_release") is False,
            "PCB-PWR active CIN_HF ECO review/release interlock drift")
    evidence_fields = (
        "source_commit_sha", "source_tree_sha", "schematic_gate_run", "ci_run",
        "pcb_native_gate_run", "artifact", "artifact_id", "artifact_digest",
        "erc", "schematic_pdf", "schematic_source_sha256",
    )
    active_source_dir = ROOT / "hardware/kicad/native/PCB-PWR"
    if evidence_complete:
        require(all(current_evidence.get(key) is not None for key in evidence_fields),
                "PCB-PWR completed CIN_HF ECO evidence has null commit/artifact fields")
        require(len(str(current_evidence["source_commit_sha"])) == 40 and
                len(str(current_evidence["source_tree_sha"])) == 40,
                "PCB-PWR completed CIN_HF ECO evidence commit/tree SHA malformed")
        require(all(str(current_evidence[key]).startswith("https://github.com/skif-ops/rs-zs-bpla/actions/runs/")
                    for key in ("schematic_gate_run", "ci_run", "pcb_native_gate_run")),
                "PCB-PWR completed CIN_HF ECO run URL drift")
        erc = current_evidence["erc"]
        require(erc.get("path") == "artifacts/kicad-native/PCB-PWR/erc.json" and
                erc.get("sheets") == 5 and erc.get("violations") == 0 and
                len(str(erc.get("sha256", ""))) == 64,
                "PCB-PWR completed CIN_HF ECO ERC evidence drift")
        pdf = current_evidence["schematic_pdf"]
        require(pdf.get("path") == "artifacts/kicad-native/PCB-PWR/PCB-PWR_schematic.pdf" and
                pdf.get("pages") == 5 and pdf.get("page_size") == "A3" and
                pdf.get("orientation") == "landscape" and
                pdf.get("visual_preflight") ==
                "PASS_ALL_5_PAGES_NO_TEXT_SYMBOL_OR_CONNECTION_OVERLAP_NO_CLIPPING" and
                len(str(pdf.get("sha256", ""))) == 64,
                "PCB-PWR completed CIN_HF ECO PDF evidence drift")
        source_hashes = current_evidence["schematic_source_sha256"]
        expected_files = {"PCB-PWR.kicad_sch", *(spec["file"] for spec in EXPECTED_SHEETS.values())}
        require(set(source_hashes) == expected_files,
                "PCB-PWR completed CIN_HF ECO source-hash file set drift")
        for filename, expected_sha256 in source_hashes.items():
            source_path = active_source_dir / filename
            require(source_path.is_file(), f"PCB-PWR current evidence source is missing: {filename}")
            actual_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
            require(actual_sha256 == expected_sha256,
                    f"PCB-PWR current evidence source hash drift: {filename}")
        result["erc_native_kicad_9"] = "PASS_COMMIT_BOUND_POST_CINHF_ECO"
        result["hierarchy_pdf_evidence"] = "PASS_COMMIT_BOUND_POST_CINHF_ECO"
    else:
        require(current_evidence.get("status") ==
                "PENDING_COMMIT_BOUND_KICAD_9_ERC_PDF_EVIDENCE" and
                all(current_evidence.get(key) is None for key in evidence_fields),
                "PCB-PWR pending CIN_HF ECO evidence must keep commit/artifact fields null")

    superseded_pre_cinhf = hierarchy.get("superseded_pre_cinhf_evidence", {})
    require(superseded_pre_cinhf.get("status") ==
            "PASS_COMMIT_BOUND_KICAD_9_ERC_PDF_EVIDENCE_HUMAN_REVIEW_PENDING" and
            superseded_pre_cinhf.get("source_commit_sha") ==
            "6ba3ba5d219b95cb7de12f37c4eb646f7f18cfa8" and
            superseded_pre_cinhf.get("schematic_pdf", {}).get("sha256") ==
            "16afef6ecb337109f2a61318c9459167c6d06f4b74534b656c97884c1fed57dd" and
            superseded_pre_cinhf.get("change", {}).get("pin_net_semantic_sha256_after") ==
            PRE_CINHF_SEMANTIC_SHA256,
            "PCB-PWR superseded pre-CIN_HF evidence boundary drift")
    superseded_legibility = hierarchy.get("superseded_legibility_evidence", {})
    require(superseded_legibility == {
        "status": "PASS_COMMIT_BOUND_KICAD_9_ERC_PDF_EVIDENCE_HUMAN_REVIEW_PENDING",
        "eco": {
            "change": "F1_0451005.MRL_TO_0451008.MRL",
            "applied_date": "2026-09-17",
            "value_only": True,
            "pin_net_semantic_sha256_before": PRE_CINHF_SEMANTIC_SHA256,
            "pin_net_semantic_sha256_after": PRE_CINHF_SEMANTIC_SHA256,
        },
        "source_commit_sha": "091a2eb223161cb4396fc6838921eeb79150c38d",
        "source_tree_sha": "72ef5630c0952a287d503f1ab3dda9dcbbee2a33",
        "schematic_gate_run": "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35197150159",
        "ci_run": "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35197150164",
        "pcb_native_gate_run": "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35197150191",
        "artifact": "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35197150159/artifacts/10486481159",
        "artifact_id": 10486481159,
        "artifact_digest": "sha256:bf80f07c9b20d93d610c3e8c124887becb4209f8d688f085fe68bac53e0ad0b9",
        "erc": {
            "path": "artifacts/kicad-native/PCB-PWR/erc.json",
            "sha256": "a31be06d1a32bde0fad9ffa26cb90f8076c133450915494437e95a532659cece",
            "kicad_version": "9.0.9",
            "sheets": 5,
            "violations": 0,
        },
        "schematic_pdf": {
            "path": "artifacts/kicad-native/PCB-PWR/PCB-PWR_schematic.pdf",
            "sha256": "9733a1df0026a53ecfc56355cf185e04fb372242a9dcdcb13ef214cced81c744",
            "pages": 5,
            "page_size": "A3",
            "orientation": "landscape",
            "file_size_bytes": 642059,
            "pdf_version": "1.5",
            "visual_preflight": "PASS_NO_CLIPPING_NO_VISIBLE_DUPLICATE_ROOT_LABELS",
        },
        "schematic_source_sha256": {
            "PCB-PWR.kicad_sch": "16365f1c8be5a98eb5f2635f2740198998baf560db15b2ee761d65c9ade903a5",
            "PCB-PWR_01_INPUT_PROTECTION.kicad_sch": "ede876600dec02b803645a0d2cb9dd182c53b565d1786421ce9b46773aaf035a",
            "PCB-PWR_02_3V8_MODEM.kicad_sch": "c746b8a526c647d87c39c18163cb69f4fcf8952ec60859b95a2d7bb6718087e0",
            "PCB-PWR_03_3V3_DIGITAL.kicad_sch": "53c1297232aa3932310d8f60135ff555516b45a4a5f31f29476d5b0bc26be724",
            "PCB-PWR_04_AUX_HARNESS.kicad_sch": "b9a73ead5a7897857b8c57987cd79b65f66b4f13070a9023b15b0b00dece0c71",
        },
        "independent_human_review": None,
        "routing_authorized": False,
        "manufacturing_release": False,
    }, "PCB-PWR superseded legibility evidence boundary drift")
    evidence = hierarchy.get("historical_evidence", {})
    require(isinstance(evidence, dict) and evidence.get("status") ==
            "SUPERSEDED_BY_F1_VALUE_ECO_HISTORICAL_RECORD_ONLY",
            "PCB-PWR historical hierarchy evidence status drift")
    for key, expected in {
        "source_commit_sha": "2a973f6856aa115aa59323d619be985578780682",
        "source_tree_sha": "c8cd8272c0ebe50a4e5fc30fd484427740dbda11",
        "schematic_gate_run": "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35122481138",
        "ci_run": "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35122481079",
        "pcb_native_gate_run": "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35122481037",
        "artifact": "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35122481138/artifacts/10457498007",
        "artifact_id": 10457498007,
        "artifact_digest": "sha256:01d19ff8622c2cd3dbe420987439f3452800499116c84f72708df918503b4a75",
        "routing_authorized": False,
        "manufacturing_release": False,
    }.items():
        require(evidence.get(key) == expected,
                f"PCB-PWR hierarchy evidence {key} drift: {evidence.get(key)!r} != {expected!r}")
    erc_evidence = evidence.get("erc", {})
    require(erc_evidence == {
        "path": "artifacts/kicad-native/PCB-PWR/erc.json",
        "sha256": "0ec8289ecac2437eafc3c72b560dad1cdf92f1039c996658b245ab5ae0126b92",
        "kicad_version": "9.0.9",
        "sheets": 5,
        "violations": 0,
    }, "PCB-PWR commit-bound ERC evidence drift")
    pdf_evidence = evidence.get("schematic_pdf", {})
    require(pdf_evidence == {
        "path": "artifacts/kicad-native/PCB-PWR/PCB-PWR_schematic.pdf",
        "sha256": "7a1eee774d6a0dd03e6cb72935824f5a7d2af4bebe0e37ad739f61eb8d32a1f4",
        "pages": 5,
        "page_size": "A3",
        "orientation": "landscape",
        "visual_preflight": "PASS_NO_CLIPPING_NO_VISIBLE_DUPLICATE_ROOT_LABELS",
    }, "PCB-PWR commit-bound PDF evidence drift")
    expected_source_sha256 = {
        "PCB-PWR.kicad_sch": "16365f1c8be5a98eb5f2635f2740198998baf560db15b2ee761d65c9ade903a5",
        "PCB-PWR_01_INPUT_PROTECTION.kicad_sch": "33d557e3a6450e18f3e89a676284a24406a5a5cca9c4cf4d4c63b827711ebd9e",
        "PCB-PWR_02_3V8_MODEM.kicad_sch": "c746b8a526c647d87c39c18163cb69f4fcf8952ec60859b95a2d7bb6718087e0",
        "PCB-PWR_03_3V3_DIGITAL.kicad_sch": "53c1297232aa3932310d8f60135ff555516b45a4a5f31f29476d5b0bc26be724",
        "PCB-PWR_04_AUX_HARNESS.kicad_sch": "b9a73ead5a7897857b8c57987cd79b65f66b4f13070a9023b15b0b00dece0c71",
    }
    require(evidence.get("schematic_source_sha256") == expected_source_sha256,
            "PCB-PWR hierarchy evidence source-hash register drift")
    # These hashes bind the superseded 5 A source only. They must remain in the
    # historical register but must not be compared with the active post-ECO source.
    require(evidence.get("independent_human_review") == {
        "status": "ACCEPTED_INDEPENDENT_HUMAN_REVIEW",
        "reviewer": "Скиф",
        "date": "2026-09-16",
        "decision": "ACCEPT_HIERARCHY_ONLY",
        "scope": "PCB_PWR_HUMAN_READABLE_HIERARCHY_ONLY",
        "reviewed_source_commit_sha": "2a973f6856aa115aa59323d619be985578780682",
        "reviewed_pdf_sha256": "7a1eee774d6a0dd03e6cb72935824f5a7d2af4bebe0e37ad739f61eb8d32a1f4",
    }, "PCB-PWR hierarchy human-review acceptance record drift")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PCB-PWR human-readable hierarchy and electrical-equivalence audit PASS")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
