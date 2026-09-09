#!/usr/bin/env python3
"""KiCad 9 compatibility entry point for PCB-MIC native generation.

The Ubuntu KiCad 9.0.9 Python wrapper is unstable for custom PAD primitives: the
circle API is not exported and polygon primitives can segfault. Therefore the T5838
center annulus is represented exclusively with ordinary rectangular SMD pads, all
using pin number 3, arranged tangentially with deliberate overlap.

This is a normal KiCad construction for compound exposed/thermal pads: all segments
share the same pad number and net, form one continuous copper land, and do not depend
on custom primitive APIs. Radial thickness and center radius reproduce TDK Figure 36.
"""
from __future__ import annotations

import math

import pcbnew

import generate_pcb_mic_native as base


def _build_segmented_annulus(mic, pin_number: str, center_x_mm: float, center_y_mm: float,
                             r_inner_mm: float, r_outer_mm: float, segments: int = 32) -> None:
    if segments < 24:
        raise ValueError("annulus segmentation too coarse")
    radial = r_outer_mm - r_inner_mm
    r_mid = (r_outer_mm + r_inner_mm) / 2.0
    # 12% tangential overlap ensures a continuous ring after integer-nanometre rounding.
    tangential = 2.0 * math.pi * r_mid / segments * 1.12

    for i in range(segments):
        angle = 360.0 * i / segments
        a = math.radians(angle)
        p = pcbnew.PAD(mic)
        p.SetNumber(pin_number)
        p.SetShape(pcbnew.PAD_SHAPE_RECTANGLE)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(base.layer_set(pcbnew.F_Cu, pcbnew.F_Mask))
        # Local X tangential, local Y radial.
        p.SetSize(base.v(tangential, radial))
        base.set_rel(p, center_x_mm + r_mid * math.cos(a), center_y_mm + r_mid * math.sin(a))
        p.SetOrientationDegrees(angle + 90.0)
        mic.Add(p)


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
    """Build TDK Figure 36/37 center land using only stable KiCad primitives."""
    for pad in list(mic.Pads()):
        if str(pad.GetNumber()) in ("3", ""):
            mic.RemoveNative(pad)

    # Figure 36 copper: outer phi1.625, inner phi1.025.
    r_outer = 1.625 / 2.0
    r_inner = 1.025 / 2.0
    _build_segmented_annulus(
        mic,
        pin_number="3",
        center_x_mm=-0.65,
        center_y_mm=0.0,
        r_inner_mm=r_inner,
        r_outer_mm=r_outer,
        segments=32,
    )

    # Figure 37 stencil: outer phi1.625, inner phi1.125.
    paste_inner = 1.125 / 2.0
    paste_outer = 1.625 / 2.0
    _add_paste_ring_graphic(
        mic,
        center_x_mm=-0.65,
        center_y_mm=0.0,
        center_radius_mm=(paste_inner + paste_outer) / 2.0,
        width_mm=paste_outer - paste_inner,
    )

    # Acoustic opening: unplated 0.8 mm, within TDK 0.5..1.0 mm recommendation.
    hole = pcbnew.PAD(mic)
    hole.SetNumber("")
    hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    hole.SetLayerSet(hole.UnplatedHoleMask())
    hole.SetSize(base.v(0.8, 0.8))
    hole.SetDrillSize(base.v(0.8, 0.8))
    base.set_rel(hole, -0.65, 0.0)
    mic.Add(hole)

    # Figure 37 paste reductions on the signal/power pads.
    for number in ("1", "2", "6", "7"):
        base.one_pad(mic, number).SetLocalSolderPasteMargin(-base.mm(0.05))
    for number in ("4", "5"):
        base.one_pad(mic, number).SetLocalSolderPasteMargin(-base.mm(0.015))

    # Exact radial dimensions are construction inputs, not inferred after the fact.
    if abs(2.0 * r_outer - 1.625) > 1e-9 or abs(2.0 * r_inner - 1.025) > 1e-9:
        raise RuntimeError("T5838 copper annulus dimension mismatch")
    if abs(2.0 * paste_outer - 1.625) > 1e-9 or abs(2.0 * paste_inner - 1.125) > 1e-9:
        raise RuntimeError("T5838 paste annulus dimension mismatch")


base.rebuild_t5838_manufacturer_land = rebuild_t5838_manufacturer_land_kicad9

if __name__ == "__main__":
    raise SystemExit(base.main())
