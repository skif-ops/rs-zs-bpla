#!/usr/bin/env python3
"""Independently audit the unrouted PCB-PWR Rev.A EVT placement candidate."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from kiutils.board import Board
from pcb_pwr_schematic_hierarchy import HierarchicalSchematic

ROOT = Path(__file__).resolve().parents[1]
PCB = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
SCHEMATIC = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_sch"
PLACEMENT = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv"
PASSIVE_AUTHORITY = ROOT / "hardware/PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
OPEN_DIMENSIONS = ROOT / "mechanics/common/OPEN_DIMENSIONS.csv"

EXPECTED_ZONE_COUNTS = Counter({
    "INPUT_PROTECTION": 7, "CURRENT_SENSE": 5, "BUCK_3V8": 16,
    "BUCK_3V3": 13, "AUX_1V8": 4, "CONTROL_INTERFACE": 4,
    "GROUND_JOIN": 3, "DFT_EDGE": 10,
})
EXPECTED_MOUNTS = {
    "H1": (5.0, 5.0),
    "H2": (82.0, 5.0),
    "H3": (68.0, 55.0),
    "H4": (5.0, 55.0),
}
ECO_002_SHA256 = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"
HOT_LOOP_006_SHA256 = "9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0"
SHUNT_BULK_007_SHA256 = "bb17dbead2445bcf4464960a83e13302347ce90463928ab09563afb3f0a3876b"
C13_C12_008_SHA256 = "bb4b5363c9d03daae5b0a81b9f048878aa6d0a38bcb541b24b681f1489b5e71e"
ECO_002_POSES = {
    "U3": (55.0, 14.0, 90.0),
    "U4": (55.0, 42.0, 90.0),
    "C4": (57.8, 14.03, 270.0),
    "C6": (57.8, 42.03, 270.0),
    "C20": (52.35, 14.0, 90.0),
    "C21": (52.35, 42.0, 90.0),
    "L1": (62.5, 14.0, 180.0),
    "L2": (62.5, 42.0, 180.0),
}


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
    if footprint.properties.get("Reference"):
        return str(footprint.properties["Reference"])
    return next((str(item.text) for item in footprint.graphicItems
                 if getattr(item, "type", None) == "reference"), "")


def close(actual: float, expected: float, message: str, tolerance: float = 0.002) -> None:
    require(abs(actual - expected) <= tolerance, f"{message}: {actual} != {expected}")


def main() -> int:
    placements = read_csv(PLACEMENT)
    require(len(placements) == 62, "placement authority must contain exactly 62 rows")
    require(all(all(value.strip() for value in row.values()) for row in placements),
            "placement authority contains a blank field")
    by_ref = {row["RefDes"]: row for row in placements}
    require(len(by_ref) == 62, "duplicate placement RefDes")
    require(all(row["Side"] == "TOP" and row["Placement_Status"].startswith("PROVISIONAL_")
                for row in placements), "placement state must stay provisional and top-side")
    require(Counter(row["Functional_Zone"] for row in placements) == EXPECTED_ZONE_COUNTS,
            "placement functional-zone allocation drift")
    passive_population = {row["RefDes"]: row["Population"]
                          for row in read_csv(PASSIVE_AUTHORITY)}

    model = HierarchicalSchematic(SCHEMATIC)
    expected = {}
    for ref, record in model.symbols.items():
        instance = record.instance
        if not ref or ref.startswith("#"):
            continue
        symbol = record.symbol
        pins = {}
        for number in selected_pins(symbol, instance.unit or 1):
            found = model.pin_nets(ref, number)
            require(len(found) <= 1, f"{ref}.{number}: ambiguous schematic label set {sorted(found)}")
            pins[number] = next(iter(found)) if found else "NC"
        expected[ref] = {
            "value": prop(instance, "Value"), "footprint": prop(instance, "Footprint"),
            "population": "DNP" if instance.dnp else "FITTED", "pins": pins,
        }
    require(len(expected) == 62 and set(expected) == set(by_ref),
            "native schematic and placement physical sets differ")
    require(all(item["footprint"] for item in expected.values()),
            "native schematic still has a blank physical footprint")

    board = Board.from_file(str(PCB), encoding="utf-8")
    board_sha256 = hashlib.sha256(PCB.read_bytes()).hexdigest()
    copper = [layer.name for layer in board.layers if layer.name.endswith(".Cu")]
    require(copper == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
            f"unexpected controlled copper-layer count: {copper}")
    close(float(board.general.thickness), 1.6, "EVT board thickness")
    footprints = {ref_of(item): item for item in board.footprints}
    require(len(footprints) == len(board.footprints) == 66,
            "board must contain 62 electrical and four mounting references")
    require(set(footprints) == set(expected) | set(EXPECTED_MOUNTS),
            "board electrical/mounting reference set differs")

    for ref, wanted in expected.items():
        footprint = footprints[ref]
        row = by_ref[ref]
        wanted_pose = (
            ECO_002_POSES[ref]
            if board_sha256 in {ECO_002_SHA256, HOT_LOOP_006_SHA256, SHUNT_BULK_007_SHA256, C13_C12_008_SHA256} and ref in ECO_002_POSES
            else (float(row["X_mm"]), float(row["Y_mm"]),
                  float(row["Rotation_deg"]) % 360.0)
        )
        close(float(footprint.position.X), wanted_pose[0], f"{ref} X")
        close(float(footprint.position.Y), wanted_pose[1], f"{ref} Y")
        close(float(footprint.position.angle or 0.0) % 360.0,
              wanted_pose[2], f"{ref} rotation", 0.01)
        require(footprint.layer == "F.Cu", f"{ref}: provisional placement must remain top-side")
        require(footprint.libId == wanted["footprint"],
                f"{ref}: footprint binding differs from native schematic")
        population = passive_population.get(ref, "FITTED")
        require(wanted["population"] == ("DNP" if population == "DNP" else "FITTED"),
                f"{ref}: schematic population state differs from authority")
        description = "|".join((
            "DIONEA_PCB_PWR_REV_A",
            f"population={population}",
            f"zone={row['Functional_Zone']}",
            f"placement={row['Placement_Status']}",
            f"authority={row['Source_Authority']}",
        ))
        require(footprint.description == description, f"{ref}: placement metadata drift")
        require(footprint.tags == "DIONEA PCB-PWR EVT DIM-003 ACCEPTED NOT FOR MANUFACTURE",
                f"{ref}: EVT mechanical/release tags drift")
        excluded = population in {"DNP", "PCB_FEATURE"}
        require(footprint.attributes.excludeFromPosFiles is excluded and
                footprint.attributes.excludeFromBom is excluded,
                f"{ref}: BOM/POS exclusion state drift")

        pads: dict[str, list[object]] = defaultdict(list)
        for pad in footprint.pads:
            if pad.number:
                pads[str(pad.number)].append(pad)
        require(set(pads) == set(wanted["pins"]), f"{ref}: board/schematic pin set mismatch")
        for number, net in wanted["pins"].items():
            actual = {pad.net.name if pad.net is not None else "NC" for pad in pads[number]}
            require(actual == {net}, f"{ref}.{number}: board net {sorted(actual)} != {net}")

    for ref, expected_xy in EXPECTED_MOUNTS.items():
        footprint = footprints[ref]
        close(float(footprint.position.X), expected_xy[0], f"{ref} X")
        close(float(footprint.position.Y), expected_xy[1], f"{ref} Y")
        require(footprint.libId == "DioneyaPWR:MountingHole_M3_3.4_EVT",
                f"{ref}: mounting footprint binding differs")
        require(footprint.attributes.boardOnly and
                footprint.attributes.excludeFromPosFiles and
                footprint.attributes.excludeFromBom,
                f"{ref}: board-only/BOM/PnP attributes differ")
        require(len(footprint.pads) == 1, f"{ref}: expected one mounting pad")
        pad = footprint.pads[0]
        require(pad.type == "np_thru_hole" and pad.shape == "circle" and
                abs(float(pad.size.X) - 3.4) <= 0.001 and
                abs(float(pad.size.Y) - 3.4) <= 0.001 and
                pad.drill is not None and
                abs(float(pad.drill.diameter) - 3.4) <= 0.001 and
                abs(float(pad.clearance) - 2.3) <= 0.001,
                f"{ref}: NPTH drill or D8 copper exclusion differs")

    expected_nets = {net for item in expected.values() for net in item["pins"].values() if net != "NC"}
    board_nets = {net.name for net in board.nets if net.number != 0}
    require(board_nets == expected_nets, "board net set differs from native schematic")
    require((len(board.traceItems), len(board.zones)) in
            {(0, 0), (2, 0), (3, 0), (4, 0), (8, 0), (14, 0), (35, 2), (37, 2), (39, 2)},
            "PCB-PWR contains copper beyond the accepted C13-to-C12 008 successor")

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
            (55.0, 14.0, 60.75, 14.0), "3V8 power-stage anchor drift")
    require((float(by_ref["U4"]["X_mm"]), float(by_ref["U4"]["Y_mm"]),
             float(by_ref["L2"]["X_mm"]), float(by_ref["L2"]["Y_mm"])) ==
            (55.0, 42.0, 60.75, 42.0), "3V3 power-stage anchor drift")
    for index in range(1, 11):
        row = by_ref[f"TP{index}"]
        close(float(row["X_mm"]), 25.0 + (index - 1) * 2.54, f"TP{index} pitch")
        close(float(row["Y_mm"]), 56.0, f"TP{index} row")

    dim_rows = {row["ID"]: row for row in read_csv(OPEN_DIMENSIONS)}
    require(dim_rows["DIM-003"]["Status"] ==
            "CLOSED_EVT_ENGINEERING_18_OF_18_ACCEPTED_SERIAL_REVALIDATION_REQUIRED"
            and dim_rows["DIM-003"]["Owner"] == "EE_ME",
            "DIM-003 EVT acceptance state differs")
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    layout = status["native_layout"]
    require(status["manufacturing_release"] is False and
            layout["status"] == "EVT_FITTED_2D_AND_MOUNTING_CLEARANCE_PASS_DIM_003_ACCEPTED" and
            layout["layer_count_authority"] == "hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv" and
            layout["layer_count_status"] == "FROZEN_REV_A_EVT_STACKUP_ACCEPTED" and
            layout["routing_present"] is True and layout["copper_zones_present"] is True and
            layout["cam_export_authorized"] is False and layout["mounting_holes"] == 4 and
            layout["mounting_status"] == "EVT_DIM_003_ACCEPTED_H1_H4_NPTH_3P4",
            "PCB-PWR capture-status interlock drift")

    print("PCB-PWR EVT placement-candidate independent audit PASS")
    print("62 electrical footprints + H1-H4; exact schematic nets; 90x60 four-layer canvas; accepted C13-to-C12 008 successor")
    print("DIM-003 18/18 EVT accepted; DRC/CAM/Review B/manufacturing remain prohibited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
