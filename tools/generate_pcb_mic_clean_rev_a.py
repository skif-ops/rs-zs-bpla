#!/usr/bin/env python3
"""Generate PCB-MIC Rev.A using only board-owned KiCad objects.

Production T5838 footprint is created from scratch from TDK dimensions. Secondary
EasyEDA CAD is only an independent geometry check and is never mutated or copied into
MK1. Object ownership follows KiCad's own Python example exactly:
BOARD -> FOOTPRINT(board) -> BOARD.Add -> PAD(footprint) -> FOOTPRINT.Add.

The 24 x 22 mm electrical outline is still provisional (DIM-004 OPEN). Even a clean
ERC/DRC does not make this board FOR_MANUFACTURE until mechanical freeze, SI EVT and
Review A/B are complete.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pcbnew


def mm(x: float) -> int:
    return pcbnew.FromMM(x)


def v(x: float, y: float):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def layer_set(*layers):
    ls = pcbnew.LSET()
    for layer in layers:
        ls.AddLayer(layer)
    return ls


def add_net(board, name: str):
    net = pcbnew.NETINFO_ITEM(board, name)
    board.Add(net)
    return net


def load_one(root: Path):
    mods = sorted(root.rglob("*.kicad_mod"))
    if len(mods) != 1:
        raise RuntimeError(f"expected one footprint below {root}, found {mods}")
    fp = pcbnew.FootprintLoad(str(mods[0].parent), mods[0].stem)
    if fp is None:
        raise RuntimeError(f"could not load {mods[0]}")
    return fp


def hide_fields(fp) -> None:
    try:
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
    except Exception:
        pass


def pads_by_number(fp, number: str):
    return [p for p in fp.Pads() if str(p.GetNumber()) == str(number)]


def one_pad(fp, number: str):
    p = pads_by_number(fp, number)
    if len(p) != 1:
        raise RuntimeError(f"{fp.GetReference()} pad {number}: expected 1, got {len(p)}")
    return p[0]


def assign(fp, number: str, net) -> None:
    p = pads_by_number(fp, number)
    if not p:
        raise RuntimeError(f"{fp.GetReference()} missing pad {number}")
    for pad in p:
        pad.SetNet(net)


def pos(pad):
    p = pad.GetPosition()
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def add_smd_pad(fp, number: str, x: float, y: float, w: float, h: float,
                *, angle: float = 0.0, copper_paste: bool = True):
    p = pcbnew.PAD(fp)
    p.SetNumber(number)
    p.SetShape(pcbnew.PAD_SHAPE_RECTANGLE)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetLayerSet(p.SMDMask() if copper_paste else layer_set(pcbnew.F_Cu, pcbnew.F_Mask))
    p.SetSize(v(w, h))
    p.SetPosition(v(x, y))
    p.SetOrientationDegrees(angle)
    fp.Add(p)
    return p


def add_edge(board, a, b):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(v(*a))
    s.SetEnd(v(*b))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.15))
    board.Add(s)


def add_track(board, net, points, *, width=0.22, layer=pcbnew.F_Cu):
    for a, b in zip(points, points[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(v(*a)); t.SetEnd(v(*b)); t.SetWidth(mm(width))
        t.SetLayer(layer); t.SetNet(net); board.Add(t)


def add_via(board, net, xy, *, diameter=0.65, drill=0.30):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(v(*xy)); via.SetWidth(mm(diameter)); via.SetDrill(mm(drill))
    via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetNet(net); board.Add(via)
    return via


def add_ground_zone(board, gnd_net, width: float, height: float):
    z = pcbnew.ZONE(board)
    z.SetLayer(pcbnew.B_Cu); z.SetNetCode(gnd_net.GetNetCode())
    z.SetZoneName("PCB_MIC_BCU_GND_REFERENCE")
    poly = pcbnew.SHAPE_LINE_CHAIN()
    inset = 0.65
    for xy in ((inset,inset),(width-inset,inset),(width-inset,height-inset),(inset,height-inset)):
        poly.Append(v(*xy))
    poly.SetClosed(True); z.AddPolygon(poly); board.Add(z)
    return z


def build_t5838(board, center=(12.0, 16.0)):
    """Create T5838 footprint already rotated 270 degrees for Rev.A placement."""
    cx, cy = center
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("MK1")
    fp.SetValue("T5838")
    board.Add(fp)
    fp.SetPosition(v(cx, cy))
    hide_fields(fp)
    print("MK1 owner attached", flush=True)

    # TDK/reference relative pad coordinates before rotation are:
    # 1:+1.42,-0.63; 2:+0.60,-0.63; 4:-1.42,-1.07;
    # 5:-1.42,+1.07; 6:+0.60,+0.63; 7:+1.42,+0.63.
    # Rev.A uses 270 deg: (x,y)->(y,-x). Rectangular pads rotate 90 deg.
    source = {
        "1": ( 1.42,-0.63,0.522,0.725),
        "2": ( 0.60,-0.63,0.522,0.725),
        "4": (-1.42,-1.07,0.300,0.300),
        "5": (-1.42, 1.07,0.300,0.300),
        "6": ( 0.60, 0.63,0.522,0.725),
        "7": ( 1.42, 0.63,0.522,0.725),
    }
    for n, (x,y,w,h) in source.items():
        px, py = cx + y, cy - x
        p = add_smd_pad(fp, n, px, py, w, h, angle=90.0, copper_paste=True)
        if n in ("1","2","6","7"):
            p.SetLocalSolderPasteMargin(-mm(0.05))
        else:
            p.SetLocalSolderPasteMargin(-mm(0.015))
    print("MK1 six perimeter pads added", flush=True)

    # Figure 36 GND land: outer phi1.625 / inner phi1.025 => radial 0.300 mm.
    # Create 32 ordinary SMD pads, all pin 3, attached to an already board-owned fp.
    gx, gy = cx, cy + 0.65
    ro, ri = 1.625/2.0, 1.025/2.0
    rm, radial = (ro+ri)/2.0, ro-ri
    segments = 32
    tangent = 2*math.pi*rm/segments*1.12
    for i in range(segments):
        a = 2*math.pi*i/segments
        angle = math.degrees(a)+90.0
        add_smd_pad(fp, "3", gx+rm*math.cos(a), gy+rm*math.sin(a),
                    tangent, radial, angle=angle, copper_paste=False)
    print("MK1 segmented GND annulus added", flush=True)

    # Figure 37 paste ring represented as board graphic, not a pad/custom primitive.
    pi, po = 1.125/2.0, 1.625/2.0
    paste = pcbnew.PCB_SHAPE(board)
    paste.SetShape(pcbnew.SHAPE_T_CIRCLE)
    paste.SetStart(v(gx, gy))
    paste.SetEnd(v(gx+(pi+po)/2.0, gy))
    paste.SetWidth(mm(po-pi))
    paste.SetLayer(pcbnew.F_Paste)
    board.Add(paste)
    print("MK1 paste ring graphic added", flush=True)

    # TDK recommends PCB acoustic hole 0.5..1.0 mm; Rev.A candidate = 0.8 mm NPTH.
    hole = pcbnew.PAD(fp)
    hole.SetNumber("")
    hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    hole.SetLayerSet(hole.UnplatedHoleMask())
    hole.SetSize(v(0.8,0.8)); hole.SetDrillSize(v(0.8,0.8)); hole.SetPosition(v(gx,gy))
    fp.Add(hole)
    print("MK1 acoustic NPTH added", flush=True)

    # Simple manufacturer body reference on F.Fab. Body 3.50 x 2.65 mm.
    x0,x1 = cx-2.65/2, cx+2.65/2
    y0,y1 = cy-3.50/2, cy+3.50/2
    for a,b in (((x0,y0),(x1,y0)),((x1,y0),(x1,y1)),((x1,y1),(x0,y1)),((x0,y1),(x0,y0))):
        s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(v(*a)); s.SetEnd(v(*b)); s.SetWidth(mm(0.10)); s.SetLayer(pcbnew.F_Fab); board.Add(s)

    return fp


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--t5838-root",type=Path,required=True)
    ap.add_argument("--molex-root",type=Path,required=True)
    ap.add_argument("--reference-report",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    report=json.loads(args.reference_report.read_text(encoding="utf-8"))
    if not report["t5838"]["t5838_check"]["manufacturer_geometry_partial_pass"]:
        raise RuntimeError("T5838 secondary geometry check failed")
    if not report["molex_5040500691"]["molex_check"]["six_circuit_partial_pass"]:
        raise RuntimeError("Molex secondary geometry check failed")

    board=pcbnew.BOARD(); board.GetDesignSettings().SetCopperLayerCount(2)
    nets={n:add_net(board,n) for n in ("1V8_MIC","GND","PDM_CLK","PDM_DATA","MIC_WAKE","AAD_CFG","PDM_DATA_MIC")}
    bw,bh=24.0,22.0

    mic=build_t5838(board)
    assign(mic,"1",nets["PDM_DATA_MIC"]); assign(mic,"2",nets["GND"]); assign(mic,"3",nets["GND"])
    assign(mic,"4",nets["MIC_WAKE"]); assign(mic,"5",nets["AAD_CFG"]); assign(mic,"6",nets["PDM_CLK"]); assign(mic,"7",nets["1V8_MIC"])
    print("MK1 nets assigned", flush=True)

    j1=load_one(args.molex_root); j1.SetReference("J1"); j1.SetValue("5040500691")
    j1.SetOrientationDegrees(180.0); j1.SetPosition(v(12.0,5.0)); hide_fields(j1); board.Add(j1)
    for p in list(j1.Pads()):
        if str(p.GetNumber()) in ("7","8"):
            p.SetNumber("")
    for n,net in {"1":"1V8_MIC","2":"GND","3":"PDM_CLK","4":"PDM_DATA","5":"MIC_WAKE","6":"AAD_CFG"}.items(): assign(j1,n,nets[net])
    print("J1 attached and nets assigned", flush=True)

    c1=pcbnew.FootprintLoad("/usr/share/kicad/footprints/Capacitor_SMD.pretty","C_0402_1005Metric")
    c1.SetReference("C1"); c1.SetValue("100nF X7R"); c1.SetPosition(v(14.1,13.25)); hide_fields(c1); board.Add(c1)
    assign(c1,"1",nets["1V8_MIC"]); assign(c1,"2",nets["GND"])
    r1=pcbnew.FootprintLoad("/usr/share/kicad/footprints/Resistor_SMD.pretty","R_0402_1005Metric")
    r1.SetReference("R1"); r1.SetValue("0R EVT_SI_TUNE"); r1.SetOrientationDegrees(270.0); r1.SetPosition(v(11.25,10.55)); hide_fields(r1); board.Add(r1)
    assign(r1,"1",nets["PDM_DATA"]); assign(r1,"2",nets["PDM_DATA_MIC"])

    for a,b in (((0,0),(bw,0)),((bw,0),(bw,bh)),((bw,bh),(0,bh)),((0,bh),(0,0))): add_edge(board,a,b)

    jp={str(i):pos(one_pad(j1,str(i))) for i in range(1,7)}
    mp={str(i):pos(one_pad(mic,str(i))) for i in (1,2,4,5,6,7)}
    rp1,rp2=pos(one_pad(r1,"1")),pos(one_pad(r1,"2")); cp1,cp2=pos(one_pad(c1,"1")),pos(one_pad(c1,"2"))

    add_track(board,nets["PDM_DATA"],[jp["4"],rp1],width=0.22)
    add_track(board,nets["PDM_DATA_MIC"],[rp2,(rp2[0],13.45),mp["1"]],width=0.22)
    add_track(board,nets["PDM_CLK"],[jp["3"],(14.0,9.0),(17.2,9.0),(17.2,mp["6"][1]),mp["6"]],width=0.22)
    add_track(board,nets["MIC_WAKE"],[jp["5"],(jp["5"][0],mp["4"][1]),mp["4"]],width=0.20)
    add_track(board,nets["AAD_CFG"],[jp["6"],(jp["6"][0],20.25),(mp["5"][0],20.25),mp["5"]],width=0.20)

    vdd_in=(18.6,7.7); vdd_local=(13.35,12.15)
    add_via(board,nets["1V8_MIC"],vdd_in); add_via(board,nets["1V8_MIC"],vdd_local)
    add_track(board,nets["1V8_MIC"],[jp["1"],vdd_in],width=0.35)
    add_track(board,nets["1V8_MIC"],[vdd_in,(20.0,8.5),(20.0,11.6),vdd_local],width=0.40,layer=pcbnew.B_Cu)
    add_track(board,nets["1V8_MIC"],[vdd_local,cp1,mp["7"]],width=0.30)

    # GND fanout is deliberately kept clear of the J1 PDM_CLK escape. The previous
    # via at (14.25, 8.65) physically intersected the clock route and was caught by
    # independent KiCad DRC. Rev.A moves the via above the connector and provides an
    # explicit B.Cu return backbone so connectivity does not depend on an unfilled zone.
    gx,gy=12.0,16.65
    gnd_j=(14.50,6.70); gnd_c=(15.25,cp2[1]); gnd_m=(15.0,gy)
    add_via(board,nets["GND"],gnd_j); add_via(board,nets["GND"],gnd_c); add_via(board,nets["GND"],gnd_m)
    add_track(board,nets["GND"],[jp["2"],gnd_j],width=0.35)
    add_track(board,nets["GND"],[cp2,gnd_c],width=0.30)
    add_track(board,nets["GND"],[(12.70,gy),gnd_m],width=0.30)
    add_track(board,nets["GND"],[mp["2"],(11.70,16.05)],width=0.16)

    # Explicit B.Cu star/backbone is the first-control connectivity path. The B.Cu
    # zone remains present for the final low-impedance reference plane and is checked
    # separately by KiCad. This prevents a false PASS caused by assuming an unfilled
    # zone electrically connects the three GND vias.
    gnd_spine_x=9.0
    add_track(board,nets["GND"],[gnd_j,(gnd_spine_x,6.70),(gnd_spine_x,16.65),gnd_m],width=0.50,layer=pcbnew.B_Cu)
    add_track(board,nets["GND"],[(gnd_spine_x,cp2[1]),gnd_c],width=0.50,layer=pcbnew.B_Cu)
    print("explicit B.Cu GND backbone added", flush=True)

    add_ground_zone(board,nets["GND"],bw,bh)
    print("before zone fill", flush=True)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    print("zone fill complete", flush=True)

    txt=pcbnew.PCB_TEXT(board); txt.SetText("PCB-MIC Rev.A ELECTRICAL CANDIDATE - DIM-004 OPEN")
    txt.SetPosition(v(12.0,21.2)); txt.SetLayer(pcbnew.F_Fab); txt.SetTextHeight(mm(0.7)); txt.SetTextWidth(mm(0.7)); txt.SetTextThickness(mm(0.11)); board.Add(txt)

    args.output.parent.mkdir(parents=True,exist_ok=True)
    print("before SaveBoard", flush=True)
    pcbnew.SaveBoard(str(args.output),board)
    print(f"saved {args.output}", flush=True)
    print("tracks/vias",len(board.GetTracks()),"footprints",len(list(board.GetFootprints())),"zones",len(list(board.Zones())),flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
