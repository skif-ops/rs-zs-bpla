#!/usr/bin/env python3
"""Independently audit the unrouted PCB-PWR Rev.A placement candidate."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from kiutils.board import Board
from kiutils.schematic import Schematic

ROOT = Path(__file__).resolve().parents[1]
PCB = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
SCHEMATIC = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_sch"
PLACEMENT = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
OPEN_DIMENSIONS = ROOT / "mechanics/common/OPEN_DIMENSIONS.csv"

EXPECTED_ZONE_COUNTS = Counter({
    "INPUT_PROTECTION": 7, "CURRENT_SENSE": 5, "BUCK_3V8": 15,
    "BUCK_3V3": 12, "AUX_1V8": 4, "CONTROL_INTERFACE": 4,
    "GROUND_JOIN": 3, "DFT_EDGE": 10,
})


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def prop(symbol, key: str) -> str:
    return next((item.value for item in symbol.properties if item.key == key), "")


def selected_pins(symbol, unit: int = 1) -> dict[str, object]:
    found: dict[str, object] = {}

    def visit(node, active: bool) -> None:
        node_active = active
        if node is not symbol:
            node_active = (node.unitId in (None, 0, unit)) and (node.styleId in (None, 1))
        if node_active:
            for pin in node.pins:
                found[str(pin.number)] = pin
        for child in node.units:
            visit(child, node_active)

    visit(symbol, True)
    return found


def endpoint(instance, symbol, pin_number: str) -> tuple[float, float]:
    pin = selected_pins(symbol, instance.unit or 1)[pin_number]
    return (round(instance.position.X + pin.position.X, 4),
            round(instance.position.Y - pin.position.Y, 4))


def ref_of(footprint) -> str:
    return next((str(item.text) for item in footprint.graphicItems
                 if getattr(item, "type", None) == "reference"), "")


def close(actual: float, expected: float, message: str, tolerance: float = 0.002) -> None:
    require(abs(actual - expected) <= tolerance, f"{message}: {actual} != {expected}")


def main() -> int:
    placements = read_csv(PLACEMENT)
    require(len(placements) == 60, "placement authority must contain exactly 60 rows")
    require(all(all(value.strip() for value in row.values()) for row in placements),
            "placement authority contains a blank field")
    by_ref = {row["RefDes"]: row for row in placements}
    require(len(by_ref) == 60, "duplicate placement RefDes")
    require(all(row["Side"] == "TOP" and row["Placement_Status"].startswith("PROVISIONAL_")
                for row in placements), "placement state must stay provisional and top-side")
    require(Counter(row["Functional_Zone"] for row in placements) == EXPECTED_ZONE_COUNTS,
            "placement functional-zone allocation drift")

    schematic = Schematic.from_file(str(SCHEMATIC), encoding="utf-8")
    libraries = {item.libId: item for item in schematic.libSymbols}
    labels: dict[tuple[float, float], set[str]] = defaultdict(set)
    for label in schematic.labels:
        labels[(round(label.position.X, 4), round(label.position.Y, 4))].add(str(label.text))
    expected = {}
    for instance in schematic.schematicSymbols:
        ref = prop(instance, "Reference")
        if not ref or ref.startswith("#"):
            continue
        symbol = libraries[instance.libId]
        pins = {}
        for number in selected_pins(symbol, instance.unit or 1):
            found = labels.get(endpoint(instance, symbol, number), set())
            require(len(found) <= 1, f"{ref}.{number}: ambiguous schematic label set {sorted(found)}")
            pins[number] = next(iter(found)) if found else "NC"
        expected[ref] = {
            "value": prop(instance, "Value"), "footprint": prop(instance, "Footprint"),
            "population": "DNP" if instance.dnp else "FITTED", "pins": pins,
        }
    require(len(expected) == 60 and set(expected) == set(by_ref),
            "native schematic and placement physical sets differ")
    require(all(item["footprint"] for item in expected.values()),
            "native schematic still has a blank physical footprint")

    board = Board.from_file(str(PCB), encoding="utf-8")
    copper = [layer.name for layer in board.layers if layer.name.endswith(".Cu")]
    require(copper == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
            f"unexpected provisional copper stack: {copper}")
    close(float(board.general.thickness), 1.6, "provisional board thickness")
    footprints = {ref_of(item): item for item in board.footprints}
    require(len(footprints) == len(board.footprints) == 60, "board must contain 60 unique references")
    require(set(footprints) == set(expected), "board and schematic reference sets differ")

    for ref, wanted in expected.items():
        footprint = footprints[ref]
        row = by_ref[ref]
        close(float(footprint.position.X), float(row["X_mm"]), f"{ref} X")
        close(float(footprint.position.Y), float(row["Y_mm"]), f"{ref} Y")
        close(float(footprint.position.angle or 0.0) % 360.0,
              float(row["Rotation_deg"]) % 360.0, f"{ref} rotation", 0.01)
        require(footprint.layer == "F.Cu", f"{ref}: provisional placement must remain top-side")
        require(footprint.properties.get("DIONEA_FOOTPRINT_BINDING") == wanted["footprint"],
                f"{ref}: footprint binding differs from native schematic")
        require(footprint.properties.get("DIONEA_FUNCTIONAL_ZONE") == row["Functional_Zone"],
                f"{ref}: functional zone drift")
        require(footprint.properties.get("DIONEA_PLACEMENT_STATUS") == row["Placement_Status"],
                f"{ref}: provisional status drift")
        population = footprint.properties.get("DIONEA_POPULATION")
        if wanted["population"] == "DNP":
            require(population == "DNP", f"{ref}: DNP state drift")
        else:
            require(population in {"FITTED", "PCB_FEATURE"}, f"{ref}: population state drift")

        pads: dict[str, list[object]] = defaultdict(list)
        for pad in footprint.pads:
            if pad.number:
                pads[str(pad.number)].append(pad)
        require(set(pads) == set(wanted["pins"]), f"{ref}: board/schematic pin set mismatch")
        for number, net in wanted["pins"].items():
            actual = {pad.net.name if pad.net is not None else "NC" for pad in pads[number]}
            require(actual == {net}, f"{ref}.{number}: board net {sorted(actual)} != {net}")

    expected_nets = {net for item in expected.values() for net in item["pins"].values() if net != "NC"}
    board_nets = {net.name for net in board.nets if net.number != 0}
    require(board_nets == expected_nets, "board net set differs from native schematic")
    require(len(board.traceItems) == 0 and len(board.zones) == 0,
            "provisional placement candidate contains routing or copper zones")

    edges = [item for item in board.graphicItems if getattr(item, "layer", None) == "Edge.Cuts"]
    require(len(edges) == 4, "provisional outline must contain four line segments")
    endpoints = {((round(item.start.X, 3), round(item.start.Y, 3)),
                  (round(item.end.X, 3), round(item.end.Y, 3))) for item in edges}
    wanted_edges = {((0.0, 0.0), (90.0, 0.0)), ((90.0, 0.0), (90.0, 60.0)),
                    ((90.0, 60.0), (0.0, 60.0)), ((0.0, 60.0), (0.0, 0.0))}
    require(endpoints == wanted_edges, "provisional 90 x 60 mm outline drift")

    require((float(by_ref["J1"]["X_mm"]), float(by_ref["J2"]["X_mm"])) == (6.0, 90.0),
            "input/harness edge-anchor intent drift")
    require((float(by_ref["U3"]["X_mm"]), float(by_ref["U3"]["Y_mm"]),
             float(by_ref["L1"]["X_mm"]), float(by_ref["L1"]["Y_mm"])) ==
            (55.0, 14.0, 62.0, 14.0), "3V8 power-stage anchor drift")
    require((float(by_ref["U4"]["X_mm"]), float(by_ref["U4"]["Y_mm"]),
             float(by_ref["L2"]["X_mm"]), float(by_ref["L2"]["Y_mm"])) ==
            (55.0, 42.0, 62.0, 42.0), "3V3 power-stage anchor drift")
    for index in range(1, 11):
        row = by_ref[f"TP{index}"]
        close(float(row["X_mm"]), 25.0 + (index - 1) * 2.54, f"TP{index} pitch")
        close(float(row["Y_mm"]), 56.0, f"TP{index} row")

    dim_rows = {row["ID"]: row for row in read_csv(OPEN_DIMENSIONS)}
    require(dim_rows["DIM-003"]["Status"] == "OPEN" and dim_rows["DIM-003"]["Owner"] == "EE",
            "DIM-003 must remain an open EE blocker")
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    layout = status["native_layout"]
    require(status["manufacturing_release"] is False and
            layout["status"] == "PROVISIONAL_PLACEMENT_CANVAS_DIM_003_OPEN" and
            layout["routing_present"] is False and layout["copper_zones_present"] is False and
            layout["cam_export_authorized"] is False and layout["mounting_holes"] == 0,
            "PCB-PWR capture-status interlock drift")

    print("PCB-PWR provisional placement-candidate independent audit PASS")
    print("60 footprints; exact schematic nets; 90x60 four-layer canvas; routing/zones/holes absent")
    print("DIM-003 OPEN; DRC/CAM/Review B/manufacturing remain prohibited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
