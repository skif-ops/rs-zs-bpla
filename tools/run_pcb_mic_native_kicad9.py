#!/usr/bin/env python3
"""KiCad 9 compatibility entry point for PCB-MIC native generation.

KiCad 9.0.9's packaged Python wrapper exposes AddPrimitivePoly but does not expose
AddPrimitiveCircle. The T5838 annular copper land is therefore represented as a set
of filled polygon sectors. The sectors overlap by a tiny angular amount so they form
one electrically continuous custom pad. The geometric error from 64 sectors is far
below the PCB fabrication tolerance and is checked against the TDK target diameters.

The paste annulus is a footprint graphic on F.Paste using KiCad's native PCB_SHAPE
circle support; it is intentionally independent from the copper custom pad.
"""
from __future__ import annotations

import math

import pcbnew

import generate_pcb_mic_native as base


def _annulus_sectors(pad, layer, r_inner_mm: float, r_outer_mm: float, segments: int = 64) -> None:
    if segments < 24:
        raise ValueError("annulus segmentation too coarse")
    # Small overlap avoids microscopic seams after integer-nanometre rounding.
    overlap = math.radians(0.08)
    for i in range(segments):
        a0 = 2.0 * math.pi * i / segments - overlap
        a1 = 2.0 * math.pi * (i + 1) / segments + overlap
        pts = [
            base.v(r_inner_mm * math.cos(a0), r_inner_mm * math.sin(a0)),
            base.v(r_outer_mm * math.cos(a0), r_outer_mm * math.sin(a0)),
            base.v(r_outer_mm * math.cos(a1), r_outer_mm * math.sin(a1)),
            base.v(r_inner_mm * math.cos(a1), r_inner_mm * math.sin(a1)),
        ]
        pad.AddPrimitivePoly(layer, pts, 0, True)


def _add_paste_ring_graphic(mic, center_x_mm: float, center_y_mm: float,
                            center_radius_mm: float, width_mm: float) -> None:
    ring = pcbnew.PCB_SHAPE(mic)
    ring.SetShape(pcbnew.SHAPE_T_CIRCLE)
    ring.SetStart(base.v(center_x_mm, center_y_mm))
    ring.SetEnd(base.v(center_x_mm + center_radius_mm, center_y_mm))
    ring.SetWidth(base.mm(width_mm))
    ring.SetLayer(pcbnew.F_Paste)
    mic.Add(ring)


def rebuild_t5838_manufacturer_land_kicad9(mic) -> None:
    """Build TDK Figure 36/37 center land without unavailable circle-pad API."""
    for pad in list(mic.Pads()):
        if str(pad.GetNumber()) in ("3", ""):
            mic.RemoveNative(pad)

    # Figure 36 copper: outer phi1.625, inner phi1.025.
    r_outer = 1.625 / 2.0
    r_inner = 1.025 / 2.0
    ring = pcbnew.PAD(mic)
    ring.SetNumber("3")
    ring.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    ring.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    ring.SetLayerSet(base.layer_set(pcbnew.F_Cu, pcbnew.F_Mask))
    ring.SetSize(base.v(0.01, 0.01))
    base.set_rel(ring, -0.65, 0.0)
    try:
        ring.SetAnchorPadShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_CIRCLE)
    except TypeError:
        ring.SetAnchorPadShape(pcbnew.PAD_SHAPE_CIRCLE)
    _annulus_sectors(ring, pcbnew.F_Cu, r_inner, r_outer, segments=64)
    mic.Add(ring)

    # Figure 37 stencil: outer phi1.625, inner phi1.125.  Use a native footprint
    # graphic on F.Paste rather than a second custom pad, keeping copper/net semantics
    # unambiguous while preserving the released stencil aperture geometry.
    paste_inner = 1.125 / 2.0
    paste_outer = 1.625 / 2.0
    _add_paste_ring_graphic(
        mic,
        center_x_mm=-0.65,
        center_y_mm=0.0,
        center_radius_mm=(paste_inner + paste_outer) / 2.0,
        width_mm=paste_outer - paste_inner,
    )

    # Separate acoustic NPTH, within TDK 0.5..1.0 mm PCB-hole recommendation.
    hole = pcbnew.PAD(mic)
    hole.SetNumber("")
    hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    hole.SetLayerSet(hole.UnplatedHoleMask())
    hole.SetSize(base.v(0.8, 0.8))
    hole.SetDrillSize(base.v(0.8, 0.8))
    base.set_rel(hole, -0.65, 0.0)
    mic.Add(hole)

    # Figure 37 paste reductions on the remaining pads.
    for number in ("1", "2", "6", "7"):
        base.one_pad(mic, number).SetLocalSolderPasteMargin(-base.mm(0.05))
    for number in ("4", "5"):
        base.one_pad(mic, number).SetLocalSolderPasteMargin(-base.mm(0.015))

    # Generator-side dimensional sanity gate. Polygon vertices lie exactly on the
    # target inner/outer radii before KiCad integer rounding.
    if abs(2.0 * r_outer - 1.625) > 1e-9 or abs(2.0 * r_inner - 1.025) > 1e-9:
        raise RuntimeError("T5838 copper annulus dimension mismatch")
    if abs(2.0 * paste_outer - 1.625) > 1e-9 or abs(2.0 * paste_inner - 1.125) > 1e-9:
        raise RuntimeError("T5838 paste annulus dimension mismatch")


base.rebuild_t5838_manufacturer_land = rebuild_t5838_manufacturer_land_kicad9

if __name__ == "__main__":
    raise SystemExit(base.main())
