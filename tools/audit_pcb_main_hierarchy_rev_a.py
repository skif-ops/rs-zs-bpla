#!/usr/bin/env python3
"""Independently audit PCB-MAIN hierarchy and exact electrical equivalence.

This audit reads the committed hierarchy, resolves real wire connectivity, checks
functional-sheet allocation and printable geometry, compares every pin/net against
the independent Rev.A authorities and every fitted PCB pad, and preserves a hard
boundary: hierarchy acceptance never authorizes routing or manufacture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from kiutils.board import Board

from audit_pcb_main_native_schematic_rev_a import expected_components
from pcb_main_schematic_hierarchy import (
    HierarchicalSchematic,
    endpoint,
    point,
    property_value,
    selected_pins,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMATIC = ROOT / "hardware" / "kicad" / "native" / "PCB-MAIN" / "PCB-MAIN.kicad_sch"
PCB = ROOT / "hardware" / "kicad" / "native" / "PCB-MAIN" / "PCB-MAIN.kicad_pcb"
STATUS = ROOT / "hardware" / "PCB_MAIN_CAPTURE_STATUS_REV_A.json"
ROOT_LABEL_FONT_MAX_MM = 0.02


def ref_range(prefix: str, first: int, last: int) -> set[str]:
    return {f"{prefix}{index}" for index in range(first, last + 1)}


EXPECTED_SHEETS = {
    "Power entry and rail interface": {
        "file": "PCB-MAIN_01_POWER.kicad_sch", "page": "2",
        "title": "Dioneya PCB-MAIN Rev.A - Power",
        "refs": {"J_PWR", "C19", "C20", "R103"},
    },
    "MCU clocks reset and straps": {
        "file": "PCB-MAIN_02_MCU.kicad_sch", "page": "3",
        "title": "Dioneya PCB-MAIN Rev.A - MCU",
        "refs": {"U1", "X1", "L1"} | ref_range("C", 1, 18) | ref_range("R", 1, 6),
    },
    "PDM audio AAD and microphone harnesses": {
        "file": "PCB-MAIN_03_AUDIO.kicad_sch", "page": "4",
        "title": "Dioneya PCB-MAIN Rev.A - PDM audio",
        "refs": (
            {"U7", "U17", "U18"}
            | {f"J_MIC{index}" for index in range(1, 5)}
            | ref_range("C", 27, 32) | ref_range("R", 17, 23) | ref_range("U", 19, 22)
        ),
    },
    "GNSS timing antenna and supervisor": {
        "file": "PCB-MAIN_04_GNSS.kicad_sch", "page": "5",
        "title": "Dioneya PCB-MAIN Rev.A - GNSS",
        "refs": (
            {"U9", "J9", "L2", "FL1", "U5", "Q4", "D4"}
            | ref_range("C", 60, 65) | ref_range("R", 56, 62)
        ),
    },
    "Cellular modem dual SIM and recovery": {
        "file": "PCB-MAIN_05_CELLULAR.kicad_sch", "page": "6",
        "title": "Dioneya PCB-MAIN Rev.A - Cellular + dual SIM",
        "refs": (
            {
                "U8", "U16", "Q1", "Q2", "U13", "U14", "U15", "Q3",
                "J6", "J7", "J8", "TP_CELL_USB", "TP_CELL_DBG", "FB1",
                "U26", "U27", "D1", "D2", "D3", "D10", "C79", "C80",
            }
            | ref_range("C", 33, 59) | ref_range("R", 24, 55)
        ),
    },
    "LoRa radio control and conducted RF": {
        "file": "PCB-MAIN_06_LORA.kicad_sch", "page": "7",
        "title": "Dioneya PCB-MAIN Rev.A - LoRa",
        "refs": {"U10", "J10", "D5"} | ref_range("C", 66, 70) | ref_range("R", 63, 73),
    },
    "BLE module reset DFU and SWD": {
        "file": "PCB-MAIN_07_BLE.kicad_sch", "page": "8",
        "title": "Dioneya PCB-MAIN Rev.A - BLE",
        "refs": {"U11", "TP_BLE_SWD", "U6"} | ref_range("C", 71, 73) | ref_range("R", 74, 78),
    },
    "Storage sensors microSD and tamper": {
        "file": "PCB-MAIN_08_STORAGE_SENSORS.kicad_sch", "page": "9",
        "title": "Dioneya PCB-MAIN Rev.A - Storage + sensors",
        "refs": (
            {
                "U2", "U3", "U4", "U12", "J12", "J13", "U23", "U24",
                "D9", "D11", "C78", "R99", "R100",
            }
            | ref_range("C", 21, 26) | ref_range("C", 74, 76)
            | ref_range("R", 7, 16) | ref_range("R", 79, 90)
        ),
    },
    "USB service debug and EOL fixture": {
        "file": "PCB-MAIN_09_CONNECTORS_TEST.kicad_sch", "page": "10",
        "title": "Dioneya PCB-MAIN Rev.A - USB + debug",
        "refs": (
            {"J11", "TP_MCU_SWD", "TP_EOL", "C77", "U25", "D6", "D7", "D8"}
            | ref_range("R", 91, 98) | ref_range("R", 101, 102)
        ),
    },
}


def natural(value: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part
                 for part in re.split(r"(\d+)", value))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def board_ref(footprint) -> str:
    if footprint.properties.get("Reference"):
        return str(footprint.properties["Reference"])
    return next((str(item.text) for item in footprint.graphicItems
                 if getattr(item, "type", None) == "reference"), "")


def wire_count(schematic) -> int:
    return sum(1 for item in schematic.graphicalItems
               if getattr(item, "type", None) == "wire")


def root_pin_net(model: HierarchicalSchematic, pin) -> set[str]:
    return model.connectivity[model.root.path].nets_at(
        point(pin.position.X, pin.position.Y)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schematic", type=Path, default=SCHEMATIC)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    model = HierarchicalSchematic(args.schematic.resolve())
    root = model.root.schematic
    require(root.generator == "dioneya-pcb-main-hierarchy",
            "PCB-MAIN root is not the controlled hierarchy materialization")
    require(len(root.sheets) == 9 and not root.schematicSymbols,
            "root must contain nine functional sheets and no physical symbols")
    require(len(root.sheetInstances) == 1 and
            root.sheetInstances[0].instancePath == "/" and
            root.sheetInstances[0].page == "1",
            "root sheet-instance/page contract drift")
    require(root.paper.paperSize == "A2" and not root.paper.portrait,
            "root overview must use A2 landscape")
    require(not root.globalLabels and not root.hierarchicalLabels,
            "root overview must not bypass sheet pins")
    require(len(root.labels) == wire_count(root) and len(root.labels) > 0,
            "root sheet pins must each have one explicit wire and hidden label")
    require(all(item.effects.hide for item in root.labels),
            "root connectivity labels must remain hidden")
    require(all(float(item.effects.font.height) <= ROOT_LABEL_FONT_MAX_MM and
                float(item.effects.font.width) <= ROOT_LABEL_FONT_MAX_MM
                for item in root.labels),
            "root hidden labels must remain sub-print")

    documents = {document.sheet_name: document for document in model.documents[1:]}
    require(set(documents) == set(EXPECTED_SHEETS),
            f"functional sheet-name drift: {sorted(documents)}")
    root_sheets = {str(item.sheetName.value): item for item in root.sheets}
    spatial_page_order = []
    for sheet in sorted(
        root.sheets,
        key=lambda item: (float(item.position.X), float(item.position.Y)),
    ):
        paths = [path for project in sheet.instances for path in project.paths]
        require(len(paths) == 1, "root sheet must have one project page instance")
        spatial_page_order.append(paths[0].page)
    require(spatial_page_order == [str(page) for page in range(2, 11)],
            f"KiCad spatial PDF page order drift: {spatial_page_order}")
    sheet_refs: dict[str, set[str]] = {}
    total_child_wires = 0
    total_child_labels = 0
    total_child_nc = 0

    for name, expected_sheet in EXPECTED_SHEETS.items():
        document = documents[name]
        schematic = document.schematic
        require(document.path.name == expected_sheet["file"], f"{name}: file binding drift")
        require(schematic.paper.paperSize == "A2" and not schematic.paper.portrait,
                f"{name}: child sheet must use A2 landscape")
        require(schematic.titleBlock is not None and
                "Human-readable hierarchy candidate" in
                schematic.titleBlock.comments.get(1, ""),
                f"{name}: hierarchy/review title control missing")
        require(schematic.titleBlock.title == expected_sheet["title"],
                f"{name}: short printable title drift")
        require(schematic.texts and schematic.graphicalItems,
                f"{name}: readable note or explicit wires missing")
        require(not schematic.globalLabels, f"{name}: global labels are forbidden")
        require(all(not label.effects.hide
                    for labels in (schematic.labels, schematic.hierarchicalLabels)
                    for label in labels),
                f"{name}: functional pin/net labels must remain visible")

        refs = {property_value(item, "Reference") for item in schematic.schematicSymbols}
        require(refs == expected_sheet["refs"],
                f"{name}: ref allocation drift missing={sorted(expected_sheet['refs']-refs)} "
                f"extra={sorted(refs-expected_sheet['refs'])}")
        sheet_refs[name] = refs

        root_sheet = root_sheets[name]
        instance_paths = [path for project in root_sheet.instances for path in project.paths]
        require(len(instance_paths) == 1 and instance_paths[0].page == expected_sheet["page"],
                f"{name}: root page instance drift")
        root_pin_names = {str(pin.name) for pin in root_sheet.pins}
        child_hier_names = {str(label.text) for label in schematic.hierarchicalLabels}
        require(root_pin_names == child_hier_names,
                f"{name}: root pins and child hierarchical labels differ")
        for pin in root_sheet.pins:
            require(root_pin_net(model, pin) == {str(pin.name)},
                    f"{name}.{pin.name}: root sheet pin is not explicitly wired/labeled")

        label_positions = {
            point(label.position.X, label.position.Y)
            for labels in (schematic.labels, schematic.hierarchicalLabels)
            for label in labels
        }
        connected = 0
        nc = 0
        for ref in refs:
            record = model.symbols[ref]
            for number in selected_pins(record.symbol, record.instance.unit or 1):
                at = endpoint(record.instance, record.symbol, number)
                nets = model.pin_nets(ref, number)
                is_nc = model.pin_is_no_connect(ref, number)
                require((len(nets) == 1 and not is_nc) or (not nets and is_nc),
                        f"{ref}.{number}: must resolve to one net or one explicit NC")
                require(at not in label_positions,
                        f"{ref}.{number}: label remains directly on pin")
                connected += int(bool(nets))
                nc += int(is_nc)
            visible = {
                str(item.key): item for item in record.instance.properties
                if str(item.key) in {"Reference", "Value"}
            }
            require(set(visible) == {"Reference", "Value"} and
                    all(not item.effects.hide for item in visible.values()),
                    f"{ref}: visible reference/value field drift")
            require(all(12.7 <= float(item.position.X) <= 581.3 and
                        12.7 <= float(item.position.Y) <= 407.3
                        for item in visible.values()),
                    f"{ref}: visible property escaped A2 printable area")

        current_wires = wire_count(schematic)
        current_labels = (len(schematic.labels) + len(schematic.hierarchicalLabels))
        require(current_wires == connected,
                f"{name}: expected one wire per connected pin ({connected}), got {current_wires}")
        require(current_labels == connected,
                f"{name}: expected one label per connected pin ({connected}), got {current_labels}")
        require(len(schematic.noConnects) == nc,
                f"{name}: explicit NC count drift")
        total_child_wires += current_wires
        total_child_labels += current_labels
        total_child_nc += nc

    allocated = set().union(*sheet_refs.values())
    require(len(allocated) == sum(len(items) for items in sheet_refs.values()) == 248,
            "hierarchy must allocate 248 unique symbols exactly once")

    expected = expected_components()
    require(set(expected) == allocated, "hierarchy component authority set mismatch")
    net_sheets: dict[str, set[str]] = defaultdict(set)
    semantic_rows: list[str] = []
    for ref in sorted(expected, key=natural):
        expected_pins = expected[ref]["pins"]
        record = model.symbols[ref]
        actual_pins = selected_pins(record.symbol, record.instance.unit or 1)
        require(set(actual_pins) == set(expected_pins), f"{ref}: hierarchy pin set drift")
        for number in sorted(expected_pins, key=natural):
            expected_net = str(expected_pins[number]["native"])
            if expected_net == "NC":
                require(model.pin_is_no_connect(ref, number) and
                        not model.pin_nets(ref, number),
                        f"{ref}.{number}: expected NC")
            else:
                require(model.pin_nets(ref, number) == {expected_net},
                        f"{ref}.{number}: hierarchy net drift")
                net_sheets[expected_net].add(record.document.sheet_name)
            semantic_rows.append(f"{ref}|{number}|{expected_net}")

    cross_nets = {net for net, sheets in net_sheets.items() if len(sheets) > 1}
    hierarchical_labels = sum(len(document.schematic.hierarchicalLabels)
                              for document in model.documents[1:])
    participations = sum(len(sheets) for net, sheets in net_sheets.items()
                         if net in cross_nets)
    require(len(cross_nets) == 75, f"cross-sheet net count drift: {len(cross_nets)}")
    require(hierarchical_labels == participations == 168,
            "cross-sheet hierarchical-label participation drift")
    require(len(root.labels) == 168 and wire_count(root) == 168,
            "root cross-sheet connection count drift")
    require(total_child_wires == total_child_labels == 905,
            "connected pin/wire/label count drift")
    require(total_child_nc == 169, "explicit NC count drift")

    board = Board.from_file(str(PCB), encoding="utf-8")
    footprints = {board_ref(item): item for item in board.footprints if board_ref(item)}
    physical_refs = {ref for ref, item in expected.items() if item["on_board"]}
    require(physical_refs <= set(footprints),
            f"PCB is missing schematic refs: {sorted(physical_refs-set(footprints))}")
    logical_pad_numbers = 0
    physical_pad_occurrences = 0
    repeated_logical_pad_numbers = 0
    repeated_pad_map: dict[str, dict[str, int]] = {}
    for ref in sorted(physical_refs, key=natural):
        pads: dict[str, list[object]] = defaultdict(list)
        for pad in footprints[ref].pads:
            if str(pad.number):
                pads[str(pad.number)].append(pad)
        logical_pad_numbers += len(pads)
        physical_pad_occurrences += sum(len(items) for items in pads.values())
        repeated_logical_pad_numbers += sum(
            1 for items in pads.values() if len(items) > 1
        )
        repeated = {
            number: len(items) for number, items in pads.items() if len(items) > 1
        }
        if repeated:
            repeated_pad_map[ref] = repeated
        expected_pins = expected[ref]["pins"]
        require(set(pads) == set(expected_pins), f"{ref}: PCB/schematic pin set mismatch")
        for number, pin in expected_pins.items():
            expected_net = str(pin["native"])
            board_nets = {
                str(pad.net.name) if pad.net is not None else "NC"
                for pad in pads[number]
            }
            require(board_nets == {expected_net},
                    f"{ref}.{number}: PCB {sorted(board_nets)} != hierarchy {expected_net}")
    duplicate_pad_occurrences = physical_pad_occurrences - logical_pad_numbers
    require(logical_pad_numbers == 1066,
            f"logical PCB pad-number count drift: {logical_pad_numbers}")
    require(physical_pad_occurrences == 1077,
            f"physical PCB pad occurrence count drift: {physical_pad_occurrences}")
    require(repeated_logical_pad_numbers == 7,
            f"repeated logical PCB pad-number count drift: {repeated_logical_pad_numbers}")
    require(duplicate_pad_occurrences == 11,
            f"duplicate physical PCB pad occurrence count drift: {duplicate_pad_occurrences}")
    expected_repeated_pad_map = {
        "J6": {"SHIELD": 2},
        "J7": {"SHIELD": 2},
        "J8": {"SHIELD": 2},
        "J9": {"SHIELD": 2},
        "J10": {"SHIELD": 2},
        "J11": {"SHIELD": 4},
        "J12": {"SHIELD": 4},
    }
    require(repeated_pad_map == expected_repeated_pad_map,
            f"repeated physical PCB pad map drift: {repeated_pad_map!r}")

    semantic_sha256 = hashlib.sha256(
        ("\n".join(semantic_rows) + "\n").encode()
    ).hexdigest()
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    hierarchy = status.get("human_readable_hierarchy", {})
    require(hierarchy.get("generator") == "tools/materialize_pcb_main_hierarchy_rev_a.py" and
            hierarchy.get("connectivity_reader") == "tools/pcb_main_schematic_hierarchy.py" and
            hierarchy.get("independent_audit") == "tools/audit_pcb_main_hierarchy_rev_a.py" and
            hierarchy.get("review_record") ==
            "hardware/reviews/PCB_MAIN_HIERARCHY_REVIEW_REV_A.md" and
            (ROOT / hierarchy["review_record"]).is_file(),
            "PCB-MAIN status does not bind the hierarchy toolchain")
    control = hierarchy.get("control", {})
    expected_control = {
        "state": "PASS_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE_"
                 "NATIVE_KICAD_9_ERC_PDF_EVIDENCE_HUMAN_ACCEPTED",
        "pages": 10,
        "functional_child_sheets": 9,
        "symbols": 248,
        "physical_symbols": 247,
        "logical_pad_numbers": 1066,
        "physical_pad_occurrences": 1077,
        "repeated_logical_pad_numbers": 7,
        "duplicate_pad_occurrences": 11,
        "wire_segments": 1073,
        "connected_pin_wires": 905,
        "explicit_nc": 169,
        "cross_sheet_nets": 75,
        "hierarchical_labels": 168,
        "pin_net_semantic_sha256": semantic_sha256,
        "pin_net_review_a_retained": True,
        "native_kicad_9_erc_pass": True,
        "committed_erc_evidence": True,
        "committed_pdf_evidence": True,
        "independent_human_review_complete": True,
        "routing_authorized": False,
        "manufacturing_release": False,
    }
    require(control == expected_control,
            f"PCB-MAIN hierarchy control drift: {control!r} != {expected_control!r}")
    evidence = hierarchy.get("evidence", {})
    require(isinstance(evidence, dict) and evidence.get("status") ==
            "PASS_COMMIT_BOUND_KICAD_9_ERC_PDF_EVIDENCE_HUMAN_ACCEPTED",
            "PCB-MAIN hierarchy evidence status drift")
    for key, expected in {
        "source_commit_sha": "9aceca9531f0b9c18679bee1a8050ae7cd94308a",
        "source_tree_sha": "f77848562f0f2c0ff4965ff8474b582cf49b6885",
        "pcb_native_gate_run":
        "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35136239933",
        "ci_run": "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35136240003",
        "artifact":
        "https://github.com/skif-ops/rs-zs-bpla/actions/runs/35136239933/artifacts/10462359549",
        "artifact_id": 10462359549,
        "artifact_digest":
        "sha256:8839e26a79f17da3deb342e9e4c5009f4b7eb365a0f04c4cb526f7e5051bc697",
        "routing_authorized": False,
        "manufacturing_release": False,
    }.items():
        require(evidence.get(key) == expected,
                f"PCB-MAIN hierarchy evidence {key} drift: "
                f"{evidence.get(key)!r} != {expected!r}")
    require(evidence.get("erc") == {
        "path": "artifacts/kicad-native/PCB-MAIN/erc.json",
        "sha256": "d4dc32aa136be917106a4211734ec9ff0e5db903a268a30b4cd4babb004df5c8",
        "kicad_version": "9.0.9",
        "sheets": 10,
        "violations": 0,
    }, "PCB-MAIN commit-bound ERC evidence drift")
    require(evidence.get("schematic_pdf") == {
        "path": "artifacts/kicad-native/PCB-MAIN/PCB-MAIN_schematic.pdf",
        "sha256": "7e6ef20a989ec66c55b3e1a32de0a914b9e37a6e70cc5835d36f3260b65ff8d9",
        "pages": 10,
        "page_size": "A2",
        "orientation": "landscape",
        "visual_preflight":
        "PASS_ORDERED_1_TO_10_NO_CLIPPING_NO_VISIBLE_DUPLICATE_ROOT_LABELS",
    }, "PCB-MAIN commit-bound PDF evidence drift")
    expected_source_sha256 = {
        "PCB-MAIN.kicad_sch":
        "810a3aa16d88e4179cf84a7bfbfd9c29d1a5d95066a75a6e2517f4d1d30a0918",
        "PCB-MAIN_01_POWER.kicad_sch":
        "4c163f8c88b42a4ffd35e4b6cb27acd32753c1fa2004acb194084997c8de51c0",
        "PCB-MAIN_02_MCU.kicad_sch":
        "e2f13a507e66a9658d65dc628897db0eb824d46216fcefe7f7f8e8b153d8e405",
        "PCB-MAIN_03_AUDIO.kicad_sch":
        "e359b46850186940efd914460eaefa8e6f292d0cddaae91ad92ae1f99d5c2516",
        "PCB-MAIN_04_GNSS.kicad_sch":
        "0741780507d2c4b5907d8ab0b00807eb2b1ecb2becf899e6246d3a4787b1e38c",
        "PCB-MAIN_05_CELLULAR.kicad_sch":
        "b944b2ae8eed85e9436577e62beac1e0fdd6a6831dcc292f2e2bf37058bdecd4",
        "PCB-MAIN_06_LORA.kicad_sch":
        "733c2996581794b49eb7061019c9136c53476750a251e0499e37a849a05db155",
        "PCB-MAIN_07_BLE.kicad_sch":
        "af66b777d65d86645893dd1966b6980045a2c444b9d06e6979bc676cfb72f7fd",
        "PCB-MAIN_08_STORAGE_SENSORS.kicad_sch":
        "24a76c439aa3f7ad22b3f2b761d8458b852b190ea62169647ab0d150a00260aa",
        "PCB-MAIN_09_CONNECTORS_TEST.kicad_sch":
        "fe24ad6ccc93310acd2bede9d9f5839bfa825a857bef9e9319ec1b6ef3ec658d",
    }
    require(evidence.get("schematic_source_sha256") == expected_source_sha256,
            "PCB-MAIN hierarchy evidence source-hash register drift")
    for filename, expected_sha256 in expected_source_sha256.items():
        path = args.schematic.parent / filename
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual_sha256 == expected_sha256,
                f"PCB-MAIN hierarchy evidence source drift: {filename} "
                f"{actual_sha256} != {expected_sha256}")
    require(evidence.get("independent_human_review") == {
        "status": "ACCEPTED_INDEPENDENT_HUMAN_REVIEW",
        "reviewer": "Скиф",
        "date": "2026-09-16",
        "decision": "ACCEPT_HIERARCHY_ONLY",
        "scope": "PCB_MAIN_HUMAN_READABLE_HIERARCHY_ONLY",
        "reviewed_source_commit_sha":
        "9aceca9531f0b9c18679bee1a8050ae7cd94308a",
        "reviewed_pdf_sha256":
        "7e6ef20a989ec66c55b3e1a32de0a914b9e37a6e70cc5835d36f3260b65ff8d9",
    }, "PCB-MAIN hierarchy human-review acceptance record drift")

    report = {
        "status": "PASS_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE",
        "root_sheets": 9,
        "pages": 10,
        "pdf_page_order": [str(page) for page in range(1, 11)],
        "symbols": 248,
        "physical_symbols": 247,
        "logical_pad_numbers": logical_pad_numbers,
        "physical_pad_occurrences": physical_pad_occurrences,
        "repeated_logical_pad_numbers": repeated_logical_pad_numbers,
        "duplicate_pad_occurrences": duplicate_pad_occurrences,
        "repeated_pad_map": repeated_pad_map,
        "wire_segments": 1073,
        "connected_pin_wires": 905,
        "explicit_nc": 169,
        "cross_sheet_nets": 75,
        "hierarchical_labels": 168,
        "pin_net_semantic_sha256": semantic_sha256,
        "erc_native_kicad_9": "PASS_COMMIT_BOUND_ZERO_VIOLATIONS",
        "hierarchy_pdf_evidence": "PASS_COMMIT_BOUND_TEN_PAGE_A2_VISUAL_PREFLIGHT",
        "hierarchy_human_review": "ACCEPTED_SKIF_ACCEPT_HIERARCHY_ONLY",
        "routing_authorized": False,
        "manufacturing_release": False,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PCB-MAIN human-readable hierarchy and electrical-equivalence audit PASS")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
