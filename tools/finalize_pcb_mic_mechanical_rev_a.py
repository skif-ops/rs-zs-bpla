#!/usr/bin/env python3
"""Apply the frozen EVT-PRE-20 Rev.A mechanical metadata to PCB-MIC.

Electrical routing and component placement remain owned by the electrical generator.
This stage owns the frozen leaf outline/thickness, mounting holes and board title block.
Surface-finish metadata is intentionally NOT written through KiCad 9's deprecated SWIG
stackup API: GetStackupDescriptor() is opaque on supported Linux builds. ENIG is carried
by the versioned fabrication_metadata.json and independently asserted in the generated
Gerber job by kicad_native_gate.py.

This stage does not release the board for manufacture; Review A/B, DFM and acoustic
validation remain mandatory.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pcbnew

BOARD_W_MM = 24.0
BOARD_H_MM = 22.0
BOARD_THICKNESS_MM = 1.0
MOUNT_HOLE_MM = 2.2
MOUNTS = (
    ("H1", 4.0, 16.65),
    ("H2", 20.0, 16.65),
)


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def v(x: float, y: float):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def hide_fields(fp) -> None:
    try:
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
    except Exception:
        pass


def add_mount_hole(board, reference: str, x: float, y: float) -> None:
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(reference)
    fp.SetValue("M2_CLEARANCE_NPTH_2.2")
    fp.SetPosition(v(x, y))
    fp.SetBoardOnly(True)
    fp.SetExcludedFromBOM(True)
    fp.SetExcludedFromPosFiles(True)
    fp.SetAllowMissingCourtyard(True)
    board.Add(fp)
    hide_fields(fp)

    pad = pcbnew.PAD(fp)
    pad.SetNumber("")
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    pad.SetLayerSet(pad.UnplatedHoleMask())
    pad.SetSize(v(MOUNT_HOLE_MM, MOUNT_HOLE_MM))
    pad.SetDrillSize(v(MOUNT_HOLE_MM, MOUNT_HOLE_MM))
    pad.SetPosition(v(x, y))
    fp.Add(pad)


def set_mechanical_metadata(board) -> None:
    settings = board.GetDesignSettings()
    settings.SetBoardThickness(mm(BOARD_THICKNESS_MM))

    title = board.GetTitleBlock()
    title.SetTitle("Dioneya EVT-PRE-20 PCB-MIC")
    title.SetRevision("A")
    title.SetCompany("Dioneya / ZS-BPLA")
    title.SetDate("2026-09-09")
    title.SetComment(0, "NOT FOR MANUFACTURE until Review A/B and DFM close")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    args = ap.parse_args()

    board = pcbnew.LoadBoard(str(args.board))
    if board is None:
        raise RuntimeError(f"cannot load board {args.board}")

    existing = {fp.GetReference() for fp in board.GetFootprints()}
    for ref, _, _ in MOUNTS:
        if ref in existing:
            raise RuntimeError(f"mounting reference {ref} already exists; refusing duplicate mechanical finalization")

    set_mechanical_metadata(board)
    for ref, x, y in MOUNTS:
        add_mount_hole(board, ref, x, y)

    updated_note = False
    for drawing in board.GetDrawings():
        if not hasattr(drawing, "GetText") or not hasattr(drawing, "SetText"):
            continue
        text = drawing.GetText()
        if "DIM-004 OPEN" in text:
            drawing.SetText("PCB-MIC Rev.A MECHANICAL FREEZE - NOT FOR MANUFACTURE")
            updated_note = True

    if not updated_note:
        note = pcbnew.PCB_TEXT(board)
        note.SetText("PCB-MIC Rev.A MECHANICAL FREEZE - NOT FOR MANUFACTURE")
        note.SetPosition(v(12.0, 21.2))
        note.SetLayer(pcbnew.F_Fab)
        note.SetTextHeight(mm(0.7))
        note.SetTextWidth(mm(0.7))
        note.SetTextThickness(mm(0.11))
        board.Add(note)

    pcbnew.SaveBoard(str(args.board), board)
    print(
        f"PCB-MIC finalization applied: {BOARD_W_MM:.1f}x{BOARD_H_MM:.1f}x{BOARD_THICKNESS_MM:.1f} mm; "
        f"H1/H2 NPTH {MOUNT_HOLE_MM:.1f} mm; mounting refs excluded from BOM/PnP; "
        "surface finish controlled by fabrication_metadata.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
