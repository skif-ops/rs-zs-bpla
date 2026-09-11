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
FOOTPRINT_REVIEW = ROOT / "hardware/reviews/PCB_MAIN_KICAD_FOOTPRINT_REVIEW_REV_A.csv"


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
        if len(pads) > 1:
            positions = {(round(pad.position.X, 4), round(pad.position.Y, 4)) for pad in pads.values()}
            require(len(positions) > 1, f"{ref}: all logical pads collapse onto one point")

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

    pogo_rows: dict[str, list[dict[str, str]]] = {}
    with MECH.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["Feature_Type"] == "TEST_PAD":
                pogo_rows.setdefault(row["RefDes"], []).append(row)
    for ref, rows in pogo_rows.items():
        fp = footprints[ref]
        require(fp.layer == "B.Cu", f"{ref}: fixture footprint is not bottom-side")
        pads = {pad.number: pad for pad in fp.pads if pad.number}
        for row in rows:
            pad = pads[row["Contact"]]
            actual_x = fp.position.X + pad.position.X
            actual_y = fp.position.Y + pad.position.Y
            require(abs(actual_x - float(row["X_mm"])) < 0.002 and
                    abs(actual_y - float(row["Y_mm"])) < 0.002,
                    f"{ref}.{row['Contact']}: pogo coordinate drift")
            require(abs(pad.size.X - 1.70) < 0.002 and abs(pad.size.Y - 1.70) < 0.002,
                    f"{ref}.{row['Contact']}: pogo copper must be 1.70 mm")
            require(pad.layers == ["B.Cu", "B.Mask"],
                    f"{ref}.{row['Contact']}: pogo layers must exclude paste")
            require(abs(float(pad.solderMaskMargin or 0.0) - 0.20) < 0.002,
                    f"{ref}.{row['Contact']}: pogo mask opening must be 2.10 mm")

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
    library_verified = sorted(ref for ref, fp in footprints.items()
                              if fp.properties.get("DIONEA_FOOTPRINT_STATUS") ==
                              "KICAD_LIBRARY_PATTERN_DRAWING_VERIFIED")
    manufacturer_controlled = sorted(ref for ref, fp in footprints.items()
                                     if fp.properties.get("DIONEA_FOOTPRINT_STATUS") ==
                                     "MANUFACTURER_DRAWING_PATTERN_CONTROLLED")
    require(not provisional, f"manufacturer-specific provisional footprints remain: {provisional}")
    require(len(library_pending) == 36,
            f"unexpected KiCad-library review count: {len(library_pending)}")
    require(library_verified == ["J11", "J_MIC1", "J_MIC2", "J_MIC3", "J_MIC4"],
            f"unexpected drawing-verified KiCad set: {library_verified}")
    require(manufacturer_controlled == ["D3", "D5", "FL1", "J10", "J12", "J13", "J6",
                                        "J7", "J8", "J9", "J_PWR", "U10", "U4", "U5",
                                        "U8", "U9", "X1"],
            f"unexpected manufacturer-controlled set: {manufacturer_controlled}")

    register_rows = list(csv.DictReader(FOOTPRINT_REVIEW.open(encoding="utf-8", newline="")))
    require(len(register_rows) == 19, "KiCad footprint-review register must contain 19 patterns")
    registered: set[str] = set()
    registered_by_status: dict[str, set[str]] = {}
    for row in register_rows:
        refs = {ref for ref in row["References"].split(";") if ref}
        require(len(refs) == int(row["Instances"]),
                f"{row['Library_Source']}: register instance count mismatch")
        require(not registered.intersection(refs),
                f"duplicate references in footprint-review register: {sorted(registered.intersection(refs))}")
        registered.update(refs)
        registered_by_status.setdefault(row["Review_Status"], set()).update(refs)
        expected_status = {
            "PENDING": "KICAD_LIBRARY_PATTERN_REVIEW_PENDING",
            "DRAWING_VERIFIED": "KICAD_LIBRARY_PATTERN_DRAWING_VERIFIED",
            "REPLACED_PROJECT_CONTROLLED": "MANUFACTURER_DRAWING_PATTERN_CONTROLLED",
        }.get(row["Review_Status"])
        require(expected_status is not None,
                f"{row['Library_Source']}: unknown register status")
        for ref in refs:
            require(footprints[ref].properties.get("DIONEA_FOOTPRINT_STATUS") == expected_status,
                    f"{ref}: board/register footprint status mismatch")
            require(footprints[ref].properties.get("DIONEA_FOOTPRINT_SOURCE") == row["Board_Source"],
                    f"{ref}: board/register footprint source mismatch")
    require(len(registered) == 44, "footprint-review register must cover 44 original instances")
    require(registered_by_status.get("PENDING", set()) == set(library_pending),
            "register pending references differ from board")
    require(registered_by_status.get("DRAWING_VERIFIED", set()) == set(library_verified),
            "register verified references differ from board")
    require(registered_by_status.get("REPLACED_PROJECT_CONTROLLED", set()) == {"J8", "J9", "J10"},
            "register project-controlled replacement set differs from board")

    # U.FL copper matches the Hirose mounting pattern.  The manufacturer metal
    # mask is smaller than the KiCad-library paste, so three separate paste-only
    # apertures are required in the controlled local footprint.
    for ref in ("J8", "J9", "J10"):
        pads = footprints[ref].pads
        copper = [pad for pad in pads if pad.number]
        paste = [pad for pad in pads if not pad.number]
        actual_copper = {
            (pad.number, round(pad.position.X, 3), round(pad.position.Y, 3),
             round(pad.size.X, 3), round(pad.size.Y, 3), tuple(pad.layers))
            for pad in copper
        }
        expected_copper = {
            ("1", -1.050, 0.000, 1.050, 1.000, ("F.Cu", "F.Mask")),
            ("SHIELD", 0.475, -1.475, 2.200, 1.050, ("F.Cu", "F.Mask")),
            ("SHIELD", 0.475, 1.475, 2.200, 1.050, ("F.Cu", "F.Mask")),
        }
        require(actual_copper == expected_copper,
                f"{ref}: copper differs from Hirose recommended PCB pattern")
        actual_paste = {
            (round(pad.position.X, 3), round(pad.position.Y, 3),
             round(pad.size.X, 3), round(pad.size.Y, 3), tuple(pad.layers))
            for pad in paste
        }
        expected_paste = {
            (-1.050, 0.000, 0.850, 0.800, ("F.Paste",)),
            (0.475, -1.475, 2.000, 0.900, ("F.Paste",)),
            (0.475, 1.475, 2.000, 0.900, ("F.Paste",)),
        }
        require(actual_paste == expected_paste,
                f"{ref}: apertures differ from Hirose recommended metal mask")

    for ref in ("J_MIC1", "J_MIC2", "J_MIC3", "J_MIC4"):
        logical = {pad.number: pad for pad in footprints[ref].pads if pad.number}
        require(set(logical) == {str(number) for number in range(1, 7)},
                f"{ref}: Pico-Lock six-contact pad set")
        for number, expected_x in enumerate((-3.75, -2.25, -0.75, 0.75, 2.25, 3.75), 1):
            pad = logical[str(number)]
            require(abs(pad.position.X - expected_x) < 0.002 and
                    abs(pad.position.Y + 2.795) < 0.002 and
                    abs(pad.size.X - 0.60) < 0.002 and abs(pad.size.Y - 1.00) < 0.002 and
                    pad.layers == ["F.Cu", "F.Paste", "F.Mask"],
                    f"{ref}.{number}: land differs from Molex 504050-0691 pattern")
        shell = [pad for pad in footprints[ref].pads if not pad.number]
        require(len(shell) == 2 and
                {round(pad.position.X, 3) for pad in shell} == {-6.355, 6.355} and
                all(abs(pad.position.Y - 2.395) < 0.002 and
                    abs(pad.size.X - 1.25) < 0.002 and abs(pad.size.Y - 1.80) < 0.002 and
                    pad.layers == ["F.Cu", "F.Paste", "F.Mask"] for pad in shell),
                f"{ref}: shell lands differ from Molex 504050-0691 pattern")

    j11_pads = [pad for pad in footprints["J11"].pads if pad.number]
    j11_contacts = {pad.number: pad for pad in j11_pads if pad.number != "SHIELD"}
    expected_j11 = {
        "A1": (-3.20, 0.60), "A4": (-2.40, 0.60), "A5": (-1.25, 0.30),
        "A6": (-0.25, 0.30), "A7": (0.25, 0.30), "A8": (1.25, 0.30),
        "A9": (2.40, 0.60), "A12": (3.20, 0.60), "B1": (3.20, 0.60),
        "B4": (2.40, 0.60), "B5": (1.75, 0.30), "B6": (0.75, 0.30),
        "B7": (-0.75, 0.30), "B8": (-1.75, 0.30), "B9": (-2.40, 0.60),
        "B12": (-3.20, 0.60),
    }
    require(set(j11_contacts) == set(expected_j11), "J11: USB4105 contact pad set")
    for number, (x, width) in expected_j11.items():
        pad = j11_contacts[number]
        require(abs(pad.position.X - x) < 0.002 and abs(pad.position.Y + 3.68) < 0.002 and
                abs(pad.size.X - width) < 0.002 and abs(pad.size.Y - 1.15) < 0.002 and
                pad.layers == ["F.Cu", "F.Paste", "F.Mask"],
                f"J11.{number}: land differs from GCT USB4105 Rev B4")
    j11_shell = [pad for pad in j11_pads if pad.number == "SHIELD"]
    actual_j11_shell = {
        (round(pad.position.X, 2), round(pad.position.Y, 3),
         round(pad.size.X, 2), round(pad.size.Y, 2),
         round(pad.drill.diameter, 2), round(pad.drill.width, 2))
        for pad in j11_shell
    }
    expected_j11_shell = {
        (-4.32, -3.105, 1.00, 2.10, 0.60, 1.70),
        (-4.32, 1.075, 1.00, 1.80, 0.60, 1.40),
        (4.32, -3.105, 1.00, 2.10, 0.60, 1.70),
        (4.32, 1.075, 1.00, 1.80, 0.60, 1.40),
    }
    require(actual_j11_shell == expected_j11_shell,
            "J11: shell lands/slots differ from GCT USB4105 Rev B4")
    j11_holes = [pad for pad in footprints["J11"].pads if not pad.number]
    require(len(j11_holes) == 2 and
            {(round(pad.position.X, 2), round(pad.position.Y, 3)) for pad in j11_holes} ==
            {(-2.89, -2.605), (2.89, -2.605)} and
            all(pad.type == "np_thru_hole" and pad.drill is not None and
                abs(pad.drill.diameter - 0.65) < 0.002 for pad in j11_holes),
            "J11: locating holes differ from GCT USB4105 Rev B4")
    for ref in ("D3", "D5"):
        pads = {pad.number: pad for pad in footprints[ref].pads if pad.number}
        require(set(pads) == {"1", "2"}, f"{ref}: SOD962 pad set")
        require(abs(pads["1"].position.X + 0.2) < 0.002 and
                abs(pads["2"].position.X - 0.2) < 0.002,
                f"{ref}: SOD962 pitch must be 0.4 mm")
        for pad in pads.values():
            require(abs(pad.size.X - 0.256) < 0.002 and abs(pad.size.Y - 0.2) < 0.002,
                    f"{ref}: SOD962 land differs from Nexperia Figure 14")
    u4 = {pad.number: pad for pad in footprints["U4"].pads if pad.number}
    require(set(u4) == {"1", "2", "3", "4", "5", "6", "EP"}, "U4: UDFN pad set")
    require(abs(u4["1"].size.X - 0.27) < 0.002 and abs(u4["1"].size.Y - 0.70) < 0.002,
            "U4: lead land differs from ST Figure 10")
    require(abs(u4["EP"].size.X - 1.45) < 0.002 and abs(u4["EP"].size.Y - 0.65) < 0.002,
            "U4: exposed pad differs from ST Figure 10")
    require(abs(abs(u4["1"].position.Y - u4["6"].position.Y) - 1.08) < 0.002,
            "U4: row spacing differs from ST Figure 10")
    u5 = {pad.number: pad for pad in footprints["U5"].pads if pad.number}
    require(set(u5) == {"1", "2", "3", "4", "5", "6", "EP"}, "U5: DCB pad set")
    require(abs(u5["1"].size.X - 0.25) < 0.002 and abs(u5["1"].size.Y - 0.70) < 0.002,
            "U5: lead land differs from LTC drawing 05-08-1715")
    require(abs(u5["EP"].size.X - 1.35) < 0.002 and abs(u5["EP"].size.Y - 1.65) < 0.002,
            "U5: exposed pad differs from LTC drawing 05-08-1715")
    require(abs(abs(u5["1"].position.Y - u5["6"].position.Y) - 2.85) < 0.002,
            "U5: row spacing differs from LTC drawing 05-08-1715")
    x1 = {pad.number: pad for pad in footprints["X1"].pads if pad.number}
    require(set(x1) == {"1", "2", "3", "4"}, "X1: CSP pad set")
    for pad in x1.values():
        require(abs(pad.size.X - 0.25) < 0.002 and abs(pad.size.Y - 0.25) < 0.002,
                "X1: NSMD land diameter differs from SiTime POD-35 Rev A")
        require(abs(float(pad.solderMaskMargin or 0.0) - 0.05) < 0.002,
                "X1: solder-mask opening must be 0.35 mm")
    require(abs(abs(x1["1"].position.X - x1["2"].position.X) - 1.00) < 0.002,
            "X1: column pitch differs from SiTime POD-35 Rev A")
    require(abs(abs(x1["1"].position.Y - x1["4"].position.Y) - 0.41) < 0.002,
            "X1: row pitch differs from SiTime POD-35 Rev A")
    require(x1["1"].position.X < x1["2"].position.X and
            x1["4"].position.X < x1["3"].position.X and
            x1["4"].position.Y < x1["1"].position.Y,
            "X1: bottom-view pin order differs from SiTime POD-35 Rev A")
    u9 = {pad.number: pad for pad in footprints["U9"].pads if pad.number}
    require(set(u9) == {str(n) for n in range(1, 19)}, "U9: LCC-18 pad set")
    for number, pad in u9.items():
        expected_width = 0.70 if number in {"1", "9", "10", "18"} else 0.80
        require(abs(pad.size.X - expected_width) < 0.002 and abs(pad.size.Y - 1.80) < 0.002,
                f"U9.{number}: copper land differs from u-blox Table 44")
        require(pad.layers == ["F.Cu", "F.Mask"],
                f"U9.{number}: copper/mask layers must leave process-specific paste open")
    require(abs(u9["1"].position.Y - 4.75) < 0.002 and
            abs(u9["10"].position.Y + 4.75) < 0.002,
            "U9: row spacing differs from u-blox Figure 30")
    require(all(abs(abs(u9[str(n)].position.X - u9[str(n + 1)].position.X) - 1.10) < 0.002
                for n in range(1, 9)), "U9: lower-row pitch differs from u-blox Figure 30")
    require(u9["1"].position.X < u9["9"].position.X and
            u9["10"].position.X > u9["18"].position.X,
            "U9: pin order differs from u-blox Figure 30")
    u10 = {pad.number: pad for pad in footprints["U10"].pads if pad.number}
    require(set(u10) == {str(n) for n in range(1, 23)}, "U10: castellated pad set")
    for number, pad in u10.items():
        require(abs(pad.size.X - 0.90) < 0.002 and abs(pad.size.Y - 0.80) < 0.002,
                f"U10.{number}: bottom land differs from Ebyte section 3.2")
    require(abs(u10["1"].position.X - 7.45) < 0.002 and
            abs(u10["22"].position.X + 7.45) < 0.002,
            "U10: row position differs from 14 mm module and 0.9 mm bottom pad")
    require(abs(u10["1"].position.Y - 9.00) < 0.002 and
            abs(u10["11"].position.Y + 8.00) < 0.002,
            "U10: end offsets differ from Ebyte section 3.2")
    require(abs(abs(u10["1"].position.Y - u10["2"].position.Y) - 1.27) < 0.002 and
            abs(abs(u10["3"].position.Y - u10["4"].position.Y) - 5.57) < 0.002,
            "U10: 1.27/5.57 mm pitch contract drift")
    require(u10["21"].position.X < 0 and abs(u10["21"].position.Y - 7.73) < 0.002,
            "U10: ANT pad 21 position differs from Ebyte section 3.2")
    fl1 = {pad.number: pad for pad in footprints["FL1"].pads if pad.number}
    require(set(fl1) == {"A", "B", "C", "D", "E"}, "FL1: 1109-5 pad set")
    for number, pad in fl1.items():
        require(abs(pad.size.X - 0.300) < 0.002 and abs(pad.size.Y - 0.250) < 0.002,
                f"FL1.{number}: land size differs from Abracon recommended pattern")
    expected_fl1 = {
        "A": (0.375, 0.250), "B": (0.000, 0.250), "C": (-0.375, 0.000),
        "D": (0.000, -0.250), "E": (0.375, -0.250),
    }
    for number, (x, y) in expected_fl1.items():
        require(abs(fl1[number].position.X - x) < 0.002 and
                abs(fl1[number].position.Y - y) < 0.002,
                f"FL1.{number}: coordinate differs from Abracon recommended pattern")
    for ref in ("J6", "J7"):
        pads = [pad for pad in footprints[ref].pads if pad.number]
        logical = {pad.number for pad in pads}
        require(logical == {"1", "2", "3", "4", "5", "6", "7", "SHIELD"},
                f"{ref}: TE 2336582-1 logical pad set")
        contacts = {pad.number: pad for pad in pads if pad.number not in {"SHIELD"}}
        expected_x = {"3": -3.175, "6": -1.905, "2": -0.635,
                      "5": 0.635, "1": 1.905, "4": 3.175}
        for number, x in expected_x.items():
            pad = contacts[number]
            require(abs(pad.position.X - x) < 0.002 and abs(pad.position.Y + 5.43) < 0.002,
                    f"{ref}.{number}: contact coordinate differs from TE C-2336582 A2")
            require(abs(pad.size.X - 0.80) < 0.002 and abs(pad.size.Y - 1.14) < 0.002,
                    f"{ref}.{number}: contact land differs from TE C-2336582 A2")
        cd = contacts["7"]
        require(abs(cd.position.X - 4.125) < 0.002 and abs(cd.size.X - 0.95) < 0.002,
                f"{ref}.7: card-detect land differs from TE C-2336582 A2")
        shield = [pad for pad in pads if pad.number == "SHIELD"]
        require(len(shield) == 2 and all(abs(pad.size.X - 1.50) < 0.002 and
                                        abs(pad.size.Y - 2.10) < 0.002 for pad in shield),
                f"{ref}: shell lands differ from TE C-2336582 A2")
        holes = [pad for pad in footprints[ref].pads if not pad.number]
        require(len(holes) == 6 and all(abs(pad.size.X - 1.20) < 0.002 and
                                        abs(pad.size.Y - 1.20) < 0.002 for pad in holes),
                f"{ref}: tooling-hole pattern differs from TE C-2336582 A2")

    j12_pads = [pad for pad in footprints["J12"].pads if pad.number]
    require({pad.number for pad in j12_pads} ==
            {"1", "2", "3", "4", "5", "6", "7", "8", "CD", "SHIELD"},
            "J12: MEM2052 logical pad set")
    j12_contacts = {pad.number: pad for pad in j12_pads if pad.number != "SHIELD"}
    expected_j12 = {
        "1": (1.905, 3.635, 0.80, 1.50), "2": (0.805, 3.235, 0.80, 1.50),
        "3": (-0.295, 3.635, 0.80, 1.50), "4": (-1.395, 3.835, 0.80, 1.50),
        "5": (-2.495, 3.635, 0.80, 1.50), "6": (-3.595, 3.835, 0.80, 1.50),
        "7": (-4.695, 3.635, 0.80, 1.50), "8": (-5.795, 3.635, 0.80, 1.50),
        "CD": (-3.585, -7.595, 1.00, 1.04),
    }
    for number, (x, y, sx, sy) in expected_j12.items():
        pad = j12_contacts[number]
        require(abs(pad.position.X - x) < 0.002 and abs(pad.position.Y - y) < 0.002 and
                abs(pad.size.X - sx) < 0.002 and abs(pad.size.Y - sy) < 0.002,
                f"J12.{number}: land differs from GCT MEM2052 drawing")
    expected_j12_shield = {
        (-6.575, 5.925, 1.40, 1.90), (-5.035, -7.225, 1.20, 1.40),
        (0.715, -7.225, 1.30, 1.40), (6.575, 6.925, 1.40, 1.90),
    }
    actual_j12_shield = {
        (round(pad.position.X, 3), round(pad.position.Y, 3),
         round(pad.size.X, 2), round(pad.size.Y, 2))
        for pad in j12_pads if pad.number == "SHIELD"
    }
    require(actual_j12_shield == expected_j12_shield,
            "J12: shell lands differ from GCT MEM2052 drawing")

    j13 = {pad.number: pad for pad in footprints["J13"].pads if pad.number}
    require(set(j13) == {"1", "2"}, "J13: Pico-Lock logical pad set")
    for number, x in {"1": -0.75, "2": 0.75}.items():
        pad = j13[number]
        require(abs(pad.position.X - x) < 0.002 and abs(pad.position.Y + 2.795) < 0.002 and
                abs(pad.size.X - 0.60) < 0.002 and abs(pad.size.Y - 1.00) < 0.002,
                f"J13.{number}: land differs from Molex 504050-0291 drawing")
    j13_shell = [pad for pad in footprints["J13"].pads if not pad.number]
    require(len(j13_shell) == 2 and
            {round(pad.position.X, 3) for pad in j13_shell} == {-3.355, 3.355} and
            all(abs(pad.position.Y - 2.395) < 0.002 and
                abs(pad.size.X - 1.25) < 0.002 and abs(pad.size.Y - 1.80) < 0.002
                for pad in j13_shell),
            "J13: shell lands differ from Molex 504050-0291 drawing")

    jpwr = {pad.number: pad for pad in footprints["J_PWR"].pads if pad.number}
    require(set(jpwr) == {str(number) for number in range(1, 13)},
            "J_PWR: Micro-Fit logical pad set")
    for number in range(1, 13):
        pad = jpwr[str(number)]
        expected_x = 3.0 * ((number - 1) % 6)
        expected_y = 0.0 if number <= 6 else 3.0
        require(abs(pad.position.X - expected_x) < 0.002 and
                abs(pad.position.Y - expected_y) < 0.002 and
                abs(pad.size.X - 1.50) < 0.002 and abs(pad.size.Y - 1.50) < 0.002 and
                pad.drill is not None and abs(pad.drill.diameter - 1.02) < 0.002,
                f"J_PWR.{number}: hole/land differs from Molex 43045-1202 drawing")
    jpwr_holes = [pad for pad in footprints["J_PWR"].pads if not pad.number]
    require(len(jpwr_holes) == 2 and
            {(round(pad.position.X, 2), round(pad.position.Y, 2)) for pad in jpwr_holes} ==
            {(2.15, -4.32), (12.85, -4.32)} and
            all(pad.type == "np_thru_hole" and pad.drill is not None and
                abs(pad.drill.diameter - 3.00) < 0.002 for pad in jpwr_holes),
            "J_PWR: locator holes differ from Molex 43045-1202 drawing")

    u8 = {pad.number: pad for pad in footprints["U8"].pads if pad.number}
    require(set(u8) == {str(number) for number in range(1, 103)}, "U8: BG95 pad set")
    outer_expected: dict[int, tuple[float, float, float, float]] = {}
    left_y = [-9.7 + 1.1 * index for index in range(10)] + [1.9 + 1.1 * index for index in range(8)]
    outer_expected.update({number: (-9.15, y, 1.10, 0.70)
                           for number, y in enumerate(left_y, 1)})
    top_x = [-7.45 + 1.1 * index for index in range(6)] + [0.55 + 1.1 * index for index in range(7)]
    outer_expected.update({number: (x, 11.00, 0.70, 1.10)
                           for number, x in enumerate(top_x, 19)})
    right_y = [9.6 - 1.1 * index for index in range(8)] + [0.2 - 1.1 * index for index in range(10)]
    outer_expected.update({number: (9.15, y, 1.10, 0.70)
                           for number, y in enumerate(right_y, 32)})
    bottom_x = [7.15 - 1.1 * index for index in range(7)] + [-1.95 - 1.1 * index for index in range(6)]
    outer_expected.update({number: (x, -11.00, 0.70, 1.10)
                           for number, x in enumerate(bottom_x, 50)})
    inner_expected = {
        63: (-5.95, -4.25), 64: (-5.95, -2.55), 65: (-5.95, -0.85),
        66: (-5.95, 0.85), 67: (-5.95, 2.55), 68: (-5.95, 4.25),
        69: (-2.55, 7.65), 70: (-0.85, 7.65), 71: (0.85, 7.65), 72: (2.55, 7.65),
        73: (5.95, 4.25), 74: (5.95, 2.55), 75: (5.95, 0.85),
        76: (5.95, -0.85), 77: (5.95, -2.55), 78: (5.95, -4.25),
        79: (2.55, -7.65), 80: (0.85, -7.65), 81: (-0.85, -7.65), 82: (-2.55, -7.65),
        83: (-4.25, -4.25), 84: (-4.25, -2.55), 85: (-4.25, -0.85),
        86: (-4.25, 0.85), 87: (-4.25, 2.55), 88: (-4.25, 4.25),
        89: (-2.55, 5.95), 90: (-0.85, 5.95), 91: (0.85, 5.95), 92: (2.55, 5.95),
        93: (4.25, 4.25), 94: (4.25, 2.55), 95: (4.25, 0.85),
        96: (4.25, -0.85), 97: (4.25, -2.55), 98: (4.25, -4.25),
        99: (2.55, -5.95), 100: (0.85, -5.95), 101: (-0.85, -5.95), 102: (-2.55, -5.95),
    }
    for number, (x, y, sx, sy) in outer_expected.items():
        pad = u8[str(number)]
        require(abs(pad.position.X - x) < 0.002 and abs(pad.position.Y - y) < 0.002 and
                abs(pad.size.X - sx) < 0.002 and abs(pad.size.Y - sy) < 0.002,
                f"U8.{number}: outer land differs from Quectel Figure 46")
    for number, (x, y) in inner_expected.items():
        pad = u8[str(number)]
        require(abs(pad.position.X - x) < 0.002 and abs(pad.position.Y - y) < 0.002 and
                abs(pad.size.X - 1.00) < 0.002 and abs(pad.size.Y - 1.00) < 0.002,
                f"U8.{number}: inner land differs from Quectel Figure 46")
    u8_courtyard = [item for item in footprints["U8"].graphicItems
                    if getattr(item, "layer", None) == "F.CrtYd"]
    require(len(u8_courtyard) == 1 and
            abs(u8_courtyard[0].start.X + 12.95) < 0.002 and
            abs(u8_courtyard[0].start.Y + 14.80) < 0.002 and
            abs(u8_courtyard[0].end.X - 12.95) < 0.002 and
            abs(u8_courtyard[0].end.Y - 14.80) < 0.002,
            "U8: courtyard must retain Quectel's 3 mm adjacent-component clearance")
    print("PCB-MAIN layout-candidate audit: PASS")
    print(f"components={len(expected_on_board)} holes=4 nets={len(expected_nets)} layers=6")
    print(f"provisional_footprints={len(provisional)} "
          f"kicad_library_review_pending={len(library_pending)} "
          f"kicad_library_drawing_verified={len(library_verified)} "
          f"manufacturer_controlled={len(manufacturer_controlled)} "
          "routing=ABSENT review_b=BLOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
