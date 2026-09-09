#!/usr/bin/env python3
"""KiCad 9 compatibility entry point for PCB-MIC native generation.

The base generator remains the single source for placement/routing. This shim replaces
only the T5838 custom central land builder so KiCad 9 bypasses the legacy AddPrimitive
dispatch and calls AddPrimitiveCircle explicitly.

Remove this shim after the helper is folded back into generate_pcb_mic_native.py and the
same KiCad 9 DRC/Review evidence is retained.
"""
from __future__ import annotations

import pcbnew

import generate_pcb_mic_native as base


def _add_circle_primitive(pad, radius_mm: float, width_mm: float) -> None:
    # KiCad 9's Python compatibility wrapper for AddPrimitive(*args) incorrectly
    # routes three-argument calls to AddPrimitiveSegment. Call the explicit circle
    # primitive API so the TDK annulus is represented as an annulus, not a segment.
    pad.AddPrimitiveCircle(base.v(0.0, 0.0), base.mm(radius_mm), base.mm(width_mm))


def rebuild_t5838_manufacturer_land_kicad9(mic) -> None:
    """Build TDK Figure 36/37 center land using the explicit KiCad circle API."""
    for pad in list(mic.Pads()):
        if str(pad.GetNumber()) in ("3", ""):
            mic.RemoveNative(pad)

    # Copper: Figure 36, outer phi1.625 / inner phi1.025.
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
    _add_circle_primitive(ring, 0.6625, 0.300)
    mic.Add(ring)

    # Paste-only aperture: Figure 37, outer phi1.625 / inner phi1.125.
    # This pad intentionally has only F.Paste enabled. The custom primitive geometry
    # itself is layer-independent in the legacy SWIG API and is emitted on enabled
    # technical layers by the pad layer set.
    paste = pcbnew.PAD(mic)
    paste.SetNumber("")
    paste.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    paste.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    paste.SetLayerSet(base.layer_set(pcbnew.F_Paste))
    paste.SetSize(base.v(0.01, 0.01))
    base.set_rel(paste, -0.65, 0.0)
    try:
        paste.SetAnchorPadShape(pcbnew.PAD_SHAPE_CIRCLE)
    except TypeError:
        paste.SetAnchorPadShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_CIRCLE)
    _add_circle_primitive(paste, 0.6875, 0.250)
    mic.Add(paste)

    # Acoustic opening: unplated 0.8 mm, inside TDK 0.5..1.0 mm recommendation.
    hole = pcbnew.PAD(mic)
    hole.SetNumber("")
    hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    hole.SetLayerSet(hole.UnplatedHoleMask())
    hole.SetSize(base.v(0.8, 0.8))
    hole.SetDrillSize(base.v(0.8, 0.8))
    base.set_rel(hole, -0.65, 0.0)
    mic.Add(hole)

    for number in ("1", "2", "6", "7"):
        base.one_pad(mic, number).SetLocalSolderPasteMargin(-base.mm(0.05))
    for number in ("4", "5"):
        base.one_pad(mic, number).SetLocalSolderPasteMargin(-base.mm(0.015))


base.rebuild_t5838_manufacturer_land = rebuild_t5838_manufacturer_land_kicad9

if __name__ == "__main__":
    raise SystemExit(base.main())
