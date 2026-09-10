#!/usr/bin/env python3
"""Independently audit the PCB-MAIN placement-stage native layout."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from kiutils.board import Board

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_pcb_main_native_schematic_rev_a import expected_components  # noqa: E402

PCB = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
MECH = ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def ref_of(fp) -> str:
    for item in fp.graphicItems:
        if getattr(item, "type", None) == "reference":
            return str(item.text)
    return ""


def main() -> int:
    expected = expected_components()
    expected_on_board = {ref for ref, component in expected.items() if component["on_board"]}
    board = Board.from_file(str(PCB), encoding="utf-8")
    copper = [layer.name for layer in board.layers if layer.name.endswith(".Cu")]
    require(copper == ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"],
            f"unexpected copper stack: {copper}")
    require(abs(board.general.thickness - 1.6) < 1e-6, "board thickness is not 1.6 mm")

    footprints = {ref_of(fp): fp for fp in board.footprints}
    require(len(footprints) == len(board.footprints), "duplicate or blank footprint reference")
    holes = {"H1", "H2", "H3", "H4"}
    require(set(footprints) == expected_on_board | holes,
            f"footprint set mismatch: missing={sorted(expected_on_board-set(footprints))} "
            f"extra={sorted(set(footprints)-expected_on_board-holes)}")

    net_names = {net.name for net in board.nets if net.number != 0}
    expected_nets = {pin["native"] for component in expected.values()
                     for pin in component["pins"].values() if pin["native"] != "NC"}
    require(net_names == expected_nets, "native PCB net set differs from schematic authority")

    for ref in expected_on_board:
        fp = footprints[ref]
        # Unnumbered pads are permitted only as mechanical/paste features and
        # do not participate in the schematic pin contract.
        pads = {pad.number: pad for pad in fp.pads if pad.number}
        wanted = expected[ref]["pins"]
        require(set(pads) == set(wanted), f"{ref}: pad-number set mismatch")
        for number, pin in wanted.items():
            actual = pads[number].net.name if pads[number].net is not None else "NC"
            require(actual == pin["native"], f"{ref}.{number}: {actual} != {pin['native']}")

    locked: dict[str, tuple[float, float, float]] = {}
    with MECH.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["Feature_Type"] in {"CONNECTOR_PLACEMENT", "MODULE_PLACEMENT"}:
                locked[row["RefDes"]] = (float(row["X_mm"]), float(row["Y_mm"]), float(row["Rotation_deg"]))
    for ref, (x, y, angle) in locked.items():
        fp = footprints[ref]
        require(abs(fp.position.X - x) < 0.002 and abs(fp.position.Y - y) < 0.002,
                f"{ref}: locked anchor drift")
        actual_angle = float(fp.position.angle or 0.0) % 360.0
        require(abs(actual_angle - angle) < 0.01, f"{ref}: locked orientation drift")

    edge_items = [item for item in board.graphicItems if getattr(item, "layer", None) == "Edge.Cuts"]
    require(len(edge_items) == 8, f"rounded outline must contain 4 lines + 4 arcs, got {len(edge_items)}")
    require(len(board.traceItems) == 0 and len(board.zones) == 0,
            "candidate unexpectedly contains routing or copper zones")
    provisional = sorted(ref for ref, fp in footprints.items()
                         if fp.properties.get("DIONEA_FOOTPRINT_STATUS") ==
                         "PROVISIONAL_REQUIRES_MANUFACTURER_DRAWING")
    library_pending = sorted(ref for ref, fp in footprints.items()
                             if fp.properties.get("DIONEA_FOOTPRINT_STATUS") ==
                             "KICAD_LIBRARY_PATTERN_REVIEW_PENDING")
    require(provisional, "candidate incorrectly claims every footprint is production-approved")
    require(len(provisional) == 32, f"unexpected provisional-footprint count: {len(provisional)}")
    require(len(library_pending) == 31,
            f"unexpected KiCad-library review count: {len(library_pending)}")
    print("PCB-MAIN layout-candidate audit: PASS")
    print(f"components={len(expected_on_board)} holes=4 nets={len(expected_nets)} layers=6")
    print(f"provisional_footprints={len(provisional)} "
          f"kicad_library_review_pending={len(library_pending)} "
          "routing=ABSENT review_b=BLOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
