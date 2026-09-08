#!/usr/bin/env python3
"""Generate EVT-PRE-20 PCB-MIC Rev.A native KiCad board candidate.

The board is created by KiCad's pcbnew API, not by hand-writing a .kicad_pcb file.
T5838 and connector footprints are loaded from secondary reference CAD only after the
reference geometry inspector passes. The T5838 acoustic hole is corrected to 0.8 mm
NPTH per TDK's 0.5..1.0 mm PCB-hole recommendation.

This is an ELECTRICAL LAYOUT CANDIDATE. The 24 x 18 mm outline is provisional until
microphone mount/enclosure CAD freezes the leaf-board envelope and fastening scheme.
It must never be marked FOR_MANUFACTURE solely because DRC passes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pcbnew


def v(x: float, y: float):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def load_one(root: Path):
    mods = sorted(root.rglob("*.kicad_mod"))
    if len(mods) != 1:
        raise RuntimeError(f"expected one footprint below {root}, found {mods}")
    fp = pcbnew.FootprintLoad(str(mods[0].parent), mods[0].stem)
    if fp is None:
        raise RuntimeError(f"could not load {mods[0]}")
    return fp


def add_net(board, name: str):
    net = pcbnew.NETINFO_ITEM(board, name)
    board.Add(net)
    return net


def pads_by_number(fp, number: str):
    return [p for p in fp.Pads() if str(p.GetNumber()) == str(number)]


def one_pad(fp, number: str):
    pads = pads_by_number(fp, number)
    if len(pads) != 1:
        raise RuntimeError(f"{fp.GetReference()} pad {number}: expected one, got {len(pads)}")
    return pads[0]


def assign(fp, number: str, net) -> None:
    pads = pads_by_number(fp, number)
    if not pads:
        raise RuntimeError(f"{fp.GetReference()} missing pad {number}")
    for p in pads:
        p.SetNet(net)


def pos(pad):
    p = pad.GetPosition()
    return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))


def add_track(board, net, points: list[tuple[float, float]], width: float = 0.25, layer=pcbnew.F_Cu):
    for a, b in zip(points, points[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(v(*a))
        t.SetEnd(v(*b))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(layer)
        t.SetNet(net)
        board.Add(t)


def add_edge(board, a, b):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(v(*a))
    s.SetEnd(v(*b))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(pcbnew.FromMM(0.15))
    board.Add(s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t5838-root", type=Path, required=True)
    ap.add_argument("--molex-root", type=Path, required=True)
    ap.add_argument("--reference-report", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    report = json.loads(args.reference_report.read_text(encoding="utf-8"))
    if not report["t5838"]["t5838_check"]["manufacturer_geometry_partial_pass"]:
        raise RuntimeError("T5838 secondary footprint failed manufacturer geometry check")
    if not report["molex_5040500691"]["molex_check"]["six_circuit_partial_pass"]:
        raise RuntimeError("Molex secondary footprint failed six-circuit check")

    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)

    nets = {n: add_net(board, n) for n in (
        "1V8_MIC", "GND", "PDM_CLK", "PDM_DATA", "MIC_WAKE", "AAD_CFG", "PDM_DATA_MIC"
    )}

    mic = load_one(args.t5838_root)
    mic.SetReference("MK1")
    mic.SetValue("T5838")
    mic.SetPosition(v(12.0, 13.0))
    board.Add(mic)

    # Correct the imported acoustic through-hole to an unplated 0.8 mm opening.
    acoustic = [p for p in mic.Pads() if str(p.GetNumber()) == ""]
    if len(acoustic) != 1:
        raise RuntimeError(f"expected one unnumbered acoustic hole, got {len(acoustic)}")
    hole = acoustic[0]
    hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    hole.SetSize(v(0.8, 0.8))
    hole.SetDrillSize(v(0.8, 0.8))

    # Datasheet pin mapping: 1 DATA, 2 SELECT, 3 GND, 4 WAKE, 5 THSEL, 6 CLK, 7 VDD.
    assign(mic, "1", nets["PDM_DATA_MIC"])
    assign(mic, "2", nets["GND"])  # SELECT fixed low: same PDM edge for all four independent channels.
    assign(mic, "3", nets["GND"])
    assign(mic, "4", nets["MIC_WAKE"])
    assign(mic, "5", nets["AAD_CFG"])
    assign(mic, "6", nets["PDM_CLK"])
    assign(mic, "7", nets["1V8_MIC"])

    j1 = load_one(args.molex_root)
    j1.SetReference("J1")
    j1.SetValue("5040500691")
    j1.SetOrientationDegrees(180.0)
    j1.SetPosition(v(12.0, 3.0))
    board.Add(j1)
    for number, netname in {
        "1": "1V8_MIC", "2": "GND", "3": "PDM_CLK", "4": "PDM_DATA", "5": "MIC_WAKE", "6": "AAD_CFG"
    }.items():
        assign(j1, number, nets[netname])
    # Pads 7/8 are mechanical hold-down pads and intentionally have no electrical net.

    caplib = Path("/usr/share/kicad/footprints/Capacitor_SMD.pretty")
    c1 = pcbnew.FootprintLoad(str(caplib), "C_0402_1005Metric")
    if c1 is None:
        raise RuntimeError("KiCad C_0402_1005Metric footprint unavailable")
    c1.SetReference("C1")
    c1.SetValue("100nF X7R")
    c1.SetPosition(v(15.0, 12.9))
    board.Add(c1)
    assign(c1, "1", nets["1V8_MIC"])
    assign(c1, "2", nets["GND"])

    rlib = Path("/usr/share/kicad/footprints/Resistor_SMD.pretty")
    r1 = pcbnew.FootprintLoad(str(rlib), "R_0402_1005Metric")
    if r1 is None:
        raise RuntimeError("KiCad R_0402_1005Metric footprint unavailable")
    r1.SetReference("R1")
    r1.SetValue("50R")
    r1.SetOrientationDegrees(90.0)
    r1.SetPosition(v(12.0, 9.1))
    board.Add(r1)
    assign(r1, "1", nets["PDM_DATA"])
    assign(r1, "2", nets["PDM_DATA_MIC"])

    # Provisional 24 x 18 mm electrical outline. Mechanics remains a release blocker.
    for a, b in [((0, 0), (24, 0)), ((24, 0), (24, 18)), ((24, 18), (0, 18)), ((0, 18), (0, 0))]:
        add_edge(board, a, b)

    # Route from connector. Connector is rotated 180° to minimize crossover.
    jp = {str(i): pos(one_pad(j1, str(i))) for i in range(1, 7)}
    mp = {str(i): pos(one_pad(mic, str(i))) for i in (1, 2, 4, 5, 6, 7)}
    rp1, rp2 = pos(one_pad(r1, "1")), pos(one_pad(r1, "2"))
    cp1, cp2 = pos(one_pad(c1, "1")), pos(one_pad(c1, "2"))
    gnd_anchor = pos(pads_by_number(mic, "3")[0])

    add_track(board, nets["1V8_MIC"], [jp["1"], (15.75, 10.8), cp1])
    add_track(board, nets["1V8_MIC"], [cp1, (14.0, 13.6), mp["7"]])
    add_track(board, nets["GND"], [jp["2"], (14.25, 10.2), cp2])
    add_track(board, nets["GND"], [cp2, (12.0, 11.3), gnd_anchor], width=0.35)
    add_track(board, nets["GND"], [mp["2"], gnd_anchor], width=0.25)
    add_track(board, nets["PDM_CLK"], [jp["3"], (12.75, 10.5), mp["6"]])
    add_track(board, nets["PDM_DATA"], [jp["4"], (11.25, 8.2), rp1])
    add_track(board, nets["PDM_DATA_MIC"], [rp2, (13.8, 10.1), mp["1"]])
    add_track(board, nets["MIC_WAKE"], [jp["5"], (9.75, 10.5), mp["4"]])
    add_track(board, nets["AAD_CFG"], [jp["6"], (8.25, 14.8), (10.0, 14.8), mp["5"]])

    # Add explicit board note on fabrication layer so provisional outline cannot be mistaken for frozen mechanics.
    txt = pcbnew.PCB_TEXT(board)
    txt.SetText("PCB-MIC Rev.A ELECTRICAL CANDIDATE - OUTLINE/FASTENING PROVISIONAL")
    txt.SetPosition(v(12.0, 17.2))
    txt.SetLayer(pcbnew.F_Fab)
    txt.SetTextHeight(pcbnew.FromMM(0.8))
    txt.SetTextWidth(pcbnew.FromMM(0.8))
    txt.SetThickness(pcbnew.FromMM(0.12))
    board.Add(txt)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(args.output), board)
    print(f"saved {args.output}")
    print("ratsnest", len(board.GetTracks()), "tracks; footprints", len(list(board.GetFootprints())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
