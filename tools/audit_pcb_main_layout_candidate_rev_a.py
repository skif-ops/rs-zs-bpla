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
    require(len(library_pending) == 3,
            f"unexpected KiCad-library review count: {len(library_pending)}")
    require(library_verified == ["J11", "J_MIC1", "J_MIC2", "J_MIC3", "J_MIC4"],
            f"unexpected drawing-verified KiCad set: {library_verified}")
    require(manufacturer_controlled == ["C36", "C44", "D1", "D10", "D11", "D2", "D3", "D4", "D5", "D6", "D7",
                                        "D8", "D9", "FL1", "J10", "J12", "J13", "J6",
                                        "J7", "J8", "J9", "J_PWR", "Q1", "Q2", "Q3", "Q4",
                                        "U1", "U10", "U11", "U13", "U14", "U15", "U16",
                                        "U17", "U18", "U19", "U20", "U21",
                                        "U22", "U23", "U24", "U27", "U3", "U4", "U5",
                                        "U6", "U7", "U8", "U9", "X1"],
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
    require(registered_by_status.get("REPLACED_PROJECT_CONTROLLED", set()) ==
            {"J8", "J9", "J10", "U1", "U3", "U7", "U11", "U13", "U14", "U15", "U16", "U17",
             "U18", "U19", "U20", "U21", "U22", "U23", "U24", "U27",
             "D1", "D2", "D4", "D6", "D7", "D8", "D9", "D10", "D11",
             "Q1", "Q2", "Q3", "Q4", "U6", "C36", "C44"},
            "register project-controlled replacement set differs from board")

    # KEMET/YAGEO T2076 Table 2 defines the D / 7343-31 Density Level B
    # nominal robust-reflow pattern: W=2.43, L=2.37, S=3.87 mm and a
    # 9.12 x 5.10 mm courtyard.  S + L yields 6.24 mm between land centers.
    for ref in ("C36", "C44"):
        pads = {pad.number: pad for pad in footprints[ref].pads if pad.number}
        require(set(pads) == {"1", "2"}, f"{ref}: KEMET D-case pad set")
        for number, x in (("1", -3.12), ("2", 3.12)):
            pad = pads[number]
            require(abs(pad.position.X - x) < 0.002 and
                    abs(pad.position.Y) < 0.002 and
                    abs(pad.size.X - 2.37) < 0.002 and
                    abs(pad.size.Y - 2.43) < 0.002 and
                    pad.shape == "rect" and
                    pad.layers == ["F.Cu", "F.Paste", "F.Mask"],
                    f"{ref}.{number}: land differs from KEMET T2076 Density B")
        courtyard = [item for item in footprints[ref].graphicItems
                     if getattr(item, "layer", None) == "F.CrtYd"]
        require(len(courtyard) == 1 and
                abs(courtyard[0].start.X + 4.56) < 0.002 and
                abs(courtyard[0].start.Y + 2.55) < 0.002 and
                abs(courtyard[0].end.X - 4.56) < 0.002 and
                abs(courtyard[0].end.Y - 2.55) < 0.002,
                f"{ref}: courtyard differs from KEMET T2076 Density B")

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

    # STM32U585 DS13086 Rev 10 Figure 96 defines the 1L LQFP100 example:
    # 1.2 x 0.3 mm rectangular lands on 0.5 mm pitch, 16.7 mm outer and
    # 14.3 mm inner spans.  This independently yields +/-7.75 mm centers.
    expected_u1: dict[str, tuple[float, float, float, float]] = {}
    for number in range(1, 26):
        expected_u1[str(number)] = (-7.75, -6.0 + (number - 1) * 0.5, 1.2, 0.3)
    for number in range(26, 51):
        expected_u1[str(number)] = (-6.0 + (number - 26) * 0.5, 7.75, 0.3, 1.2)
    for number in range(51, 76):
        expected_u1[str(number)] = (7.75, 6.0 - (number - 51) * 0.5, 1.2, 0.3)
    for number in range(76, 101):
        expected_u1[str(number)] = (6.0 - (number - 76) * 0.5, -7.75, 0.3, 1.2)
    u1 = {pad.number: pad for pad in footprints["U1"].pads if pad.number}
    require(set(u1) == set(expected_u1), "U1: STM32U585 LQFP100 pad set")
    for number, (x, y, sx, sy) in expected_u1.items():
        pad = u1[number]
        require(abs(pad.position.X - x) < 0.002 and abs(pad.position.Y - y) < 0.002 and
                abs(pad.size.X - sx) < 0.002 and abs(pad.size.Y - sy) < 0.002 and
                pad.shape == "rect" and pad.layers == ["F.Cu", "F.Paste", "F.Mask"],
                f"U1.{number}: land differs from DS13086 Rev 10 Figure 96")

    # TI PW0014A 4220202/B and PW0024A 4220208/A give the complete example
    # board layouts: 1.50 x 0.45 mm R0.05 lands on 0.65 mm pitch, 5.80 mm
    # between row centers, equal-size stencil apertures, and preferred NSMD
    # openings up to 0.05 mm per side.
    expected_u17: dict[str, tuple[float, float]] = {}
    for number in range(1, 8):
        expected_u17[str(number)] = (-2.90, -1.95 + (number - 1) * 0.65)
    for number in range(8, 15):
        expected_u17[str(number)] = (2.90, 1.95 - (number - 8) * 0.65)
    u17 = {pad.number: pad for pad in footprints["U17"].pads if pad.number}
    require(set(u17) == set(expected_u17), "U17: TI PW0014A pad set")
    for number, (x, y) in expected_u17.items():
        pad = u17[number]
        require(abs(pad.position.X - x) < 0.002 and abs(pad.position.Y - y) < 0.002 and
                abs(pad.size.X - 1.50) < 0.002 and abs(pad.size.Y - 0.45) < 0.002 and
                pad.shape == "roundrect" and
                pad.layers == ["F.Cu", "F.Paste", "F.Mask"] and
                abs(float(pad.solderMaskMargin or 0.0) - 0.05) < 0.002,
                f"U17.{number}: land differs from TI PW0014A 4220202/B")

    expected_pw24: dict[str, tuple[float, float]] = {}
    for number in range(1, 13):
        expected_pw24[str(number)] = (-2.90, -3.575 + (number - 1) * 0.65)
    for number in range(13, 25):
        expected_pw24[str(number)] = (2.90, 3.575 - (number - 13) * 0.65)
    for ref in ("U7", "U13", "U16"):
        pads = {pad.number: pad for pad in footprints[ref].pads if pad.number}
        require(set(pads) == set(expected_pw24), f"{ref}: TI PW0024A pad set")
        for number, (x, y) in expected_pw24.items():
            pad = pads[number]
            require(abs(pad.position.X - x) < 0.002 and
                    abs(pad.position.Y - y) < 0.002 and
                    abs(pad.size.X - 1.50) < 0.002 and
                    abs(pad.size.Y - 0.45) < 0.002 and
                    pad.shape == "roundrect" and
                    pad.layers == ["F.Cu", "F.Paste", "F.Mask"] and
                    abs(float(pad.solderMaskMargin or 0.0) - 0.05) < 0.002,
                    f"{ref}.{number}: land differs from TI PW0024A 4220208/A")

    # TI DRL0006A 4223266/F defines the complete board/stencil layout:
    # 0.67 x 0.30 mm R0.05 lands, 0.50 mm pitch, 1.48 mm between row
    # centers, equal-size apertures and a preferred +0.05 mm NSMD opening.
    expected_u18 = {
        "1": (-0.74, -0.50), "2": (-0.74, 0.00), "3": (-0.74, 0.50),
        "4": (0.74, 0.50), "5": (0.74, 0.00), "6": (0.74, -0.50),
    }
    u18 = {pad.number: pad for pad in footprints["U18"].pads if pad.number}
    require(set(u18) == set(expected_u18), "U18: TI DRL0006A pad set")
    for number, (x, y) in expected_u18.items():
        pad = u18[number]
        require(abs(pad.position.X - x) < 0.002 and
                abs(pad.position.Y - y) < 0.002 and
                abs(pad.size.X - 0.67) < 0.002 and
                abs(pad.size.Y - 0.30) < 0.002 and
                pad.shape == "roundrect" and
                abs(float(pad.roundrectRatio or 0.0) - (1 / 3)) < 0.002 and
                pad.layers == ["F.Cu", "F.Paste", "F.Mask"] and
                abs(float(pad.solderMaskMargin or 0.0) - 0.05) < 0.002,
                f"U18.{number}: land differs from TI DRL0006A 4223266/F")

    # TI DQA0010A 4220328/A defines 0.565 mm land length, 0.835 mm row
    # separation and 0.50 mm pitch.  Signal lands are 0.20 mm wide; GND
    # lands 3/8 are 0.40 mm wide with separate 0.36 mm stencil apertures.
    expected_dqa = {
        "1": (-0.4175, -1.00), "2": (-0.4175, -0.50),
        "3": (-0.4175, 0.00), "4": (-0.4175, 0.50),
        "5": (-0.4175, 1.00), "6": (0.4175, 1.00),
        "7": (0.4175, 0.50), "8": (0.4175, 0.00),
        "9": (0.4175, -0.50), "10": (0.4175, -1.00),
    }
    for ref in ("U19", "U20", "U21", "U22", "U23", "U24", "U27"):
        pads = {pad.number: pad for pad in footprints[ref].pads if pad.number}
        require(set(pads) == set(expected_dqa), f"{ref}: TI DQA0010A pad set")
        for number, (x, y) in expected_dqa.items():
            pad = pads[number]
            ground = number in {"3", "8"}
            expected_width = 0.40 if ground else 0.20
            expected_layers = ["F.Cu", "F.Mask"] if ground else ["F.Cu", "F.Paste", "F.Mask"]
            expected_ratio = 0.25 if ground else 0.50
            require(abs(pad.position.X - x) < 0.002 and
                    abs(pad.position.Y - y) < 0.002 and
                    abs(pad.size.X - 0.565) < 0.002 and
                    abs(pad.size.Y - expected_width) < 0.002 and
                    pad.shape == "roundrect" and
                    abs(float(pad.roundrectRatio or 0.0) - expected_ratio) < 0.002 and
                    pad.layers == expected_layers and
                    abs(float(pad.solderMaskMargin or 0.0) - 0.07) < 0.002,
                    f"{ref}.{number}: land differs from TI DQA0010A 4220328/A")
        paste = [pad for pad in footprints[ref].pads if not pad.number]
        require(len(paste) == 2 and
                {(round(pad.position.X, 4), round(pad.position.Y, 4),
                  round(pad.size.X, 3), round(pad.size.Y, 3), tuple(pad.layers))
                 for pad in paste} ==
                {(-0.4175, 0.0, 0.565, 0.36, ("F.Paste",)),
                 (0.4175, 0.0, 0.565, 0.36, ("F.Paste",))},
                f"{ref}: GND stencil apertures differ from TI DQA0010A")

    # TI DYA0002A 4224978/B defines two 0.67 x 0.40 mm R0.05 lands,
    # 1.48 mm center spacing, equal-size stencil apertures and a preferred
    # +0.05 mm NSMD opening.
    for ref in ("D4", "D6", "D7", "D8", "D9", "D10", "D11"):
        pads = {pad.number: pad for pad in footprints[ref].pads if pad.number}
        require(set(pads) == {"1", "2"}, f"{ref}: TI DYA0002A pad set")
        for number, x in (("1", -0.74), ("2", 0.74)):
            pad = pads[number]
            require(abs(pad.position.X - x) < 0.002 and
                    abs(pad.position.Y) < 0.002 and
                    abs(pad.size.X - 0.67) < 0.002 and
                    abs(pad.size.Y - 0.40) < 0.002 and
                    pad.shape == "roundrect" and
                    abs(float(pad.roundrectRatio or 0.0) - 0.25) < 0.002 and
                    pad.layers == ["F.Cu", "F.Paste", "F.Mask"] and
                    abs(float(pad.solderMaskMargin or 0.0) - 0.05) < 0.002,
                    f"{ref}.{number}: land differs from TI DYA0002A 4224978/B")

    # Nexperia PESD5V0S1UL v5 Figure 11 defines 0.40 x 0.70 mm R0.05
    # copper, 0.50 x 0.80 mm solder-resist openings and separate
    # 0.30 x 0.60 mm R0.05 paste apertures at 0.70 mm center spacing.
    for ref in ("D1", "D2"):
        pads = {pad.number: pad for pad in footprints[ref].pads if pad.number}
        require(set(pads) == {"1", "2"}, f"{ref}: Nexperia SOD882 pad set")
        for number, x in (("1", -0.35), ("2", 0.35)):
            pad = pads[number]
            require(abs(pad.position.X - x) < 0.002 and
                    abs(pad.position.Y) < 0.002 and
                    abs(pad.size.X - 0.40) < 0.002 and
                    abs(pad.size.Y - 0.70) < 0.002 and
                    pad.shape == "roundrect" and
                    abs(float(pad.roundrectRatio or 0.0) - 0.25) < 0.002 and
                    pad.layers == ["F.Cu", "F.Mask"] and
                    abs(float(pad.solderMaskMargin or 0.0) - 0.05) < 0.002,
                    f"{ref}.{number}: copper/mask differs from PESD5V0S1UL Figure 11")
        paste = [pad for pad in footprints[ref].pads if not pad.number]
        require(len(paste) == 2 and
                {(round(pad.position.X, 3), round(pad.position.Y, 3),
                  round(pad.size.X, 3), round(pad.size.Y, 3),
                  round(float(pad.roundrectRatio or 0.0), 3), tuple(pad.layers))
                 for pad in paste} ==
                {(-0.35, 0.0, 0.3, 0.6, 0.333, ("F.Paste",)),
                 (0.35, 0.0, 0.3, 0.6, 0.333, ("F.Paste",))},
                f"{ref}: stencil apertures differ from PESD5V0S1UL Figure 11")

    # Nexperia MMBT3904 v5 Figure 8 defines rectangular 0.60 x 0.70 mm
    # copper lands, 0.50 x 0.60 mm stencil apertures, and 0.75 x 0.85 mm
    # solder-resist openings at 1.90 mm lead pitch and 2.00 mm row spacing.
    # The controlled footprint is rotated into the project's established
    # orientation without changing pin 1/2/3 electrical identity.
    expected_mmbt3904 = {
        "1": (-1.00, -0.95),
        "2": (-1.00, 0.95),
        "3": (1.00, 0.00),
    }
    for ref in ("Q1", "Q2", "Q3"):
        pads = {pad.number: pad for pad in footprints[ref].pads if pad.number}
        require(set(pads) == set(expected_mmbt3904),
                f"{ref}: Nexperia MMBT3904 SOT23 pad set")
        for number, (x, y) in expected_mmbt3904.items():
            pad = pads[number]
            require(abs(pad.position.X - x) < 0.002 and
                    abs(pad.position.Y - y) < 0.002 and
                    abs(pad.size.X - 0.70) < 0.002 and
                    abs(pad.size.Y - 0.60) < 0.002 and
                    pad.shape == "rect" and
                    pad.layers == ["F.Cu", "F.Mask"] and
                    abs(float(pad.solderMaskMargin or 0.0) - 0.075) < 0.002,
                    f"{ref}.{number}: copper/mask differs from MMBT3904 Figure 8")
        paste = [pad for pad in footprints[ref].pads if not pad.number]
        require(len(paste) == 3 and
                {(round(pad.position.X, 2), round(pad.position.Y, 2),
                  round(pad.size.X, 2), round(pad.size.Y, 2),
                  pad.shape, tuple(pad.layers)) for pad in paste} ==
                {(-1.0, -0.95, 0.6, 0.5, "rect", ("F.Paste",)),
                 (-1.0, 0.95, 0.6, 0.5, "rect", ("F.Paste",)),
                 (1.0, 0.0, 0.6, 0.5, "rect", ("F.Paste",))},
                f"{ref}: stencil apertures differ from MMBT3904 Figure 8")

    # TI DBV0005A drawing 4214839/K defines 1.10 x 0.60 mm R0.05 lands
    # and equal stencil apertures at 0.95 mm pitch and 2.60 mm row-center
    # separation.  The controlled footprint uses the preferred NSMD detail's
    # 0.07 mm maximum clearance around the exposed metal.
    expected_u6 = {
        "1": (-1.30, -0.95), "2": (-1.30, 0.00), "3": (-1.30, 0.95),
        "4": (1.30, 0.95), "5": (1.30, -0.95),
    }
    u6 = {pad.number: pad for pad in footprints["U6"].pads}
    require(set(u6) == set(expected_u6), "U6: TI DBV0005A pad set")
    for number, (x, y) in expected_u6.items():
        pad = u6[number]
        require(abs(pad.position.X - x) < 0.002 and
                abs(pad.position.Y - y) < 0.002 and
                abs(pad.size.X - 1.10) < 0.002 and
                abs(pad.size.Y - 0.60) < 0.002 and
                pad.shape == "roundrect" and
                abs(float(pad.roundrectRatio or 0.0) - 1 / 6) < 0.002 and
                pad.layers == ["F.Cu", "F.Paste", "F.Mask"] and
                abs(float(pad.solderMaskMargin or 0.0) - 0.07) < 0.002,
                f"U6.{number}: copper/mask/stencil differs from TI 4214839/K")

    # ST ESDALC6V1-5P6 Rev 3 Figure 14 defines six rectangular
    # 0.30 x 0.99 mm lands at 0.50 mm pitch, with a 0.62 mm inner gap
    # and 2.60 mm outer span.  The controlled pattern is rotated into the
    # board's established pin orientation, giving 1.61 mm row centers.
    expected_esdalc6v1 = {
        "1": (-0.805, -0.50), "2": (-0.805, 0.00),
        "3": (-0.805, 0.50), "4": (0.805, 0.50),
        "5": (0.805, 0.00), "6": (0.805, -0.50),
    }
    for ref in ("U14", "U15"):
        pads = {pad.number: pad for pad in footprints[ref].pads}
        require(set(pads) == set(expected_esdalc6v1),
                f"{ref}: ST ESDALC6V1-5P6 SOT666 pad set")
        for number, (x, y) in expected_esdalc6v1.items():
            pad = pads[number]
            require(abs(pad.position.X - x) < 0.002 and
                    abs(pad.position.Y - y) < 0.002 and
                    abs(pad.size.X - 0.99) < 0.002 and
                    abs(pad.size.Y - 0.30) < 0.002 and
                    pad.shape == "rect" and
                    pad.layers == ["F.Cu", "F.Paste", "F.Mask"],
                    f"{ref}.{number}: copper differs from ST Rev 3 Figure 14")

    # Vishay Application Note 826 defines the SC-89 six-lead minimum pads as
    # rectangular 0.300 x 0.478 mm lands at 0.500 mm lead pitch with a
    # 0.798 mm inner gap.  Rotating the pattern into the board's established
    # pin orientation gives 0.478 x 0.300 mm lands and 1.276 mm row centers.
    expected_si1016x = {
        "1": (-0.638, -0.50), "2": (-0.638, 0.00),
        "3": (-0.638, 0.50), "4": (0.638, 0.50),
        "5": (0.638, 0.00), "6": (0.638, -0.50),
    }
    q4 = {pad.number: pad for pad in footprints["Q4"].pads}
    require(set(q4) == set(expected_si1016x), "Q4: Vishay Si1016X SC-89 pad set")
    for number, (x, y) in expected_si1016x.items():
        pad = q4[number]
        require(abs(pad.position.X - x) < 0.002 and
                abs(pad.position.Y - y) < 0.002 and
                abs(pad.size.X - 0.478) < 0.002 and
                abs(pad.size.Y - 0.300) < 0.002 and
                pad.shape == "rect" and
                pad.layers == ["F.Cu", "F.Paste", "F.Mask"],
                f"Q4.{number}: copper differs from Vishay Application Note 826")

    # LIS2DW12 DS11811 Rev 9 defines 0.275 x 0.250 mm package pads on
    # 0.5 mm pitch.  TN0018 Rev 8 adds 0.1 mm to each PCB-land dimension,
    # 0.1 mm to each mask-opening dimension, and allows 70-90% paste area.
    expected_u3 = {
        "1": (-0.7625, -0.75, 0.375, 0.350),
        "2": (-0.7625, -0.25, 0.375, 0.350),
        "3": (-0.7625, 0.25, 0.375, 0.350),
        "4": (-0.7625, 0.75, 0.375, 0.350),
        "5": (-0.25, 0.7625, 0.350, 0.375),
        "6": (0.25, 0.7625, 0.350, 0.375),
        "7": (0.7625, 0.75, 0.375, 0.350),
        "8": (0.7625, 0.25, 0.375, 0.350),
        "9": (0.7625, -0.25, 0.375, 0.350),
        "10": (0.7625, -0.75, 0.375, 0.350),
        "11": (0.25, -0.7625, 0.350, 0.375),
        "12": (-0.25, -0.7625, 0.350, 0.375),
    }
    u3 = {pad.number: pad for pad in footprints["U3"].pads if pad.number}
    require(set(u3) == set(expected_u3), "U3: LIS2DW12 LGA-12L pad set")
    for number, (x, y, sx, sy) in expected_u3.items():
        pad = u3[number]
        require(abs(pad.position.X - x) < 0.002 and abs(pad.position.Y - y) < 0.002 and
                abs(pad.size.X - sx) < 0.002 and abs(pad.size.Y - sy) < 0.002,
                f"U3.{number}: copper differs from DS11811/TN0018 land rule")
        require(pad.layers == ["F.Cu", "F.Paste", "F.Mask"] and
                abs(float(pad.solderMaskMargin or 0.0) - 0.05) < 0.002 and
                abs(float(pad.solderPasteMarginRatio or 0.0) + 0.10) < 0.002,
                f"U3.{number}: mask/stencil differs from TN0018 Rev 8")

    # Raytac's 230606 Eagle library and solder-pad drawing define all 61
    # 0.6 x 0.4 mm lands.  Rotated lands are normalized by swapping stored
    # X/Y sizes; the independent coordinates below do not import the generator.
    expected_u11 = {
        1: (-4.65, -3.75, .6, .4), 2: (-4.65, -2.65, .6, .4),
        3: (-4.65, -1.85, .6, .4), 4: (-4.65, -.25, .6, .4),
        5: (-3.75, .15, .6, .4), 6: (-4.65, .55, .6, .4),
        7: (-3.75, .95, .6, .4), 8: (-4.65, 1.35, .6, .4),
        9: (-3.75, 1.75, .6, .4), 10: (-4.65, 2.15, .6, .4),
        11: (-3.75, 2.55, .6, .4), 12: (-4.65, 2.95, .6, .4),
        13: (-3.75, 3.35, .6, .4), 14: (-4.65, 3.75, .6, .4),
        34: (4.65, 6.15, .6, .4), 35: (4.65, 5.35, .6, .4),
        36: (3.75, 4.95, .6, .4), 37: (4.65, 4.55, .6, .4),
        38: (3.75, 4.15, .6, .4), 39: (4.65, 3.75, .6, .4),
        40: (3.75, 3.35, .6, .4), 41: (4.65, 2.95, .6, .4),
        42: (3.75, 2.55, .6, .4), 43: (3.75, 1.75, .6, .4),
        44: (4.65, 1.35, .6, .4), 45: (3.75, .95, .6, .4),
        46: (4.65, .55, .6, .4), 47: (3.75, .15, .6, .4),
        48: (4.65, -.25, .6, .4), 49: (3.75, -.65, .6, .4),
        50: (3.75, -1.45, .6, .4), 51: (4.65, -1.85, .6, .4),
        52: (3.75, -2.25, .6, .4), 53: (4.65, -2.65, .6, .4),
        54: (3.75, -3.05, .6, .4), 55: (4.65, -3.75, .6, .4),
    }
    for number, x in zip((15, 16, 17, 18, 20, 22, 24, 26, 28, 30, 31, 32, 33),
                         (-4.8, -4.0, -3.2, -2.4, -1.6, -.8, 0, .8, 1.6, 2.4, 3.2, 4.0, 4.8)):
        expected_u11[number] = (x, 7.15, .4, .6)
    for number, x in zip((19, 21, 23, 25, 27, 29), (-2.0, -1.2, -.4, .4, 1.2, 2.0)):
        expected_u11[number] = (x, 6.25, .4, .6)
    for number, x in zip(range(56, 62), (-2.0, -1.2, -.4, .4, 1.2, 2.0)):
        expected_u11[number] = (x, .55, .4, .6)
    u11 = {int(pad.number): pad for pad in footprints["U11"].pads if pad.number}
    require(set(u11) == set(range(1, 62)), "U11: MDBT50Q 61-pad set")
    for number, (x, y, sx, sy) in expected_u11.items():
        pad = u11[number]
        require(abs(pad.position.X - x) < 0.002 and abs(pad.position.Y - y) < 0.002 and
                abs(pad.size.X - sx) < 0.002 and abs(pad.size.Y - sy) < 0.002 and
                pad.layers == ["F.Cu", "F.Paste", "F.Mask"],
                f"U11.{number}: land differs from Raytac 230606 pattern")

    def zone_bounds(zone) -> tuple[float, float, float, float]:
        points = zone.polygons[0].coordinates
        return (round(min(point.X for point in points), 3),
                round(min(point.Y for point in points), 3),
                round(max(point.X for point in points), 3),
                round(max(point.Y for point in points), 3))

    u11_zones = footprints["U11"].zones
    require(len(u11_zones) == 2, "U11: expected feed and antenna keepouts")
    u11_by_layers = {tuple(zone.layers): zone for zone in u11_zones}
    require(set(u11_by_layers) == {("F.Cu",), ("*.Cu",)},
            "U11: keepout layer scopes differ from Raytac control")
    require(zone_bounds(u11_by_layers[("F.Cu",)]) == (105.0, 32.95, 106.2, 34.55),
            "U11: top-layer feed keepout differs from Raytac layout")
    require(zone_bounds(u11_by_layers[("*.Cu",)]) == (106.2, 30.0, 110.0, 40.5),
            "U11: all-layer 3.8 x 10.5 mm antenna keepout differs from Raytac layout")
    for zone in u11_zones:
        settings = zone.keepoutSettings
        require(settings is not None and
                {settings.tracks, settings.vias, settings.pads,
                 settings.copperpour, settings.footprints} == {"not_allowed"},
                "U11: antenna rule area permits copper or components")

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
